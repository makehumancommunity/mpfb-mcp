"""
All six refitting commands, against a real Rigify regenerate: kept, reset, and unchanged.

**In this layer because the claim is that the six agree**, and the layer's rule puts that here even
though every command dispatched is a mutating one; FR 054 named ``ddd_mutating/``, whose own docstring
says one module per command. A table of the six runs through one set of assertions, so a seventh way of
calling ``refit()`` has nowhere to hide.

**Each generated rig is posed by the tools, and read by plain ``bpy``**, so what is asserted is what is
on the bones rather than what a command reports about them. ``_pose()`` holds a switch off its default,
so that FK is in charge, and an FK control and a head off rest. The switch is the half that hurt: the
photo studio session found out from a ``chain_not_in_charge`` that a write was refused, and that sequence
is here in full.

**The data roots keep MPFB's rigs.** A refit of a meta-rig reads ``rigs/`` out of ``mpfb_data``, and the
fixtures that redirect ``mpfb_data`` to a target tree or to a small pack would leave it nothing to read,
so a symlink to the real ones stands in that tree. The fixture is otherwise the one the commands' own
modules use.
"""

import os

import bpy
import pytest

from .._fixtures import Character
from .._fixtures import build_target_tree
from .._fixtures import dispatch
from .._fixtures import expression_library
from .._fixtures import redirected_locations
from .._fixtures import rest_pose
from .._fixtures import result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip

_SIDED = {"section": "arms", "category": "lowerarm-scale-depth-decr-incr"}


def _refit_human(name, value, keep_pose):
    assert value is not None
    return "refit_human", {"name": name, "keep_pose": keep_pose}


def _set_macro_details(name, value, keep_pose):
    return "set_macro_details", {
        "name": name, "refit": True, "keep_pose": keep_pose,
        "changes": [{"argument": "muscle", "property": "muscle", "value": value}]}


def _set_targets(name, value, keep_pose):
    return "set_targets", {
        "name": name, "refit": True, "keep_pose": keep_pose,
        "modifiers": [{"section": "nose", "category": "nose-scale-depth-decr-incr",
                       "value": value}]}


def _symmetrize_targets(name, value, keep_pose):
    made = dispatch("set_targets", {"name": name, "modifiers": [dict(_SIDED, side="left",
                                                                     value=value)]})
    assert made["status"] == "ok" and made["result"]["performed"], made
    return "symmetrize_targets", {"name": name, "direction": "left_to_right", "refit": True,
                                  "keep_pose": keep_pose}


def _set_face_units(name, value, keep_pose):
    return "set_face_units", {"name": name, "keep_pose": keep_pose,
                              "face_units": [{"face_unit": "jawOpen", "value": value}]}


def _apply_expressions(name, value, keep_pose):
    return "apply_expressions", {"name": name, "keep_pose": keep_pose, "mode": "replace",
                                 "expressions": [{"fragment": "jaw.json", "weight": value}]}


_TARGET_TREE = (_set_targets, _symmetrize_targets)
_PACK = (_set_face_units, _apply_expressions)
SIX = (_refit_human, _set_macro_details, _set_targets, _symmetrize_targets, _set_face_units,
       _apply_expressions)


def _ids(call):
    return call.__name__.lstrip("_")


class _Roots:
    """The data roots one of the six needs while a real refit reads the real rigs."""

    def __init__(self, services, call, root):
        self.services = services
        self.call = call
        self.root = str(root)
        self.real_rigs = os.path.join(
            services["LocationService"].get_mpfb_data(), "rigs")
        self.opened = None

    def _with_rigs(self, mpfb_data):
        os.makedirs(mpfb_data, exist_ok=True)
        link = os.path.join(mpfb_data, "rigs")
        if not os.path.exists(link):
            os.symlink(self.real_rigs, link)

    def __enter__(self):
        if self.call in _TARGET_TREE:
            paths = build_target_tree(self.root)
            self._with_rigs(paths["mpfb_data"])
            self.opened = redirected_locations(self.services, mpfb_data=paths["mpfb_data"],
                                               user_data=paths["user_data"])
        elif self.call in _PACK:
            self._with_rigs(os.path.join(self.root, "system"))
            self.opened = expression_library(self.services, self.root)
        if self.opened is not None:
            self.opened.__enter__()
        return self

    def __exit__(self, *args):
        if self.opened is not None:
            self.opened.__exit__(*args)


