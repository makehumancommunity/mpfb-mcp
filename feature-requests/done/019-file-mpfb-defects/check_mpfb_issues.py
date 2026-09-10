# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR-6: the seven candidate MPFB defects, confirmed or refuted against the install.

FR 008 through FR 011 each ended by naming things that looked like MPFB bugs.
All seven were read from source and none was observed, which is a weak basis for
filing an issue against somebody's project - and, in one case, for a design
decision this package took. This script provokes each one.

The proxy item is the one that is not merely tidiness. FR 010's Architecture
section justifies which code path ``mpfb_add_asset`` follows *on those three
paths differing*, so if they do not differ, a documented decision has lost its
reason. The field-by-field measurement over three characters was made once, by
[FR 010](../010-mesh-assets/README.md); what this script adds is the two paths'
source-level relationship, which is what a filed issue would have to describe.

**It lives here rather than in ``verification/`` because it is not a check of
mpfb-mcp's tools at all** - it provokes defects in *MPFB*, on behalf of the
report [FR 019](README.md) filed, and that report cites it by path from the
mpfb2 repository. [FR 023](../023-verification-smoke-test/README.md) made
``verification/`` a smoke run that changes nothing outside the ``.blend``; this
script writes target files into MPFB's user ``custom`` directory, which is
exactly the kind of thing that no longer belongs there. It still uses
``verification/harness.py`` for the tools, the scratch scene and the report.

Every item below is destructive to a scratch character and to nothing else, and
each cleans up after itself. ``set_character_skin()``'s five-``if`` dispatch is
the exception worth naming: provoking it destroys the materials on the character
it is aimed at, which is the whole point of the report.

Run from the repository root::

    PYTHONPATH=. python3 feature-requests/done/019-file-mpfb-defects/check_mpfb_issues.py
