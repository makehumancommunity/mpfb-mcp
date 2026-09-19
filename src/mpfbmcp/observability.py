"""
The record of what crossed the socket, and this package's logger.

A tool's call is a request that crosses a socket and an envelope that comes
back. Nothing kept the request afterwards and nothing recorded the response, so
a failure inside Blender arrived as a traceback naming a line number in a
program that no longer existed on either side of the socket. This module is
that record. It attaches at the socket boundary and nowhere else, which is what
keeps it out of the twenty-five tool modules, out of the payloads and out of
``codegen``.

**The attachment point does not move; the unit does.** There are two transports
now, and a request is a *program* on the generated path and a *command and its
parameters* on the bridge. Both are opened the same way and before the socket
call, both write one file, and both add one line to the same index in call
order - so a session that mixes the two reads as one sequence of calls rather
than as two logs that have to be interleaved by hand. What differs is the
file's extension and the word the error annotation uses for it, because calling
a JSON request a "program" would be a small lie told on every failure.

Two environment variables drive it, both off by default:

``MPFB_MCP_RECORD_DIR``
    Names a directory to write a per-call record into: the exact request - the
    program on the generated path, the JSON on the bridge, byte for byte as it
    went on the wire - the full response envelope, and one line in a
    tab-separated index. Unset, no directory is created, no file is opened,
    nothing is formatted, and the bytes on the wire are identical.

``MPFB_MCP_LOG_LEVEL``
    Attaches a ``stderr`` handler to this package's logger at that level. At
    ``INFO``, one line per call; at ``DEBUG``, what the tool modules decided
    locally before reaching the socket.

Neither carries the ``BLENDER_MCP_`` prefix, deliberately. Those two are shared
with blender_mcp because both processes talk to the same add-on and have to
agree about its address; these are mpfb-mcp's own settings, and blender_mcp
knows nothing about them.

One consequence of the host is worth naming, because it decides two things
here. ``FastMCP()`` calls ``logging.basicConfig()`` on construction, so in the
real server the *root* logger is already at ``INFO`` with a handler on it
before any tool runs. So the per-call line is gated on this package's own
variable rather than on ``logger.isEnabledFor()`` - otherwise every session
would pay for timing and formatting nobody asked for - and propagation is
turned off while this module's own handler is attached, or every line would be
printed twice. (mcp's handler is a ``RichHandler`` on a ``Console(stderr=True)``,
so it is not itself a threat to the transport; the point is only that it is
there.)

**Never stdout.** The server runs ``mcp.run(transport="stdio")``, so stdout is
the JSON-RPC channel. A ``print()`` left in while debugging, or a
``logging.StreamHandler()`` at its default stream, corrupts the protocol - and
not loudly: it surfaces as a client that hangs, drops the connection, or
reports a parse error nowhere near the cause. Every handler attached here names
``sys.stderr`` explicitly, and nothing in this package writes to stdout.

The record is diagnostic output *about the user's machine*: it contains
absolute paths from their install, their asset library layout, the MHMAT and
MHCLO files they have, and the parameters of the character they are building.
There are no credentials anywhere in this system, so no scrubbing is done and
none should be added; what is done instead is saying so, here and in the
documentation, and never defaulting the directory to somewhere inside the
repository.

Nothing here may turn a working call into a failed one. Every disk touch is
best-effort: an unwritable directory, a full disk or a response that will not
serialize produces one warning on the logger and is otherwise swallowed. A
read-only tool that raises because a diagnostic directory was not writable
would be strictly worse than a tool with no diagnostics at all.
"""

from __future__ import annotations

__all__ = (
    "LOG_LEVEL_VARIABLE",
    "RECORD_DIRECTORY_VARIABLE",
    "begin",
    "begin_command",
    "configure_from_environment",
    "get_logger",
    "tool_name_from_command",
    "tool_name_from_program",
)

import datetime
import json
import logging
import os
import re
import sys
import threading
import time

