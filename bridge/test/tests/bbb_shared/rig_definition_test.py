"""
``shared/rig_definition.py`` called directly: the table both ways, and the fit.

Four claims, each one a way the authoring tools could go wrong without any of their own
answers looking odd:

- **A shipped rig read as a table and resolved again gives MPFB's strategies back.** That is
  what makes a read-back a write, checked here at the translation rather than through a build.
- **Positions are MPFB's, with the shape keys evaluated, and not ``mesh.vertices[].co``.** On a
  modelled body the two differ, and the fit agrees with the bones MPFB's own adding function
  builds.
- **The in-memory fit creates nothing**: no object, no mesh, no shape key, and the active shape
  key is where it was.
- **A version-110 header needs no upgrade**, which is the claim that lets ``create_rig`` build
  from a dictionary instead of writing a temporary file for ``from_json_file_and_basemesh()``.
"""

import os

import bpy
from mathutils import Vector

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import services_or_skip
from .._fixtures import small_rig_table

_MODELLED = {"gender": 1.0, "age": 0.9, "muscle": 0.5, "weight": 0.9, "proportions": 0.5,
             "height": 0.1, "cupsize": 0.5, "firmness": 0.5,
             "race": {"asian": 1.0 / 3.0, "caucasian": 1.0 / 3.0, "african": 1.0 / 3.0}}


def _module():
    return bridge_module("shared.rig_definition")


def _default_rig_file(services):
    path, _weights, _from = _module().catalogue_files(services, "default_no_toes")
    assert path is not None and os.path.isfile(path), "MPFB ships default_no_toes"
    return path


def _empty_fit(services, basemesh):
    return _module().fit_definition(services, basemesh, {"bones": {}, "version": 110})


def test_a_shipped_rig_read_and_resolved_gives_its_strategies_back():
    services = services_or_skip()
    module = _module()
    with Character() as character:
        basemesh = character.basemesh
        fit = module.fit_file(services, basemesh, _default_rig_file(services))
        space = module.Space(basemesh, basemesh)

        def locate(_name, _key, info):
            return fit.get_best_location_from_strategy(info)

        rows, _features = module.read_bones(fit.rig_definition, space, locate)
        definition, _notes, errors = module.resolve_table(
            _empty_fit(services, basemesh), space, rows, len(basemesh.data.vertices),
            module.max_snap_metres(services))

        assert errors == []
        for name, info in fit.rig_definition.items():
            for key in ("head", "tail"):
                assert module.end_signature(definition[name][key])[:2] == \
                    module.end_signature(info[key])[:2], "{:s}.{:s}".format(name, key)
            assert definition[name]["parent"] == (info.get("parent") or "")


def test_positions_are_the_shape_keyed_body_and_agree_with_mpfbs_own_rig():
    services = services_or_skip()
    module = _module()
    with Character(macro_detail_dict=_MODELLED) as character:
        basemesh = character.basemesh
        fit = _empty_fit(services, basemesh)
        group = basemesh.vertex_groups["joint-l-elbow"]
        members = [vertex.co for vertex in basemesh.data.vertices
                   if any(element.group == group.index for element in vertex.groups)]
        from_co = sum(members, Vector()) / len(members)
        fitted = Vector(fit.position_info["cubes"]["joint-l-elbow"])
        assert (fitted - from_co).length > 0.005, \
            "on a modelled body the shape keys move a joint, which reading co would miss"

        armature = services["HumanService"].add_builtin_rig(basemesh, "default_no_toes",
                                                            import_weights=False)
        built = armature.data.bones["lowerarm01.L"].head_local
        assert (Vector(built) - fitted).length < 1e-4, \
            "the fit is where MPFB's own adding function puts the bone"


def test_the_in_memory_fit_creates_nothing_and_leaves_the_active_key():
    services = services_or_skip()
    module = _module()
    with Character() as character:
        basemesh = character.basemesh
        basemesh.active_shape_key_index = 2
        counts = (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures),
                  len(basemesh.data.shape_keys.key_blocks))
        module.fit_file(services, basemesh, _default_rig_file(services))
        _empty_fit(services, basemesh)
        assert (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures),
                len(basemesh.data.shape_keys.key_blocks)) == counts
        assert basemesh.active_shape_key_index == 2


def test_a_version_110_header_needs_no_upgrade():
    services = services_or_skip()
    module = _module()
    with Character() as character:
        basemesh = character.basemesh
        fit = _empty_fit(services, basemesh)
        space = module.Space(basemesh, basemesh)
        definition, _notes, errors = module.resolve_table(
            fit, space, small_rig_table(), len(basemesh.data.vertices),
            module.max_snap_metres(services))
        assert errors == []
        header = module.header_for(services, basemesh, definition)
        rig = module.fit_definition(services, basemesh, header)
        before = repr(rig.rig_header)
        # pylint: disable=protected-access
        assert rig._upgrade_definition() is False, "a version-110 header must not be upgraded"
        assert repr(rig.rig_header) == before
        assert header["version"] == module.current_version(services)


def test_the_space_is_one_conversion_each_way_on_a_turned_body():
    services_or_skip()
    module = _module()
    with Character() as character:
        basemesh = character.basemesh
        basemesh.rotation_euler = (0.0, 0.0, 1.2)
        basemesh.location = (1.0, -2.0, 0.0)
        bpy.context.view_layer.update()
        space = module.Space(basemesh, basemesh)
        local = Vector((0.17, -0.02, 1.32))
        back = space.to_local(space.point(local))
        assert (back - local).length < 0.001, "rounded to the millimetre, and no further off"
        # A turned body's frame turns with it, so a point keeps its frame coordinates.
        assert space.point(local) == module.Space(basemesh, basemesh).point(local)


def test_an_unknown_joint_and_a_missing_vertex_are_errors_and_nothing_else():
    services = services_or_skip()
    module = _module()
    with Character() as character:
        basemesh = character.basemesh
        table = small_rig_table()
        table[0]["head"] = {"joint": "joint-that-no-body-has"}
        table[1]["tail"] = {"vertex": 10 ** 6}
        _definition, _notes, errors = module.resolve_table(
            _empty_fit(services, basemesh), module.Space(basemesh, basemesh), table,
            len(basemesh.data.vertices), module.max_snap_metres(services))
        assert sorted(error["error"] for error in errors) == ["unknown_joint",
                                                              "vertex_out_of_range"]
        assert [error["where"] for error in errors] == ["bones[0].head", "bones[1].tail"]


def test_a_position_snaps_as_mpfbs_own_matcher_would():
    services = services_or_skip()
    module = _module()
    with Character() as character:
        basemesh = character.basemesh
        fit = _empty_fit(services, basemesh)
        space = module.Space(basemesh, basemesh)
        elbow = space.point(fit.position_info["cubes"]["joint-l-elbow"])
        near = dict(elbow, up=elbow["up"] + 0.004)
        table = small_rig_table()
        table[3]["tail"] = {"position": near}
        table[4]["tail"] = {"position": near, "snap": False}
        definition, notes, errors = module.resolve_table(
            fit, space, table, len(basemesh.data.vertices), module.max_snap_metres(services))
        assert errors == []
        assert definition["t_arm.L"]["tail"]["cube_name"] == "joint-l-elbow"
        assert notes["t_arm.L"]["snapped_to"]["tail"]["joint"] == "joint-l-elbow"
        assert definition["t_arm.R"]["tail"]["strategy"] == "DEFAULT"
        assert notes["t_arm.R"]["fixed_ends"] == ["tail"]
