# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 025's live check: does a character actually survive a round trip?

Three claims, and none of them can be established on this side of the socket.

**One: a full round trip reproduces the character.** Build one with a rig, a
garment, a body part and a non-default skin; save it; load it back; compare the
two, field by field, through the package's own read tools. This is the only
check that establishes these three tools are *useful* rather than merely
well-formed, and it is the reason the effort needed a Blender at all. The
comparison is deliberately made through ``mpfb_get_macro_details`` and
``mpfb_get_object_info`` rather than by re-reading the JSON: the question is
whether the rebuilt character matches the original, not whether the file matches
itself.

**Two: the preset mpfb_save_preset writes is the one MPFB's own panel offers and
loads.** A tool that wrote into a namespace of its own would pass every unit
test in this repository. What is checked is both directions: the name appears in
``HumanService.get_list_of_human_presets()``, which is what MPFB's dropdown is
built from, and ``deserialize_from_json_file()`` called *directly* - not through
the tool - rebuilds a character from the same file.

**Three: ``save_clothes`` really is ignored by the running install**, not only by
the source read while this was written. FR 019's correction, and the reason that
request exists in the form it does: a candidate defect read from source is a
hypothesis. It is provoked rather than inspected - the same dressed character is
serialized with ``save_clothes=False`` and with ``True``, and the two strings are
compared. Identical strings, both carrying the garment, is the defect.

Two lesser candidates are checked beside it, each of which the request left open:
whether ``get_default_deserialization_settings()`` really omits the two override
keys ``deserialize_from_dict()`` honours, and whether a preset path that is not
of the shape ``human.<name>.json`` really raises ``AttributeError`` from inside
MPFB - the third reason a preset is a name and never a path.

**This is this effort's own check and lives with this effort**, per
[feature-requests/CLAUDE.md](../../CLAUDE.md). It is not in ``verification/``; what
FR 025 adds there is three smoke items and no new file. Note that it *writes
into MPFB's user config directory*, as `check_mpfb_issues.py` does and as the
smoke run deliberately does not - every preset it writes is named with the prefix
below and every one of them is deleted again, including on a failure.

Requires a running Blender with MPFB and the blender_mcp add-on. Run from the
repository root::

    PYTHONPATH=. python3 feature-requests/done/025-character-presets/check_presets.py