RECORD_DIRECTORY_VARIABLE = "MPFB_MCP_RECORD_DIR"
LOG_LEVEL_VARIABLE = "MPFB_MCP_LOG_LEVEL"

# The logger hierarchy is rooted at the package name, so a module can simply
# ask for logging.getLogger(__name__) and land underneath it.
LOGGER_ROOT = "mpfbmcp"

_INDEX_FILE_NAME = "index.tsv"
_INDEX_HEADER = "# seq\ttimestamp\ttool\tbytes\tms\tstatus\tresponse_bytes\n"
_INDEX_MISSING = "-"

# codegen.assemble() labels the last seam of every generated program with this
# marker, so that a line number reported from inside Blender can be traced back
# to the file it came from. It names the tool too, which is the whole reason
# send_code() needs no extra argument to say which tool called it. The format
# is therefore written by one module and parsed by another, and is pinned by
# tests on both sides rather than left as a comment.
# Trailing whitespace and a stray carriage return are tolerated: the marker
# has to be found in whatever was handed to send_code(), not only in what
# codegen produced.
_PAYLOAD_MARKER = re.compile(r"^# --- payload: (?P<name>.+?) ---[ \t\r]*$", re.MULTILINE)

# What a program with no marker is recorded as - something assembled by hand,
# or a future call that is not a payload. Recorded under a neutral name rather
# than rejected.
_UNKNOWN_TOOL_NAME = "unnamed"

_UNSAFE_IN_A_FILENAME = re.compile(r"[^A-Za-z0-9_.-]")

# What each transport's request file is called, and what a failure calls it.
# The response file is ``.json`` on both paths and keeps that name, so a mixed
# run's directory listing pairs a request with its answer by sequence number
# whichever transport carried it.
_PROGRAM_EXTENSION = ".py"
_PROGRAM_KEY = "program"
_REQUEST_EXTENSION = "-request.json"
_REQUEST_KEY = "request"

_LOG = logging.getLogger(__name__)

# Rebuilt by configure_from_environment(); None means the record is off.
_recorder: "_Recorder | None" = None

# The handler that MPFB_MCP_LOG_LEVEL attaches, kept so that re-reading the
# environment can detach the previous one rather than stacking a second.
_stderr_handler: "logging.Handler | None" = None

# Whether MPFB_MCP_LOG_LEVEL asked for the per-call line, which is a separate
# question from whether some other logger in the process is at INFO.
_logging_per_call = False


def get_logger(name: str) -> logging.Logger:
    """Return the logger for a module of this package.

    Callers pass ``__name__``. Since the package is itself named ``mpfbmcp``,
    that is already a child of the root logger this module configures - the
    helper exists so that the hierarchy is an explicit decision rather than a
    coincidence of the package name.
    """
    return logging.getLogger(name)


def tool_name_from_program(code: str) -> str:
    """Name the tool a generated program belongs to, from its payload seam."""
    match = _PAYLOAD_MARKER.search(code)
    if match is None:
        return _UNKNOWN_TOOL_NAME
    name = match.group("name").strip()
    if name.endswith(".py"):
        name = name[:-len(".py")]
    return _safe_file_name(name)


def tool_name_from_command(command: str) -> str:
    """Name a bridge call from the command it dispatches.

    The command names the call directly, so there is nothing to parse: a
    payload seam marker exists because a program carries no other statement of
    what it is, and a request that names its command needs no such device.
    Payload and command share a name by convention - ``list_objects.py`` becomes
    ``list_objects`` - so a mixed run's index stays sorted by the same word
    whichever transport a line came from.
    """
    return _safe_file_name(str(command).strip())


def _safe_file_name(name: str) -> str:
    """One call's name, reduced to something that cannot escape a directory.

    Nothing in this package produces a name needing this. A hand-assembled
    program could put anything after the payload marker, and a command name
    reaches here from a caller's argument; either way the name becomes part of
    a filename.
    """
    return _UNSAFE_IN_A_FILENAME.sub("_", name) or _UNKNOWN_TOOL_NAME


