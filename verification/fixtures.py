# SPDX-License-Identifier: GPL-3.0-or-later

"""
The install this session needs, the characters it runs on, and the three
targets it has to bring with it.

FR 013's second functional requirement is that the install be *checked* before
the session starts rather than discovered halfway through it: at least one
custom rig, Rigify enabled, a skin MHMAT, one asset with alternative materials
beside it, and one asset whose MHCLO declares no delete vertices. Every check
below is on the running install rather than on a list written here, because the
point is to fail early and say which piece is missing.

The three probe targets are the exception - they cannot be required of an
install, since none of them ships with MPFB, so the harness installs them and
takes them away again the way FR 006's run did with its gzipped probe. Note
what installing them does *not* buy: ``mpfb/ui/model/_modelsubpanels.py`` builds
its category table at module import time, so MPFB's own panel will not show
these categories until Blender restarts. mpfb-mcp's payloads reimplement that
scan and do see them, which is the whole reason the reimplementation exists -
and it is also why the "reads back on MPFB's own slider" half of FR 008's
checklist has to be done on a target that was already installed when Blender
started.
"""

from __future__ import annotations

__all__ = (
    "ALTERNATIVE_MATERIAL_ASSET",
    "EYES_ASSET",
    "NO_DELETE_GROUP_ASSET",
    "NO_MATERIAL_ASSET",
    "CHARACTER_A",
    "CHARACTER_B",
    "MAX_SAFE_TARGET_NAME_LENGTH",
    "PROBE_TARGETS",
    "SAFE_AT_STARTUP",
    "SKIN_FRAGMENT",
    "build_character_b",
    "check_install",
    "ensure_character_a",
    "fresh_human",
    "skin_fragment",
    "stage_of",
    "install_probe_targets",
    "remove_probe_targets",
    "user_custom_target_dir",
)

import os

from verification.harness import probe

# Assets this session names by fragment. Each is here because a checklist needs
# the property named beside it, and each is asserted to exist by check_install()
# rather than assumed.
CLOTHES_ASSET = "cortu_jeans_shorts/cortu_jeans_shorts.mhclo"
NO_DELETE_GROUP_ASSET = "culturalibre_cl_bowler_hat/culturalibre_cl_bowler_hat.mhclo"
NO_MATERIAL_ASSET = "jujube_newsboy_cap/jujube_newsboy_cap.mhclo"
ALTERNATIVE_MATERIAL_ASSET = "nurse_uniform_coat_clothsim/nurse_uniform_coat_clothsim.mhclo"
EYES_ASSET = "high-poly/high-poly.mhclo"
HAIR_ASSET = "long01/long01.mhclo"
PROXY_ASSET = "female_generic/female_generic.proxy"

# A skin is resolved at run time - installs differ, and hard-coding one would
# make check_install() report a missing prerequisite that is really a missing
# line here.
SKIN_FRAGMENT = None

# The three targets FR 008 needs and no install ships: a gzipped custom target
# (the naming divergence), a name long enough that MPFB encodes it, and one
# whose name contains "basis" and which MPFB's own stack listing therefore
# cannot see.
# The long one is deliberately built out of substrings MPFB's encoding table
# knows ("female", "average", "muscle", "weight", "height", "young"): the >60
# character rule only turns encoding *on*, and a long name containing none of
# those encodes to itself, which would make the check pass while proving
# nothing.
#
# **The long one must never be on disk when Blender starts.** It is in
# UNSAFE_AT_STARTUP below and it is there because leaving it installed across a
# restart, once, prevented MPFB from registering at all:
# ``ui/model/_modelsubpanels.py`` does
# ``setattr(bpy.types.Scene, "custom_" + name, prop)`` at module import time,
# Blender caps a property identifier at 63 characters, and the resulting
# ValueError propagates out of MPFB's ``register()``. A single long-named target
# file in a scanned user directory therefore disables the whole add-on on the
# next start. That is an MPFB defect and it is filed as one - see
# check_mpfb_issues.py - but it is also a hazard this harness must not leave
# behind, so ``install_probe_targets()`` and ``remove_probe_targets()`` are
# always used as a pair inside one checklist run.
PROBE_TARGETS = (
    "mpfbmcp_probe_vwide.target.gz",
    "mpfbmcp_probe_a_very_long_female_average_muscle_weight_height_young_name.target",
    "mpfbmcp_probe_basis_containing_name.target",
)

