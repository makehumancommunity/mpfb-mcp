"""
``create_export_copy`` against a real MPFB: the original untouched, and what each option does to the copy.

**The original is read before and after every call** (:func:`_state`): every
object in its family, with each one's modifiers and what they point at, its
shape keys and their values, its materials, vertex count, vertex groups and
parent - plus the scene's selection and active object. FR 039's requirement 4 is
that none of it changes, and this is where that is held.

The packs are this suite's own, written into a redirected user data root and
built **after** the character - ``create_human()`` reads the base mesh out of
``mpfb_data``, which :func:`only_these_data_roots` points away. The viseme
fixture is deliberately partial (three of the 22 Microsoft visemes), so one test
covers both the load and ``could_not_load``.

**Two of FR 039's findings are reproduced here as fixtures**, built the shape MPFB
builds them: a garment that is the child of its own sub-rig, which is a
grandchild of the rig, and an ``Armature PV`` modifier beside ``Armature`` -
MPFB's ``create_character_copy()`` copies neither correctly, and
``copy_repairs`` is what says this command did. The Rigify test makes the same
point on the rig MPFB generates: posing the original must not move the copy.
"""

import os
import sys

import bpy
import pytest

from .._fixtures import Character as _Character
from .._fixtures import expression_library
from .._fixtures import linked_plain_object
from .._fixtures import material_character
from .._fixtures import material_data_roots
from .._fixtures import only_these_data_roots
from .._fixtures import result as _fixture_result
from .._fixtures import rigged_character
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import typed_child
from .._fixtures import write_loadable_mhclo
from .._fixtures import write_mhmat
from .._fixtures import write_png
from .._fixtures import write_target


def _result(params=None):
    return _fixture_result("create_export_copy", params)


@pytest.fixture(autouse=True)
def _no_export_collection_left_behind():
    """The 'export copy' collection the command creates, removed again if a test made it."""
    existed = "export copy" in bpy.data.collections
    yield
    collection = bpy.data.collections.get("export copy")
    if collection is not None and not existed:
        bpy.data.collections.remove(collection)


def _family(root):
    family = [root]
    index = 0
    while index < len(family):
        family.extend(o for o in bpy.data.objects if o.parent == family[index])
        index += 1
    return family


def _object_state(blender_object):
    keys = blender_object.data.shape_keys if blender_object.type == "MESH" else None
    return dict(
        parent=None if blender_object.parent is None else blender_object.parent.name,
        modifiers=[(m.name, m.type, getattr(getattr(m, "object", None), "name", None))
                   for m in blender_object.modifiers],
        shape_keys=None if keys is None else [(k.name, round(k.value, 6)) for k in keys.key_blocks],
        materials=[m.name if m else None for m in getattr(blender_object.data, "materials", [])],
        vertices=len(blender_object.data.vertices) if blender_object.type == "MESH" else None,
        vertex_groups=[g.name for g in getattr(blender_object, "vertex_groups", [])],
        custom=sorted(blender_object.keys()),
    )


def _state(basemesh):
    root = basemesh.parent if basemesh.parent is not None else basemesh
    active = bpy.context.view_layer.objects.active
    return dict(
        objects={o.name: _object_state(o) for o in _family(root)},
        selected=sorted(o.name for o in bpy.context.view_layer.objects if o.select_get()),
        active=None if active is None else active.name,
        node_groups=sorted(group.name for group in bpy.data.node_groups),
    )


def _material_state(names):
    """Each original mesh's materials, their node counts and the groups they use."""
    state = {}
    for name in names:
        materials = []
        for material in bpy.data.objects[name].data.materials:
            nodes = material.node_tree.nodes if material and material.node_tree else []
            materials.append((material.name, len(nodes), sorted(
                node.node_tree.name for node in nodes
                if node.type == "GROUP" and node.node_tree is not None)))
        state[name] = materials
    return state


