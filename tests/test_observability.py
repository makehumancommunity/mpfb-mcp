# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for mpfbmcp.observability, the record of what crossed the socket.

Unusually for this repo, almost all of this is testable on this side of the
socket, because it is entirely on this side of the socket: the only thing that
still needs a running Blender is that a traceback line number from a real
add-on failure resolves to the right line of the dumped program.

Two things here are load-bearing rather than incidental. The tool-name
extraction is asserted against a *real* ``codegen.assemble()`` output for every
payload in the package rather than against a hand-written marker, because the
marker format is written by ``codegen`` and parsed by ``observability`` and
that coupling is the thing worth pinning. And the ordering test - that the
program file is on disk before the add-on answers - is asserted by having the
fake add-on look at the filesystem while it holds the request, since an
implementation that writes both files together after the response arrives
passes every other test here.

Run with::

    python -m unittest tests.test_observability -v
"""

__all__ = ()

import contextlib
import io
import json
import logging
import os
import shutil
import sys
import tempfile
import unittest

from mpfbmcp import codegen, connection, observability
from tests import fake_addon


class ObservabilityTestCase(fake_addon.EnvVarTestCase):
    """Manages the two MPFB_MCP_ variables and re-reads them per test."""

    def setUp(self) -> None:
        super().setUp()
        # Registered first, so it runs *last* - after every environment
        # variable a test set has been put back.
        self.addCleanup(observability.configure_from_environment)
        self.set_env_var(observability.RECORD_DIRECTORY_VARIABLE, None)
        self.set_env_var(observability.LOG_LEVEL_VARIABLE, None)
        observability.configure_from_environment()

    def scratch_directory(self) -> str:
        directory = tempfile.mkdtemp(prefix="mpfbmcp-observability-")
        self.addCleanup(shutil.rmtree, directory, True)
        return directory

    def enable_record(self) -> str:
        """Point MPFB_MCP_RECORD_DIR at a fresh directory and re-read it."""
        root = self.scratch_directory()
        self.set_env_var(observability.RECORD_DIRECTORY_VARIABLE, root)
        observability.configure_from_environment()
        return root

    def enable_log(self, level: str) -> None:
        self.set_env_var(observability.LOG_LEVEL_VARIABLE, level)
        observability.configure_from_environment()

    def run_directory(self, root: str) -> str:
        runs = [name for name in os.listdir(root) if name.startswith("run-")]
        self.assertEqual(len(runs), 1, "expected exactly one run directory in {}".format(root))
        return os.path.join(root, runs[0])

    def index_lines(self, root: str) -> list[str]:
        path = os.path.join(self.run_directory(root), "index.tsv")
        with open(path, encoding="utf-8") as stream:
            return [line for line in stream.read().splitlines() if line]


class ToolNameTests(unittest.TestCase):
    """The coupling between codegen's seam marker and observability's parser."""

    def test_every_payload_is_named_from_its_own_assembled_program(self) -> None:
        for payload in codegen.payload_names():
            with self.subTest(payload=payload):
                source = codegen.assemble(payload, params={"name": "Human"})
                self.assertEqual(
                    observability.tool_name_from_program(source),
                    payload[:-len(".py")])

    def test_a_program_with_no_marker_gets_a_neutral_name(self) -> None:
        self.assertEqual(observability.tool_name_from_program("result = {}"), "unnamed")

    def test_a_marker_naming_a_path_cannot_escape_the_run_directory(self) -> None:
        # Nothing in this package writes such a marker; a hand-assembled
        # program could, and the name becomes part of a filename.
        name = observability.tool_name_from_program("# --- payload: ../../etc/passwd ---\n")
        self.assertEqual(os.path.basename(name), name)
        self.assertNotIn(os.sep, name)


class LoggerTests(ObservabilityTestCase):
    def test_no_handler_is_attached_by_default(self) -> None:
        handlers = logging.getLogger(observability.LOGGER_ROOT).handlers
        self.assertTrue(all(isinstance(handler, logging.NullHandler) for handler in handlers),
                        "expected only a NullHandler, got {!r}".format(handlers))

    def test_the_level_variable_attaches_a_stderr_handler(self) -> None:
        self.enable_log("DEBUG")

        root = logging.getLogger(observability.LOGGER_ROOT)
        streams = [handler for handler in root.handlers
                   if isinstance(handler, logging.StreamHandler)
                   and not isinstance(handler, logging.NullHandler)]

        self.assertEqual(len(streams), 1)
        self.assertIs(streams[0].stream, sys.stderr)
        self.assertEqual(root.level, logging.DEBUG)

    def test_re_reading_the_environment_does_not_stack_handlers(self) -> None:
        self.enable_log("INFO")
        self.enable_log("DEBUG")

        root = logging.getLogger(observability.LOGGER_ROOT)
        streams = [handler for handler in root.handlers
                   if isinstance(handler, logging.StreamHandler)
                   and not isinstance(handler, logging.NullHandler)]

        self.assertEqual(len(streams), 1)
        self.assertEqual(root.level, logging.DEBUG)

    def test_an_unrecognised_level_still_attaches_a_handler_and_says_so(self) -> None:
        # assertLogs() restores the logger's level when it exits, so the level
        # this sets has to be read while still inside it. stderr is redirected
        # because the handler being attached is a real one and would otherwise
        # write the warning into the test run's own output.
        with self.assertLogs(observability.LOGGER_ROOT, level="WARNING") as captured:
            with contextlib.redirect_stderr(io.StringIO()):
                self.enable_log("DEGUB")
            level_while_configured = logging.getLogger(observability.LOGGER_ROOT).level

        self.assertIn("DEGUB", "\n".join(captured.output))
        self.assertEqual(level_while_configured, logging.WARNING)

    def test_a_call_logs_one_line(self) -> None:
        self.run_fake_server({"status": "ok", "result": 1})
        self.enable_log("INFO")

        with self.assertLogs(observability.LOGGER_ROOT, level="INFO") as captured:
            connection.send_code("# --- payload: create_human.py ---\n")

        self.assertEqual(len(captured.output), 1)
        self.assertIn("create_human", captured.output[0])

    def test_our_handler_does_not_propagate_to_the_host_s_own(self) -> None:
        # FastMCP() calls logging.basicConfig(), so the root logger already has
        # a handler on it in the real server; propagating would print each line
        # twice.
        with contextlib.redirect_stderr(io.StringIO()):
            self.enable_log("INFO")
        self.assertFalse(logging.getLogger(observability.LOGGER_ROOT).propagate)

    def test_an_ambient_info_logger_does_not_switch_the_per_call_line_on(self) -> None:
        # The one that matters in the real server: the root logger is at INFO
        # there whether or not anyone asked this package for anything.
        previous = logging.getLogger().level
        self.addCleanup(logging.getLogger().setLevel, previous)
        logging.getLogger().setLevel(logging.INFO)

        self.assertIs(observability.begin("result = {}"), observability._DISABLED_RECORD)


class DisabledPathTests(ObservabilityTestCase):
    """Off means unchanged, which is the path all the other tests exercise."""

    def test_begin_returns_the_shared_do_nothing_record(self) -> None:
        self.assertIs(observability.begin("result = {}"), observability._DISABLED_RECORD)

    def test_nothing_is_written_and_no_directory_is_created(self) -> None:
        root = self.scratch_directory()
        self.set_env_var(observability.RECORD_DIRECTORY_VARIABLE, None)
        observability.configure_from_environment()
        self.run_fake_server({"status": "ok", "result": 1})

        connection.send_code("# --- payload: create_human.py ---\n")

        self.assertEqual(os.listdir(root), [])

    def test_the_bytes_on_the_wire_are_identical(self) -> None:
        program = "# --- payload: create_human.py ---\nresult = {}\n"

        off = self.run_fake_server({"status": "ok", "result": 1})
        connection.send_code(program)

        self.enable_record()
        on = self.run_fake_server({"status": "ok", "result": 1})
        connection.send_code(program)

        self.assertEqual(off.requests, on.requests)


class RecordTests(ObservabilityTestCase):
    def test_the_program_and_the_response_are_written(self) -> None:
        root = self.enable_record()
        self.run_fake_server({"status": "ok", "result": {"object_name": "Human"}})

        connection.send_code("# --- payload: create_human.py ---\nresult = {}\n")

        directory = self.run_directory(root)
        self.assertTrue(os.path.isfile(os.path.join(directory, "0001-create_human.py")))
        with open(os.path.join(directory, "0001-create_human.json"), encoding="utf-8") as stream:
            self.assertEqual(json.load(stream),
                             {"status": "ok", "result": {"object_name": "Human"}})

    def test_the_program_is_written_byte_for_byte(self) -> None:
        # The things that tempt an implementation to normalize: non-ASCII, a
        # CRLF, trailing whitespace and a very long line.
        program = ("# --- payload: create_human.py ---\r\n"
                   "# äöü — café\n"
                   "result = {}   \n"
                   "# " + "x" * 5000 + "\n")
        root = self.enable_record()
        self.run_fake_server({"status": "ok", "result": 1})

        connection.send_code(program)

        path = os.path.join(self.run_directory(root), "0001-create_human.py")
        with open(path, encoding="utf-8", newline="") as stream:
            self.assertEqual(stream.read(), program)

    def test_the_program_is_on_disk_before_the_add_on_answers(self) -> None:
        root = self.enable_record()
        seen: dict[str, object] = {}

        def look_while_holding_the_request(request: dict[str, object]) -> dict[str, object]:
            directory = os.path.join(root, os.listdir(root)[0])
            seen["files"] = sorted(os.listdir(directory))
            return {"status": "ok", "result": 1}

        self.run_fake_server(responder=look_while_holding_the_request)

        connection.send_code("# --- payload: create_human.py ---\n")

        self.assertIn("0001-create_human.py", seen["files"])
        self.assertNotIn("0001-create_human.json", seen["files"])

    def test_a_call_that_never_answers_still_leaves_its_program(self) -> None:
        root = self.enable_record()
        self.run_fake_server(responder=lambda request: None)

        with self.assertRaises(ConnectionError):
            connection.send_code("# --- payload: set_targets.py ---\n")

        directory = self.run_directory(root)
        self.assertTrue(os.path.isfile(os.path.join(directory, "0001-set_targets.py")))
        self.assertFalse(os.path.isfile(os.path.join(directory, "0001-set_targets.json")))

    def test_the_index_has_a_header_and_one_line_per_call(self) -> None:
        root = self.enable_record()
        self.run_fake_server({"status": "ok", "result": 1})

        connection.send_code("# --- payload: create_human.py ---\n")
        connection.send_code("# --- payload: refit_human.py ---\n")

        header, first, second = self.index_lines(root)
        self.assertTrue(header.startswith("#"))
        self.assertEqual(header.split("\t"),
                         ["# seq", "timestamp", "tool", "bytes", "ms", "status", "response_bytes"])

        sequence, timestamp, tool, size, milliseconds, status, response_bytes = first.split("\t")
        self.assertEqual(sequence, "0001")
        self.assertTrue(timestamp.startswith("20"), timestamp)
        self.assertEqual(tool, "create_human")
        self.assertEqual(int(size), len("# --- payload: create_human.py ---\n"))
        self.assertGreaterEqual(float(milliseconds), 0.0)
        self.assertEqual(status, "ok")
        self.assertGreater(int(response_bytes), 0)

        self.assertEqual(second.split("\t")[0], "0002")
        self.assertEqual(second.split("\t")[2], "refit_human")

    def test_the_index_says_when_there_was_no_response(self) -> None:
        root = self.enable_record()
        self.run_fake_server(responder=lambda request: None)

        with self.assertRaises(ConnectionError):
            connection.send_code("# --- payload: create_human.py ---\n")

        fields = self.index_lines(root)[1].split("\t")
        self.assertEqual(fields[5], "no-response")
        self.assertEqual(fields[6], "-")
        self.assertGreaterEqual(float(fields[4]), 0.0)

    def test_the_run_directory_carries_the_process_id(self) -> None:
        root = self.enable_record()
        self.run_fake_server({"status": "ok", "result": 1})

        connection.send_code("# --- payload: create_human.py ---\n")

        self.assertTrue(os.path.basename(self.run_directory(root)).endswith(
            "-{:d}".format(os.getpid())))

    def test_the_response_file_tolerates_a_value_json_cannot_encode(self) -> None:
        # FR 005 found one coming back from MPFB (get_asset_list()'s "thumb"),
        # so the record has to survive it rather than be missing precisely on
        # the calls that most need it.
        root = self.scratch_directory()
        recorder = observability._Recorder(root)

        path, size = recorder.write_response(1, "list_assets", {"thumb": object()})

        self.assertIsNotNone(path)
        self.assertGreater(int(size), 0)
        with open(path, encoding="utf-8") as stream:
            self.assertIn("object object at", stream.read())


class FailureIsSwallowedTests(ObservabilityTestCase):
    def test_an_unwritable_directory_does_not_fail_the_call(self) -> None:
        blocked = os.path.join(self.scratch_directory(), "a-file")
        with open(blocked, "w", encoding="utf-8") as stream:
            stream.write("not a directory\n")
        self.set_env_var(observability.RECORD_DIRECTORY_VARIABLE,
                         os.path.join(blocked, "records"))
        observability.configure_from_environment()
        self.run_fake_server({"status": "error", "message": "boom"})

        with self.assertLogs(observability.LOGGER_ROOT, level="WARNING"):
            response = connection.send_code("# --- payload: create_human.py ---\n")

        self.assertEqual(response, {"status": "error", "message": "boom"})


class StdoutTests(ObservabilityTestCase):
    def test_nothing_reaches_stdout_in_any_configuration(self) -> None:
        # Stdout is the JSON-RPC channel: anything written there corrupts the
        # protocol, and not loudly. Asserted by capture rather than by reading
        # the code, since the way this breaks is a handler left at its default
        # stream. stderr is captured in the same breath, both to keep the test
        # run quiet and to show where the log line went instead.
        for name, configure in (("off", lambda: None),
                                ("record", self.enable_record),
                                ("log", lambda: self.enable_log("DEBUG"))):
            with self.subTest(configuration=name):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stderr(err):
                    configure()
                    self.run_fake_server({"status": "ok", "result": 1})
                    with contextlib.redirect_stdout(out):
                        connection.send_code("# --- payload: create_human.py ---\n")

                self.assertEqual(out.getvalue(), "")
                if name == "log":
                    self.assertIn("create_human", err.getvalue())


class ErrorEnvelopeTests(ObservabilityTestCase):
    def test_an_error_envelope_names_the_files_that_were_written(self) -> None:
        root = self.enable_record()
        self.run_fake_server({"status": "error", "message": "NameError on line 312"})

        response = connection.send_code("# --- payload: set_targets.py ---\n")

        record = response["mpfb_mcp_record"]
        directory = self.run_directory(root)
        self.assertEqual(record["program"], os.path.join(directory, "0001-set_targets.py"))
        self.assertEqual(record["response"], os.path.join(directory, "0001-set_targets.json"))

    def test_a_success_envelope_is_untouched(self) -> None:
        self.enable_record()
        self.run_fake_server({"status": "ok", "result": {"object_name": "Human"}})

        response = connection.send_code("# --- payload: create_human.py ---\n")

        self.assertEqual(response, {"status": "ok", "result": {"object_name": "Human"}})

    def test_an_error_envelope_is_untouched_when_the_record_is_off(self) -> None:
        self.run_fake_server({"status": "error", "message": "boom"})

        response = connection.send_code("# --- payload: create_human.py ---\n")

        self.assertEqual(response, {"status": "error", "message": "boom"})


if __name__ == "__main__":
    unittest.main()