@pytest.fixture(name="generated", scope="module")
def _generated():
    services = services_or_skip()
    with Character() as character:
        yield character.basemesh, rigged_character(services, character, "generated:human_toes")


@pytest.fixture(name="default_rig", scope="module")
def _default_rig():
    services = services_or_skip()
    with Character() as character:
        yield character.basemesh, rigged_character(services, character, "default_no_toes")


_SWITCH_BONE = "upper_arm_parent.L"
_FK_BONE = "upper_arm_fk.L"


def _pose(basemesh):
    """Left arm in FK, posed, and the head turned: through the tools, as a session does it."""
    switched = result("set_pose_switches", {"name": basemesh.name, "switches": [
        {"body_part": "left_arm", "switch": "IK_FK", "value": 1.0}]})
    assert switched["performed"] is True, switched["message"]
    axis = {"forward": 1.0, "left": 0.0, "up": 0.0}
    posed = result("set_pose_bones", {"name": basemesh.name, "bones": [
        {"bone": _FK_BONE, "rotate_by": {"axis": axis, "degrees": 30.0}},
        {"bone": "head", "rotate_by": {"axis": axis, "degrees": 10.0}}]})
    assert posed["performed"] is True, posed["message"]


def _held(rig):
    """What the pose holds, read straight off the bones."""
    bpy.context.view_layer.update()
    bones = rig.pose.bones
    return dict(
        switch=float(bones[_SWITCH_BONE]["IK_FK"]),
        fk=tuple(bones[_FK_BONE].rotation_quaternion),
        head=tuple(bones["head"].rotation_quaternion),
        hand=tuple(bones["DEF-hand.L"].tail),
    )


def _close(first, second, tolerance=1e-4):
    return all(abs(a - b) <= tolerance for a, b in zip(first, second))


def _run(call, basemesh, value, keep_pose):
    command, params = call(basemesh.name, value, keep_pose)
    answer = result(command, params)
    assert answer["refit_performed"] is True, answer["message"]
    return answer


@pytest.mark.parametrize("call", SIX, ids=_ids)
def test_a_generated_rig_keeps_its_pose_by_default(call, generated, tmp_path):
    services = services_or_skip()
    basemesh, rig = generated
    rest_pose(rig)
    with _Roots(services, call, tmp_path):
        _pose(basemesh)
        before = _held(rig)
        answer = _run(call, basemesh, 0.2, True)

    assert answer["pose_after_refit"] == "kept", answer["message"]
    assert answer["pose_kept_count"] >= 3, "the switch, the FK bone and the head"
    assert answer["bones_not_restored"] == []
    assert "limbs_made_stretched" in answer and "limbs_made_unreachable" in answer
    after = _held(rig)
    assert after["switch"] == 1.0
    assert _close(after["fk"], before["fk"]), "channels come back exactly"
    assert _close(after["head"], before["head"])


@pytest.mark.parametrize("call", SIX, ids=_ids)
def test_keep_pose_false_is_reset_and_restore_with_puts_it_back(call, generated, tmp_path):
    services = services_or_skip()
    basemesh, rig = generated
    rest_pose(rig)
    with _Roots(services, call, tmp_path):
        _pose(basemesh)
        before = _held(rig)
        answer = _run(call, basemesh, 0.3, False)

        assert answer["pose_after_refit"] == "reset", answer["message"]
        assert answer["pose_reset_count"] >= 3
        reset = _held(rig)
        assert reset["switch"] == 0.0, "MPFB's result stands"
        assert _close(reset["head"], (1.0, 0.0, 0.0, 0.0))

        back = answer["restore_with"]
        assert result("set_pose_switches", back["mpfb_set_pose_switches"])["performed"] is True
        assert result("set_pose_bones", back["mpfb_set_pose_bones"])["performed"] is True
    restored = _held(rig)
    assert restored["switch"] == 1.0
    assert _close(restored["fk"], before["fk"], 1e-3)
    assert _close(restored["head"], before["head"], 1e-3)