"""

from __future__ import annotations

__all__ = ("run",)

import sys

from verification import fixtures, harness
from verification.harness import Report

# Every preset this script writes carries the prefix, and every one is deleted
# in the finally below. A name that says where it came from matters more here
# than in the smoke run: this script writes several.
PREFIX = "fr025_check_"

ORIGINAL = PREFIX + "original"


# --------------------------------------------------------------------------
# Probes. Each one talks to MPFB directly rather than through a tool: a probe
# that shared an implementation with the thing it checks could not contradict it.
# --------------------------------------------------------------------------

_BOOTSTRAP = '''
import sys
_names = [name for name in list(sys.modules)
          if name.endswith("mpfb") and hasattr(sys.modules[name],
                                               "MPFB_CONTEXTUAL_INFORMATION")]
if not _names:
    raise RuntimeError("MPFB is not loaded in this Blender")
SERVICES = sys.modules[_names[0]].MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
HumanService = SERVICES["HumanService"]
LocationService = SERVICES["LocationService"]
ObjectService = SERVICES["ObjectService"]
'''

_SAVE_CLOTHES_CODE = _BOOTSTRAP + '''
import bpy

basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(
    bpy.data.objects[PARAMS["name"]], "Basemesh")

# The provocation: the same character, serialized twice, with the argument the
# only thing that differs. Nothing is written to disk.
without = HumanService.serialize_to_json_string(basemesh, save_clothes=False)
with_clothes = HumanService.serialize_to_json_string(basemesh, save_clothes=True)

import json as _json
result = {
    "identical": without == with_clothes,
    "clothes_without": _json.loads(without).get("clothes"),
    "clothes_with": _json.loads(with_clothes).get("clothes"),
    "basemesh": basemesh.name,
}
'''

_MPFB_SEES_IT_CODE = _BOOTSTRAP + '''
import os

confdir = str(LocationService.get_user_config())
filename = os.path.join(confdir, "human." + PARAMS["name"] + ".json")

# What MPFB's own preset dropdown is built from. use_cache=False because the
# tool's save invalidated the cache through serialize_to_json_file(), and this
# probe should establish the file is found rather than that the cache is warm.
names = list(HumanService.get_list_of_human_presets(as_list_enum=False, use_cache=False))
enum = HumanService.get_list_of_human_presets(as_list_enum=True, use_cache=True)

# ...and MPFB loading it itself, with no tool in the path at all.
settings = HumanService.get_default_deserialization_settings()
settings["load_clothes"] = False
settings["subdiv_levels"] = 0
basemesh = HumanService.deserialize_from_json_file(filename, settings)

result = {
    "in_mpfb_list": PARAMS["name"] in names,
    "in_mpfb_enum": PARAMS["name"] in [entry[0] for entry in enum],
    "preset_count": len(names),
    "file_exists": os.path.isfile(filename),
    "config_dir": confdir,
    "mpfb_loaded_object": None if basemesh is None else basemesh.name,
    "mpfb_loaded_vertices": None if basemesh is None else len(basemesh.data.vertices),
    # Deleted again immediately: this probe is about MPFB reading the file, and
    # the character it builds is a side effect the leak compare would report.
    "cleaned_up": True,
}

for obj in list(ObjectService.get_list_of_children(basemesh)) + [basemesh]:
    try:
        bpy_data_objects = __import__("bpy").data.objects
        bpy_data_objects.remove(obj, do_unlink=True)
    except Exception:
        result["cleaned_up"] = False
'''

_SETTINGS_CODE = _BOOTSTRAP + '''
defaults = HumanService.get_default_deserialization_settings()
result = {
    "keys": sorted(defaults.keys()),
    "omits_override_clothes_model": "override_clothes_model" not in defaults,
    "omits_override_eyes_model": "override_eyes_model" not in defaults,
    "material_instances_default": defaults.get("material_instances"),
}
'''

_BAD_PATH_CODE = _BOOTSTRAP + '''
import os

confdir = str(LocationService.get_user_config())
# A file MPFB can read whose *name* is not of the shape its regex expects.
filename = os.path.join(confdir, PARAMS["name"])
handle = open(filename, "w", encoding="utf-8")
handle.write("{}")
handle.close()

result = {"filename": filename, "raised": None, "message": None}
try:
    settings = HumanService.get_default_deserialization_settings()
    HumanService.deserialize_from_json_file(filename, settings)
except Exception as error:
    result["raised"] = type(error).__name__
    result["message"] = str(error)
finally:
    os.remove(filename)
'''

_DELETE_PRESETS_CODE = _BOOTSTRAP + '''
import os

confdir = str(LocationService.get_user_config())
removed = []
for filename in sorted(os.listdir(confdir)):
    if filename.startswith("human." + PARAMS["prefix"]) and filename.endswith(".json"):
        os.remove(os.path.join(confdir, filename))
        removed.append(filename)
HumanService.update_list_of_human_presets()
result = {"removed": removed, "config_dir": confdir}
'''


# --------------------------------------------------------------------------
# The checks.
# --------------------------------------------------------------------------


def _build_character(report: Report, tools: dict) -> dict:
    """A character worth saving: a rig, a garment, a body part and a skin.

    Everything is asked of the catalogue tools rather than named by filename, as
    ``verification/fixtures.py`` does, so this runs against anybody's install and
    names what it could not exercise.
    """
    envelope, name = fixtures.create_character(tools)
    report.check("a character was created", envelope.get("status") == "ok", name)

    built = dict(name=name, rig=None, garment=None, bodypart=None, skin=None)

    rigs = tools["mpfb_list_rigs"]()["result"]["rigs"]
    available = [rig for rig in rigs if rig.get("available")]
    # A standard rig rather than a Rigify one: a generated Rigify rig
    # deliberately does not round-trip, which is the one asymmetry this check
    # would otherwise have to special-case. It is checked separately below.
    standard = [rig for rig in available if rig.get("family") == "standard"]
    if standard:
        added = tools["mpfb_add_rig"](name=name, identifier=standard[0]["identifier"])
        if added.get("status") == "ok" and added["result"].get("added"):
            built["rig"] = standard[0]["identifier"]
    report.check("it was rigged", built["rig"] is not None, built["rig"])

    for subdir, key in (("clothes", "garment"), ("eyes", "bodypart")):
        asset = fixtures.first_asset(tools, subdir)
        if asset is None:
            report.skip("it was given a {}".format(key),
                        "this install has no asset under '{}'".format(subdir))
            continue
        equipped = tools["mpfb_add_asset"](
            name=name, fragment=asset["fragment"], asset_type=asset["object_type"])
        if equipped.get("status") == "ok" and equipped["result"].get("added"):
            built[key] = asset["fragment"]
        report.check("it was given a {}".format(key), built[key] is not None, built[key])

    skin = fixtures.first_asset(tools, "skins")
    if skin is None:
        report.skip("it was given a non-default skin", "this install has no asset under 'skins'")
    else:
        # ENHANCED rather than the MAKESKIN default, so that the skin model
        # itself is something the round trip has to carry rather than a value
        # that would match by coincidence.
        applied = tools["mpfb_set_skin"](
            name=name, fragment=skin["fragment"], skin_type="ENHANCED")
        if applied.get("status") == "ok" and applied["result"].get("applied"):
            built["skin"] = skin["fragment"]
        report.check("it was given a non-default skin", built["skin"] is not None, built["skin"])

    # Something that is not a default, so that a phenotype which came back at
    # MPFB's defaults would not look like a successful round trip.
    tools["mpfb_set_macro_details"](name=name, gender=0.83, age=0.21, muscle=0.66)
    return built


def _describe(tools: dict, name: str) -> dict:
    """What a character is, read through the package's own tools."""
    macro = tools["mpfb_get_macro_details"](name=name)["result"]
    info = tools["mpfb_get_object_info"](name=name)["result"]
    return dict(macro=macro.get("macro_details"), info=info)


