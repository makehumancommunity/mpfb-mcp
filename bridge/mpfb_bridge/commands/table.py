"""
The closed command vocabulary. This module *is* the security argument.

Everything this add-on can be made to do from outside is in :data:`COMMANDS`
below. A request names a key of that dict; a name that is not a key is refused
with an error that lists the alternatives. There is no ``exec``, no ``eval``, no
``importlib`` reachable from a request and no path by which a caller's string
becomes Python. That claim is only worth making if it can be checked, and
checking it means reading one short file - this one.

**The table is written out here rather than assembled.** No decorator, no
``__init_subclass__``, no scan of this directory, no registration as an import
side effect. A command module that is not named below is dead code and is
unreachable, which is the property the whole design turns on: a dict assembled
by imports is a dict whose contents depend on import order, and a directory scan
would make adding a command to this add-on a matter of dropping a file in a
folder. That is very nearly the thing a closed vocabulary exists to deny.

**One module per command, from the first two.** Each command's handler and its
parameter specification live in a module named for the command -
``get_status.py``, ``list_commands.py`` - and this file holds the table and
nothing else. The split mirrors ``src/mpfbmcp/tools/`` on the other side of the
socket, deliberately and down to the naming, so that a tool and the command it
sends are findable from each other. The difference is that a tool module
registers itself with the MCP server and a command module registers nothing at
all, for the reason in the paragraph above.

**A second directory has appeared beside this one, and it does not weaken the
claim above.** ``shared/`` holds the concepts two or more commands model
identically - the preset name rule, MPFB's asset section table, the modeling
category scan. **Nothing in it is reachable from the wire**: no module there has
a handler, a ``PARAMS`` or an entry below, and a command imports one the way it
imports ``os``. The vocabulary is still exactly the keys of :data:`COMMANDS`,
and reading this file is still enough to know it.

Where the record's fields live is a deliberate split too. ``params`` is long and
belongs beside the handler it constrains; ``requires_mpfb`` and ``summary`` are
short and are spelled out *here*, so that the sceptic reading one file learns
not only what this add-on can be asked to do but which of it touches MPFB.
"""

__all__ = (
    "COMMANDS",
)

from . import add_asset
from . import add_rig
from . import apply_expressions
from . import create_human
from . import create_export_copy
from . import create_human_from_preset
from . import generate_rigify_rig
from . import export_character
from . import get_character_summary
from . import get_expression
from . import get_face_units
from . import get_macro_details
from . import get_material_settings
from . import get_mpfb_status
from . import get_object_info
from . import get_pose
from . import get_pose_controls
from . import get_rigify_hand_shape
from . import get_target_stack
from . import get_status
from . import list_asset_materials
from . import list_assets
from . import list_commands
from . import list_expressions
from . import list_objects
from . import list_presets
from . import list_rigs
from . import list_targets
from . import list_urls
from . import place_character
from . import refit_human
from . import remove_asset
from . import reset_pose
from . import save_expression
from . import save_preset
from . import set_asset_material
from . import set_face_units
from . import set_macro_details
from . import set_material_settings
from . import set_pose_bones
from . import set_pose_switches
from . import set_rigify_hand_shape
from . import set_skin
from . import set_targets
from . import symmetrize_targets
from .command import Command