# Probe targets that are safe to leave on disk across a Blender restart, for the
# two checks that need a target to have been present when the panel built its
# table. Anything not listed here is removed before a restart is suggested.
SAFE_AT_STARTUP = (
    "mpfbmcp_probe_vwide.target.gz",
    "mpfbmcp_probe_basis_containing_name.target",
)

# The rule the split above encodes, stated once: MPFB derives a Scene property
# identifier as "custom_" + the target's name with dots and dashes replaced, and
# Blender rejects one over 63 characters. So a user target name over 56
# characters breaks MPFB's registration - while the *encoding* this checklist is
# about only starts above 60. The two conditions cannot both be met by a file
# left on disk, which is the sharp form of the defect.
MAX_SAFE_TARGET_NAME_LENGTH = 63 - len("custom_")


def user_custom_target_dir() -> str:
    """MPFB's user ``custom`` target directory, asked of MPFB rather than guessed."""
    return probe("custom_target_dir", _CUSTOM_DIR_CODE)["path"]


_CUSTOM_DIR_CODE = '''
import os, sys

# The extension has no stable import path, so MPFB is resolved the way its own
# code resolves it - see codegen/bootstrap.py.
candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
LocationService = services["LocationService"]

path = LocationService.get_user_data("custom")
result = dict(path=str(path), exists=os.path.isdir(str(path)))
'''


def install_probe_targets() -> dict:
    """Write the three probe targets, and report which were newly created.

    A target file is a list of ``vertex dx dy dz`` lines; two vertices moved a
    little is enough to be loadable and to show up as a shape key, and small
    enough that writing it is not itself a cost.
    """
    return probe("install_probe_targets", _INSTALL_CODE,
                 names=list(PROBE_TARGETS))


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


def remove_probe_targets() -> dict:
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


def check_install(tools: dict) -> dict:
    """Everything FR-2 says to check before starting, asked of the install.

    Returns a dict of prerequisite name to a description of what was found, with
    ``None`` for anything missing. A caller that finds a ``None`` should stop:
    discovering it halfway through a checklist is the failure mode this exists
    to prevent.
    """
    found = dict()

    status = tools["mpfb_get_status"]()["result"]
    found["mpfb"] = status["state"] if status["state"] == "ok" else None
    found["mpfb_version"] = status.get("version")
    found["blender"] = status["blender"]["version"]

    rigs = tools["mpfb_list_rigs"]()["result"]
    custom = [rig["identifier"] for rig in rigs["rigs"]
              if rig["identifier"].startswith("custom.")]
    found["custom_rig"] = custom[0] if custom else None
    found["rigify"] = True if rigs["rigify_available"] else None

    skins = tools["mpfb_list_assets"](asset_subdir="skins", limit=500)["result"]
    found["skin"] = skins["assets"][0]["fragment"] if skins["assets"] else None
    found["skin_count"] = skins["total_count"]

    found.update(_check_asset_files())
    return found


def _check_asset_files() -> dict:
    # find_asset_absolute_path() defaults its second argument to "clothes", so
    # every fragment has to carry the subdir it lives under. A fragment alone is
    # not a globally resolvable identifier, which is worth knowing here as well
    # as in mpfb_add_asset.
    return probe("check_asset_files", _ASSET_FILES_CODE, assets=dict(
        clothes=[CLOTHES_ASSET, "clothes"],
        no_delete_group=[NO_DELETE_GROUP_ASSET, "clothes"],
        no_material=[NO_MATERIAL_ASSET, "clothes"],
        alternative_materials=[ALTERNATIVE_MATERIAL_ASSET, "clothes"],
        eyes=[EYES_ASSET, "eyes"],
        hair=[HAIR_ASSET, "hair"],
        proxy=[PROXY_ASSET, "proxymeshes"],
    ))


_ASSET_FILES_CODE = '''
import os, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
AssetService = services["AssetService"]

found = dict()
for key in sorted(PARAMS["assets"]):
    fragment, subdir = PARAMS["assets"][key]
    path = AssetService.find_asset_absolute_path(fragment, subdir)
    found[key] = None if not path or not os.path.isfile(str(path)) else str(path)

# The two properties that cannot be read off a filename: whether the MHCLO
# declares delete vertices, and whether it names a material.
declares = dict()
for key in ["no_delete_group", "no_material", "clothes"]:
    path = found.get(key)
    if not path:
        continue
    handle = open(path, "r")
    text = handle.read()
    handle.close()
    declares[key] = dict(
        delete_verts=("\\ndelete_verts" in text or text.startswith("delete_verts")),
        material=any(line.startswith("material ") for line in text.split("\\n")),
    )

# Alternative materials sit beside the asset, not in the asset library index.
alternatives = []
alternative_path = found.get("alternative_materials")
if alternative_path:
    directory = os.path.dirname(alternative_path)
    alternatives = sorted([name for name in os.listdir(directory) if name.endswith(".mhmat")])

result = dict(paths=found, declares=declares, alternatives=alternatives)
'''


