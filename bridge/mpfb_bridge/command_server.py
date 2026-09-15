"""
The bridge's command server: a local socket that dispatches *names*, never code.

This is the part of the pivot that had to be proved rather than assumed, and it
is deliberately the smallest thing that can be: a non-blocking listening socket
drained from a ``bpy.app.timers`` callback, so every command runs on Blender's
main thread and ``bpy`` is never touched from anywhere else.

**The vocabulary is closed.** A request names a command from a fixed table and
carries parameters; there is no request shape that causes caller-supplied source
to be executed, and there is no ``exec()`` in this file. That is the whole
argument for the bridge over the two general-purpose MCP add-ons it replaces, and
it is one a sceptical user can check by reading :mod:`commands` - which is why the
table is a plain dict in a module of its own rather than a registry assembled at
import time.

**Framing is NUL-delimited JSON, and nothing is decoded before the frame
boundary.** The buffer is a ``bytearray`` and the delimiter search is a byte
search, so a multi-byte UTF-8 sequence split across two ``recv()`` calls is a
non-issue rather than a bug waiting for a non-ASCII asset name: NUL cannot occur
inside a UTF-8 multi-byte sequence, whose continuation bytes are all 0x80-0xBF.
This is the single most important thing copied from
``blender_mcp/addon/blender_mcp_addon/mcp_to_blender_server.py``, which is this
module's model throughout.

**One thing is deliberately not copied from it.** That server does exactly one
``recv(4096)`` per timer tick and then returns, which is why a request costs
roughly 250 ms per 4 KB against a busy Blender and 1 s per 4 KB against an idle
one - the tax the whole pivot exists to remove. It also never resets its client
deadline when data arrives, so the two limits together cap a request far below
the maximum the code advertises. Here the socket is drained until it would block,
and the deadline is reset whenever a chunk arrives. At parameter sizes neither
would matter much, which is precisely the point: the bridge should not inherit
the defect it was built to avoid.

``bpy`` is not imported here, and must not be. Keeping the protocol free of it is
what lets this module be read, reasoned about and exercised without a running
Blender.
"""

__all__ = (
    "PROTOCOL_VERSION",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "TIMER_INTERVAL_ACTIVE",
    "is_running",
    "start",
    "stop",
    "poll",
    "timer_idle_reset",
    "timer_idle_interval",
    "timer_internal_vars_calc",
)

import json
import math
import socket
import traceback

from .log import get_logger

_LOG = get_logger("commandserver")

# Bumped when the request or response shape changes in a way a client must know
# about. Every answer carries it, and a client is expected to check it: this
# add-on, MPFB and the MCP server are three separately released pieces, and a
# handshake that exists from the first command is the cheap defence against that
# matrix. Nothing else in the MakeHuman MCP stack carries a version today.
PROTOCOL_VERSION = 1

# Not 9876. Both blender lab's MCP add-on and the community "blender-mcp" default
# to that port, and a user may well have one of them running.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9877

# Seconds between main-thread timer ticks while requests are arriving.
TIMER_INTERVAL_ACTIVE = 0.05
# Seconds between ticks once nothing has happened for a while.
_TIMER_INTERVAL_IDLE = 1.0
# Seconds of quiet before dropping to the idle interval.
_TIMER_INTERVAL_IDLE_DELAY = 5.0

# Requests carry parameters, not programs, so this is generous rather than
# load-bearing. It exists so that a confused or hostile local client cannot make
# Blender allocate without bound.
_MAX_REQUEST_BYTES = 4 * 1024 * 1024
_LISTEN_BACKLOG = 5
_RECV_BUFFER_SIZE = 65536
# Seconds a client gets to finish sending one request before it is dropped. The
# countdown is reset by every chunk that arrives, so this bounds silence rather
# than the size of a request.
_CLIENT_TIMEOUT = 10.0

# Error slugs. A caller branches on these; the human sentence beside one may be
# reworded without notice, the slug may not.
ERROR_MALFORMED_REQUEST = "malformed_request"
ERROR_UNKNOWN_COMMAND = "unknown_command"
ERROR_INVALID_PARAMS = "invalid_params"
ERROR_COMMAND_FAILED = "command_failed"
ERROR_RESULT_NOT_SERIALIZABLE = "result_not_serializable"
ERROR_REQUEST_TOO_LARGE = "request_too_large"
ERROR_TIMEOUT = "timeout"


class _TimerState:
    """Tick intervals and the derived countdowns, updated from the preferences."""

    __slots__ = (
        "interval_active",
        "interval_idle",
        "interval_idle_delay",
        "idle_countdown_reset",
        "idle_countdown",
        "client_timeout_countdown",
    )

    def __init__(self):
        self.interval_active = TIMER_INTERVAL_ACTIVE
        self.interval_idle = _TIMER_INTERVAL_IDLE
        self.interval_idle_delay = _TIMER_INTERVAL_IDLE_DELAY
        self.idle_countdown_reset = 0
        self.idle_countdown = 0
        self.client_timeout_countdown = 2