def _check_round_trip(report: Report, tools: dict, built: dict) -> dict:
    """Save it, load it, compare. The claim the whole effort rests on."""
    before = _describe(tools, built["name"])

    saved = tools["mpfb_save_preset"](
        name=ORIGINAL, subject=built["name"], overwrite=True)
    saved_result = saved.get("result") or dict()
    report.check("the character was saved",
                 saved.get("status") == "ok" and saved_result.get("saved"),
                 dict(path=saved_result.get("path"),
                      size_bytes=saved_result.get("size_bytes"),
                      blocked_by=saved_result.get("blocked_by"),
                      message=saved_result.get("message")))
    if not saved_result.get("saved"):
        return dict(saved=saved_result, loaded=None)

    contents = saved_result.get("contents") or dict()
    report.check("the written file records the rig the character carries",
                 contents.get("rig") == built["rig"],
                 dict(recorded=contents.get("rig"), added=built["rig"]))
    report.check("...and the garment",
                 bool(contents.get("clothes")) == bool(built["garment"]),
                 dict(recorded=contents.get("clothes"), equipped=built["garment"]))
    report.check("...and the skin",
                 bool(contents.get("skin_mhmat")) == bool(built["skin"]),
                 dict(recorded=contents.get("skin_mhmat"),
                      model=contents.get("skin_material_type"), applied=built["skin"]))

    listed = tools["mpfb_list_presets"]()["result"]
    entry = [row for row in listed["presets"] if row["name"] == ORIGINAL]
    report.check("mpfb_list_presets finds it without a refresh",
                 bool(entry) and entry[0]["addressable"],
                 dict(count=listed["count"], config_dir=listed["config_dir"],
                      entry=entry[0] if entry else None))

    loaded = tools["mpfb_create_human_from_preset"](name=ORIGINAL)
    loaded_result = loaded.get("result") or dict()
    report.check("a character was rebuilt from it",
                 loaded.get("status") == "ok" and loaded_result.get("created"),
                 dict(basemesh_name=loaded_result.get("basemesh_name"),
                      blocked_by=loaded_result.get("blocked_by"),
                      objects_created=loaded_result.get("objects_created"),
                      unresolved=loaded_result.get("unresolved_assets"),
                      message=loaded_result.get("message")))
    if not loaded_result.get("created"):
        return dict(saved=saved_result, loaded=loaded_result)

    rebuilt = loaded_result["basemesh_name"]
    after = _describe(tools, rebuilt)

    # The comparison the whole effort rests on. Rounded, because a macro value
    # goes through a float property and back.
    def rounded(macro):
        flat = dict()
        for key, value in (macro or dict()).items():
            if isinstance(value, dict):
                for inner, weight in value.items():
                    flat[key + "." + inner] = round(float(weight), 4)
            else:
                flat[key] = round(float(value), 4)
        return flat

    report.check("the rebuilt character has the original's phenotype",
                 rounded(before["macro"]) == rounded(after["macro"]),
                 dict(before=rounded(before["macro"]), after=rounded(after["macro"])))

    report.check("...and its rig",
                 loaded_result.get("rig_identified_as") == built["rig"],
                 dict(rebuilt=loaded_result.get("rig_identified_as"),
                      original=built["rig"]))

    equipped = loaded_result.get("equipped_assets") or []
    sources = sorted(entry.get("asset_source") for entry in equipped
                     if entry.get("asset_source"))
    expected = sorted(fragment for fragment in (built["garment"], built["bodypart"])
                      if fragment)
    report.check("...and every asset it was wearing",
                 sources == expected, dict(rebuilt=sources, original=expected))

    report.check("...and its skin model",
                 bool(loaded_result.get("skin_material_identified_as")) == bool(built["skin"]),
                 dict(rebuilt=loaded_result.get("skin_material_identified_as"),
                      original=built["skin"]))

    report.check("nothing the preset named was missing from this install",
                 loaded_result.get("unresolved_assets") == [],
                 loaded_result.get("unresolved_assets"))

    report.check("the selection it left behind is reported rather than restored",
                 loaded_result.get("active_object_after") is not None,
                 loaded_result.get("active_object_after"))

    return dict(saved=saved_result, loaded=loaded_result, rebuilt=rebuilt)