def _new_objects(before):
    return [o for o in bpy.data.objects if o.name not in before]


def _subrig_and_garment(services, rig, basemesh):
    """A garment parented to its own sub-rig, which is parented to the rig, as MPFB builds one.

    And an ``Armature PV`` modifier on the body beside ``Armature``, which is
    what ``RigService.ensure_armature_modifier()`` adds for preserve-volume
    weights. The sub-rig is a bare armature carrying MPFB's ``Subrig`` type.
    """
    general = sys.modules[services["ObjectService"].__module__].GeneralObjectProperties
    subrig = bpy.data.objects.new("Fixture.garment.rig", bpy.data.armatures.new("Fixture.garment.rig"))
    bpy.context.scene.collection.objects.link(subrig)
    subrig.parent = rig
    general.set_value("object_type", "Subrig", entity_reference=subrig)
    garment = typed_child(services, subrig, "Fixture.garment", "Clothes")
    garment.modifiers.new("Armature", "ARMATURE").object = rig
    garment.modifiers.new("Armature Subrig", "ARMATURE").object = subrig
    basemesh.modifiers.new("Armature PV", "ARMATURE").object = rig
    return subrig, garment


def test_the_default_copy_leaves_the_original_exactly_as_it_was():
    services = _services_or_skip()
    with _Character() as character:
        basemesh = character.basemesh
        rig = services["HumanService"].add_builtin_rig(basemesh, "default", import_weights=True)
        bystander = linked_plain_object("Fixture.bystander")
        bpy.context.view_layer.objects.active = bystander
        for o in bpy.context.view_layer.objects:
            o.select_set(o in (bystander, rig))
        before_names = set(o.name for o in bpy.data.objects)
        before = _state(basemesh)

        result = _result({"name": basemesh.name})

        assert result["created"] is True and result["performed"] is True, result["message"]
        assert _state(basemesh) == before, "the original, the selection or a node group changed"
        copies = _new_objects(before_names)
        assert set(o.name for o in copies) == set(entry["name"] for entry in result["copied_objects"])
        assert result["copy_root_name"] == rig.name + "_export_copy"
        assert result["copy_basemesh_name"] == basemesh.name + "_export_copy"
        assert result["collection_name"] == "export copy"
        assert all(o.name in bpy.data.collections["export copy"].objects for o in copies)
        assert not any(o.select_get() for o in copies), "the copy is left deselected"
        copy = bpy.data.objects[result["copy_basemesh_name"]]
        # bake_shapekeys and delete_helpers are on by default.
        assert copy.data.shape_keys is None
        assert result["shape_keys_baked"], "the macro keys should be named as baked"
        assert result["helper_vertices_left"] == 0
        assert result["basemesh_vertices_after"] < result["basemesh_vertices_before"]
        assert result["face_baked_into_mesh"] == [] and result["expressions_baked_into_mesh"] == []
        assert result["copy_repairs"] == dict(objects_copied=[], references_retargeted=[])
        assert result["options_used"]["mask_modifiers"] == "KEEP"
        for key in ("faceunits01_installed", "visemes01_installed", "visemes02_installed"):
            assert isinstance(result[key], bool)


