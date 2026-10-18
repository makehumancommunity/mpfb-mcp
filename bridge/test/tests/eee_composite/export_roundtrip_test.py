"""
FR 039 across both commands: a copy made for export, written in each format, read back into Blender.

The claim is about the pair, which is why this is ``eee_composite/``: what
``create_export_copy`` produces is what ``export_character`` writes, and what is
written reads back as the same character - the same meshes, the same bones, the
same shape keys on each mesh. The copy carries everything the round trip can
lose: a rig, a garment, MPFB's masks baked, visemes loaded and interpolated.

**Read back into the scene and removed again**, everything the importer made,
however the test ends. Not into a scratch scene: Blender's FBX importer builds
the pose through the view layer's depsgraph, and an armature imported into a
scene no window shows has no pose bones yet, so it fails with ``KeyError: 'root'``.

**What this cannot establish** is that Unity, Unreal or Godot accept the file. It
proves the file is well-formed enough for Blender's own importers to rebuild the
character; another application is FR 039's live check's to try, and the command
docstring says so beside the preset tables.

Four counts differ on purpose and are asserted as differences. MPFB's
``subdiv_modifiers`` acts on the basemesh, so a garment keeps its Subdivision
beside the visemes interpolated onto it, and FBX - which applies modifiers -
drops that garment's shape keys; ``readiness`` names the garment. And USD
names a blend shape once per skeleton, so a viseme interpolated onto the
garment comes back from a ``.usdz`` with a digit appended (``aa_02`` becomes
``aa_022``) - the same keys, renamed. ``generic`` FBX
keeps Blender's ``add_leaf_bones`` default, which appends one bone per chain;
the presets turn it off, so the ``unreal`` FBX has exactly the copy's bones.
And glTF stores a vertex per UV seam corner, so its vertex counts are not the
copy's; its shape keys and bones are.
"""

import os

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character as _Character
from .._fixtures import material_data_roots
from .._fixtures import result as _result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import write_loadable_mhclo
from .._fixtures import write_target


@pytest.fixture(name="exports")
def _exports(tmp_path_factory):
    module = bridge_module("export_directory")
    directory = tmp_path_factory.mktemp("exports")
    module.set_command_line(str(directory))
    try:
        yield directory
    finally:
        module.set_command_line(None)


def _counts(objects):
    """Per kind: armatures' bone counts, and each mesh's shape key names, sorted.

    ``None`` in ``objects`` stands for a mesh with no shape keys, for a count
    in which one mesh's keys are expected to be gone.
    """
    bones = sorted(len(o.data.bones) for o in objects if o is not None and o.type == "ARMATURE")
    keys = sorted(
        () if o is None or o.data.shape_keys is None else
        tuple(sorted(k.name for k in o.data.shape_keys.key_blocks if k != o.data.shape_keys.reference_key))
        for o in objects if o is None or o.type == "MESH")
    return dict(bones=bones, shape_keys=keys)


def _read_back(path, chosen_format):
    """Import ``path``, return the counts, and remove everything imported again."""
    before = set(bpy.data.objects)
    try:
        if chosen_format == "fbx":
            bpy.ops.import_scene.fbx(filepath=path)
        elif chosen_format == "gltf":
            bpy.ops.import_scene.gltf(filepath=path)
        else:
            bpy.ops.wm.usd_import(filepath=path)
        imported = [o for o in bpy.data.objects if o not in before]
        # The glTF importer adds a sphere to draw bones with; it is not the character.
        return _counts([o for o in imported if not o.name.startswith("Icosphere")])
    finally:
        for o in [o for o in bpy.data.objects if o not in before]:
            bpy.data.objects.remove(o, do_unlink=True)


def test_a_copy_reads_back_the_same_in_every_format(exports, tmp_path):
    services = _services_or_skip()
    root = str(tmp_path)
    for name in ("sil_00", "aa_02", "p_b_m_21"):
        write_target(os.path.join(root, "targets", "visemes", name + ".target"))
    write_loadable_mhclo(os.path.join(root, "clothes", "fixture_shirt", "fixture_shirt.mhclo"))
    with _Character() as character:
        basemesh = character.basemesh
        with material_data_roots(services, root):
            services["HumanService"].add_builtin_rig(basemesh, "default", import_weights=True)
            added = _result("add_asset", {"name": basemesh.name, "object_type": "Clothes",
                                          "fragment": "fixture_shirt/fixture_shirt.mhclo"})
            assert added["added"] is True, added["message"]
            copy = _result("create_export_copy", {
                "name": basemesh.name, "mask_modifiers": "BAKE", "subdiv_modifiers": "REMOVE",
                "load_microsoft_visemes": True, "interpolate": True})
        try:
            assert copy["created"] is True, copy["message"]
            copied = [bpy.data.objects[entry["name"]] for entry in copy["copied_objects"]]
            expected = _counts(copied)
            assert ("aa_02", "p_b_m_21", "sil_00") in expected["shape_keys"]

            # MPFB's subdiv_modifiers acts on the basemesh only, so the garment
            # keeps its Subdivision beside the visemes interpolated onto it -
            # which FBX, applying the modifier, drops. Measured, and reported.
            shirt = next(o for o in copied if o.name.startswith("Human.fixture_shirt"))
            assert [m.type for m in shirt.modifiers if m.type == "SUBSURF"] == ["SUBSURF"]
            without_shirt_keys = _counts([o for o in copied if o != shirt] + [None])
            for chosen_format, engine in (("fbx", "generic"), ("fbx", "unreal"),
                                          ("gltf", "generic"), ("usd", "generic")):
                exported = _result("export_character", {
                    "name": copy["copy_root_name"], "export_name": "trip_" + chosen_format + engine,
                    "format": chosen_format, "target_engine": engine})
                assert exported["exported"] is True, exported["message"]
                assert exported["readiness"]["meshes_with_modifiers_beside_shape_keys"] == [shirt.name]
                read = _read_back(exported["path"], chosen_format)
                wanted = without_shirt_keys if chosen_format == "fbx" else expected
                if chosen_format == "usd":
                    # USD names a blend shape once per skeleton, so the second
                    # mesh carrying one comes back with a digit appended.
                    assert [len(keys) for keys in read["shape_keys"]] == \
                        [len(keys) for keys in wanted["shape_keys"]]
                    assert ("aa_02", "p_b_m_21", "sil_00") in read["shape_keys"]
                    assert ("aa_022", "p_b_m_212", "sil_002") in read["shape_keys"]
                else:
                    assert read["shape_keys"] == wanted["shape_keys"], (chosen_format, engine)
                if (chosen_format, engine) == ("fbx", "generic"):
                    assert read["bones"][0] > expected["bones"][0], "leaf bones are added"
                else:
                    assert read["bones"] == expected["bones"], (chosen_format, engine)
        finally:
            collection = bpy.data.collections.get("export copy")
            if collection is not None:
                bpy.data.collections.remove(collection)
