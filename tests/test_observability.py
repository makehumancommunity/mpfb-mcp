# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tests for mpfbmcp.observability, the record of what crossed the socket.

Unusually for this repo, all of this is testable on this side of the socket,
because it is entirely on this side of the socket: nothing here is a claim
about MPFB or about Blender, only about what this process writes down while it
makes a call.

Two things are load-bearing rather than incidental. **The ordering test** - that
the request file is on disk before the add-on answers - is asserted by having
the fake bridge look at the filesystem while it holds the request, since an
implementation that writes both files together after the response arrives
passes every other test here. And **off means unchanged**, asserted by
comparing the bytes that reached the fake with the record on and the record
off, because a diagnostic that alters the call it describes is worse than none.

The handshake probe is a call and is recorded as one, so the command under test
is usually sequence ``0002``. That is asserted rather than worked around: an
index that silently omitted the probe would misreport the order of what
happened.

This module was larger, and lost nothing it was about. Half of it exercised the
same claims over the generated code path, whose fake and whose ``send_code()``
FR 033 deleted; each of those claims is made here once, on the transport that
remains.

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

from mpfbmcp import bridge_connection, observability
from tests import fake_bridge


class ObservabilityTestCase(fake_bridge.BridgeTestCase):
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

    def bridge(self, result=None, command: str = "list_objects"):
        """A fake bridge answering the handshake probe and one command."""
        return self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            command: fake_bridge.ok_envelope(
                command, {"count": 0} if result is None else result),
        })


class CommandNameTests(unittest.TestCase):
    """Naming a record for the command it dispatches."""

    def test_a_command_names_its_own_record(self) -> None:
        self.assertEqual(observability.tool_name_from_command("list_objects"), "list_objects")

    def test_a_command_name_cannot_escape_the_run_directory(self) -> None:
        # Nothing in this package sends such a command name - every one is a
        # key of the add-on's closed vocabulary. The argument is a string
        # nonetheless, and it becomes part of a filename.
        name = observability.tool_name_from_command("../../etc/passwd")
        self.assertEqual(os.path.basename(name), name)
        self.assertNotIn(os.sep, name)

    def test_an_empty_command_gets_a_neutral_name(self) -> None:
        self.assertEqual(observability.tool_name_from_command("   "), "unnamed")


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

    def test_a_call_logs_one_line_naming_the_command(self) -> None:
        self.bridge()
        self.enable_log("INFO")

        with self.assertLogs(observability.LOGGER_ROOT, level="INFO") as captured:
            bridge_connection.send_command("list_objects")

        self.assertEqual(len(captured.output), 2, "the probe is a call and is logged as one")
        self.assertIn("get_status", captured.output[0])
        self.assertIn("list_objects", captured.output[1])

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

        self.assertIs(observability.begin_command("list_objects", "{}"),
                      observability._DISABLED_RECORD)


class DisabledPathTests(ObservabilityTestCase):
    """Off means unchanged, which is the path all the other tests exercise."""

    def test_begin_command_returns_the_shared_do_nothing_record(self) -> None:
        self.assertIs(observability.begin_command("list_objects", "{}"),
                      observability._DISABLED_RECORD)

    def test_nothing_is_written_and_no_directory_is_created(self) -> None:
        root = self.scratch_directory()
        self.set_env_var(observability.RECORD_DIRECTORY_VARIABLE, None)
        observability.configure_from_environment()
        self.bridge()

        bridge_connection.send_command("list_objects")

        self.assertEqual(os.listdir(root), [])

    def test_the_bytes_on_the_wire_are_identical(self) -> None:
        params = {"object_type": None}

        off = self.bridge()
        bridge_connection.send_command("list_objects", params)

        self.enable_record()
        bridge_connection.forget_handshakes()
        on = self.bridge()
        bridge_connection.send_command("list_objects", params)

        self.assertEqual(off.requests, on.requests)