def test_masks_baked_removed_and_kept():
    services = _services_or_skip()
    with _Character() as character:
        basemesh = character.basemesh
        delete_group = basemesh.vertex_groups.new(name="fixture-delete")
        delete_group.add(list(range(200)), 1.0, "REPLACE")
        mask = basemesh.modifiers.new("Delete.fixture", "MASK")
        mask.vertex_group = "fixture-delete"
        mask.invert_vertex_group = True
        before = _state(basemesh)

        baked = _result({"name": basemesh.name, "mask_modifiers": "BAKE", "suffix": "_baked"})
        removed = _result({"name": basemesh.name, "mask_modifiers": "REMOVE", "suffix": "_removed"})
        kept = _result({"name": basemesh.name, "suffix": "_kept"})

        assert _state(basemesh)["objects"] == before["objects"]
        baked_copy = bpy.data.objects[baked["copy_basemesh_name"]]
        removed_copy = bpy.data.objects[removed["copy_basemesh_name"]]
        kept_copy = bpy.data.objects[kept["copy_basemesh_name"]]
        assert not [m for m in baked_copy.modifiers if m.type == "MASK"]
        assert set(baked["modifiers_baked"][baked_copy.name]) >= {"Hide helpers", "Delete.fixture"}
        assert not [m for m in removed_copy.modifiers if m.type == "MASK"]
        assert removed["modifiers_removed"] == {removed_copy.name: ["Delete.fixture"]}
        assert [m.name for m in kept_copy.modifiers if m.type == "MASK"] == ["Delete.fixture"]
        # The delete group's 200 vertices are gone only where the mask was baked.
        assert len(baked_copy.data.vertices) == len(removed_copy.data.vertices) - 200
        assert len(kept_copy.data.vertices) == len(removed_copy.data.vertices)


def test_subdivision_baked_and_removed():
    services = _services_or_skip()
    with _Character() as character:
        basemesh = character.basemesh
        modifier = basemesh.modifiers.new("Subdivision", "SUBSURF")
        modifier.levels = 0
        modifier.render_levels = 1

        baked = _result({"name": basemesh.name, "subdiv_modifiers": "BAKE", "suffix": "_baked"})
        removed = _result({"name": basemesh.name, "subdiv_modifiers": "REMOVE", "suffix": "_removed"})

        assert [m.name for m in basemesh.modifiers if m.type == "SUBSURF"] == ["Subdivision"]
        baked_copy = bpy.data.objects[baked["copy_basemesh_name"]]
        removed_copy = bpy.data.objects[removed["copy_basemesh_name"]]
        assert not [m for m in baked_copy.modifiers if m.type == "SUBSURF"]
        # Baked at the render level, as MPFB's service does: more vertices.
        assert len(baked_copy.data.vertices) > len(removed_copy.data.vertices)
        assert removed["modifiers_removed"] == {removed_copy.name: ["Subdivision"]}


def test_keeping_the_shape_keys_and_the_basemeshs_own_collection():
    services = _services_or_skip()
    with _Character() as character:
        basemesh = character.basemesh
        result = _result({"name": basemesh.name, "bake_shapekeys": False,
                          "in_export_collection": False, "suffix": "_keep"})
        copy = bpy.data.objects[result["copy_basemesh_name"]]
        assert result["shape_keys_baked"] is None
        assert result["face_baked_into_mesh"] is None
        assert copy.data.shape_keys is not None
        assert [k.name for k in copy.data.shape_keys.key_blocks] == \
            [k.name for k in basemesh.data.shape_keys.key_blocks]
        assert result["collection_name"] == basemesh.users_collection[0].name
        assert copy.name in basemesh.users_collection[0].objects


def test_mpfbs_copy_is_repaired_where_it_falls_short():
    services = _services_or_skip()
    with _Character() as character:
        basemesh = character.basemesh
        rig = services["HumanService"].add_builtin_rig(basemesh, "default", import_weights=True)
        subrig, garment = _subrig_and_garment(services, rig, basemesh)
        before = _state(basemesh)

        result = _result({"name": garment.name})

        assert result["created"] is True, result["message"]
        assert _state(basemesh)["objects"] == before["objects"]
        copied = {entry["source_name"]: entry["name"] for entry in result["copied_objects"]}
        assert garment.name in copied, "the sub-rig's garment, a grandchild, must be copied"
        assert result["copy_repairs"]["objects_copied"] == [
            dict(name=copied[garment.name], source_name=garment.name)]
        garment_copy = bpy.data.objects[copied[garment.name]]
        assert garment_copy.parent.name == copied[subrig.name]
        assert {m.name: m.object.name for m in garment_copy.modifiers} == {
            "Armature": copied[rig.name], "Armature Subrig": copied[subrig.name]}
        body_copy = bpy.data.objects[copied[basemesh.name]]
        assert {m.name: m.object.name for m in body_copy.modifiers if m.type == "ARMATURE"} == {
            "Armature": copied[rig.name], "Armature PV": copied[rig.name]}
        retargeted = {(r["object_name"], r["name"]) for r in result["copy_repairs"]["references_retargeted"]}
        assert (body_copy.name, "Armature PV") in retargeted
        assert (garment_copy.name, "Armature Subrig") in retargeted


