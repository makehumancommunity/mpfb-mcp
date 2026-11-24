"""
Every mutating command against a character whose collection is excluded from the view layer.

**The scan FR 054 asked for, kept as a table.** No command may answer ``command_failed`` here, and that
is the assertion that fails first if one starts borrowing a selection. Each row is what was measured of
that command and why it is where it is:

- ``WRAPPED`` commands raised, refused for no reason a caller could act on, or answered from a pose an
  excluded rig never evaluated. They include the collection, say so, and leave it excluded.
- ``UNWRAPPED`` commands already work, or refuse in terms of what stopped them, as
  ``generate_delete_group``'s ``mesh_not_evaluated`` does. "Commands that work today are not wrapped".

**The table is held to the directory.** ``ddd_mutating/`` has one module per mutating command, by that
layer's own rule, so a command added there with no row here fails :func:`test_every_mutating_command_has_a_row`.
That is what makes this a scan rather than a list of the ones somebody remembered.

Every row also asserts what is the whole reason this is acceptable: the collection ends excluded, a
bystander stays selected and active, and the exclusion's parent is not disturbed.
"""

import os

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import dispatch
from .._fixtures import redirected_locations
from .._fixtures import rigged_character
from .._fixtures import services_or_skip
from .._fixtures import small_rig_table
from .._fixtures import write_expression
from .._fixtures import write_loadable_mhclo
from .._fixtures import write_mhmat
from .._fixtures import write_target

_COLLECTION = "BridgeTestCast"
_AXIS = {"forward": 1.0, "left": 0.0, "up": 0.0}

# Commands that take no character to begin with, so that no exclusion can stand in their way.
NO_SUBJECT = ("create_human", "create_human_from_preset")


def _row(params, rig="default_no_toes", prepare=None, performed=True, blocked_by=None):
    """What to send, on which rig, after which ``prepare``, and what the answer should be."""
    return dict(params=params, rig=rig, prepare=prepare, performed=performed,
                blocked_by=blocked_by)


def _posed(scene):
    return ("set_pose_bones", {"name": scene["body"], "bones": [
        {"bone": "head", "rotate_by": {"axis": _AXIS, "degrees": 5.0}}]})


def _asymmetric(scene):
    return ("set_targets", {"name": scene["body"], "modifiers": [
        {"section": "arms", "category": "lowerarm-scale-depth-decr-incr", "side": "left",
         "value": 0.4}]})


def _authored_rig(scene):
    return ("create_rig", {"name": scene["body"], "bones": small_rig_table()})


def _with_a_face(scene):
    return ("set_face_units", {"name": scene["body"], "refit": False, "face_units": [
        {"face_unit": "jawOpen", "value": 0.2}]})


WRAPPED = {
    "refit_human": _row(lambda s: {"name": s["body"]}),
    "add_asset": _row(lambda s: {"name": s["body"], "path": s["second_mhclo"],
                                 "object_type": "Clothes"}),
    "add_rig": _row(lambda s: {"name": s["body"], "identifier": "default"}, rig=None),
    "generate_rigify_rig": _row(lambda s: {"name": s["body"]}, rig="rigify.human_toes"),
    "set_macro_details": _row(lambda s: {"name": s["body"], "refit": True, "changes": [
        {"argument": "muscle", "property": "muscle", "value": 0.6}]}),
    "set_targets": _row(lambda s: {"name": s["body"], "refit": True, "modifiers": [
        {"section": "nose", "category": "nose-scale-depth-decr-incr", "value": 0.1}]}),
    "symmetrize_targets": _row(lambda s: {"name": s["body"], "direction": "left_to_right",
                                          "refit": True}, prepare=_asymmetric),
    "set_face_units": _row(lambda s: {"name": s["body"], "face_units": [
        {"face_unit": "jawOpen", "value": 0.4}]}),
    "apply_expressions": _row(lambda s: {"name": s["body"], "expressions": [
        {"fragment": "scan.json", "weight": 0.5}]}),
    "set_skin": _row(lambda s: {"name": s["body"], "path": s["mhmat"]}),
    "set_asset_material": _row(lambda s: {"name": s["garment"], "path": s["mhmat"]}),
    "export_character": _row(lambda s: {"name": s["body"], "export_name": "excluded_scan"}),
    "set_pose_bones": _row(lambda s: _posed(s)[1]),
    "set_pose_switches": _row(lambda s: {"name": s["body"], "switches": [
        {"body_part": "left_arm", "switch": "IK_FK", "value": 1.0}]},
                              rig="generated:human_toes"),
    "set_rigify_hand_shape": _row(lambda s: {"name": s["body"], "hands": [
        {"body_part": "left_hand", "shape": "fist"}]}, rig="generated:human_toes"),
    "reset_pose": _row(lambda s: {"name": s["body"]}, prepare=_posed),
    # The three that build, weight and read an authored rig run operators on it (armature_add,
    # parent_set, edit mode), which an excluded armature fails. The garment is on before the rig,
    # which is also what create_rig's assets_not_rigged reports.
    "create_rig": _row(lambda s: {"name": s["body"], "bones": small_rig_table()}, rig=None),
    "weight_rig": _row(lambda s: {"name": s["body"], "method": "automatic"}, rig=None,
                       prepare=_authored_rig),
    "store_rig": _row(lambda s: {"name": s["body"], "rig_name": "excluded_scan",
                                 "dry_run": True}, rig=None, prepare=_authored_rig,
                      performed=False),
}

