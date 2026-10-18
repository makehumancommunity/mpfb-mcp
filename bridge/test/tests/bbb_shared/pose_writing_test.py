"""
``shared/pose_writing.py`` called directly: how the three pose writers write, check and undo.

What only a real armature can establish about it:

- **The undo is exact.** :func:`snapshot` then :func:`restore` gives back every
  channel to the last bit, including a quaternion read the other way round and
  an Euler angle past 180 degrees - which is what lets ``set_pose_bones`` write,
  check and roll back and still say "nothing was applied".
- **Locks are read the way Rigify reads them**: per component on an Euler bone
  and under ``lock_rotations_4d``, as a whole otherwise, and a connected bone's
  location always locked. ``pose_bone.matrix`` ignores all of it, which is why
  :func:`lock_violations` exists.
- **Drivers and animation are found by data path**: a driver on a bone's
  location, a keyframe on its rotation, and a bone name with a quote in it.
- **A restore entry, written back through the setter, recreates the bone's own
  channels** after a parent has been moved, which is the property
  ``reset_pose``'s ``restore_with`` rests on.
- **The frame's new inverse conversions are inverses** of the reading ones on a
  rig moved, turned and scaled.
"""

import math

import bpy
from mathutils import Quaternion
from mathutils import Vector

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import rigged_character
from .._fixtures import services_or_skip


def _writing():
    return bridge_module("shared.pose_writing")


def _frame_class():
    return bridge_module("shared.character_frame").Frame


def _armature(name, bones):
    """An armature object built in edit mode from ``(name, parent, head, tail, connected)``."""
    armature = bpy.data.armatures.new(name + "Data")
    rig = bpy.data.objects.new(name, armature)
    bpy.context.scene.collection.objects.link(rig)
    previous = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    for bone_name, parent, head, tail, connected in bones:
        edit_bone = armature.edit_bones.new(bone_name)
        edit_bone.head = head
        edit_bone.tail = tail
        if parent is not None:
            edit_bone.parent = armature.edit_bones[parent]
            edit_bone.use_connect = connected
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.context.view_layer.objects.active = previous
    bpy.context.view_layer.update()
    return rig


def _chain():
    return _armature("WritingChain", [
        ("base", None, (0, 0, 0), (0, 0, 1), False),
        ("middle", "base", (0, 0, 1), (0, 0, 2), True),
        ("loose", "middle", (0, 0.5, 2), (0, 0.5, 3), False),
        ('odd"name', None, (1, 0, 0), (1, 0, 1), False),
    ])


def _remove(rig):
    action = rig.animation_data.action if rig.animation_data else None
    armature = rig.data
    bpy.data.objects.remove(rig, do_unlink=True)
    bpy.data.armatures.remove(armature)
    if action is not None:
        bpy.data.actions.remove(action)


def test_snapshot_and_restore_give_back_every_channel_exactly():
    """pose_writing.snapshot()/restore() after a write that changed every kind"""
    rig = _chain()
    try:
        writing = _writing()
        loose = rig.pose.bones["loose"]
        loose.rotation_mode = "XYZ"
        loose.rotation_euler = (0.1, 3.5, -0.2)
        loose.location = (0.01, 0.02, 0.03)
        rig.pose.bones["base"].rotation_quaternion = Quaternion((0.0, 0.0, 1.0), 2.0)
        saved = writing.snapshot(rig)
        writing.write(loose, head=Vector((0.3, 0.6, 2.2)),
                      orientation=Quaternion((1.0, 0.0, 0.0), 0.7), scale={"y": 0.4})
        writing.write(rig.pose.bones["base"], orientation=Quaternion())
        assert writing.channels(loose) != saved["loose"]
        writing.restore(rig, saved)
        assert writing.snapshot(rig) == saved
    finally:
        _remove(rig)


def test_parents_come_first_and_the_rest_keep_their_order():
    """pose_writing.parents_first()"""
    rig = _chain()
    try:
        ordered = _writing().parents_first(rig, ["loose", 'odd"name', "middle", "base"])
        assert ordered == ['odd"name', "base", "middle", "loose"]
    finally:
        _remove(rig)