class RecordTests(ObservabilityTestCase):
    def test_the_request_and_the_response_are_written(self) -> None:
        root = self.enable_record()
        self.bridge({"basemesh_name": "Human"}, command="create_human")

        bridge_connection.send_command("create_human", {"gender": 0.5})

        directory = self.run_directory(root)
        self.assertTrue(os.path.isfile(
            os.path.join(directory, "0002-create_human-request.json")))
        with open(os.path.join(directory, "0002-create_human.json"), encoding="utf-8") as stream:
            envelope = json.load(stream)
        self.assertEqual(envelope["status"], "ok")
        self.assertEqual(envelope["result"], {"basemesh_name": "Human"})

    def test_the_request_is_written_as_the_json_that_went_on_the_wire(self) -> None:
        root = self.enable_record()
        server = self.bridge()

        bridge_connection.send_command("list_objects", {"object_type": "Basemesh"})

        path = os.path.join(self.run_directory(root), "0002-list_objects-request.json")
        with open(path, encoding="utf-8") as stream:
            written = stream.read()
        self.assertEqual(json.loads(written),
                         {"command": "list_objects",
                          "params": {"object_type": "Basemesh"},
                          "protocol_version": bridge_connection.PROTOCOL_VERSION})
        # Byte for byte what was sent: a record that is nearly the request is
        # one that has to be argued with.
        self.assertEqual(written.encode("utf-8"),
                         server.requests[-1].partition(b"\0")[0])

    def test_a_non_ascii_parameter_survives_the_round_trip_to_disk(self) -> None:
        # The thing that tempts an implementation to normalize. An asset name
        # with a diaeresis in it is not exotic, and the file is read back as
        # UTF-8 because that is what it was written as.
        root = self.enable_record()
        self.bridge()

        bridge_connection.send_command("list_objects", {"object_type": "Bäsemesh — café"})

        path = os.path.join(self.run_directory(root), "0002-list_objects-request.json")
        with open(path, encoding="utf-8") as stream:
            self.assertEqual(json.load(stream)["params"]["object_type"], "Bäsemesh — café")

    def test_the_record_is_named_for_the_command(self) -> None:
        root = self.enable_record()
        self.bridge()

        bridge_connection.send_command("list_objects")

        files = sorted(os.listdir(self.run_directory(root)))
        self.assertIn("0001-get_status-request.json", files)
        self.assertIn("0002-list_objects-request.json", files)
        self.assertIn("0002-list_objects.json", files)

    def test_the_request_is_on_disk_before_the_bridge_answers(self) -> None:
        root = self.enable_record()
        seen: dict[str, object] = {}

        def look_while_holding_the_request(request):
            command = str(request.get("command"))
            if command == "list_objects":
                directory = os.path.join(root, os.listdir(root)[0])
                seen["files"] = sorted(os.listdir(directory))
            result = (fake_bridge.status_result() if command == "get_status"
                      else {"count": 0})
            return fake_bridge.ok_envelope(command, result)

        self.run_fake_bridge(responder=look_while_holding_the_request)

        bridge_connection.send_command("list_objects")

        self.assertIn("0002-list_objects-request.json", seen["files"])
        self.assertNotIn("0002-list_objects.json", seen["files"])

    def test_a_call_that_never_answers_still_leaves_its_request(self) -> None:
        root = self.enable_record()
        self.run_fake_bridge(responder=lambda request: None)

        with self.assertRaises(ConnectionError):
            bridge_connection.send_command("list_objects")

        directory = self.run_directory(root)
        # The probe is the call that failed, since it goes first.
        self.assertTrue(os.path.isfile(
            os.path.join(directory, "0001-get_status-request.json")))
        self.assertFalse(os.path.isfile(os.path.join(directory, "0001-get_status.json")))

    def test_the_index_has_a_header_and_one_line_per_call(self) -> None:
        root = self.enable_record()
        self.bridge()

        bridge_connection.send_command("list_objects", {"object_type": None})

        header, probe, call = self.index_lines(root)
        self.assertTrue(header.startswith("#"))
        self.assertEqual(header.split("\t"),
                         ["# seq", "timestamp", "tool", "bytes", "ms", "status", "response_bytes"])

        self.assertEqual(probe.split("\t")[0], "0001")
        self.assertEqual(probe.split("\t")[2], "get_status")

        sequence, timestamp, tool, size, milliseconds, status, response_bytes = call.split("\t")
        self.assertEqual(sequence, "0002")
        self.assertTrue(timestamp.startswith("20"), timestamp)
        self.assertEqual(tool, "list_objects")
        self.assertGreater(int(size), 0, "bytes counts the request")
        self.assertGreaterEqual(float(milliseconds), 0.0)
        self.assertEqual(status, "ok")
        self.assertGreater(int(response_bytes), 0)

    def test_the_index_is_one_sequence_in_call_order(self) -> None:
        root = self.enable_record()
        self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "list_objects": fake_bridge.ok_envelope("list_objects", {"count": 0}),
            "refit_human": fake_bridge.ok_envelope("refit_human", {"performed": True}),
        })

        bridge_connection.send_command("list_objects")
        bridge_connection.send_command("refit_human")

        lines = self.index_lines(root)[1:]
        self.assertEqual([line.split("\t")[2] for line in lines],
                         ["get_status", "list_objects", "refit_human"])
        self.assertEqual([line.split("\t")[0] for line in lines], ["0001", "0002", "0003"])
        for line in lines:
            self.assertEqual(len(line.split("\t")), 7)

    def test_the_index_says_when_there_was_no_response(self) -> None:
        root = self.enable_record()
        self.run_fake_bridge(responder=lambda request: None)

        with self.assertRaises(ConnectionError):
            bridge_connection.send_command("list_objects")

        fields = self.index_lines(root)[1].split("\t")
        self.assertEqual(fields[5], "no-response")
        self.assertEqual(fields[6], "-")
        self.assertGreaterEqual(float(fields[4]), 0.0)

    def test_the_run_directory_carries_the_process_id(self) -> None:
        root = self.enable_record()
        self.bridge()

        bridge_connection.send_command("list_objects")

        self.assertTrue(os.path.basename(self.run_directory(root)).endswith(
            "-{:d}".format(os.getpid())))

    def test_the_response_file_tolerates_a_value_json_cannot_encode(self) -> None:
        # FR 005 found one coming back from MPFB (get_asset_list()'s "thumb"),
        # so the record has to survive it rather than be missing precisely on
        # the calls that most need it. The bridge serializes a result before it
        # commits to an answer, so one should not reach here any more - which
        # makes this a claim about the record being robust, not about MPFB.
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
        self.bridge()

        with self.assertLogs(observability.LOGGER_ROOT, level="WARNING"):
            response = bridge_connection.send_command("list_objects")

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"], {"count": 0})


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
                bridge_connection.forget_handshakes()
                with contextlib.redirect_stderr(err):
                    configure()
                    self.bridge()
                    with contextlib.redirect_stdout(out):
                        bridge_connection.send_command("list_objects")

                self.assertEqual(out.getvalue(), "")
                if name == "log":
                    self.assertIn("list_objects", err.getvalue())