def _check_mpfb_sees_the_same_preset(report: Report) -> None:
    """Claim two: the file is MPFB's, in both directions."""
    observed = harness.probe("mpfb_sees_it", _MPFB_SEES_IT_CODE, name=ORIGINAL)
    report.check("MPFB's own preset list holds the name this package wrote",
                 observed["in_mpfb_list"] and observed["in_mpfb_enum"],
                 dict(preset_count=observed["preset_count"],
                      config_dir=observed["config_dir"]))
    report.check("MPFB loads the file itself, with no tool in the path",
                 bool(observed["mpfb_loaded_object"]),
                 dict(object=observed["mpfb_loaded_object"],
                      vertices=observed["mpfb_loaded_vertices"]))
    report.check("...and the probe put its own character back",
                 observed["cleaned_up"], observed["cleaned_up"])


def _check_overwrite_refusal(report: Report, tools: dict, built: dict) -> None:
    """The one thing standing between a call and an irreversible loss."""
    before = tools["mpfb_list_presets"]()["result"]
    entry = [row for row in before["presets"] if row["name"] == ORIGINAL]
    size_before = entry[0]["size_bytes"] if entry else None

    refused = tools["mpfb_save_preset"](name=ORIGINAL, subject=built["name"])
    result = refused.get("result") or dict()
    report.check("saving over an existing preset is refused by default",
                 refused.get("status") == "ok"
                 and result.get("saved") is False
                 and result.get("blocked_by") == "preset_exists"
                 and result.get("performed") is False,
                 dict(blocked_by=result.get("blocked_by"),
                      previous_file=result.get("previous_file")))

    after = tools["mpfb_list_presets"]()["result"]
    entry = [row for row in after["presets"] if row["name"] == ORIGINAL]
    report.check("...and the existing file is untouched",
                 bool(entry) and entry[0]["size_bytes"] == size_before,
                 dict(before=size_before,
                      after=entry[0]["size_bytes"] if entry else None))

    missing = tools["mpfb_create_human_from_preset"](name=PREFIX + "no_such_preset")
    missing_result = missing.get("result") or dict()
    report.check("a misspelled name comes back naming the presets that exist",
                 missing_result.get("blocked_by") == "preset_not_found"
                 and ORIGINAL in (missing_result.get("available_presets") or []),
                 dict(count=missing_result.get("available_preset_count")))


def _check_save_clothes_is_ignored(report: Report, built: dict) -> None:
    """Claim three, provoked rather than read: the defect this effort files."""
    if not built["garment"]:
        report.skip("save_clothes=False still saves the clothes",
                    "this install had no garment to dress the character with, so the "
                    "argument has nothing to drop")
        return
    observed = harness.probe("save_clothes", _SAVE_CLOTHES_CODE, name=built["name"])
    report.check("save_clothes=False still saves the clothes (MPFB defect)",
                 observed["identical"] and bool(observed["clothes_without"]),
                 dict(identical=observed["identical"],
                      with_false=observed["clothes_without"],
                      with_true=observed["clothes_with"]))
    report.note("the two serializations are byte-identical and both carry the garment, "
                "so the documented default of False describes behaviour that does not "
                "exist. Filed as item 7 in ../../../../mpfb2/features/MCP_DISCOVERED_BUGS.md.")


