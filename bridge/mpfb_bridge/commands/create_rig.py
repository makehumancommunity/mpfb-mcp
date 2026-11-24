"""
``create_rig``: a bone table, built onto a character by MPFB's own fitter.

**MPFB fits the bones** ([FR 060](../../../feature-requests/done/060-authoring-rigs/README.md)).
The table is resolved against this body by
[`shared/rig_definition.py`](../shared/rig_definition.py) into MPFB's own bone format, a
``Rig`` is made from it in memory and ``create_armature_and_fit_to_basemesh(for_developer=True)``
builds the armature. ``for_developer`` is what makes MPFB save each end's strategy on the bone,
which is what ``Rig.from_given_armature_context()`` - and so ``store_rig`` - reads back, and
what ``get_rig_definition`` reads as ``definition_from: "armature"``. No position is computed
here from ``mesh.vertices[].co``: a joint, a vertex and a mean are where MPFB's position info
puts them, with the shape keys evaluated.

**This replaces MakeRig's "Load rig" and nothing calls it**, per
[mpfb-integration.md](../../../specifications/mpfb-integration.md#a-third-party-add-ons-ui-operators-are-reimplemented-never-called).
Its body is ``Rig.from_json_file_and_basemesh()`` and the same fitting call; the departures:

- **A table, not a file.** The ``Rig`` is given its header and definition directly, so no
  temporary file is written. ``from_json_file_and_basemesh()``'s upgrade step is
  version-gated and a version-110 header needs none, which a bridge test holds.
- **Parenting is ``add_custom_rig()``'s, not the operator's.** The rig is named
  ``<basemesh>.rig``, its rotation mode normalised, the basemesh parented and moved to the
  origin under it, and - as ``add_rig`` does since FR 045 - a turned basemesh's rotation moved
  to the rig, which MPFB drops.
- **``use_deform`` is written.** MPFB's format has no such key, so every bone it builds
  deforms; the table's ``deform: false`` is set on the bone afterwards, and ``store_rig`` names
  it as a flag the library file will lose.
- **The armature is stamped as authored**, so that ``replace`` and ``weight_rig`` can tell
  it from a shipped rig after a store has made it ``custom.*``.

**All or nothing.** Every end is resolved before anything is touched, and an error anywhere
is ``resolution_failed`` with every error listed. A build that raises removes what it
created. ``replace`` is the one exception: the old rig is taken off before the new one is
built, because MPFB fits to the basemesh's own place and the old rig is in the way, so a
build that fails after that leaves the character unrigged, and the answer says so.

**On a rebuild, weights that still mean the same thing are kept.** A bone whose name and
both ends' strategies (anchor and offset) are unchanged keeps its vertex group; every other
group of the old rig's bones is removed. Both are listed. Nothing else on the body is
touched, masks included.

**Equipping comes after rigging, and this cannot change that.** Every asset already on the
character is named in ``assets_not_rigged``, exactly as ``add_rig`` names them, because
nothing rigs an asset after the fact.
"""

__all__ = (
    "MAX_BONES",
    "PARAMS",
    "SUMMARY",
    "create_rig",
)

import bpy
from mathutils import Quaternion  # pylint: disable=import-error

from ..log import get_logger
from ..shared import blender_data
from ..shared import placement
from ..shared import rig_definition
from ..shared import selection
from ..shared import subject_resolution
from ..shared import view_layer
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.createrig")

# Far above any deform skeleton and above every rig MPFB ships (the default is 163), so that
# a shipped rig read back with get_rig_definition is always a table this accepts.
MAX_BONES = 1000

_ROTATION_NOISE_RADIANS = 1e-6

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("bones", TYPE_ARRAY, required=True,
          description="The bone table: name, parent, head, tail and optionally roll, deform, "
                      "connect, collections. Each end is one of joint, vertex, mean or "
                      "position, with an optional offset."),
    Param("replace", TYPE_BOOLEAN, default=False,
          description="Rebuild over a rig this command built, or one identified as unknown. "
                      "A shipped or library rig is refused."),
)

SUMMARY = "Build a rig onto a character from a bone table, fitted by MPFB to the body's joints."

_NEXT_WITH = "mpfb_weight_rig"


def _answer(subject, resolved_by, basemesh, **fields):
    answer = dict(
        found=basemesh is not None,
        ready=False,
        created=False,
        blocked_by=None,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        rig_object_name=None,
    )
    answer.update(fields)
    return answer


