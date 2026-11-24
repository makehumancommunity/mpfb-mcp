"""
One reading of a weighting: what ``weight_rig`` reports, ``check_rig_weights`` reads and
``store_rig`` names agree.

FR 061 put the three behind ``shared/rig_weights.py`` so that they cannot disagree, and this is the
claim end to end: a character weighted and then checked gets the same counts twice, and the store's
``unweighted_bones`` is the check's, on a weighting with a bone left deliberately unweighted.
"""

import bpy

from .._fixtures import Character
from .._fixtures import result
from .._fixtures import rig_library
from .._fixtures import services_or_skip
from .._fixtures import small_rig_table


def test_weighting_checking_and_storing_count_alike(tmp_path):
    services = services_or_skip()
    table = small_rig_table("ag_")
    with rig_library(services, str(tmp_path)), Character() as character:
        name = character.basemesh.name
        built = result("create_rig", {"name": name, "bones": table})
        weighted = result("weight_rig", {"name": name, "method": "automatic",
                                         "max_influences": 3})
        checked = result("check_rig_weights", {"name": name})
        assert weighted["unweighted"]["after_fill"]["body"] == \
            checked["coverage"]["unweighted"]["body"] == 0
        assert sum(weighted["unweighted"]["after_fill"].values()) == \
            checked["coverage"]["unweighted"]["total"]
        assert weighted["clean"]["histogram_after"] == checked["influences"]["histogram"]
        assert {row["name"]: row["vertex_count"] for row in weighted["bones"]} == \
            {row["name"]: row["vertex_count"] for row in checked["bones"]["rows"]}

        basemesh = bpy.data.objects[name]
        basemesh.vertex_groups.remove(basemesh.vertex_groups["ag_head"])
        checked = result("check_rig_weights", {"name": name, "sections": ["coverage"]})
        stored = result("store_rig", {"name": name, "rig_name": "agreement", "dry_run": True})
        assert checked["coverage"]["unweighted_bones"] == stored["unweighted_bones"] == \
            ["ag_head"]
        assert bpy.data.objects[built["rig_object_name"]].data.bones["ag_head"].use_deform