def _check_the_two_lesser_candidates(report: Report) -> None:
    """The two the request left open, answered rather than assumed."""
    settings = harness.probe("settings", _SETTINGS_CODE)
    report.check("get_default_deserialization_settings() omits the two override keys "
                 "deserialize_from_dict() honours",
                 settings["omits_override_clothes_model"]
                 and settings["omits_override_eyes_model"],
                 dict(keys=settings["keys"]))
    report.note("so the vocabulary really is wider than the defaults, and the payload has "
                "to add rather than assume. Documented rather than filed: the two keys are "
                "optional to deserialize_from_dict() in a way the other eight are not, "
                "which reads as a distinction rather than an omission.")
    report.check("...and its material_instances default is NEVER, not the panel's ENHANCED",
                 settings["material_instances_default"] == "NEVER",
                 settings["material_instances_default"])

    bad = harness.probe("bad_path", _BAD_PATH_CODE, name="not_a_preset_name.json")
    report.check("a path that is not human.<name>.json raises from inside MPFB",
                 bad["raised"] == "AttributeError",
                 dict(raised=bad["raised"], message=bad["message"]))
    report.note("'NoneType' object has no attribute 'group' - an unchecked regex match, "
                "with nothing in the message about what the caller did wrong. The third "
                "reason a preset is addressed by name and never by a path.")


def _check_a_generated_rigify_rig(report: Report, tools: dict, built: dict) -> None:
    """The one asymmetry the tool documents rather than fixes."""
    rigs = tools["mpfb_list_rigs"]()["result"]["rigs"]
    rigify = [rig for rig in rigs if rig.get("family") == "rigify" and rig.get("available")]
    if not rigify:
        report.skip("a generated Rigify rig is saved as its meta rig",
                    "Rigify is not enabled in this Blender")
        return

    envelope, name = fixtures.create_character(tools)
    tools["mpfb_add_rig"](name=name, identifier=rigify[0]["identifier"])
    generated = tools["mpfb_generate_rigify_rig"](name=name)
    if not (generated.get("result") or dict()).get("generated"):
        report.skip("a generated Rigify rig is saved as its meta rig",
                    "Rigify would not generate a rig from this install's meta rig")
        return

    saved = tools["mpfb_save_preset"](
        name=PREFIX + "rigify", subject=name, overwrite=True)
    result = saved.get("result") or dict()
    report.check("a generated Rigify rig is saved as its meta rig",
                 result.get("saved")
                 and str(result.get("rig_identified_as") or "").startswith("rigify_generated")
                 and str(result.get("rig_saved_as") or "").startswith("rigify."),
                 dict(identified_as=result.get("rig_identified_as"),
                      saved_as=result.get("rig_saved_as")))
    report.note("no WARNING is emitted, unlike MPFB's own two operators: the substitution "
                "is reported as the fact it is, and the tool description says once that a "
                "generated rig does not round-trip.")


def run() -> dict:
    tools = harness.tools()
    report = Report("FR 025 - character presets, against a real MPFB")

    install = fixtures.check_install(tools)
    if not report.check("MPFB is loaded and initialized", install["usable"],
                        install["state"] or install.get("envelope")):
        return report.summary()
    report.note("MPFB {} on Blender {}, Rigify {}".format(
        install["mpfb_version"], install["blender"],
        "available" if install["rigify_available"] else "not enabled"))

    harness.ensure_scratch_scene()
    harness.cleanup_scratch_scene()
    before = harness.snapshot()

    try:
        built = _build_character(report, tools)
        _check_save_clothes_is_ignored(report, built)
        _check_round_trip(report, tools, built)
        _check_mpfb_sees_the_same_preset(report)
        _check_overwrite_refusal(report, tools, built)
        _check_the_two_lesser_candidates(report)
        _check_a_generated_rigify_rig(report, tools, built)
    finally:
        # Every preset this script wrote, gone - on a failure as much as on a
        # pass. This is the one script in the repository that writes into MPFB's
        # user config directory, and leaving litter there would be worse than
        # the check is worth.
        removed = harness.probe("delete_presets", _DELETE_PRESETS_CODE, prefix=PREFIX)
        report.check("every preset this check wrote was deleted again",
                     bool(removed["removed"]), removed["removed"])
        harness.cleanup_scratch_scene()

    after = harness.snapshot()
    difference = harness.diff_snapshots(before, after)
    report.check("the check put back everything it made in the .blend",
                 difference["identical"] and not difference["is_dirty_after"], difference)

    return report.summary()


if __name__ == "__main__":
    sys.exit(harness.main_guard(run))