def _replace_refusal(services, basemesh, existing, replace):
    """Why an existing rig stops this build, as ``(blocked_by, sentence, extra)``, or None."""
    identified = services["RigService"].identify_rig(existing)
    if not replace:
        return ("already_rigged",
                "'{:s}' already has the rig '{:s}' (identified as '{!s}'), so nothing was "
                "built. Pass replace=true to rebuild over a rig mpfb_create_rig made; MPFB has "
                "no way to swap any other.".format(basemesh.name, existing.name, identified),
                dict(existing_rig_object_name=existing.name,
                     existing_rig_identified_as=identified))
    if not rig_definition.is_authored(existing) and identified != "unknown":
        return ("rig_not_authored",
                "'{:s}' is the rig '{!s}', which mpfb_create_rig did not build, so it was not "
                "replaced. Read it with mpfb_get_rig_definition and build from that table onto a "
                "character with no rig.".format(existing.name, identified),
                dict(existing_rig_object_name=existing.name,
                     existing_rig_identified_as=identified))
    return None


def _kept_and_dropped(services, basemesh, existing, definition):
    """Which of the old rig's groups survive the rebuild. See the module docstring."""
    old, _saved = rig_definition.armature_definition(services, existing)
    kept = []
    dropped = []
    for bone_name, old_info in old.items():
        if bone_name not in basemesh.vertex_groups:
            continue
        new_info = definition.get(bone_name)
        same = new_info is not None and all(
            rig_definition.end_signature(old_info[key])
            == rig_definition.end_signature(new_info[key]) for key in ("head", "tail"))
        (kept if same else dropped).append(bone_name)
    return (sorted(kept), sorted(dropped))


def _take_off(existing, basemesh, dropped):
    """Remove the old rig, keeping every child where it stands, and the dropped groups."""
    for child in list(existing.children):
        world = child.matrix_world.copy()
        child.parent = None
        child.matrix_world = world
    for group_name in dropped:
        group = basemesh.vertex_groups.get(group_name)
        if group is not None:
            basemesh.vertex_groups.remove(group)
    data = existing.data
    bpy.data.objects.remove(existing, do_unlink=True)
    if data is not None and data.users == 0:
        bpy.data.armatures.remove(data)
    bpy.context.view_layer.update()


def _build(services, basemesh, header, notes):
    """Fit and parent the armature, returning it. Removes what it made if anything raises."""
    rig_service = services["RigService"]
    names_before = blender_data.object_names()
    rotation = placement.local_rotation(basemesh)
    rotation_moved = rotation.angle > _ROTATION_NOISE_RADIANS
    if rotation_moved:
        placement.set_local_rotation(basemesh, Quaternion())
        bpy.context.view_layer.update()
    try:
        with selection.restored_all():
            services["ObjectService"].activate_blender_object(basemesh)
            rig = rig_definition.fit_definition(services, basemesh, header)
            armature = rig.create_armature_and_fit_to_basemesh(for_developer=True)
            armature.name = armature.data.name = basemesh.name + ".rig"
            rig_service.normalize_rotation_mode(armature)
            basemesh.parent = armature
            armature.location = basemesh.location
            basemesh.location = (0.0, 0.0, 0.0)
        for bone_name, note in notes.items():
            armature.data.bones[bone_name].use_deform = note["deform"]
        rig_definition.mark_authored(armature)
        if rotation_moved:
            placement.set_local_rotation(armature, rotation)
        bpy.context.view_layer.update()
    except Exception:
        for name in blender_data.object_names() - names_before:
            leftover = bpy.data.objects.get(name)
            if leftover is not None:
                bpy.data.objects.remove(leftover, do_unlink=True)
        if basemesh.parent is None:
            placement.set_local_rotation(basemesh, rotation)
        raise
    return (armature, rotation_moved)