UNWRAPPED = {
    "remove_asset": _row(lambda s: {"name": s["garment"]}),
    "place_character": _row(lambda s: {"name": s["body"], "position": {"x": 0.5}}),
    "save_preset": _row(lambda s: {"name": s["body"], "preset_name": "excluded_scan"}),
    "save_expression": _row(lambda s: {"name": s["body"], "expression_name": "excluded_scan"},
                            prepare=_with_a_face),
    "create_export_copy": _row(lambda s: {"name": s["body"]}),
    "set_makeskin_material": _row(lambda s: {"name": s["garment"],
                                             "material_name": "excluded_scan", "replace": True}),
    # Nothing named, so nothing written: what this row asks is only that it does not raise. The
    # command's docstring has why it borrows nothing that an exclusion could stop.
    "set_material_settings": _row(lambda s: {"name": s["body"]}, performed=False),
    # A dry run writes nothing, and reads no selection on the way to saying what it would.
    "store_makeskin_material": _row(lambda s: {"name": s["garment"], "store_as": "alternate",
                                               "material_name": "excluded_scan", "dry_run": True},
                                    performed=False),
    # Both say what stopped them, which a caller can act on, so neither is wrapped.
    "write_mesh_asset": _row(lambda s: {"name": s["garment"], "asset_name": "excluded_scan",
                                        "destination": "export_directory", "basemesh": s["body"]},
                             performed=False, blocked_by="mesh_not_visible"),
    "generate_delete_group": _row(lambda s: {"name": s["garment"], "dry_run": True},
                                  performed=False, blocked_by="mesh_not_evaluated"),
}


def test_every_mutating_command_has_a_row():
    directory = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ddd_mutating")
    commands = set(name[:-len("_test.py")] for name in os.listdir(directory)
                   if name.endswith("_test.py"))
    assert commands == set(WRAPPED) | set(UNWRAPPED) | set(NO_SUBJECT)


def _scene(services, character, rig, root):
    """A character dressed and alone in a collection, with a selected bystander outside it."""
    garment = write_loadable_mhclo(os.path.join(root, "clothes", "scan", "scan.mhclo"))
    second = write_loadable_mhclo(os.path.join(root, "clothes", "second", "second.mhclo"))
    mhmat = write_mhmat(os.path.join(root, "skins", "scan", "scan.mhmat"))
    if rig is not None:
        rigged_character(services, character, rig)
    equipped = dispatch("add_asset", {"name": character.basemesh.name, "path": garment,
                                      "object_type": "Clothes"})
    assert equipped["status"] == "ok" and equipped["result"]["added"], equipped
    return dict(body=character.basemesh.name, garment=equipped["result"]["asset_object_name"],
                second_mhclo=second, mhmat=mhmat)