class ErrorEnvelopeTests(ObservabilityTestCase):
    def _failing_bridge(self):
        return self.run_fake_bridge(responder=lambda request: (
            fake_bridge.ok_envelope("get_status", fake_bridge.status_result())
            if request.get("command") == "get_status"
            else fake_bridge.error_envelope("command_failed", "it raised inside Blender")))

    def test_an_error_envelope_names_the_files_that_were_written(self) -> None:
        root = self.enable_record()
        self._failing_bridge()

        response = bridge_connection.send_command("list_objects")

        directory = self.run_directory(root)
        self.assertEqual(response["mpfb_mcp_record"], {
            "request": os.path.join(directory, "0002-list_objects-request.json"),
            "response": os.path.join(directory, "0002-list_objects.json"),
        })

    def test_a_success_envelope_is_untouched(self) -> None:
        self.enable_record()
        self.bridge({"basemesh_name": "Human"})

        response = bridge_connection.send_command("list_objects")

        self.assertNotIn("mpfb_mcp_record", response)

    def test_an_error_envelope_is_untouched_when_the_record_is_off(self) -> None:
        self._failing_bridge()

        response = bridge_connection.send_command("list_objects")

        self.assertEqual(response["status"], "error")
        self.assertNotIn("mpfb_mcp_record", response)


if __name__ == "__main__":
    unittest.main()