def configure_from_environment() -> None:
    """Read both variables and (re)build the record and the stderr handler.

    Called once at import. It is a function rather than import-time code alone
    so that a test can set the variables and ask for them to be re-read, the
    way ``tests/test_connection.py`` already does with the address variables.
    """
    global _recorder  # pylint: disable=global-statement
    _recorder = _recorder_from_environment()
    _attach_stderr_handler_from_environment()
    _already_warned.clear()


def begin(code: str) -> "_CallRecord | _DisabledRecord":
    """Open a record for one generated-code call, writing the program first.

    Writing the request up front is the point rather than an implementation
    detail: a call that hangs, times out or takes Blender down still leaves
    behind what caused it. Writing both files together after the response
    arrives would lose exactly the cases this exists for.

    Returns a shared do-nothing record when neither the record nor an
    INFO-level log is enabled, so that the disabled path - the one every
    existing test exercises - performs no formatting, no ``perf_counter()``
    bracketing that feeds nothing, and no directory probing.
    """
    return _begin(tool_name_from_program(code), code, _PROGRAM_EXTENSION, _PROGRAM_KEY)


def begin_command(command: str, request: str) -> "_CallRecord | _DisabledRecord":
    """Open a record for one bridge call, writing the request first.

    ``request`` is the serialized JSON, and it is written verbatim - the same
    string the client is about to put on the wire, so the record cannot drift
    from the call it describes. That is the same property the generated path's
    program file has, and it is why the request is not re-serialized here for
    readability: a record that is *nearly* what was sent is a record that has
    to be argued with.
    """
    return _begin(tool_name_from_command(command), request, _REQUEST_EXTENSION, _REQUEST_KEY)


def _begin(tool: str, request: str, extension: str,
           annotation_key: str) -> "_CallRecord | _DisabledRecord":
    recorder = _recorder
    if recorder is None and not _logging_per_call:
        return _DISABLED_RECORD
    return _CallRecord(recorder, tool, request, extension, annotation_key)


class _DisabledRecord:
    """The record of a call nobody asked to be recorded."""

    def finished(self, response: object) -> None:
        pass

    def failed(self, exception: BaseException) -> None:
        pass

    def annotate(self, response: dict[str, object]) -> dict[str, object]:
        return response


_DISABLED_RECORD = _DisabledRecord()


