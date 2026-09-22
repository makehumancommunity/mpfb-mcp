"""
The record of what crossed the socket, and this package's logger.

A tool's call is a request that crosses a socket and an envelope that comes
back. Nothing kept the request afterwards and nothing recorded the response, so
a failure inside Blender arrived as a message about something that no longer
existed on either side of the socket. This module is that record. **It attaches
at the socket boundary and nowhere else**, which is what keeps it out of the
twenty-five tool modules and out of the add-on: the diagnostics belong to the
call, not to what the call causes Blender to do.

There was a second transport until FR 033, and the record had two units
accordingly - a *program* on the generated path, a *command and its parameters*
on the bridge - written to one directory and one index so that a mixed session
read as one sequence of calls. The generated path is gone and so is the
distinction; what is left is what a bridge call always wrote, unchanged down to
the index columns.

Two environment variables drive it, both off by default:

``MPFB_MCP_RECORD_DIR``
    Names a directory to write a per-call record into: the exact request, byte
    for byte as it went on the wire, the full response envelope, and one line
    in a tab-separated index. Unset, no directory is created, no file is
    opened, nothing is formatted, and the bytes on the wire are identical.

``MPFB_MCP_LOG_LEVEL``
    Attaches a ``stderr`` handler to this package's logger at that level. At
    ``INFO``, one line per call; at ``DEBUG``, what the tool modules decided
    locally before reaching the socket.

Neither carries the ``MPFB_BRIDGE_`` prefix, deliberately. Those two address
the add-on and are read by the wire client; these say what this process does
with a call it has already decided to make, and would mean nothing to the
add-on.

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
    "begin_command",
    "configure_from_environment",
    "get_logger",
    "tool_name_from_command",
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

# What a call with no name of its own is recorded as. Nothing in this package
# produces one; a caller reaching ``begin_command()`` with an empty command
# would, and it is recorded under a neutral name rather than rejected.
_UNKNOWN_TOOL_NAME = "unnamed"

_UNSAFE_IN_A_FILENAME = re.compile(r"[^A-Za-z0-9_.-]")

# What the two files of one call are called. The suffixes differ so that a
# directory listing pairs a request with its answer by sequence number, and
# ``_REQUEST_KEY`` is the word an error envelope uses when it names the file
# the reader should open.
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


def tool_name_from_command(command: str) -> str:
    """Name a call's record from the command it dispatches.

    The command names the call directly, so there is nothing to parse. Tool and
    command share a name by convention - ``mpfb_list_objects`` sends
    ``list_objects`` - so the index reads as a list of the tools that were
    called, which is what somebody opening it is looking for.
    """
    return _safe_file_name(str(command).strip())


def _safe_file_name(name: str) -> str:
    """One call's name, reduced to something that cannot escape a directory.

    Nothing in this package produces a name needing this - every command name
    is a key of the add-on's closed vocabulary. It reaches here from a caller's
    argument nonetheless, and becomes part of a filename.
    """
    return _UNSAFE_IN_A_FILENAME.sub("_", name) or _UNKNOWN_TOOL_NAME


def configure_from_environment() -> None:
    """Read both variables and (re)build the record and the stderr handler.

    Called once at import. It is a function rather than import-time code alone
    so that a test can set the variables and ask for them to be re-read, the
    way ``tests/test_bridge_connection.py`` already does with the address
    variables.
    """
    global _recorder  # pylint: disable=global-statement
    _recorder = _recorder_from_environment()
    _attach_stderr_handler_from_environment()
    _already_warned.clear()


def begin_command(command: str, request: str) -> "_CallRecord | _DisabledRecord":
    """Open a record for one call, writing the request first.

    Writing the request up front is the point rather than an implementation
    detail: a call that hangs, times out or takes Blender down still leaves
    behind what caused it. Writing both files together after the response
    arrives would lose exactly the cases this exists for.

    ``request`` is the serialized JSON, and it is written verbatim - the same
    string the client is about to put on the wire, so the record cannot drift
    from the call it describes. That is why it is not re-serialized here for
    readability: a record that is *nearly* what was sent is a record that has
    to be argued with.

    Returns a shared do-nothing record when neither the record nor an
    INFO-level log is enabled, so that the disabled path - the one every
    existing test exercises - performs no formatting, no ``perf_counter()``
    bracketing that feeds nothing, and no directory probing.
    """
    recorder = _recorder
    if recorder is None and not _logging_per_call:
        return _DISABLED_RECORD
    return _CallRecord(recorder, tool_name_from_command(command), request,
                       _REQUEST_EXTENSION, _REQUEST_KEY)


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

    The sequence number, the timestamp, the index line, the duration and the
    log line are all properties of *a call* rather than of what was in it. The
    extension and the annotation key are still constructor arguments rather
    than constants inlined below, which is what let one record serve two
    transports and is now simply where the two spellings live.

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

        No prettifying, no truncation, no re-wrapping. The job this file has is
        to be the request that can be replayed, which an indented copy of it is
        not.
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