def test_a_generated_rigify_copy_moves_with_its_own_rig():
    services = _services_or_skip()
    with _Character() as character:
        generated = rigged_character(services, character, "generated:human_toes")
        basemesh = character.basemesh
        result = _result({"name": basemesh.name, "bake_shapekeys": False, "delete_helpers": False})
        assert result["created"] is True, result["message"]
        copy_rig = bpy.data.objects[result["copy_root_name"]]
        copy_body = bpy.data.objects[result["copy_basemesh_name"]]
        assert all(m.object == copy_rig for m in copy_body.modifiers if m.type == "ARMATURE")
        # The object's drivers Blender remaps itself; the armature data's
        # B-bone drivers it does not, and those are the repair.
        for owner in (copy_rig, copy_rig.data):
            for fcurve in owner.animation_data.drivers:
                for variable in fcurve.driver.variables:
                    for target in variable.targets:
                        assert target.id != generated, (owner.name, fcurve.data_path)
        data_drivers = [r for r in result["copy_repairs"]["references_retargeted"]
                        if r["kind"] == "driver" and r["name"] == copy_rig.data.name]
        assert data_drivers, "the armature data's drivers should be named as retargeted"

        def evaluated_vertex():
            bpy.context.view_layer.update()
            depsgraph = bpy.context.evaluated_depsgraph_get()
            mesh = copy_body.evaluated_get(depsgraph).to_mesh()
            try:
                return tuple(round(c, 5) for c in mesh.vertices[5000].co)
            finally:
                copy_body.evaluated_get(depsgraph).to_mesh_clear()

        resting = evaluated_vertex()
        torso = generated.pose.bones["torso"]
        torso.location = (0.0, 0.3, 0.0)
        try:
            assert evaluated_vertex() == resting, "posing the original moved the copy"
        finally:
            torso.location = (0.0, 0.0, 0.0)
            bpy.context.view_layer.update()


def test_the_visemes_load_after_the_bake_and_say_what_could_not(tmp_path):
    services = _services_or_skip()
    root = str(tmp_path)
    for name in ("sil_00", "aa_02", "p_b_m_21"):
        write_target(os.path.join(root, "targets", "visemes", name + ".target"))
    with _Character() as character:
        basemesh = character.basemesh
        with only_these_data_roots(services, user_data=root):
            result = _result({"name": basemesh.name, "load_microsoft_visemes": True})
        assert result["visemes01_installed"] is True
        loaded = result["shape_keys_loaded"]["microsoft_visemes"]
        assert loaded["loaded_count"] == 3
        assert "sil_00" not in loaded["could_not_load"]
        assert len(loaded["could_not_load"]) == 19
        copy = bpy.data.objects[result["copy_basemesh_name"]]
        names = [k.name for k in copy.data.shape_keys.key_blocks]
        # Loaded after the bake: the visemes are there and the macro keys are not.
        assert {"sil_00", "aa_02", "p_b_m_21"} <= set(names)
        assert not [name for name in names if name.startswith("$md")]
        assert "could not be loaded" in result["message"]


