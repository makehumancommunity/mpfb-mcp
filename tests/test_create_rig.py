# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the mpfb_create_rig tool: the bone table's shape, on both sides of the socket.

Two layers (see ``tests/test_list_objects.py``, the template), and a third that is the reason
this module is longer than a wrapper's: the table's shape is checked twice, here before
sending and in the bridge's ``shared/rig_table.py`` because its socket is reachable by more than
this package, and ``BothSidesTests`` runs the two over one table of cases, executing the bridge
file's source directly as ``tests/test_save_preset.py`` does ``artifact_names.py``.

**No joint, vertex count or bone vocabulary is checked here.** Which joints a body has, how many
vertices it holds and where MPFB fits a bone are Blender's, and are
``bridge/test/tests/ddd_mutating/create_rig_test.py``'s and
``bridge/test/tests/bbb_shared/rig_definition_test.py``'s.

Run with::

    python -m unittest tests.test_create_rig -v
"""

__all__ = ()

import pathlib
import unittest
from unittest import mock

from mcp.server.fastmcp import FastMCP

from mpfbmcp import bridge_connection
from mpfbmcp.tools import create_rig

from tests import fake_bridge

_BRIDGE = pathlib.Path(__file__).resolve().parent.parent / "bridge" / "mpfb_bridge"


def _tool_callable():
    """The sync function behind the tool, which @mcp.tool wraps in a coroutine."""
    mcp = FastMCP("test")
    create_rig.register(mcp)
    return mcp._tool_manager._tools[  # pylint: disable=protected-access
        "mpfb_create_rig"].fn


def _bone(name="root", parent="", head=None, tail=None, **extra):
    bone = {"name": name, "parent": parent,
            "head": head if head is not None else {"joint": "joint-ground"},
            "tail": tail if tail is not None else {"joint": "joint-pelvis"}}
    bone.update(extra)
    return bone


_POSITION = {"forward": 0.0, "left": 0.1, "up": 1.0}

# Tables both sides must accept.
ACCEPTED = (
    [_bone()],
    [_bone(), _bone("spine", "root", {"joint": "joint-pelvis"}, {"vertex": 12}, connect=True)],
    [_bone(head={"mean": [1, 2, 3]}, tail={"position": _POSITION})],
    [_bone(head={"position": _POSITION, "snap": False}, tail={"vertex": 0, "offset": {"up": 0.1}})],
    [_bone(roll="align_z_world_z", deform=False, collections=["Body", "Arms"])],
    [_bone(roll={"degrees": -12.5})],
    # A reading, sent back: the resolved position beside another kind, and what is not carried.
    [_bone(head={"joint": "joint-ground", "position": _POSITION}, features_not_carried=["x"])],
    [_bone("a", "b"), _bone("b", "")],
)

# Tables both sides must refuse.
REFUSED = (
    [],
    "root",
    [_bone(tial={"joint": "j"})],
    [_bone(), _bone()],
    [_bone(name="")],
    [_bone(parent="nobody")],
    [_bone("a", "b"), _bone("b", "a")],
    [_bone("a", "a")],
    [_bone(connect=True)],
    [{"name": "root", "parent": "", "head": {"joint": "j"}}],
    [_bone(head={})],
    [_bone(head={"joint": "j", "vertex": 1})],
    [_bone(head={"vertex": -1})],
    [_bone(head={"vertex": True})],
    [_bone(head={"vertex": 1.5})],
    [_bone(head={"mean": [1]})],
    [_bone(head={"mean": [1, 1]})],
    [_bone(head={"mean": [1, "2"]})],
    [_bone(head={"position": {"forward": 0.0, "left": 0.0}})],
    [_bone(head={"position": {"forward": 0.0, "left": 0.0, "up": float("nan")}})],
    [_bone(head={"position": {"forward": 0.0, "left": 0.0, "up": 1.0, "down": 1.0}})],
    [_bone(head={"joint": "j", "snap": False})],
    [_bone(head={"position": _POSITION, "snap": "false"})],
    [_bone(head={"joint": "j", "offset": {"sideways": 1.0}})],
    [_bone(head={"joint": "j", "offset": {}})],
    [_bone(head={"joint": "j", "offset": {"up": True}})],
    [_bone(roll="align_y")],
    [_bone(roll=12)],
    [_bone(roll={"degrees": 12, "axis": "x"})],
    [_bone(deform="yes")],
    [_bone(collections=[])],
    [_bone(collections=["Body", "Body"])],
    [_bone(parent=None)],
    [_bone(head={"strategy": "XYZ", "vertex_indices": [1, 2, 3], "expressible": False})],
)


class ArgumentValidationTests(unittest.TestCase):

    def setUp(self):
        self.tool = _tool_callable()

    def _sent(self, **arguments):
        with mock.patch.object(bridge_connection, "send_command") as send_command:
            send_command.return_value = {"status": "ok", "result": {}}
            self.tool(**arguments)
        return send_command.call_args[0][1]

    def test_bones_is_required(self):
        with self.assertRaises(TypeError):
            self.tool()

    def test_every_refused_table_is_refused_before_sending(self):
        for table in REFUSED:
            with self.subTest(table=table):
                with mock.patch.object(bridge_connection, "send_command") as send_command:
                    with self.assertRaises(ValueError):
                        self.tool(bones=table)
                send_command.assert_not_called()

    def test_every_accepted_table_crosses(self):
        for table in ACCEPTED:
            with self.subTest(table=table):
                self.assertEqual(len(self._sent(bones=table)["bones"]), len(table))

    def test_what_a_reading_adds_is_dropped_before_sending(self):
        sent = self._sent(bones=[_bone(head={"joint": "joint-ground", "position": _POSITION},
                                       features_not_carried=["constraint:IK"])])
        self.assertEqual(sent["bones"][0]["head"], {"joint": "joint-ground"})
        self.assertNotIn("features_not_carried", sent["bones"][0])

    def test_a_position_alone_is_the_kind_and_crosses(self):
        sent = self._sent(bones=[_bone(head={"position": _POSITION, "snap": False})])
        self.assertEqual(sent["bones"][0]["head"], {"position": _POSITION, "snap": False})

    def test_no_joint_vocabulary_is_checked_here(self):
        sent = self._sent(bones=[_bone(head={"joint": "joint-that-no-body-has"})])
        self.assertEqual(sent["bones"][0]["head"], {"joint": "joint-that-no-body-has"})

    def test_the_default_call_reaches_the_wire(self):
        self.assertEqual(self._sent(bones=[_bone()]),
                         {"name": None, "bones": [create_rig.validated_bones([_bone()])[0]],
                          "replace": False})

    def test_replace_must_be_a_real_bool(self):
        for bad in ("true", 1, None):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    self.tool(bones=[_bone()], replace=bad)

    def test_the_cap_is_the_bridges(self):
        self.assertEqual(create_rig.MAX_BONES, 1000)
        with self.assertRaises(ValueError):
            self.tool(bones=[_bone("b{:d}".format(index)) for index in range(1001)])


@unittest.skipUnless(_BRIDGE.exists(), "the add-on's source is not beside this checkout")
class BothSidesTests(unittest.TestCase):
    """The bridge's ``shared/rig_table.py`` and this tool's checks, over one table of cases."""

    def setUp(self):
        namespace: dict = {}
        path = _BRIDGE / "shared" / "rig_table.py"
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), namespace)  # noqa: S102
        self.bridge = namespace

    def _bridge_accepts(self, table):
        return not self.bridge["table_shape_errors"](table, create_rig.MAX_BONES)

    def _tool_accepts(self, table):
        try:
            create_rig.validated_bones(table)
        except ValueError:
            return False
        return True

    def test_both_accept_the_same_tables(self):
        for table in ACCEPTED:
            with self.subTest(table=table):
                self.assertTrue(self._tool_accepts(table))
                self.assertTrue(self._bridge_accepts(table))

    def test_both_refuse_the_same_tables(self):
        # The XYZ heel is refused on both sides for one reason, and the tool says so with a
        # sentence of its own: it has keys an end does not take.
        for table in REFUSED:
            with self.subTest(table=table):
                self.assertFalse(self._tool_accepts(table))
                self.assertFalse(self._bridge_accepts(table))

    def test_both_know_the_same_keys(self):
        self.assertEqual(self.bridge["BONE_KEYS"], create_rig.BONE_KEYS)
        self.assertEqual(self.bridge["END_KEYS"], create_rig.END_KEYS)
        self.assertEqual(tuple(self.bridge["ROLL_ALIGNMENTS"]), create_rig.ROLL_ALIGNMENTS)

    def test_the_bridge_names_where_each_fault_is(self):
        errors = self.bridge["table_shape_errors"](
            [_bone(), _bone("spine", "root", tail={"vertex": -1})], 10)
        self.assertEqual([error["where"] for error in errors], ["bones[1].tail"])


class BridgePathTests(fake_bridge.BridgeTestCase):

    def test_the_command_and_its_answer(self):
        server = self.run_answering_bridge({
            "get_status": fake_bridge.ok_envelope("get_status", fake_bridge.status_result()),
            "create_rig": fake_bridge.ok_envelope("create_rig", {"created": True}),
        })
        envelope = _tool_callable()(bones=[_bone()])
        self.assertEqual(envelope["result"], {"created": True})
        self.assertEqual(server.commands()[-1], "create_rig")
        params = server.decoded_requests()[-1]["params"]
        self.assertEqual(params["bones"][0]["head"], {"joint": "joint-ground"})


if __name__ == "__main__":
    unittest.main()