"""

from __future__ import annotations

__all__ = ("run",)

import sys

from verification import harness
from verification.harness import Report, probe

# --------------------------------------------------------------------------
# The fixtures this script needs, carried with it.
#
# They used to live in verification/fixtures.py. FR 023 turned that directory
# into a smoke run that changes nothing outside the .blend, and these three do
# change something outside it: they write target files into MPFB's own user
# `custom` directory. They belong here, with the defects they provoke, because
# **one of the three prevents MPFB from loading if it is still on disk when
# Blender starts** - which is how that defect was found, and which makes this
# the single riskiest thing anything in this project does to a developer's
# install. install/remove are always used as a pair inside one run.
# --------------------------------------------------------------------------

# A gzipped custom target (the naming divergence), a name long enough that MPFB
# encodes it, and one whose name contains "basis". The long one is deliberately
# built out of substrings MPFB's encoding table knows ("female", "average",
# "muscle", "weight", "height", "young"): the >60 character rule only turns
# encoding *on*, and a long name containing none of those encodes to itself.
PROBE_TARGETS = (
    "mpfbmcp_probe_vwide.target.gz",
    "mpfbmcp_probe_a_very_long_female_average_muscle_weight_height_young_name.target",
    "mpfbmcp_probe_basis_containing_name.target",
)

# MPFB derives a Scene property identifier as "custom_" + the target's name, and
# Blender rejects one over 63 characters. So a user target name over 56
# characters breaks MPFB's registration - while the *encoding* only starts above
# 60. The two conditions cannot both be met by a file left on disk, which is the
# sharp form of the defect.
MAX_SAFE_TARGET_NAME_LENGTH = 63 - len("custom_")

# The one asset named by filename anywhere in this project. FR 023 removed the
# rest; this one stays because the defect it provokes is about an asset that has
# alternative materials beside it, and the script says so when it is missing.
ALTERNATIVE_MATERIAL_ASSET = "nurse_uniform_coat_clothsim/nurse_uniform_coat_clothsim.mhclo"


def _install_probe_targets() -> dict:
    """Write the three probe targets, and report which were newly created."""
    return probe("install_probe_targets", _INSTALL_CODE, names=list(PROBE_TARGETS))


_INSTALL_CODE = '''
import gzip, os, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
LocationService = services["LocationService"]

directory = str(LocationService.get_user_data("custom"))
if not os.path.isdir(directory):
    os.makedirs(directory)

# Two vertices on the belly, moved outwards. Vertex indices are hm08's and any
# valid index would do: nothing here checks where the target points.
body = "3000 0.100000 0.000000 0.000000\\n3001 0.100000 0.000000 0.000000\\n"

created = []
existed = []
for name in PARAMS["names"]:
    full_path = os.path.join(directory, name)
    if os.path.exists(full_path):
        existed.append(full_path)
        continue
    if name.endswith(".gz"):
        handle = gzip.open(full_path, "wt")
    else:
        handle = open(full_path, "w")
    handle.write(body)
    handle.close()
    created.append(full_path)

result = dict(directory=directory, created=created, existed=existed)
'''


def _remove_probe_targets() -> dict:
    """Take the three probe targets away again, leaving the install as it was."""
    return probe("remove_probe_targets", _REMOVE_CODE, names=list(PROBE_TARGETS))


_REMOVE_CODE = '''
import os, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
LocationService = services["LocationService"]

directory = str(LocationService.get_user_data("custom"))
removed = []
missing = []
for name in PARAMS["names"]:
    full_path = os.path.join(directory, name)
    if os.path.exists(full_path):
        os.remove(full_path)
        removed.append(full_path)
    else:
        missing.append(full_path)

result = dict(directory=directory, removed=removed, missing=missing)
'''


def _fresh_human(tools: dict, rename_to: str) -> str:
    """A scratch character with a name of its own, so two of them are told apart."""
    response = tools["mpfb_create_human"]()
    if response.get("status") != "ok":
        raise RuntimeError("could not create a character: {}".format(response))
    return harness.rename_object(response["result"]["object_name"], rename_to)


def _skin_fragment(tools: dict) -> str:
    """The first skin this install has, resolved rather than named."""
    listing = tools["mpfb_list_assets"](asset_subdir="skins", limit=1)["result"]
    if not listing["assets"]:
        raise RuntimeError("this install has no skin to apply")
    return listing["assets"][0]["fragment"]


ITEMS = (
    "a gzipped custom target is addressed under two different names",
    "identify_rig() cannot return None, so the Rigify operator's poll() is safe",
    "the three proxy code paths",
    "unload_mhclo_asset() deletes whatever object it is handed",
    "set_character_skin()'s five-if dispatch destroys materials on a typo",
    "alternative_materials_for_asset()'s exclude_default is never read",
    "alternative_materials_for_asset()'s cache has an invalidator after all",
    "a long-named user target prevents MPFB from registering at all",
)


def run() -> dict:
    tools = harness.tools()
    report = Report("FR-6 - the seven candidate mpfb2 defects")
    harness.ensure_scratch_scene()
    harness.cleanup_scratch_scene()
    before = harness.snapshot()
    _install_probe_targets()

    _check_gzip_naming(report)
    _check_identify_rig_poll(tools, report)
    _check_proxy_paths(report)
    _check_unload_anything(tools, report)
    _check_skin_typo(tools, report)
    _check_exclude_default(tools, report)
    _check_long_target_name_breaks_registration(report)

    _remove_probe_targets()
    harness.cleanup_scratch_scene()
    after = harness.snapshot()
    difference = harness.diff_snapshots(before, after)
    report.check("revert: every datablock collection identical afterwards",
                 difference["identical"] and not difference["is_dirty_after"], difference)
    return report.summary()


def _check_gzip_naming(report: Report) -> None:
    observed = probe("gzip_naming", _GZIP_NAMING_CODE,
                     filename=PROBE_TARGETS[0])
    report.check("a gzipped custom target is addressed under two different names",
                 observed["panel_name"] != observed["service_name"],
                 dict(file=PROBE_TARGETS[0],
                      name_modelsubpanels_builds=observed["panel_name"],
                      name_filename_to_shapekey_name_builds=observed["service_name"],
                      confirmed="the two names differ, so one file is two shape keys",
                      not_confirmed_here=("that both shape keys can exist at once - the panel "
                                          "property is built at module import time, so this "
                                          "needs a Blender started with the file in place")))


def _check_identify_rig_poll(tools: dict, report: Report) -> None:
    _fresh_human(tools, "PollCharacter")
    observed = probe("identify_rig_poll", _IDENTIFY_RIG_POLL_CODE, name="PollCharacter")
    # Refuted, and the refutation is the useful half: identify_rig() ends with a
    # `if guessed_rig is None:` block that assigns one of three strings, so the
    # None FR 009 read from the top of the function cannot reach the caller.
    report.check("identify_rig() cannot return None, so the Rigify operator's poll() is safe",
                 observed["identify_rig_returned"] is not None
                 and observed["operator_found"] and not observed["poll_raised"],
                 dict(observed,
                      refutes=("FR 009's candidate defect. identify_rig() falls through to "
                               "'unknown', 'rigify.unknown' or 'rigify_generated.unknown' "
                               "rather than returning None"),
                      but_note=("object_is_rigify_metarig() *does* raise AttributeError for "
                                "an armature object whose .pose is None - which is what a "
                                "hand-built bpy.data.objects.new() armature is until the "
                                "depsgraph has seen it. A different defect, found by "
                                "accident, and worth filing on its own")))
    harness.cleanup_scratch_scene()


def _check_proxy_paths(report: Report) -> None:
    observed = probe("proxy_paths", _PROXY_PATHS_CODE)
    report.check("the three proxy code paths",
                 observed["check_add_proxy_calls_add_mhclo_asset"]
                 and not observed["library_operator_calls_add_mhclo_asset"],
                 dict(observed,
                      note=("the *observable* comparison was made once, by FR 010 (see "
                            "feature-requests/done/010-mesh-assets/README.md): "
                            "add_mhclo_asset() alone differs from _check_add_proxy(), but "
                            "_check_add_proxy() and the library operator produced identical "
                            "state on every field compared - so this is duplicated "
                            "implementation rather than divergent behaviour")))


def _check_unload_anything(tools: dict, report: Report) -> None:
    _fresh_human(tools, "UnloadCharacter")
    tools["mpfb_add_rig"](name="UnloadCharacter", identifier="default")
    observed = probe("unload_anything", _UNLOAD_ANYTHING_CODE, name="UnloadCharacter")
    refusal = tools["mpfb_remove_asset"](name="UnloadCharacter")
    refusal_result = refusal.get("result") or dict()
    report.check("unload_mhclo_asset() deletes whatever object it is handed",
                 observed["cube_deleted"],
                 dict(handed=observed["handed"], cube_deleted=observed["cube_deleted"],
                      raised=observed["raised"],
                      mpfb_mcp_refuses_the_same_thing=dict(
                          removed=refusal_result.get("removed"),
                          blocked_by=refusal_result.get("blocked_by"))))
    harness.cleanup_scratch_scene()


def _check_skin_typo(tools: dict, report: Report) -> None:
    _fresh_human(tools, "TypoCharacter")
    skin = _skin_fragment(tools)
    tools["mpfb_set_skin"](name="TypoCharacter", fragment=skin, skin_type="MAKESKIN")
    observed = probe("skin_typo", _SKIN_TYPO_CODE, name="TypoCharacter",
                     fragment=skin, skin_type="MAKSKIN")

    refused = None
    try:
        tools["mpfb_set_skin"](name="TypoCharacter", fragment=skin, skin_type="MAKSKIN")
    except ValueError as error:
        refused = str(error)

    # Confirmed, and worse than FR 011 described: with material_instances off it
    # does not raise at all. The character is left with no materials and no
    # error, which is a silent destruction rather than a misleading traceback.
    report.check("set_character_skin()'s five-if dispatch destroys materials on a typo",
                 bool(observed["materials_before"]) and not observed["materials_after"],
                 dict(materials_before=observed["materials_before"],
                      materials_after=observed["materials_after"],
                      raised=observed["raised"], raised_from=observed["raised_from"],
                      raised_with_material_instances=observed["raised_with_instances"],
                      mpfb_mcp_refuses_before_the_call=bool(refused),
                      note=("FR 011 expected a ValueError from "
                            "create_and_assign_material_slots(). That happens only when "
                            "material_instances is on; with it off - which is the default "
                            "for three of the five types - the destruction is silent")))
    harness.cleanup_scratch_scene()


def _check_exclude_default(tools: dict, report: Report) -> None:
    observed = probe("exclude_default", _EXCLUDE_DEFAULT_CODE,
                     fragment=ALTERNATIVE_MATERIAL_ASSET)
    report.check("alternative_materials_for_asset()'s exclude_default is never read",
                 observed["with_exclude"] == observed["without_exclude"]
                 and observed["default_is_in_the_list"], observed)
    # Refuted. AssetService.invalidate_alternative_materials_cache() exists and
    # clears both caches. The *staleness* FR 011 documented is real - nothing
    # calls it automatically, and FR 011's own live check saw a new .mhmat
    # written between two calls go unnoticed - but "cannot be invalidated" is
    # wrong, and it means mpfb_list_asset_materials could grow the same
    # `refresh` argument the other catalogue tools have.
    report.check("alternative_materials_for_asset()'s cache has an invalidator after all",
                 observed["invalidator"] is not None, dict(
                     invalidator=observed["invalidator"],
                     cache_attribute=observed["cache_attribute"],
                     cleared_by_it=observed["cleared_by_invalidator"],
                     refutes="FR 011's 'uninvalidatable module-level cache'",
                     still_true=("nothing calls it, so a listing is stale until something "
                                 "does - confirmed behaviourally by FR 011's live check, and "
                                 "the subject of FR 018")))


def _check_long_target_name_breaks_registration(report: Report) -> None:
    """The one this session found by accident, and the worst of the set.

    ``ui/model/_modelsubpanels.py`` registers one Scene property per modeling
    category at *module import time*, deriving the identifier as ``"custom_" +
    name``. Blender rejects a property identifier over 63 characters with a
    ``ValueError``, and nothing catches it - it propagates out of MPFB's
    ``register()``, so the whole add-on fails to enable on the next start. One
    long-named ``.target`` file in a scanned user directory is enough.

    It is provoked here the safe way: the registration is attempted directly,
    with the name MPFB would build, and the property is removed again. Provoking
    it the *real* way means leaving the file on disk and restarting Blender,
    which is how this was found and is not something a check should do to
    somebody's install.
    """
    observed = probe("long_property_name", _LONG_PROPERTY_NAME_CODE,
                     name=PROBE_TARGETS[1].replace(".target", ""),
                     limit=MAX_SAFE_TARGET_NAME_LENGTH)
    report.check("a long-named user target prevents MPFB from registering at all",
                 observed["raised"] and not observed["registered"],
                 dict(observed,
                      how_it_was_found=("a probe target left on disk across a Blender restart; "
                                        "MPFB's register() raised and the add-on did not load"),
                      the_sharp_form=("encoding starts above 60 characters and registration "
                                      "breaks above 56, so an encoded user target cannot exist "
                                      "on disk at startup at all")))


_LONG_PROPERTY_NAME_CODE = '''
import bpy
from bpy.props import FloatProperty

# Exactly what _modelsubpanels.py builds: "custom_" plus the target's name with
# dots and dashes replaced by underscores.
identifier = "custom_" + PARAMS["name"].replace(".", "_").replace("-", "_")

raised = None
registered = False
try:
    setattr(bpy.types.Scene, identifier, FloatProperty(name=identifier, min=-1.0, max=1.0))
    registered = hasattr(bpy.types.Scene, identifier)
except Exception as exception:
    raised = type(exception).__name__ + ": " + str(exception)

if registered:
    delattr(bpy.types.Scene, identifier)

result = dict(identifier=identifier, identifier_length=len(identifier),
              blender_limit=63, safe_name_limit=PARAMS["limit"],
              raised=raised is not None, exception=raised, registered=registered)
'''


_GZIP_NAMING_CODE = '''
import os, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
TargetService = services["TargetService"]
LocationService = services["LocationService"]

path = os.path.join(str(LocationService.get_user_data("custom")), PARAMS["filename"])

# _modelsubpanels.py: os.path.basename(target).replace(".target", "") - a
# substring replace, which leaves the ".gz" behind.
panel_name = str(os.path.basename(path)).replace(".target", "")
service_name = str(TargetService.filename_to_shapekey_name(path))

result = dict(path=path, panel_name=panel_name, service_name=service_name,
              file_exists=os.path.isfile(path))
'''

_IDENTIFY_RIG_POLL_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
RigService = services["RigService"]
ObjectService = services["ObjectService"]

basemesh = bpy.data.objects.get(PARAMS["name"])

# An armature whose bones match nothing MPFB knows. identify_rig() starts from
# guessed_rig = None and only ever assigns on a match, so this is the object
# that makes it return None rather than the string "unknown".
#
# Built through the operator rather than through bpy.data, deliberately: an
# armature object created with bpy.data.objects.new() has `pose` set to None
# until the depsgraph has seen it, and MPFB's object_is_rigify_metarig() reads
# `.pose.bones` without checking - so the hand-built object crashes it before
# identify_rig() can return anything, which would be a different bug report
# about a different object than the one worth filing.
previous_active = bpy.context.view_layer.objects.active
bpy.ops.object.armature_add(enter_editmode=False, location=(0.0, 0.0, 0.0))
armature = bpy.context.active_object
armature.name = "mpfbmcp_strange"
armature_data = armature.data
armature_data.name = "mpfbmcp_strange"
for bone in armature_data.bones:
    bone.name = "mpfbmcp_bone_mpfb_has_never_heard_of"

identified = RigService.identify_rig(armature)

# MPFB_OT_GenerateRigifyRigOperator.poll() is what the Rigify sub-panel calls to
# decide whether to enable its button.
# Reached off its own module rather than off bpy.types: registration renames
# an operator class by its bl_idname, so `MPFB_OT_GenerateRigifyRigOperator`
# is not what bpy.types calls it. Walking Operator.__subclasses__() does not
# find it either - every MPFB operator subclasses MpfbOperator, not Operator.
operator_class = None
for module_name in list(sys.modules):
    if module_name.endswith("operators.generaterigifyrig"):
        operator_class = getattr(sys.modules[module_name],
                                 "MPFB_OT_GenerateRigifyRigOperator", None)

poll_raised = None
poll_answer = None
if operator_class is not None:
    bpy.context.view_layer.objects.active = armature
    try:
        poll_answer = bool(operator_class.poll(bpy.context))
    except Exception as exception:
        poll_raised = type(exception).__name__ + ": " + str(exception)

bpy.context.view_layer.objects.active = previous_active
bpy.data.objects.remove(armature, do_unlink=True)
if armature_data.name in bpy.data.armatures:
    bpy.data.armatures.remove(armature_data)

result = dict(identify_rig_returned=identified,
              operator_found=operator_class is not None,
              poll_answer=poll_answer,
              poll_raised=poll_raised is not None,
              poll_exception=poll_raised)
'''

_PROXY_PATHS_CODE = '''
import inspect, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
HumanService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["HumanService"]

check_add_proxy = inspect.getsource(HumanService._check_add_proxy)

operator_source = None
for module_name in list(sys.modules):
    if module_name.endswith("operators.loadlibraryproxy"):
        operator_source = inspect.getsource(sys.modules[module_name])

result = dict(
    check_add_proxy_calls_add_mhclo_asset="add_mhclo_asset(" in check_add_proxy,
    check_add_proxy_extras=sorted([step for step in
                                   ["Hide base mesh", "scale_factor", "ALL_EXTRA_GROUPS",
                                    "_proxy_corrective"]
                                   if step in check_add_proxy]),
    library_operator_found=operator_source is not None,
    library_operator_calls_add_mhclo_asset=(
        None if operator_source is None else "add_mhclo_asset(" in operator_source),
    library_operator_loads_the_mhclo_itself=(
        None if operator_source is None else "mhclo.load_mesh(" in operator_source),
)
'''

_UNLOAD_ANYTHING_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
HumanService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["HumanService"]

basemesh = bpy.data.objects.get(PARAMS["name"])

# An ordinary cube. Not a MakeHuman object, not a mesh asset, not related to the
# character at all: unload_mhclo_asset() checks none of that.
mesh = bpy.data.meshes.new("mpfbmcp_innocent")
cube = bpy.data.objects.new("mpfbmcp_innocent", mesh)
bpy.context.collection.objects.link(cube)
name = cube.name

raised = None
try:
    HumanService.unload_mhclo_asset(basemesh, cube)
except Exception as exception:
    raised = type(exception).__name__ + ": " + str(exception)

deleted = name not in bpy.data.objects
if not deleted:
    bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
if mesh.name in bpy.data.meshes and mesh.users == 0:
    bpy.data.meshes.remove(mesh)

result = dict(handed=name, cube_deleted=deleted, raised=raised)
'''

_SKIN_TYPO_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
HumanService = services["HumanService"]
AssetService = services["AssetService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
path = str(AssetService.find_asset_absolute_path(PARAMS["fragment"], "skins"))

before = [material.name for material in basemesh.data.materials if material is not None]

raised = None
raised_from = None
try:
    # One letter wrong. The function tests its five known types with five
    # separate `if` statements and no `else`, so this deletes every material
    # first and then builds nothing.
    HumanService.set_character_skin(path, basemesh, skin_type=PARAMS["skin_type"],
                                    material_instances=False)
except Exception as exception:
    raised = type(exception).__name__ + ": " + str(exception)
    traceback_frame = exception.__traceback__
    while traceback_frame is not None and traceback_frame.tb_next is not None:
        traceback_frame = traceback_frame.tb_next
    if traceback_frame is not None:
        raised_from = str(traceback_frame.tb_frame.f_code.co_name)

after = [material.name for material in basemesh.data.materials if material is not None]

# And again with instancing on, which is the path FR 011 read: that one does
# reach create_and_assign_material_slots() and does raise.
raised_with_instances = None
try:
    HumanService.set_character_skin(path, basemesh, skin_type=PARAMS["skin_type"],
                                    material_instances=True)
except Exception as exception:
    raised_with_instances = type(exception).__name__ + ": " + str(exception)

result = dict(materials_before=before, materials_after=after,
              raised=raised, raised_from=raised_from,
              raised_with_instances=raised_with_instances)
'''

_EXCLUDE_DEFAULT_CODE = '''
import sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
AssetService = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["AssetService"]

fragment = PARAMS["fragment"]
without_exclude = [str(entry) for entry in
                   AssetService.alternative_materials_for_asset(fragment, "clothes")]
with_exclude = [str(entry) for entry in
                AssetService.alternative_materials_for_asset(fragment, "clothes",
                                                             exclude_default=True)]

module = sys.modules[AssetService.__module__]
cache_attribute = sorted([name for name in dir(module)
                          if "alternative" in name.lower() and "material" in name.lower()])

invalidator = None
for name in dir(AssetService):
    if "invalidate" in name.lower() and "material" in name.lower():
        invalidator = name

# The asset's *own* material, whose stem matches the MHCLO's. Compared on the
# stem rather than on the filename, since one ends .mhclo and the other .mhmat.
stem = fragment.split("/")[-1].rsplit(".", 1)[0]
default_present = any(entry.endswith("/" + stem + ".mhmat") for entry in without_exclude)

# Does the invalidator exist, and does it actually empty the cache?
cleared = None
if invalidator is not None:
    getattr(AssetService, invalidator)()
    cleared = len(getattr(module, "_ALTERNATIVE_MATERIALS", dict())) == 0

result = dict(without_exclude=sorted(without_exclude), with_exclude=sorted(with_exclude),
              default_is_in_the_list=default_present, default_stem=stem,
              cache_attribute=cache_attribute, invalidator=invalidator,
              cleared_by_invalidator=cleared)
'''


if __name__ == "__main__":
    sys.exit(harness.main_guard(run))