def _create_rig(params, resolution):  # pylint: disable=too-many-locals,too-many-return-statements
    services = resolution.services
    object_service = services["ObjectService"]
    basemesh, subject, resolved_by, message = subject_resolution.resolve_basemesh(
        services, params["name"], not_done="nothing was built",
        not_a_character="there is no body to build a rig onto")

    def blocked(reason, text, **extra):
        return with_performed(_answer(subject, resolved_by, basemesh, blocked_by=reason,
                                      message=text, **extra), False)

    if basemesh is None:
        return blocked("subject_not_found", message)
    shape_errors = rig_definition.table_shape_errors(params["bones"], MAX_BONES)
    if shape_errors:
        return blocked("invalid_table",
                       "The bone table is not well formed, so nothing was built: {:s}".format(
                           shape_errors[0]["message"]),
                       resolution_errors=shape_errors)

    existing = object_service.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")
    if existing is not None:
        refusal = _replace_refusal(services, basemesh, existing, params["replace"])
        if refusal is not None:
            return blocked(refusal[0], refusal[1], **refusal[2])
    if bpy.context.mode != "OBJECT" or basemesh.mode != "OBJECT":
        return blocked(
            "not_object_mode",
            "Blender is in {:s} mode, and building an armature runs operators that need OBJECT "
            "mode, so nothing was built. Leave edit mode and call again.".format(
                str(bpy.context.mode)))

    fit = rig_definition.fit_definition(services, basemesh, {"bones": {}, "version": 110})
    space = rig_definition.Space(basemesh, existing if existing is not None else basemesh)
    bones = [{key: value for key, value in bone.items()
              if key not in rig_definition.READ_ONLY_BONE_KEYS} for bone in params["bones"]]
    definition, notes, errors = rig_definition.resolve_table(
        fit, space, bones, len(basemesh.data.vertices), rig_definition.max_snap_metres(services))
    if errors:
        no_joints = not fit.position_info.get("cubes")
        return blocked(
            "resolution_failed",
            "{:d} end(s) could not be resolved against '{:s}', so nothing was built: {:s}{:s}"
            .format(len(errors), basemesh.name, errors[0]["message"],
                    ". This body has no joint cubes at all; a character created with "
                    "detailed_helpers off has none" if no_joints else ""),
            resolution_errors=errors)

    header = rig_definition.header_for(services, basemesh, definition)
    kept, dropped, replaced_name = [], [], None
    if existing is not None:
        kept, dropped = _kept_and_dropped(services, basemesh, existing, definition)
        replaced_name = existing.name
    groups_already_present = sorted(
        name for name in definition if name in basemesh.vertex_groups and name not in kept)
    assets_not_rigged = sorted(asset.name for asset in object_service.find_related_mesh_assets(
        basemesh) if asset is not basemesh)

    if existing is not None:
        _take_off(existing, basemesh, dropped)
    try:
        armature, rotation_moved = _build(services, basemesh, header, notes)
    except Exception:  # pylint: disable=broad-except
        if existing is None:
            raise
        _LOG.error("create_rig: rebuild failed after the old rig was removed", exc_info=True)
        return blocked(
            "build_failed",
            "MPFB's fitter raised after the rig '{:s}' had been taken off, so '{:s}' is now "
            "unrigged. The groups in weights_kept are still on it.".format(
                replaced_name, basemesh.name),
            old_rig_removed=True, weights_kept=kept, weights_dropped=dropped)

    built, _saved = rig_definition.armature_definition(services, armature)
    frame_space = rig_definition.Space(basemesh, armature)

    def locate(bone_name, key, _end_info):
        bone = armature.data.bones[bone_name]
        return frame_space.armature_to_local(
            armature, bone.head_local if key == "head" else bone.tail_local)

    rows, _features = rig_definition.read_bones(built, frame_space, locate)
    snapped = {name: note["snapped_to"] for name, note in notes.items() if note["snapped_to"]}
    fixed = ["{:s}.{:s}".format(name, key) for name, note in notes.items()
             for key in note["fixed_ends"]]
    not_deforming = sorted(name for name, note in notes.items() if not note["deform"])
    parts = ["Built '{:s}' onto '{:s}' with {:d} bone(s){:s}.".format(
        armature.name, basemesh.name, len(rows),
        "" if replaced_name is None else ", replacing '{:s}'".format(replaced_name))]
    if snapped:
        parts.append(" {:d} position end(s) snapped; see snapped_to.".format(
            sum(len(value) for value in snapped.values())))
    if fixed:
        parts.append(" {:d} end(s) are fixed positions that a refit will not move.".format(
            len(fixed)))
    if assets_not_rigged:
        parts.append(" {:d} asset(s) were on the character before the rig and are NOT rigged; "
                     "remove and re-add them.".format(len(assets_not_rigged)))
    parts.append(" Nothing is weighted yet: call {:s}.".format(_NEXT_WITH)
                 if not kept else " {:d} group(s) were kept from the old rig; weight the rest "
                 "with {:s}.".format(len(kept), _NEXT_WITH))
    _LOG.debug("create_rig: built %r with %d bones", armature.name, len(rows))
    return with_performed(_answer(
        subject, resolved_by, basemesh,
        ready=True,
        created=True,
        rig_object_name=armature.name,
        replaced=replaced_name is not None,
        replaced_rig_object_name=replaced_name,
        character_frame=frame_space.frame.describe(),
        bone_count=len(rows),
        bones=rows,
        snapped_to=snapped,
        ends_not_following_body=fixed,
        not_deforming=not_deforming,
        weights_kept=kept,
        weights_dropped=dropped,
        groups_already_present=groups_already_present,
        basemesh_rotation_moved_to_rig=rotation_moved,
        assets_not_rigged=assets_not_rigged,
        next_with={_NEXT_WITH: {"name": armature.name, "method": "automatic"}},
        message="".join(parts)), True)


def create_rig(params, resolution):
    """Build the rig, with the character in the view layer."""
    return view_layer.run(resolution.services, params["name"],
                          lambda: _create_rig(params, resolution))