COMMANDS = {
    "add_asset": Command(
        name="add_asset",
        handler=add_asset.add_asset,
        params=add_asset.PARAMS,
        requires_mpfb=True,
        summary=add_asset.SUMMARY),
    "add_rig": Command(
        name="add_rig",
        handler=add_rig.add_rig,
        params=add_rig.PARAMS,
        requires_mpfb=True,
        summary=add_rig.SUMMARY),
    "apply_expressions": Command(
        name="apply_expressions",
        handler=apply_expressions.apply_expressions,
        params=apply_expressions.PARAMS,
        requires_mpfb=True,
        summary=apply_expressions.SUMMARY),
    "create_export_copy": Command(
        name="create_export_copy",
        handler=create_export_copy.create_export_copy,
        params=create_export_copy.PARAMS,
        requires_mpfb=True,
        summary=create_export_copy.SUMMARY),
    "create_human": Command(
        name="create_human",
        handler=create_human.create_human,
        params=create_human.PARAMS,
        # True, and the first **mutating** command in this table. Everything
        # below this line in the file is read-only; everything FR 032 adds
        # changes a .blend, which is why `requires_mpfb` matters more here than
        # it did: a command that cannot reach MPFB must refuse rather than half
        # build something.
        requires_mpfb=True,
        summary=create_human.SUMMARY),
    "create_human_from_preset": Command(
        name="create_human_from_preset",
        handler=create_human_from_preset.create_human_from_preset,
        params=create_human_from_preset.PARAMS,
        requires_mpfb=True,
        summary=create_human_from_preset.SUMMARY),
    "export_character": Command(
        name="export_character",
        handler=export_character.export_character,
        params=export_character.PARAMS,
        # True, and the first command that writes a file **another application**
        # opens. The file's name comes from the request; its directory never
        # does - export_directory.py reads it from this add-on's preferences.
        requires_mpfb=True,
        summary=export_character.SUMMARY),
    "generate_rigify_rig": Command(
        name="generate_rigify_rig",
        handler=generate_rigify_rig.generate_rigify_rig,
        params=generate_rigify_rig.PARAMS,
        requires_mpfb=True,
        summary=generate_rigify_rig.SUMMARY),
    "get_character_summary": Command(
        name="get_character_summary",
        handler=get_character_summary.get_character_summary,
        params=get_character_summary.PARAMS,
        requires_mpfb=True,
        summary=get_character_summary.SUMMARY),
    "get_expression": Command(
        name="get_expression",
        handler=get_expression.get_expression,
        params=get_expression.PARAMS,
        requires_mpfb=True,
        summary=get_expression.SUMMARY),
    "get_face_units": Command(
        name="get_face_units",
        handler=get_face_units.get_face_units,
        params=get_face_units.PARAMS,
        requires_mpfb=True,
        summary=get_face_units.SUMMARY),
    "get_macro_details": Command(
        name="get_macro_details",
        handler=get_macro_details.get_macro_details,
        params=get_macro_details.PARAMS,
        requires_mpfb=True,
        summary=get_macro_details.SUMMARY),
    "get_material_settings": Command(
        name="get_material_settings",
        handler=get_material_settings.get_material_settings,
        params=get_material_settings.PARAMS,
        requires_mpfb=True,
        summary=get_material_settings.SUMMARY),
    "get_mpfb_status": Command(
        name="get_mpfb_status",
        handler=get_mpfb_status.get_mpfb_status,
        params=get_mpfb_status.PARAMS,
        # False, and the first migrated command for which it is. This is the
        # command whose whole value is that MPFB's absence is a successful
        # answer, so it must not be gated on the thing it reports about - and
        # note the name, which breaks the otherwise exact tool-to-command
        # correspondence on purpose. ``get_status`` below is about *this
        # add-on*; this one is about *MPFB*, and two commands answering
        # "status" about two different pieces of software would be a collision
        # that is cheap now and permanent later.
        requires_mpfb=False,
        summary=get_mpfb_status.SUMMARY),
    "get_object_info": Command(
        name="get_object_info",
        handler=get_object_info.get_object_info,
        params=get_object_info.PARAMS,
        requires_mpfb=True,
        summary=get_object_info.SUMMARY),
    "get_pose": Command(
        name="get_pose",
        handler=get_pose.get_pose,
        params=get_pose.PARAMS,
        requires_mpfb=True,
        summary=get_pose.SUMMARY),
    "get_pose_controls": Command(
        name="get_pose_controls",
        handler=get_pose_controls.get_pose_controls,
        params=get_pose_controls.PARAMS,
        requires_mpfb=True,
        summary=get_pose_controls.SUMMARY),
    "get_rigify_hand_shape": Command(
        name="get_rigify_hand_shape",
        handler=get_rigify_hand_shape.get_rigify_hand_shape,
        params=get_rigify_hand_shape.PARAMS,
        requires_mpfb=True,
        summary=get_rigify_hand_shape.SUMMARY),
    "get_target_stack": Command(
        name="get_target_stack",
        handler=get_target_stack.get_target_stack,
        params=get_target_stack.PARAMS,
        requires_mpfb=True,
        summary=get_target_stack.SUMMARY),
    "get_status": Command(
        name="get_status",
        handler=get_status.get_status,
        params=get_status.PARAMS,
        # False, and one of very few. This is the command that answers what is
        # wrong when everything else cannot run, so it must not be gated on the
        # thing it reports about.
        requires_mpfb=False,
        summary=get_status.SUMMARY),
    "list_asset_materials": Command(
        name="list_asset_materials",
        handler=list_asset_materials.list_asset_materials,
        params=list_asset_materials.PARAMS,
        requires_mpfb=True,
        summary=list_asset_materials.SUMMARY),
    "list_assets": Command(
        name="list_assets",
        handler=list_assets.list_assets,
        params=list_assets.PARAMS,
        requires_mpfb=True,
        summary=list_assets.SUMMARY),
    "list_commands": Command(
        name="list_commands",
        handler=list_commands.list_commands,
        params=list_commands.PARAMS,
        # False for the same reason: what this add-on can do does not depend on
        # whether MPFB finished starting, and a client discovering the interface
        # against a broken install should still get an answer.
        requires_mpfb=False,
        summary=list_commands.SUMMARY),
    "list_expressions": Command(
        name="list_expressions",
        handler=list_expressions.list_expressions,
        params=list_expressions.PARAMS,
        requires_mpfb=True,
        summary=list_expressions.SUMMARY),
    "list_objects": Command(
        name="list_objects",
        handler=list_objects.list_objects,
        params=list_objects.PARAMS,
        # True, and the first in this table. Everything this command can say is
        # read out of MPFB's ObjectService, so a Blender without MPFB has no
        # answer to give - and "no MakeHuman objects in this scene" would be a
        # plausible-looking lie rather than a missing answer.
        requires_mpfb=True,
        summary=list_objects.SUMMARY),
    "list_presets": Command(
        name="list_presets",
        handler=list_presets.list_presets,
        params=list_presets.PARAMS,
        requires_mpfb=True,
        summary=list_presets.SUMMARY),
    "list_rigs": Command(
        name="list_rigs",
        handler=list_rigs.list_rigs,
        params=list_rigs.PARAMS,
        requires_mpfb=True,
        summary=list_rigs.SUMMARY),
    "list_targets": Command(
        name="list_targets",
        handler=list_targets.list_targets,
        params=list_targets.PARAMS,
        requires_mpfb=True,
        summary=list_targets.SUMMARY),
    "list_urls": Command(
        name="list_urls",
        handler=list_urls.list_urls,
        params=list_urls.PARAMS,
        # False, and the third command for which it is. "Where do I download
        # MPFB" is asked most often by somebody whose MPFB is not working, so a
        # command gated on MPFB would refuse exactly when its answer is most
        # valuable.
        requires_mpfb=False,
        summary=list_urls.SUMMARY),
    "place_character": Command(
        name="place_character",
        handler=place_character.place_character,
        params=place_character.PARAMS,
        requires_mpfb=True,
        summary=place_character.SUMMARY),
    "refit_human": Command(
        name="refit_human",
        handler=refit_human.refit_human,
        params=refit_human.PARAMS,
        requires_mpfb=True,
        summary=refit_human.SUMMARY),
    "remove_asset": Command(
        name="remove_asset",
        handler=remove_asset.remove_asset,
        params=remove_asset.PARAMS,
        requires_mpfb=True,
        summary=remove_asset.SUMMARY),
    "reset_pose": Command(
        name="reset_pose",
        handler=reset_pose.reset_pose,
        params=reset_pose.PARAMS,
        requires_mpfb=True,
        summary=reset_pose.SUMMARY),
    "save_expression": Command(
        name="save_expression",
        handler=save_expression.save_expression,
        params=save_expression.PARAMS,
        requires_mpfb=True,
        summary=save_expression.SUMMARY),
    "save_preset": Command(
        name="save_preset",
        handler=save_preset.save_preset,
        params=save_preset.PARAMS,
        requires_mpfb=True,
        summary=save_preset.SUMMARY),
    "set_asset_material": Command(
        name="set_asset_material",
        handler=set_asset_material.set_asset_material,
        params=set_asset_material.PARAMS,
        requires_mpfb=True,
        summary=set_asset_material.SUMMARY),
    "set_face_units": Command(
        name="set_face_units",
        handler=set_face_units.set_face_units,
        params=set_face_units.PARAMS,
        requires_mpfb=True,
        summary=set_face_units.SUMMARY),
    "set_macro_details": Command(
        name="set_macro_details",
        handler=set_macro_details.set_macro_details,
        params=set_macro_details.PARAMS,
        requires_mpfb=True,
        summary=set_macro_details.SUMMARY),
    "set_material_settings": Command(
        name="set_material_settings",
        handler=set_material_settings.set_material_settings,
        params=set_material_settings.PARAMS,
        requires_mpfb=True,
        summary=set_material_settings.SUMMARY),
    "set_pose_bones": Command(
        name="set_pose_bones",
        handler=set_pose_bones.set_pose_bones,
        params=set_pose_bones.PARAMS,
        requires_mpfb=True,
        summary=set_pose_bones.SUMMARY),
    "set_pose_switches": Command(
        name="set_pose_switches",
        handler=set_pose_switches.set_pose_switches,
        params=set_pose_switches.PARAMS,
        requires_mpfb=True,
        summary=set_pose_switches.SUMMARY),
    "set_rigify_hand_shape": Command(
        name="set_rigify_hand_shape",
        handler=set_rigify_hand_shape.set_rigify_hand_shape,
        params=set_rigify_hand_shape.PARAMS,
        requires_mpfb=True,
        summary=set_rigify_hand_shape.SUMMARY),
    "set_skin": Command(
        name="set_skin",
        handler=set_skin.set_skin,
        params=set_skin.PARAMS,
        requires_mpfb=True,
        summary=set_skin.SUMMARY),
    "set_targets": Command(
        name="set_targets",
        handler=set_targets.set_targets,
        params=set_targets.PARAMS,
        requires_mpfb=True,
        summary=set_targets.SUMMARY),
    "symmetrize_targets": Command(
        name="symmetrize_targets",
        handler=symmetrize_targets.symmetrize_targets,
        params=symmetrize_targets.PARAMS,
        requires_mpfb=True,
        summary=symmetrize_targets.SUMMARY),
}