class _CallRecord:
    """One call: the request on disk before it is sent, the envelope after.

    The same record serves both transports, which is the point: what differs
    between a program and a command is the extension of one file and the word
    an error annotation uses for it, and everything else - the sequence number,
    the timestamp, the index line, the duration, the log line - is a property of
    *a call* rather than of how it travelled.

    Also handles the configuration where ``MPFB_MCP_LOG_LEVEL`` is set but
    ``MPFB_MCP_RECORD_DIR`` is not - there is a duration and a log line, but no
    files and no index. ``directory`` is then ``None``.
    """

    def __init__(self, recorder: "_Recorder | None", tool: str, request: str,
                 extension: str, annotation_key: str) -> None:
        self._recorder = recorder
        self._annotation_key = annotation_key
        self.tool = tool
        self.request_bytes = len(request.encode("utf-8"))
        self.sequence = 0
        self.request_path: str | None = None
        self.response_path: str | None = None
        self.timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="milliseconds")
        if recorder is not None:
            self.sequence = recorder.next_sequence_number()
            self.request_path = recorder.write_request(
                self.sequence, self.tool, request, extension)
        # Taken last, so that writing the request is not counted as part of the
        # round trip it is about to measure.
        self._started = time.perf_counter()

    def finished(self, response: dict[str, object]) -> None:
        """Record the envelope that came back, and how long it took."""
        duration = self._elapsed_milliseconds()
        status = _status_of(response)
        response_bytes = _INDEX_MISSING
        if self._recorder is not None:
            self.response_path, response_bytes = self._recorder.write_response(
                self.sequence, self.tool, response)
        self._append_index_line(duration, status, response_bytes)
        _LOG.info(
            "%s: %d bytes sent, %s in %s ms",
            self.tool, self.request_bytes, status, duration)

    def failed(self, exception: BaseException) -> None:
        """Record a call that raised rather than returning an envelope.

        There is a request and a duration but no response file, and the index
        says ``no-response`` rather than leaving the missing file unexplained.
        """
        duration = self._elapsed_milliseconds()
        self._append_index_line(duration, "no-response", _INDEX_MISSING)
        _LOG.info(
            "%s: %d bytes sent, no response after %s ms (%s)",
            self.tool, self.request_bytes, duration, exception)

    def annotate(self, response: dict[str, object]) -> dict[str, object]:
        """Name the record's files on an error envelope, and only there.

        A tool returns the envelope it was given, which is a standing
        convention rather than an accident, so this is deliberately narrow: an
        error envelope only, and only while the record is enabled. The reason
        to do it at all is that whoever reads the failure is usually an agent
        rather than the person who set the variable, and a failure that does
        not say where its own evidence landed wastes the record.

        The key naming the request file is the transport's word for it -
        ``program`` for generated code, ``request`` for a bridge command - so
        that an agent reading a failure is told what it is about to open.
        """
        if self.request_path is None:
            return response
        try:
            if not isinstance(response, dict) or response.get("status") != "error":
                return response
            record: dict[str, object] = {self._annotation_key: self.request_path}
            if self.response_path is not None:
                record["response"] = self.response_path
            response["mpfb_mcp_record"] = record
        except Exception as ex:  # pylint: disable=broad-except
            _warn_once("Could not annotate the response envelope: {:s}".format(str(ex)))
        return response

    def _elapsed_milliseconds(self) -> str:
        return "{:.1f}".format((time.perf_counter() - self._started) * 1000.0)

    def _append_index_line(self, duration: str, status: str, response_bytes: str) -> None:
        if self._recorder is None:
            return
        self._recorder.append_index_line("{:04d}\t{:s}\t{:s}\t{:d}\t{:s}\t{:s}\t{:s}\n".format(
            self.sequence, self.timestamp, self.tool, self.request_bytes,
            duration, status, response_bytes))