def test_a_pack_that_is_absent_refuses_before_anything_is_copied(tmp_path):
    services = _services_or_skip()
    with _Character() as character:
        basemesh = character.basemesh
        before = set(o.name for o in bpy.data.objects)
        with only_these_data_roots(services, user_data=str(tmp_path)):
            meta = _result({"name": basemesh.name, "load_meta_visemes": True})
            microsoft = _result({"name": basemesh.name, "load_microsoft_visemes": True})
        assert meta["blocked_by"] == "visemes02_not_installed" and meta["visemes02_installed"] is False
        assert microsoft["blocked_by"] == "visemes01_not_installed"
        assert meta["performed"] is False and meta["created"] is False
        assert set(o.name for o in bpy.data.objects) == before


def test_remove_basemesh_needs_a_proxy_and_works_with_one(tmp_path):
    services = _services_or_skip()
    with _Character() as character:
        basemesh = character.basemesh
        before = set(o.name for o in bpy.data.objects)
        refused = _result({"name": basemesh.name, "remove_basemesh": True})
        assert refused["blocked_by"] == "no_bodyproxy"
        assert set(o.name for o in bpy.data.objects) == before

        root = str(tmp_path)
        write_loadable_mhclo(os.path.join(root, "proxymeshes", "fixture_proxy", "fixture_proxy.mhclo"),
                             material=False)
        with material_data_roots(services, root):
            added = _fixture_result("add_asset", {
                "name": basemesh.name, "fragment": "fixture_proxy/fixture_proxy.mhclo",
                "object_type": "Proxymeshes"})
            assert added["added"] is True, added["message"]
            original = _state(basemesh)["objects"]
            result = _result({"name": basemesh.name, "remove_basemesh": True})
        assert result["created"] is True, result["message"]
        assert result["basemesh_removed"] is True
        assert result["copy_basemesh_name"] is None
        assert basemesh.name + "_export_copy" not in bpy.data.objects
        assert result["copy_bodyproxy_name"] in bpy.data.objects
        assert _state(basemesh)["objects"] == original


def test_a_face_that_is_baked_is_named(tmp_path):
    services = _services_or_skip()
    with _Character() as character:
        basemesh = character.basemesh
        with expression_library(services, tmp_path):
            neutral = _result({"name": basemesh.name, "suffix": "_neutral"})
            _fixture_result("apply_expressions", {
                "name": basemesh.name, "expressions": [{"fragment": "jaw.json", "weight": 1.0}]})
            _fixture_result("set_face_units", {
                "name": basemesh.name, "face_units": [{"face_unit": "mouthSmileLeft", "value": 0.5}]})
            faced = _result({"name": basemesh.name, "suffix": "_faced"})
        assert neutral["face_baked_into_mesh"] == [] and neutral["expressions_baked_into_mesh"] == []
        units = {u["face_unit"]: u for u in faced["face_baked_into_mesh"]}
        assert set(units) == {"jawOpen", "mouthSmileLeft"}
        assert units["jawOpen"]["from_stack"] == pytest.approx(0.7, abs=1e-4)
        assert units["mouthSmileLeft"]["from_stack"] == 0.0
        assert units["mouthSmileLeft"]["value"] == pytest.approx(0.5, abs=1e-4)
        assert [row["fragment"] for row in faced["expressions_baked_into_mesh"]] == ["jaw.json"]
        assert "baked into the mesh" in faced["message"]
        # The original keeps its face.
        assert basemesh.data.shape_keys.key_blocks["!ex-mouthSmileLeft"].value == pytest.approx(0.5)