_timer = _TimerState()


def timer_internal_vars_calc(active=None, idle=None, idle_delay=None):
    """Update the intervals and recompute the tick counts derived from them.

    Called from the preferences' update callbacks. The values are cached on this
    module rather than read per tick, because the timer fires many times a second
    and a preferences lookup is not free.
    """
    if active is not None:
        _timer.interval_active = active
    if idle is not None:
        _timer.interval_idle = idle
    if idle_delay is not None:
        _timer.interval_idle_delay = idle_delay
    # Round up, so a delay is never shorter than the one that was asked for.
    _timer.idle_countdown_reset = math.ceil(_timer.interval_idle_delay / _timer.interval_active)
    _timer.idle_countdown = _timer.idle_countdown_reset
    _timer.client_timeout_countdown = max(2, math.ceil(_CLIENT_TIMEOUT / _timer.interval_active))


def timer_idle_reset():
    """Note that something happened, so the next ticks stay at the active rate."""
    _timer.idle_countdown = _timer.idle_countdown_reset


def timer_idle_interval():
    """The interval for the next tick, decrementing the idle countdown."""
    if _timer.idle_countdown > 0:
        _timer.idle_countdown -= 1
        return _timer.interval_active
    return _timer.interval_idle


timer_internal_vars_calc()


class _Client:
    """One accepted connection, and the partial request read from it so far."""

    __slots__ = ("conn", "buffer", "ticks_remaining")

    def __init__(self, conn):
        self.conn = conn
        self.buffer = bytearray()
        self.ticks_remaining = _timer.client_timeout_countdown


class _ServerState:
    """The listening socket and its accepted clients, or nothing at all."""

    __slots__ = ("sock", "clients", "commands")

    def __init__(self):
        self.sock = None
        self.clients = []
        self.commands = {}


_state = _ServerState()


def is_running():
    """Whether the listening socket is open."""
    return _state.sock is not None


def start(host, port, commands):
    """Open the listening socket and remember the command table.

    Raises ``RuntimeError`` if already running and ``OSError`` if the address
    cannot be bound - a caller driving this from an operator should catch both
    and report, since "port already in use" is the common and unalarming case.

    Registering the timer that drives :func:`poll` is deliberately *not* done
    here: this module knows nothing about ``bpy``, and the add-on's own
    ``__init__`` owns the timer.
    """
    if is_running():
        raise RuntimeError("The MPFB Bridge command server is already running")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        sock.bind((host, port))
        sock.listen(_LISTEN_BACKLOG)
    except OSError:
        sock.close()
        raise

    _state.sock = sock
    _state.clients = []
    _state.commands = dict(commands)
    _LOG.info("Command server listening on %s:%d with %d commands", host, port, len(_state.commands))


def stop():
    """Close the listening socket and every client attached to it."""
    sock = _state.sock
    # Cleared first, so anything asking `is_running()` while this runs is told the
    # truth rather than being handed a socket that is about to close.
    _state.sock = None

    if sock is not None:
        try:
            sock.close()
        except OSError:
            pass

    for client in _state.clients:
        _close_client(client)
    _state.clients = []
    _state.commands = {}
    _LOG.info("Command server stopped")


def _close_client(client):
    try:
        client.conn.close()
    except OSError:
        pass


def _encode_response(response):
    """One response as NUL-delimited JSON bytes."""
    return (json.dumps(response) + "\0").encode("utf-8")


def _error(slug, message, **extra):
    """The uniform error envelope. Every failure in this module goes through it."""
    response = {
        "status": "error",
        "protocol_version": PROTOCOL_VERSION,
        "error": slug,
        "message": message,
    }
    response.update(extra)
    return response


def _send_and_close(client, response):
    """Answer one request and hang up. One request per connection, always."""
    try:
        client.conn.sendall(_encode_response(response))
    except OSError:
        # The client went away before it read the answer. Nothing to be done and
        # nothing worth failing over.
        _LOG.debug("Client disconnected before the response could be sent")
    _close_client(client)