@pytest.mark.parametrize("call", SIX, ids=_ids)
def test_a_default_rig_is_unchanged_and_nothing_is_written(call, default_rig, tmp_path):
    services = services_or_skip()
    basemesh, rig = default_rig
    rest_pose(rig)
    bone = next(pose_bone for pose_bone in rig.pose.bones if pose_bone.parent is not None)
    bone.rotation_mode = "XYZ"
    bone.rotation_euler = (0.25, 0.0, 0.0)
    with _Roots(services, call, tmp_path):
        answer = _run(call, basemesh, 0.2, True)
    assert answer["pose_after_refit"] == "unchanged", answer["message"]
    assert abs(bone.rotation_euler[0] - 0.25) < 1e-6
    assert "pose_kept_count" not in answer


def test_a_body_change_keeps_the_values_and_moves_the_limb(generated):
    """Non-goal in action: the control holds its value, and the hand stands somewhere new."""
    services_or_skip()
    basemesh, rig = generated
    rest_pose(rig)
    _pose(basemesh)
    before = _held(rig)
    answer = result("set_macro_details", {
        "name": basemesh.name, "refit": True,
        "changes": [{"argument": "height", "property": "height", "value": 0.95}]})
    after = _held(rig)
    result("set_macro_details", {
        "name": basemesh.name, "refit": True,
        "changes": [{"argument": "height", "property": "height", "value": 0.5}]})

    assert answer["pose_after_refit"] == "kept"
    assert _close(after["fk"], before["fk"])
    assert after["switch"] == 1.0
    assert not _close(after["hand"], before["hand"], 0.01), "the body changed, so the hand did"


def test_no_refit_is_null(generated):
    basemesh, _rig = generated
    answer = result("set_macro_details", {
        "name": basemesh.name,
        "changes": [{"argument": "muscle", "property": "muscle", "value": 0.4}]})
    assert answer["refit_performed"] is False
    assert answer["pose_after_refit"] is None


def test_a_refusal_is_null(generated):
    basemesh, _rig = generated
    answer = result("set_face_units", {
        "name": basemesh.name, "face_units": [{"face_unit": "notAUnit", "value": 0.1}]})
    assert answer["blocked_by"] == "unknown_face_units"
    assert answer["pose_after_refit"] is None


def test_a_blocked_refit_left_the_rig_untouched_and_says_unchanged():
    """``rig_refit_is_blocked()``: a generated rig whose meta-rig is gone."""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:human_toes")
        _pose(character.basemesh)
        before = _held(rig)
        metarig = services["ObjectService"].find_rigify_metarig_by_rig(rig)
        bpy.data.objects.remove(metarig)

        answer = result("refit_human", {"name": character.basemesh.name})

        assert answer["refit_performed"] is False
        assert answer["pose_after_refit"] == "unchanged"
        assert _held(rig)["switch"] == before["switch"]


def test_the_photo_studio_sequence(tmp_path):
    """Pose, switch, smile, then the write that used to be refused with chain_not_in_charge."""
    services = services_or_skip()
    with Character() as character:
        basemesh = character.basemesh
        rig = rigged_character(services, character, "generated:human_toes")
        with _Roots(services, _set_face_units, tmp_path):
            _pose(basemesh)
            smile = result("set_face_units", {
                "name": basemesh.name, "face_units": [{"face_unit": "mouthSmileLeft",
                                                       "value": 0.8}]})
            assert smile["refit_performed"] is True
            assert smile["pose_after_refit"] == "kept"

            write = result("set_pose_bones", {"name": basemesh.name, "bones": [
                {"bone": _FK_BONE, "rotate_by": {"axis": {"forward": 1.0, "left": 0.0, "up": 0.0},
                                                 "degrees": 5.0}}]})
        assert write["performed"] is True, write["message"]
        assert write["resolution_errors"] == []
        assert float(rig.pose.bones[_SWITCH_BONE]["IK_FK"]) == 1.0