def fresh_human(tools: dict, rename_to: str, **macro_details: object) -> dict:
    """Create a basemesh and give it a name this session's checklists can use.

    Renaming matters more than it looks: MPFB names every character ``Human``
    and uniquifies the second one to ``Human.001``, so two characters in one
    session would be told apart by a suffix rather than by what they are for.
    """
    response = tools["mpfb_create_human"](**macro_details)
    if response.get("status") != "ok":
        raise RuntimeError("could not create a character: {}".format(response))
    created = response["result"]["object_name"]
    renamed = probe("rename", _RENAME_CODE, old=created, new=rename_to)
    return dict(created=created, name=renamed["name"], response=response["result"])


_RENAME_CODE = '''
import bpy

obj = bpy.data.objects.get(PARAMS["old"])
if obj is None:
    raise RuntimeError("no object named " + PARAMS["old"])
obj.name = PARAMS["new"]
result = dict(name=obj.name)
'''


def object_names_under(scene: str) -> list:
    """Every object in the scratch scene, for a before/after within a checklist."""
    return probe("scene_objects", _SCENE_OBJECTS_CODE, scene=scene)["names"]


_SCENE_OBJECTS_CODE = '''
import bpy

scene = bpy.data.scenes.get(PARAMS["scene"])
names = [] if scene is None else sorted([o.name for o in scene.collection.all_objects])
result = dict(names=names)
'''


# The stages of Character A, in MPFB's documented order. FR-2 asks for one
# character built once and reused across the checklists; a checklist run on its
# own has to be able to build it anyway. Both are the same function: each stage
# is idempotent and knows how to advance from the one before, so run_all.py
# builds the character once and a single ``check_frNNN.py`` builds exactly as
# much of it as its own items need.
CHARACTER_A = "CharacterA"
CHARACTER_B = "CharacterB"

STAGES = ("created", "macro", "targets", "rigged", "dressed", "generated", "skinned")

# What Character A is: an older, heavier, taller male, one detail modifier well
# off centre so the symmetrize checks have something to work on, a Rigify meta
# rig, two garments and a skin. The values are arbitrary but fixed - a
# repeatable run needs the same character every time.
MACRO_A = dict(gender=0.9, age=0.75, muscle=0.35, weight=0.7, height=0.8, cupsize=0.2)
MODIFIER_A = dict(section="nose", category="nose-scale-horiz-decr-incr", value=0.6)


def stage_of(name: str) -> str:
    """Which stage the character in the file has reached, read off the objects."""
    state = probe("stage_of", _STAGE_CODE, name=name)
    if not state["exists"]:
        return None
    if state["has_skin"]:
        return "skinned"
    if state["generated_rig"]:
        return "generated"
    if state["mesh_assets"]:
        return "dressed"
    if state["rig"]:
        return "rigged"
    if state["detail_shapekeys"]:
        return "targets"
    if state["macro_changed"]:
        return "macro"
    return "created"


_STAGE_CODE = '''
import bpy, sys

candidates = [name for name in sys.modules if name.endswith("mpfb")]
mpfb = sys.modules[candidates[0]]
services = mpfb.MPFB_CONTEXTUAL_INFORMATION["SERVICES"]
ObjectService = services["ObjectService"]
TargetService = services["TargetService"]

basemesh = bpy.data.objects.get(PARAMS["name"])
if basemesh is None:
    result = dict(exists=False)
else:
    relatives = ObjectService.find_related_objects(basemesh)
    rig = None
    generated_rig = None
    mesh_assets = []
    for relative in relatives:
        if relative == basemesh:
            continue
        object_type = ObjectService.get_object_type(relative)
        if object_type == "Skeleton":
            rig = relative.name
            if relative.get("rig_ui") is not None or "rig" in [m.name for m in relative.modifiers]:
                pass
            # A generated Rigify rig carries Rigify's own back-link on the meta rig.
            if getattr(relative.data, "rigify_target_rig", None) is not None:
                generated_rig = relative.data.rigify_target_rig.name
        elif object_type and object_type not in ("Basemesh", "Skeleton"):
            mesh_assets.append(relative.name)

    keys = []
    if basemesh.data.shape_keys is not None:
        keys = [block.name for block in basemesh.data.shape_keys.key_blocks]
    detail = [name for name in keys if not name.startswith("$md-") and name != "Basis"]

    macro = TargetService.get_macro_info_dict_from_basemesh(basemesh)
    changed = any(abs(float(value) - 0.5) > 0.001
                  for key, value in macro.items() if not isinstance(value, dict))

    result = dict(
        exists=True,
        rig=rig,
        generated_rig=generated_rig,
        mesh_assets=sorted(mesh_assets),
        detail_shapekeys=sorted(detail),
        macro_changed=bool(changed),
        has_skin=len(basemesh.data.materials) > 0,
        shapekeys=sorted(keys),
    )
'''