def test_a_write_reaches_its_target_and_touches_nothing_it_was_not_asked_to():
    """pose_writing.write() and achieved() on a child whose parent was rotated first"""
    rig = _chain()
    try:
        writing = _writing()
        frame = _frame_class()(rig)
        base, loose = rig.pose.bones["base"], rig.pose.bones["loose"]
        writing.write(base, orientation=Quaternion((1.0, 0.0, 0.0), math.radians(30)))
        rotation_before = writing.channels(loose)["rotation_quaternion"]
        target = Vector((0.2, 0.4, 1.8))
        writing.write(loose, head=target)
        assert (loose.head - target).length < 1e-5
        assert writing.channels(loose)["rotation_quaternion"] == rotation_before, \
            "a move must not nudge the rotation"
        assert writing.achieved(frame, loose, head=target) == (True, None)
        arrived, deviation = writing.achieved(frame, loose, head=target + Vector((0, 0, 0.1)))
        assert arrived is False
        assert abs(deviation["distance"] - 0.1) < 1e-4
    finally:
        _remove(rig)


def test_locks_are_read_as_rigify_reads_them():
    """pose_writing.locks() and lock_violations()"""
    rig = _chain()
    try:
        writing = _writing()
        middle, loose = rig.pose.bones["middle"], rig.pose.bones["loose"]
        assert writing.locks(middle)["location"] == [True, True, True], \
            "a connected bone's head is its parent's tail"
        loose.lock_rotation = (True, False, False)
        assert loose.lock_rotations_4d, "Blender's default, and every generated control's"
        assert writing.locks(loose)["rotation"] == [False, True, False, False]
        loose.lock_rotations_4d = False
        assert writing.locks(loose)["rotation"] == [False] * 4, \
            "a quaternion bone without 4D locks is locked only as a whole"
        loose.lock_rotation = (True, True, True)
        before = writing.channels(loose)
        writing.write(loose, orientation=Quaternion((0.0, 1.0, 0.0), 0.3))
        assert writing.lock_violations(loose, before) == ["rotation"]
        loose.rotation_mode = "ZXY"
        loose.lock_rotation = (True, False, True)
        loose.rotation_euler = (0.0, 0.0, 0.0)
        before = writing.channels(loose)
        loose.rotation_euler[1] = 0.5
        assert writing.lock_violations(loose, before) == [], "Y is not locked"
        loose.rotation_euler[0] = 0.5
        assert writing.lock_violations(loose, before) == ["rotation"]
    finally:
        _remove(rig)


def test_drivers_and_keyframes_are_found_by_data_path():
    """pose_writing.driven_kinds() and animated_kinds(), a quoted bone name included"""
    rig = _chain()
    try:
        writing = _writing()
        assert writing.driven_kinds(rig) == {}
        assert writing.animated_kinds(rig) == {}
        rig.pose.bones["base"].driver_add("location", 0)
        rig.pose.bones['odd"name'].keyframe_insert("rotation_quaternion")
        rig.pose.bones["loose"].keyframe_insert("scale")
        assert writing.driven_kinds(rig) == {"base": {"location"}}
        assert writing.animated_kinds(rig) == {'odd"name': {"rotation"}, "loose": {"scale"}}
    finally:
        _remove(rig)