@pytest.fixture(name="excluded")
def _excluded(tmp_path):
    """Yields a function that builds it, since the rig differs by row."""
    services = services_or_skip()
    export_directory = bridge_module("export_directory")
    collection = bpy.data.collections.new(_COLLECTION)
    bpy.context.scene.collection.children.link(collection)
    bystander = bpy.data.objects.new("BridgeTestBystander", None)
    bpy.context.scene.collection.objects.link(bystander)
    layer = bpy.context.view_layer.layer_collection.children[_COLLECTION]
    root = str(tmp_path)
    export_directory.set_command_line(root)
    made = []

    def build(rig, prepare=None):
        character = Character()
        character.__enter__()
        made.append(character)
        scene = _scene(services, character, rig, root)
        if prepare is not None:
            command, params = prepare(scene)
            prepared = dispatch(command, params)
            assert prepared["status"] == "ok" and prepared["result"]["performed"], prepared
        family = bridge_module("shared.view_layer").family_of(services, character.basemesh)
        for blender_object in family:
            for owner in list(blender_object.users_collection):
                owner.objects.unlink(blender_object)
            collection.objects.link(blender_object)
        for blender_object in bpy.context.view_layer.objects:
            blender_object.select_set(False)
        bystander.select_set(True)
        bpy.context.view_layer.objects.active = bystander
        layer.exclude = True
        bpy.context.view_layer.update()
        return scene

    face_service = services["FaceService"]
    for unit in ("cheekPuff", "jawOpen"):
        write_target(os.path.join(root, "targets", "faceunits", unit + ".target"))
    write_expression(services, os.path.join(root, "expressions", "scan.json"), {"jawOpen": 0.3})
    # save_preset writes to the config directory, and it must not be the developer's.
    with redirected_locations(services, user_data=root, user_config=os.path.join(root, "config")):
        os.makedirs(os.path.join(root, "config"), exist_ok=True)
        face_service.is_faceunits01_installed(force_recheck=True)
        try:
            yield dict(build=build, layer=layer, bystander=bystander, collection=collection)
        finally:
            face_service.is_faceunits01_installed(force_recheck=True)
    export_directory.set_command_line(None)
    bpy.context.view_layer.layer_collection.children[_COLLECTION].exclude = False
    for character in made:
        character.__exit__(None, None, None)
    bpy.data.objects.remove(bystander)
    bpy.data.collections.remove(collection)


def _assert_left_as_found(excluded):
    bpy.context.view_layer.update()
    assert excluded["layer"].exclude, "the collection must end excluded"
    assert excluded["bystander"].select_get(), "a bystander's selection is the user's"
    assert bpy.context.view_layer.objects.active == excluded["bystander"]


def _assert_as_measured(row, answer):
    assert answer["blocked_by"] == row["blocked_by"], answer["message"]
    assert answer["performed"] is row["performed"], answer["message"]


@pytest.mark.parametrize("command", sorted(WRAPPED))
def test_a_wrapped_command_includes_the_collection_and_says_so(command, excluded):
    row = WRAPPED[command]
    scene = excluded["build"](row["rig"], row["prepare"])
    envelope = dispatch(command, row["params"](scene))
    assert envelope["status"] == "ok", envelope
    answer = envelope["result"]
    _assert_as_measured(row, answer)
    assert answer["temporarily_included"] == [_COLLECTION], answer["message"]
    assert _COLLECTION in answer["message"]
    _assert_left_as_found(excluded)


@pytest.mark.parametrize("command", sorted(UNWRAPPED))
def test_an_unwrapped_command_never_fails(command, excluded):
    row = UNWRAPPED[command]
    scene = excluded["build"](row["rig"], row["prepare"])
    envelope = dispatch(command, row["params"](scene))
    assert envelope["status"] == "ok", envelope
    _assert_as_measured(row, envelope["result"])
    assert "temporarily_included" not in envelope["result"]
    _assert_left_as_found(excluded)


def test_a_refit_on_a_generated_rig_keeps_the_pose_while_excluded(excluded):
    excluded["build"]("generated:human_toes")
    name = excluded["collection"].objects[0].name
    posed = dispatch("set_pose_bones", {"name": name, "bones": [
        {"bone": "head", "rotate_by": {"axis": _AXIS, "degrees": 12.0}}]})
    assert posed["status"] == "ok", posed
    assert posed["result"]["performed"] is True
    assert posed["result"]["changes"][0]["achieved"] is True, \
        "an excluded rig is never evaluated, so this is what inclusion is for"

    answer = dispatch("refit_human", {"name": name})["result"]
    assert answer["pose_after_refit"] == "kept"
    assert answer["temporarily_included"] == [_COLLECTION]
    _assert_left_as_found(excluded)