def dispatch(request):
    """Turn one decoded request into one response dict.

    Split out from the socket handling because this is the half worth reading:
    it is the whole of what a caller can make this add-on do. Note what is
    missing - there is no branch here that executes anything the caller sent.
    """
    if not isinstance(request, dict):
        return _error(
            ERROR_MALFORMED_REQUEST,
            "A request must be a JSON object, got {:s}.".format(type(request).__name__))

    name = request.get("command")
    if not isinstance(name, str) or not name.strip():
        return _error(
            ERROR_MALFORMED_REQUEST,
            "A request must carry a non-empty 'command' string naming one of the supported "
            "commands.",
            known_commands=sorted(_state.commands))

    handler = _state.commands.get(name)
    if handler is None:
        # Naming the alternatives matters more here than anywhere else: this is
        # the message a caller sees when it guessed, and the vocabulary being
        # closed is only useful if it is also discoverable.
        return _error(
            ERROR_UNKNOWN_COMMAND,
            "There is no command named {!r}. This add-on dispatches a fixed set of commands and "
            "executes nothing else.".format(name),
            command=name,
            known_commands=sorted(_state.commands))

    params = request.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _error(
            ERROR_INVALID_PARAMS,
            "'params' must be a JSON object or omitted, got {:s}.".format(type(params).__name__),
            command=name)

    try:
        result = handler(params)
    except Exception:  # pylint: disable=broad-except
        # A handler raising is a bug in this add-on, not in the caller, so the
        # traceback goes back over the wire rather than only to Blender's console:
        # the caller is on the other side of a socket and cannot see that console.
        _LOG.error("Command %r raised", name, exc_info=True)
        return _error(
            ERROR_COMMAND_FAILED,
            "The command {!r} raised while running inside Blender.".format(name),
            command=name,
            traceback=traceback.format_exc())

    response = {
        "status": "ok",
        "protocol_version": PROTOCOL_VERSION,
        "command": name,
        "result": result,
    }

    try:
        # Serialize before committing to an answer. A result that cannot be
        # encoded must fail as a clear error envelope rather than as an exception
        # halfway through writing a response the caller has already started reading.
        _encode_response(response)
    except (TypeError, ValueError) as error:
        _LOG.error("Command %r returned a result that is not JSON-serializable: %s", name, error)
        return _error(
            ERROR_RESULT_NOT_SERIALIZABLE,
            "The command {!r} produced a result that cannot be encoded as JSON: {:s}".format(
                name, str(error)),
            command=name)

    return response


def _accept_clients():
    """Accept every pending connection, not merely the first."""
    if _state.sock is None:
        return
    while True:
        try:
            conn, _address = _state.sock.accept()
        except BlockingIOError:
            return
        except OSError:
            return
        conn.setblocking(False)
        _state.clients.append(_Client(conn))


def _read_available(client):
    """Drain this client's socket until it would block.

    The loop is the point. Reading one fixed-size chunk per tick is what makes a
    request's cost a function of its length rather than of its content, and it is
    the single defect this transport exists to not have.

    Returns ``(received_anything, still_open)``.
    """
    received = False
    while True:
        try:
            chunk = client.conn.recv(_RECV_BUFFER_SIZE)
        except BlockingIOError:
            return (received, True)
        except OSError:
            return (received, False)

        if not chunk:
            # An orderly shutdown from the other end.
            return (received, False)

        client.buffer.extend(chunk)
        received = True

        if len(client.buffer) > _MAX_REQUEST_BYTES:
            return (received, True)

        if b"\0" in client.buffer:
            # The frame is complete. Anything after the delimiter is ignored: this
            # protocol is one request per connection and the connection is about
            # to be closed.
            return (received, True)


def _service_clients():
    """Advance every client by one tick. Returns whether any work was done."""
    did_work = False

    for client in list(_state.clients):
        received, still_open = _read_available(client)

        if received:
            # Reset the deadline on progress, so a large or slow request is not
            # killed for taking several ticks to arrive. It bounds silence.
            client.ticks_remaining = _timer.client_timeout_countdown
            did_work = True

        if not still_open:
            _state.clients.remove(client)
            _close_client(client)
            continue

        if len(client.buffer) > _MAX_REQUEST_BYTES:
            _state.clients.remove(client)
            _send_and_close(client, _error(
                ERROR_REQUEST_TOO_LARGE,
                "A request may be at most {:d} bytes. Commands take parameters, not "
                "programs.".format(_MAX_REQUEST_BYTES)))
            did_work = True
            continue

        delimiter = client.buffer.find(b"\0")
        if delimiter < 0:
            client.ticks_remaining -= 1
            if client.ticks_remaining <= 0:
                _state.clients.remove(client)
                _send_and_close(client, _error(
                    ERROR_TIMEOUT,
                    "No complete request arrived within {:.0f} seconds. A request is JSON "
                    "terminated by a NUL byte.".format(_CLIENT_TIMEOUT)))
                did_work = True
            continue

        raw = bytes(client.buffer[:delimiter])
        _state.clients.remove(client)
        did_work = True

        try:
            # json.loads takes bytes, so the frame is never decoded by hand. That
            # is what keeps a multi-byte character split across two recv() calls
            # from being this module's problem.
            request = json.loads(raw)
        except ValueError as error:
            _send_and_close(client, _error(
                ERROR_MALFORMED_REQUEST,
                "The request is not valid JSON: {:s}".format(str(error))))
            continue

        _send_and_close(client, dispatch(request))

    return did_work


def poll():
    """One tick: accept what is waiting, advance what is open.

    Returns whether anything happened, which the timer callback uses to decide
    whether to stay at the active interval.
    """
    if _state.sock is None:
        return False
    _accept_clients()
    return _service_clients()