def test_a_restore_entry_recreates_the_bones_own_channels():
    """pose_writing.restore_entry() written back through write(), parents first"""
    rig = _chain()
    try:
        writing = _writing()
        frame = _frame_class()(rig)
        rig.location = (2.0, -1.0, 0.5)
        rig.rotation_euler = (0.0, 0.0, math.radians(70))
        bpy.context.view_layer.update()
        frame = _frame_class()(rig)
        base, loose = rig.pose.bones["base"], rig.pose.bones["loose"]
        base.rotation_quaternion = Quaternion((0.3, 0.2, 1.0), 0.8)
        loose.location = (0.05, -0.1, 0.02)
        loose.rotation_quaternion = Quaternion((1.0, 0.4, 0.0), 1.1)
        loose.scale = (1.0, 0.6, 1.0)
        bpy.context.view_layer.update()
        posed = writing.snapshot(rig)
        entries = [writing.restore_entry(frame, rig.pose.bones[name])
                   for name in ("base", "middle", "loose")]
        assert entries[1] is None, "a bone at rest needs no entry"
        assert set(entries[2]) == {"bone", "move_to", "rotate_to", "scale_to"}
        assert entries[2]["scale_to"] == {"y": 0.6}
        for pose_bone in rig.pose.bones:
            writing.to_rest(pose_bone)
        bpy.context.view_layer.update()
        for entry in (entries[0], entries[2]):
            pose_bone = rig.pose.bones[entry["bone"]]
            head = frame.to_armature_point(entry["move_to"]) if "move_to" in entry else None
            orientation = (frame.to_armature_rotation(entry["rotate_to"])
                           @ pose_bone.bone.matrix_local.to_quaternion()
                           if "rotate_to" in entry else None)
            writing.write(pose_bone, head, orientation, entry.get("scale_to"))
        restored = writing.snapshot(rig)
        for name, channels in posed.items():
            for channel, values in channels.items():
                theirs = restored[name][channel]
                if channel == "rotation_quaternion" and sum(
                        a * b for a, b in zip(values, theirs)) < 0:
                    theirs = tuple(-value for value in theirs)
                assert all(abs(a - b) < 1e-5 for a, b in zip(values, theirs)), (name, channel)
    finally:
        _remove(rig)


def test_the_frames_inverse_conversions_invert_the_readings():
    """Frame.to_armature_point/_vector/_direction/_rotation on a moved, turned, scaled rig"""
    rig = _chain()
    try:
        rig.location = (1.0, 2.0, -0.5)
        rig.rotation_euler = (0.2, 0.0, math.radians(135))
        rig.scale = (1.5, 1.5, 1.5)
        bpy.context.view_layer.update()
        frame = _frame_class()(rig)
        point = {"forward": 0.3, "left": -0.2, "up": 1.1}
        back = frame.armature_point(frame.to_armature_point(point))
        assert all(abs(back[key] - point[key]) < 1e-3 for key in point)
        offset = frame.to_armature_vector({"up": 1.0})
        world = frame.armature_world(offset) - frame.armature_world(Vector())
        assert abs(world.length - 1.0) < 1e-6, "an offset is metres, whatever the rig's scale"
        direction = frame.armature_direction(frame.to_armature_direction({"left": 2.0}))
        assert direction == {"forward": 0.0, "left": 1.0, "up": 0.0}
        rotation = {"axis": {"forward": 0.6, "left": 0.0, "up": 0.8}, "degrees": 40.0}
        assert frame.rotation(frame.to_armature_rotation(rotation)) == rotation
        assert frame.to_armature_rotation({"axis": None, "degrees": 0.0}) == Quaternion()
    finally:
        _remove(rig)


def test_who_is_in_charge_on_a_generated_rig():
    """pose_writing.charge_refusal() on a generated human_toes rig"""
    services = services_or_skip()
    with Character() as character:
        rig = rigged_character(services, character, "generated:human_toes")
        classify = bridge_module("shared.pose_controls").classify
        root = bridge_module("mpfb_resolution").resolve().module.__name__
        classification = classify(root, rig, "rigify_generated.human_toes")
        refusal = _writing().charge_refusal
        assert refusal(classification, {"left_arm": "ik"}, "hand_ik.L") is None
        reason, _message, instead = refusal(classification, {"left_arm": "ik"},
                                            "upper_arm_fk.L")
        assert reason == "chain_not_in_charge"
        assert instead == {"tool": "mpfb_set_pose_switches", "switches": [
            {"body_part": "left_arm", "switch": "IK_FK", "value": 1.0}]}
        assert refusal(classification, {"left_arm": "fk"}, "hand_ik.L")[2]["switches"][0][
            "value"] == 0.0
        assert refusal(classification, {"left_arm": "blend"}, "upper_arm_fk.L") is None
        reason, _message, instead = refusal(classification, {}, "DEF-upper_arm.L.001")
        assert (reason, instead) == ("not_a_control", {"bone": "upper_arm_fk.L"})
        assert refusal(classification, {}, "MCH-upper_arm_ik_swing.L")[2] is None
