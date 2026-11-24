"""
The four rig authoring commands in order, then the rig on a different body.

Create, weight, store, then ``add_rig`` with ``custom.<name>`` on a character of another shape:
the rig is identified as itself, every vertex of the second body is weighted, the elbow moves
with the body, and ``get_rig_definition`` of the applied rig reads back the table it was built
from. This is FR 060's claim end to end, against a user data root of the test's own.
"""

import bpy
from mathutils import Vector

from .._fixtures import Character
from .._fixtures import result
from .._fixtures import rig_library
from .._fixtures import services_or_skip
from .._fixtures import small_rig_table

_OTHER_BODY = {"gender": 1.0, "age": 0.9, "muscle": 0.5, "weight": 0.9, "proportions": 0.5,
               "height": 0.1, "cupsize": 0.5, "firmness": 0.5,
               "race": {"asian": 1.0 / 3.0, "caucasian": 1.0 / 3.0, "african": 1.0 / 3.0}}


def _strategies(rows):
    return {row["name"]: {key: {kind: value for kind, value in row[key].items()
                                if kind != "position"} for key in ("head", "tail")}
            for row in rows}


def test_a_stored_rig_is_itself_on_another_body(tmp_path):
    services = services_or_skip()
    table = small_rig_table("rt_")
    with rig_library(services, str(tmp_path)), Character() as first, \
            Character(macro_detail_dict=_OTHER_BODY) as second:
        built = result("create_rig", {"name": first.basemesh.name, "bones": table})
        result("weight_rig", {"name": first.basemesh.name, "method": "automatic"})
        stored = result("store_rig", {"name": first.basemesh.name, "rig_name": "roundtrip"})
        assert stored["stored"] is True, stored["message"]

        added = result("add_rig", {"name": second.basemesh.name, "identifier": "custom.roundtrip"})
        assert added["added"] is True and added["weights_loaded"] is True
        armature = bpy.data.objects[added["rig_object_name"]]
        assert services["RigService"].identify_rig(armature) == "custom.roundtrip"

        read = result("get_rig_definition", {"name": second.basemesh.name})
        assert read["rig_identified_as"] == "custom.roundtrip"
        assert _strategies(read["bones"]) == _strategies(table)

        first_elbow = Vector(bpy.data.objects[built["rig_object_name"]].data.bones[
            "rt_arm.L"].tail_local)
        second_elbow = Vector(armature.data.bones["rt_arm.L"].tail_local)
        assert (first_elbow - second_elbow).length > 0.05, "the elbow follows the other body"

        deforming = {group.index for group in second.basemesh.vertex_groups
                     if group.name in armature.data.bones}
        unweighted = [vertex.index for vertex in second.basemesh.data.vertices
                      if not any(element.group in deforming and element.weight > 0
                                 for element in vertex.groups)]
        assert unweighted == []
