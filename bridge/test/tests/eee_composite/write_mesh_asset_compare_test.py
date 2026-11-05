"""
One mesh written by ``write_mesh_asset`` and by MPFB's own operator: the differences are the listed ones.

**The fidelity claim of** [FR 050](../../../../feature-requests/done/050-writing-mesh-assets/README.md)
**is that an asset written here loads as the panel's does**, and this holds it to that by running the
panel. The two MHCLOs are compared line by line, the names aside, and the two assets are equipped on
one character and compared vertex by vertex. So a departure that was not listed fails here, and so
does an MPFB change to what a write produces that this command did not follow.
"""

import os

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character as _Character
from .._fixtures import material_data_roots
from .._fixtures import mpfb_root
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip

GROUP = "helper-tights"

# What a write may differ in from the panel's, by the MHCLO's key. The uuid is generated here and
# left empty there, and an OBJ's name and an asset's name follow the file name.
_DEPARTURES = ("uuid", "name", "obj_file")


def _extracted(services, basemesh):
    before = set(blender_object.name for blender_object in bpy.data.objects)
    services["ObjectService"].extract_vertex_group_to_new_object(basemesh, GROUP)
    mesh = next(blender_object for blender_object in bpy.data.objects
                if blender_object.name not in before)
    return mesh


def _comparable(path):
    """An MHCLO's lines, without the ones allowed to differ."""
    with open(path, "r", encoding="utf8") as handle:
        lines = handle.read().splitlines()
    return [line for line in lines
            if not line.split(" ", 1)[0] in _DEPARTURES]


@pytest.fixture(name="both")
def _both(tmp_path):
    """One mesh, written by the operator and then by the command, into two asset directories."""
    services = _services_or_skip()
    root = tmp_path / "data"
    panel_file = root / "clothes" / "by_panel" / "by_panel.mhclo"
    panel_file.parent.mkdir(parents=True)
    with _Character() as character:
        body = character.basemesh
        mesh = _extracted(services, body)
        with material_data_roots(services, str(root)):
            general = bridge_module("shared.mpfb_surface").general_object_properties(services)
            general.set_value("object_type", "Clothes", entity_reference=mesh)
            clothes = bridge_module("shared.mpfb_surface").make_clothes_properties(mpfb_root())
            clothes.set_value("name", "by_panel", entity_reference=mesh)
            clothes.set_value("author", "Somebody", entity_reference=mesh)
            clothes.set_value("description", "One mesh.", entity_reference=mesh)
            clothes.set_value("license", "CC-BY", entity_reference=mesh)

            bpy.ops.object.select_all(action="DESELECT")
            mesh.select_set(True)
            body.select_set(True)
            bpy.context.view_layer.objects.active = mesh
            assert "FINISHED" in bpy.ops.mpfb.write_makeclothes_clothes(filepath=str(panel_file))

            answer = _fixture_result("write_mesh_asset", dict(
                name=mesh.name, basemesh=body.name, asset_name="by_tool"))
            assert answer["written"] is True, answer["message"]
            yield (character, mesh, str(panel_file), answer)


def test_the_two_mhclos_differ_only_in_what_is_listed(both):
    _character, _mesh, panel_file, answer = both
    ours = _comparable(answer["path"])
    theirs = _comparable(panel_file)
    assert len(ours) == len(theirs)
    assert ours == theirs


def test_the_generated_uuid_is_the_one_listed_difference_the_panel_lacks(both):
    _character, _mesh, panel_file, answer = both
    with open(panel_file, encoding="utf8") as handle:
        assert "uuid " not in handle.read()
    with open(answer["path"], encoding="utf8") as handle:
        assert "uuid {:s}\n".format(answer["uuid"]) in handle.read()


def test_the_two_objs_hold_the_same_geometry(both):
    _character, _mesh, panel_file, answer = both

    def rows(path):
        with open(path, encoding="utf8") as handle:
            return [line for line in handle if line[:2] in ("v ", "f ", "vt")]

    assert rows(os.path.splitext(answer["path"])[0] + ".obj") == rows(
        os.path.splitext(panel_file)[0] + ".obj")


def test_the_two_assets_load_identically_on_a_second_character(both):
    _character, _mesh, panel_file, answer = both
    with _Character() as second:
        added = [
            _fixture_result("add_asset", dict(
                name=second.basemesh.name, object_type="Clothes", path=path, subdiv_levels=0))
            for path in (panel_file, answer["path"])]
        assert all(entry["added"] for entry in added), added
        ours = bpy.data.objects[added[1]["asset_object_name"]]
        theirs = bpy.data.objects[added[0]["asset_object_name"]]
        assert len(ours.data.vertices) == len(theirs.data.vertices)
        for mine, other in zip(ours.data.vertices, theirs.data.vertices):
            assert (mine.co - other.co).length < 1e-5
        assert len(ours.data.polygons) == len(theirs.data.polygons)