def test_a_new_garment_goes_out_with_the_character(excluded):
    scene = excluded["build"]("default_no_toes")
    answer = dispatch("add_asset", {"name": scene["body"], "path": scene["second_mhclo"],
                                    "object_type": "Clothes"})["result"]
    assert answer["added"] is True, answer["message"]
    created = bpy.data.objects[answer["asset_object_name"]]
    assert {"object": created.name, "collection": _COLLECTION} \
        in answer["objects_moved_to_collection"]
    assert [owner.name for owner in created.users_collection] == [_COLLECTION]
    bpy.context.view_layer.update()
    assert created.name not in bpy.context.view_layer.objects


def test_a_refused_call_writes_no_face_units(excluded):
    """In another scene there is nothing to include, and the keys were written before the refit."""
    scene = excluded["build"]("default_no_toes")
    body = bpy.data.objects[scene["body"]]
    excluded["layer"].exclude = False
    bpy.context.scene.collection.children.unlink(excluded["collection"])
    other = bpy.data.scenes.new("BridgeTestOtherScene")
    other.collection.children.link(excluded["collection"])
    keys_before = list(body.data.shape_keys.key_blocks.keys())
    try:
        answer = dispatch("set_face_units", {"name": scene["body"], "face_units": [
            {"face_unit": "jawOpen", "value": 0.4}]})["result"]
        assert answer["blocked_by"] == "not_in_view_layer"
        assert answer["performed"] is False
        assert answer["refit_performed"] is False
        assert answer["pose_after_refit"] is None
        assert list(body.data.shape_keys.key_blocks.keys()) == keys_before
    finally:
        other.collection.children.unlink(excluded["collection"])
        bpy.data.scenes.remove(other)
        bpy.context.scene.collection.children.link(excluded["collection"])
        layer = bpy.context.view_layer.layer_collection.children[_COLLECTION]
        layer.exclude = True
        excluded["layer"] = layer


def _hidden(excluded):
    """The fixture's collection included again, and hidden in the viewport instead."""
    layer = bpy.context.view_layer.layer_collection.children[_COLLECTION]
    layer.exclude = False
    excluded["collection"].hide_viewport = True
    bpy.context.view_layer.update()
    return layer


def test_a_hidden_collection_refuses_rigify_rather_than_raising(excluded):
    """MPFB's refit raises "Could not generate: Target rig is not visible"."""
    scene = excluded["build"]("generated:human_toes")
    layer = _hidden(excluded)
    try:
        answer = dispatch("refit_human", {"name": scene["body"]})
        assert answer["status"] == "ok", answer
        assert answer["result"]["blocked_by"] == "not_in_view_layer"
        assert answer["result"]["not_in_view_layer"][0]["reason"] == "in_a_hidden_collection"
        assert _COLLECTION in answer["result"]["message"]
    finally:
        excluded["collection"].hide_viewport = False
        layer.exclude = True


def test_a_hidden_collection_refuses_generating_rather_than_raising(excluded):
    scene = excluded["build"]("rigify.human_toes")
    layer = _hidden(excluded)
    try:
        answer = dispatch("generate_rigify_rig", {"name": scene["body"]})
        assert answer["status"] == "ok", answer
        assert answer["result"]["blocked_by"] == "not_in_view_layer"
    finally:
        excluded["collection"].hide_viewport = False
        layer.exclude = True


@pytest.mark.parametrize("rig", ("default_no_toes", "rigify.human_toes"))
def test_a_hidden_collection_stops_no_other_refit(rig, excluded):
    """No more than what stops the work: FR 054's non-goal, as measured."""
    scene = excluded["build"](rig)
    layer = _hidden(excluded)
    try:
        answer = dispatch("refit_human", {"name": scene["body"]})
        assert answer["status"] == "ok", answer
        assert answer["result"]["blocked_by"] is None, answer["result"]["message"]
        assert answer["result"]["refit_performed"] is True
    finally:
        excluded["collection"].hide_viewport = False
        layer.exclude = True