def ensure_character_a(tools: dict, upto: str, report=None) -> dict:
    """Build Character A as far as ``upto``, from wherever it already is.

    The order is MPFB's documented one - create, macro, detail targets, rig,
    clothes, Rigify generation, skin - and it is the order because the
    constraint MPFB reports no error for lives in it: a garment is rigged only
    if a rig exists when it is attached.
    """
    if upto not in STAGES:
        raise ValueError("unknown stage: {}".format(upto))
    wanted = STAGES.index(upto)
    current = stage_of(CHARACTER_A)
    steps = []

    if current is None:
        fresh_human(tools, CHARACTER_A)
        current = "created"
        steps.append("created")

    at = STAGES.index(current)
    for index in range(at + 1, wanted + 1):
        stage = STAGES[index]
        _ADVANCE[stage](tools)
        steps.append(stage)

    state = dict(name=CHARACTER_A, stage=stage_of(CHARACTER_A), steps=steps)
    if report is not None:
        report.note("Character A at stage {} (built: {})".format(
            state["stage"], ", ".join(steps) or "already there"))
    return state


def _advance_macro(tools: dict) -> None:
    tools["mpfb_set_macro_details"](name=CHARACTER_A, **MACRO_A)


def _advance_targets(tools: dict) -> None:
    tools["mpfb_set_targets"](name=CHARACTER_A, modifiers=[dict(MODIFIER_A)])


def _advance_rigged(tools: dict) -> None:
    tools["mpfb_add_rig"](name=CHARACTER_A, identifier="rigify.human_toes")


def _advance_dressed(tools: dict) -> None:
    for fragment, asset_type in ((CLOTHES_ASSET, "Clothes"),
                                 (NO_DELETE_GROUP_ASSET, "Clothes")):
        tools["mpfb_add_asset"](name=CHARACTER_A, fragment=fragment, asset_type=asset_type)


def _advance_generated(tools: dict) -> None:
    tools["mpfb_generate_rigify_rig"](name=CHARACTER_A)


def _advance_skinned(tools: dict) -> None:
    tools["mpfb_set_skin"](name=CHARACTER_A, fragment=skin_fragment(tools))


_ADVANCE = dict(
    macro=_advance_macro,
    targets=_advance_targets,
    rigged=_advance_rigged,
    dressed=_advance_dressed,
    generated=_advance_generated,
    skinned=_advance_skinned,
)


def skin_fragment(tools: dict) -> str:
    """The skin this session applies, resolved from the install rather than named here."""
    global SKIN_FRAGMENT  # pylint: disable=global-statement
    if SKIN_FRAGMENT is None:
        listing = tools["mpfb_list_assets"](asset_subdir="skins", limit=500)["result"]
        if not listing["assets"]:
            raise RuntimeError("this install has no skin to apply")
        SKIN_FRAGMENT = listing["assets"][0]["fragment"]
    return SKIN_FRAGMENT


def build_character_b(tools: dict) -> dict:
    """The same character in the wrong order: clothes first, then the rig.

    Character B exists for one observation and no other:
    [A tool reports an ordering constraint it cannot
    enforce](../specifications/architecture.md) rests on a garment attached
    before there is a rig never being rigged afterwards, and that is currently a
    reading of MPFB's source rather than something anyone has seen.
    """
    if stage_of(CHARACTER_B) is None:
        fresh_human(tools, CHARACTER_B)
    dressed = tools["mpfb_add_asset"](
        name=CHARACTER_B, fragment=CLOTHES_ASSET, asset_type="Clothes")
    rigged = tools["mpfb_add_rig"](name=CHARACTER_B, identifier="default")
    return dict(name=CHARACTER_B, dressed=dressed.get("result"), rigged=rigged.get("result"))