def test_the_game_engine_swap_leaves_the_originals_materials_alone(tmp_path):
    services = _services_or_skip()
    root = str(tmp_path)
    with _Character() as character:
        basemesh = character.basemesh
        with material_data_roots(services, root):
            names = material_character(services, character, root)
            texture = write_png(os.path.join(root, "textures", "fixture_skin.png"))
            skin = write_mhmat(os.path.join(root, "skins", "fixture_skin", "fixture_skin.mhmat"),
                               lines=("diffuseTexture " + texture,))
            services["HumanService"].set_character_skin(
                skin, basemesh, skin_type="MAKESKIN", material_instances=False)
            shared = _result({"name": basemesh.name, "suffix": "_shared"})
            materials_before = _material_state(names.values())
            groups_before = sorted(group.name for group in bpy.data.node_groups)
            swapped = _result({"name": basemesh.name, "material_type": "GAMEENGINE",
                               "suffix": "_game"})
        assert shared["materials_shared_with_original"], "an unswapped copy shares materials"
        assert swapped["created"] is True, swapped["message"]
        assert _material_state(names.values()) == materials_before
        assert all(name in [g.name for g in bpy.data.node_groups] for name in groups_before)
        assert swapped["materials_not_swapped"] == []
        assert swapped["materials_shared_with_original"] == []
        swapped_names = {entry["object_name"] for entry in swapped["materials_swapped"]}
        assert swapped_names == {copy["name"] for copy in swapped["copied_objects"]
                                 if bpy.data.objects[copy["name"]].type == "MESH"}
        for entry in swapped["materials_swapped"]:
            assert entry["material_identified_as"] == "gameengine", entry
        eyes = next(e for e in swapped["materials_swapped"] if e["object_name"].startswith(names["eyes"]))
        assert eyes["material_identified_as_before"] == "procedural_eyes"


def test_refusals_change_nothing():
    services = _services_or_skip()
    with _Character() as character:
        basemesh = character.basemesh
        before = set(o.name for o in bpy.data.objects)
        missing = _result({"name": "No such object"})
        assert missing["found"] is False and missing["blocked_by"] == "subject_not_found"
        assert missing["created"] is False and missing["performed"] is False
        bpy.context.view_layer.objects.active = basemesh
        bpy.ops.object.mode_set(mode="EDIT")
        try:
            edit = _result({"name": basemesh.name})
        finally:
            bpy.ops.object.mode_set(mode="OBJECT")
        assert edit["blocked_by"] == "not_object_mode"
        assert set(o.name for o in bpy.data.objects) == before


def test_baking_a_proxy_that_interpolate_gives_shape_keys_is_refused(tmp_path):
    """The combination MPFB's own sequence fails on part way, refused before copying."""
    services = _services_or_skip()
    root = str(tmp_path)
    write_target(os.path.join(root, "targets", "visemes", "sil_00.target"))
    write_loadable_mhclo(os.path.join(root, "proxymeshes", "fixture_proxy", "fixture_proxy.mhclo"),
                         material=False)
    with _Character() as character:
        basemesh = character.basemesh
        with material_data_roots(services, root):
            added = _fixture_result("add_asset", {
                "name": basemesh.name, "fragment": "fixture_proxy/fixture_proxy.mhclo",
                "object_type": "Proxymeshes"})
            proxy = bpy.data.objects[added["asset_object_name"]]
            # MPFB gives an equipped asset a Subdivision of its own.
            subdivisions = [m for m in proxy.modifiers if m.type == "SUBSURF"]
            assert [m.name for m in subdivisions] == ["Subdivision"]
            subdivisions[0].render_levels = 1
            before = set(o.name for o in bpy.data.objects)
            refused = _result({"name": basemesh.name, "subdiv_modifiers": "BAKE",
                               "load_microsoft_visemes": True, "interpolate": True})
            # Without interpolate the proxy has no shape keys, and MPFB bakes it.
            allowed = _result({"name": basemesh.name, "subdiv_modifiers": "BAKE",
                               "load_microsoft_visemes": True})
        assert refused["blocked_by"] == "proxy_cannot_be_baked", refused["message"]
        assert refused["proxy_modifiers_blocking"] == ["Subdivision"]
        assert refused["performed"] is False
        assert allowed["created"] is True, allowed["message"]
        assert set(o.name for o in bpy.data.objects) - before == \
            set(entry["name"] for entry in allowed["copied_objects"])