class _Recorder:
    """The per-run directory, the sequence counter and the index.

    The directory carries the process id as well as a timestamp because more
    than one MCP client can run ``mpfb-mcp`` against the same Blender; without
    it, two sessions interleave into one index and the sequence numbers stop
    meaning anything.
    """

    def __init__(self, root: str) -> None:
        self._root = root
        self._directory: str | None = None
        self._sequence = 0
        self._lock = threading.Lock()

    def next_sequence_number(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    def write_request(self, sequence: int, tool: str, request: str,
                      extension: str) -> str | None:
        """Write the request byte-for-byte as it was handed to the transport.

        No prettifying, no truncation, no re-wrapping, and that holds for both
        transports. On the generated path the one job this file has is to be
        the thing a traceback's line number can be resolved against, and a
        52 KB file with its middle elided cannot do it; on the bridge the job
        is to be the request that can be replayed, which an indented copy of it
        is not.
        """
        path = self._path_for(sequence, tool, extension)
        if path is None:
            return None
        try:
            with open(path, "w", encoding="utf-8", newline="") as stream:
                stream.write(request)
        except OSError as ex:
            _warn_once("Could not write the request record: {:s}".format(str(ex)))
            return None
        return path

    def write_response(self, sequence: int, tool: str,
                       response: object) -> tuple[str | None, str]:
        """Write the envelope, tolerating a value ``json`` cannot encode.

        ``default=repr`` rather than a failure: FR 005 already found such a
        value coming back from MPFB, and a record that is missing precisely on
        the calls that most need it would be worse than none.
        """
        path = self._path_for(sequence, tool, ".json")
        if path is None:
            return None, _INDEX_MISSING
        try:
            encoded = json.dumps(response, indent=2, default=repr)
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(encoded)
        except (OSError, TypeError, ValueError) as ex:
            _warn_once("Could not write the response record: {:s}".format(str(ex)))
            return None, _INDEX_MISSING
        return path, str(len(encoded.encode("utf-8")))

    def append_index_line(self, line: str) -> None:
        directory = self._run_directory()
        if directory is None:
            return
        try:
            with self._lock:
                with open(os.path.join(directory, _INDEX_FILE_NAME), "a",
                          encoding="utf-8") as stream:
                    stream.write(line)
        except OSError as ex:
            _warn_once("Could not append to the record index: {:s}".format(str(ex)))

    def _path_for(self, sequence: int, tool: str, suffix: str) -> str | None:
        directory = self._run_directory()
        if directory is None:
            return None
        # Zero-padded and monotonic, so that the order of calls is recoverable
        # from the directory listing alone; a timestamp would not do, since two
        # calls can share a second.
        return os.path.join(directory, "{:04d}-{:s}{:s}".format(sequence, tool, suffix))

    def _run_directory(self) -> str | None:
        """Create the run directory on first use, never at import."""
        if self._directory is not None:
            return self._directory
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
        directory = os.path.join(self._root, "run-{:s}-{:d}".format(stamp, os.getpid()))
        try:
            os.makedirs(directory, exist_ok=True)
            with open(os.path.join(directory, _INDEX_FILE_NAME), "w",
                      encoding="utf-8") as stream:
                stream.write(_INDEX_HEADER)
        except OSError as ex:
            _warn_once("Could not create the record directory {:s}: {:s}".format(
                directory, str(ex)))
            return None
        self._directory = directory
        _LOG.debug("Recording calls into %s", directory)
        return directory


def _status_of(response: object) -> str:
    if isinstance(response, dict):
        return str(response.get("status", "unknown"))
    return "unknown"


def _recorder_from_environment() -> "_Recorder | None":
    configured = os.environ.get(RECORD_DIRECTORY_VARIABLE, "").strip()
    if not configured:
        return None
    return _Recorder(os.path.expanduser(configured))


def _attach_stderr_handler_from_environment() -> None:
    global _stderr_handler, _logging_per_call  # pylint: disable=global-statement
    root = logging.getLogger(LOGGER_ROOT)
    if _stderr_handler is not None:
        # Undo the previous reading of the variable - handler, level and
        # propagation - rather than stacking a second one on top of it.
        root.removeHandler(_stderr_handler)
        root.setLevel(logging.NOTSET)
        root.propagate = True
        _stderr_handler = None
    _logging_per_call = False
    configured = os.environ.get(LOG_LEVEL_VARIABLE, "").strip()
    if not configured:
        # No handler attached unless asked: the ordinary discipline for a
        # library, and here also what keeps a quiet server quiet. The level is
        # left alone, so an application embedding this package keeps whatever
        # it configured for itself.
        return
    level = _resolve_level(configured)
    # sys.stderr is named rather than relied on as StreamHandler's default,
    # since that default is not what the docstring's warning can depend on.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(level if level is not None else logging.WARNING)
    # See the module docstring: the host has already put a handler on the root
    # logger, so propagating would print every line twice.
    root.propagate = False
    _stderr_handler = handler
    _logging_per_call = root.isEnabledFor(logging.INFO)
    if level is None:
        _LOG.warning(
            "%s=%s is not a logging level; using WARNING", LOG_LEVEL_VARIABLE, configured)


def _resolve_level(text: str) -> int | None:
    named = getattr(logging, text.upper(), None)
    if isinstance(named, int):
        return named
    if text.isdigit():
        return int(text)
    return None


_already_warned: set[str] = set()


def _warn_once(message: str) -> None:
    """Warn about a broken record once, not once per call.

    A directory that cannot be written to will not become writable during the
    session, and a warning per call would be its own kind of damage.
    """
    key = message.split(":")[0]
    if key in _already_warned:
        return
    _already_warned.add(key)
    _LOG.warning("%s", message)


logging.getLogger(LOGGER_ROOT).addHandler(logging.NullHandler())
configure_from_environment()
