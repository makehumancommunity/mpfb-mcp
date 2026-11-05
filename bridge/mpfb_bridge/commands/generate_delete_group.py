"""
``generate_delete_group``: which of a body's vertices a garment hides, and how that stands.

**Replacing MPFB's result rather than reproducing it, which is why the rule about reproducing
quirks does not apply**
([why](../../../specifications/mpfb-integration.md#replacing-a-result-rather-than-reproducing-it)).
``mpfb.makeclothes_gendelete`` calls its own result "very rough", tells the user to edit it by hand
and refuses any garment with a modifier, which includes MPFB's own Subdivision. The panel has no
second opinion to agree with. What is compatible with MPFB here is the group's name and what it
holds, which ``mpfb_write_mesh_asset`` writes as ``delete_verts``. The algorithm is in
``shared/delete_group.py``, whose docstring has the reasons.

**The group as it was before the first run is kept as ``<group>.original``, and that is the undo**,
since a list of 3,209 vertices is about 20 KB and cannot be a ``restore_with``
([the rule](../../../specifications/mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list)).
It is also what makes this rerunnable: a group that only grows cannot be tuned, so ``merge`` starts
from it every time, whatever the last run left. Nothing else in MPFB reads a vertex group by that
name, which the request's live check confirmed through an export and a written MHCLO.

**It adds no modifier**, as the panel adds none: on the authoring body a Mask modifier is a choice,
and MPFB adds one when it loads the asset. ``mask_modifier_present`` says whether this body has one.

**A posed character is refused and a turned one is not**, against
[FR 050](../../../feature-requests/done/050-writing-mesh-assets/README.md), which refuses both. The
request left this to be provoked. Posing a thigh changes the group, since skin moves against a
garment fitted at rest. A turn changes nothing, by construction: everything is read in the body's
own frame, and ``bbb_shared/delete_group_test.py`` holds the two claims.

**The object's ``delete_group`` property is not touched.** A group named here that differs from it
is a warning, because ``mpfb_write_mesh_asset`` will otherwise write the other one.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "generate_delete_group",
)

import math

import bpy
import numpy

from ..log import get_logger
from ..shared import delete_group
from ..shared import mpfb_surface
from ..shared import pose_reading
from ..shared import subject_resolution
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_OBJECT
from ..validation import TYPE_STRING

_LOG = get_logger("commands.generatedeletegroup")

_MODES = ("merge", "replace")

_ORIGINAL_SUFFIX = ".original"

# Blender truncates a vertex group's name to this many bytes, silently.
_GROUP_NAME_BYTES = 63

# Rows of openings in one answer, longest first. A suit has 24, most of them buttons.
_MAX_OPENINGS = 30

_MAX_NAMED_BONES = 10

_NOT_DONE = "nothing was changed"

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="The garment. Omit or pass null to use whatever object is currently active."),
    Param("basemesh", TYPE_STRING, default=None, nullable=True,
          description="The body. Omit to find it among the garment's relatives, then the "
                      "selection, then the file."),
    Param("delete_group", TYPE_STRING, default=None, nullable=True,
          description="The body's vertex group to generate. Omit to take the garment's."),
    Param("mode", TYPE_STRING, default="merge", choices=_MODES,
          description="'merge' keeps the members from before the first run; 'replace' starts empty."),
    Param("margins", TYPE_OBJECT, default=None, nullable=True,
          description="Metres of skin to keep beside an open edge, per kind of opening, overriding "
                      "that kind's default: 'trunk', 'cuff', 'hem'. Never changes a classification."),
    Param("dry_run", TYPE_BOOLEAN, default=False,
          description="Work out and report everything, and write nothing."),
)

SUMMARY = "Generate a garment's delete group on its body, and say how each failure mode stands."


def _answer(params, **fields):
    answer = dict(found=True, ready=False, generated=False, blocked_by=None,
                  dry_run=params["dry_run"], mode=params["mode"], subject_name=None,
                  subject_resolved_by=None, message=None, warnings=[])
    answer.update(fields)
    return answer


def _margins_refusal(margins):
    """A sentence for a ``margins`` mpfb-mcp should have refused first, or ``None``."""
    for kind, value in (margins or dict()).items():
        if kind not in delete_group.DEFAULT_MARGINS:
            return "margins knows only {:s}, got '{!s}'.".format(
                ", ".join(sorted(delete_group.DEFAULT_MARGINS)), kind)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or value <= 0.0):
            return "margins' '{:s}' must be a finite number above 0, got {!r}.".format(kind, value)
    return None


def _group_settled(root_name, params, subject):
    """``(name, resolved_by, refusal)``. ``refusal`` is ``(blocked_by, sentence)``, or ``None``."""
    named = params["delete_group"]
    if named is not None:
        name, resolved_by = (named, "argument")
    else:
        properties = mpfb_surface.make_clothes_properties(root_name)
        if properties is None:
            raise mpfb_surface.MissingFromMpfb(
                "MPFB's MakeClothes properties are not loaded, so this command cannot read the "
                "garment's delete group. Pass delete_group, and check mpfb_get_status.")
        name = mpfb_surface.property_value(properties, "delete_group", subject)
        full_name = properties.get_fullname_key_from_shortname_key("delete_group")
        resolved_by = "object" if subject.is_property_set(full_name) else "mpfb_default"
    if not name:
        return (None, None, ("delete_group_required",
                             "'{:s}' names no delete group, so pass delete_group.".format(
                                 subject.name)))
    if name.endswith(_ORIGINAL_SUFFIX):
        return (name, resolved_by, (
            "group_is_a_kept_original",
            "'{:s}' is what an earlier run kept as the undo, and writing to it would lose that, "
            "so {:s}. Name the group it was kept from.".format(name, _NOT_DONE)))
    if len((name + _ORIGINAL_SUFFIX).encode("utf8")) > _GROUP_NAME_BYTES:
        return (name, resolved_by, (
            "group_name_too_long",
            "'{0:s}{1:s}' would not fit in Blender's {2:d} bytes, and it would silently be another "
            "name, so {3:s}. Use a shorter group.".format(
                name, _ORIGINAL_SUFFIX, _GROUP_NAME_BYTES, _NOT_DONE)))
    return (name, resolved_by, None)


def _state_refusal(body, subject):
    """A state in which the answer would be wrong, or ``(blocked_by, sentence, extra)``."""
    if bpy.context.mode != "OBJECT":
        return ("not_in_object_mode",
                "Blender is in {:s} mode, in which a mesh's vertex groups are not what its data "
                "says, so {:s}. Switch to object mode and call again.".format(
                    str(bpy.context.mode), _NOT_DONE), dict())
    if delete_group.BODY_GROUP not in body.vertex_groups:
        return ("no_body_group",
                "'{:s}' has no vertex group '{:s}', which is what says what is skin, so {:s}.".format(
                    body.name, delete_group.BODY_GROUP, _NOT_DONE), dict())
    if not any(group.name.startswith(delete_group.JOINT_PREFIX) for group in body.vertex_groups):
        return ("no_joint_groups",
                "'{:s}' has no '{:s}*' vertex groups, which is how a limb is told from a trunk at "
                "an opening, so {:s}. A character created with detailed_helpers off has none.".format(
                    body.name, delete_group.JOINT_PREFIX, _NOT_DONE), dict())
    pose_reading.evaluated()
    for rig in pose_reading.rigs_deforming(subject, body):
        posed = pose_reading.deforming_bones_off_rest(rig)
        if posed:
            return ("rig_not_at_rest",
                    "'{:s}' has {:d} deforming bone(s) off rest, and a group worked out on a pose "
                    "fits that pose, so {:s}. mpfb_reset_pose puts it back, and its restore_with "
                    "returns the pose afterwards.".format(rig.name, len(posed), _NOT_DONE),
                    dict(rig_name=rig.name, posed_bone_count=len(posed),
                         posed_bones=posed[:_MAX_NAMED_BONES]))
    return None


def _opening_row(opening):
    return dict(kind=opening.kind, reason=opening.reason, centre=delete_group.rounded_centre(opening),
                margin=opening.margin, limbs=opening.limbs, vertices=opening.vertices,
                perimeter=round(opening.perimeter, 3), open_share=round(opening.open_share, 3),
                kept_by_margin=opening.kept_by_margin)


def _write(body, group_name, original_name, current, new, original_members):
    """The group, and the kept original if there is none yet. Leaves the active group alone."""
    vertex_groups = body.vertex_groups
    active = vertex_groups.active_index
    all_vertices = list(range(len(body.data.vertices)))
    if original_name not in vertex_groups:
        kept = vertex_groups.new(name=original_name)
        kept.add(numpy.flatnonzero(original_members).tolist(), 1.0, "REPLACE")
    group = vertex_groups.get(group_name)
    if group is None:
        group = vertex_groups.new(name=group_name)
    if current.any():
        group.remove(all_vertices)
    group.add(numpy.flatnonzero(new).tolist(), 1.0, "REPLACE")
    vertex_groups.active_index = active


def _warnings_for(request_group, object_group, reading, openings, new, under_nothing):
    warnings = []
    if object_group is not None and object_group != request_group:
        warnings.append("The garment's delete group is '{:s}', so mpfb_write_mesh_asset will write "
                        "that one unless told delete_group='{:s}'.".format(
                            object_group, request_group))
    if reading.closed_component_sizes:
        warnings.append("{:d} of the garment's parts are closed shells, with no boundary to say "
                        "where their openings are, so no margin applies to them and skin under them "
                        "is kept wherever a sight line reaches it.".format(
                            len(reading.closed_component_sizes)))
    if not openings and not reading.closed_component_sizes:
        warnings.append("The garment has no boundary at all and no closed part, which should not "
                        "happen.")
    if under_nothing:
        warnings.append("No skin lies under this garment within reach, so the group has no new "
                        "members. Is it on this body?")
    if not new.any():
        warnings.append("The group would be empty, and an asset written with it hides nothing.")
    return warnings


def _message_for(params, subject, group_name, before, after, slits, under):
    return ("{:s} '{:s}' for '{:s}': {:d} vertices, from {:d}. On a character it is loaded on, "
            "{:d} removed face(s) can be seen and {:d} standing face(s) lie under the "
            "garment.".format(
                "Would generate" if params["dry_run"] else "Generated", group_name, subject.name,
                after, before, slits, under))


def generate_delete_group(params, resolution):  # pylint: disable=too-many-locals,too-many-return-statements
    """Settle every refusal, read, generate, measure, then write."""
    services = resolution.services
    root_name = resolution.module.__name__

    def blocked(reason, message, **extra):
        return with_performed(_answer(params, blocked_by=reason, message=message, **extra), False)

    subject, resolved_by, message = subject_resolution.resolve_subject(
        params["name"], not_done=_NOT_DONE, select="the garment")
    if subject is None:
        return with_performed(_answer(params, found=False, blocked_by="subject_not_found",
                                      subject_resolved_by=resolved_by, message=message), False)
    fields = dict(subject_name=subject.name, subject_resolved_by=resolved_by)
    if subject.type != "MESH":
        return blocked("not_a_mesh", "'{:s}' is a {:s}, not a mesh, so nothing can be under it.".format(
            subject.name, str(subject.type)), **fields)
    if services["ObjectService"].object_is_basemesh(subject):
        return blocked("subject_is_basemesh",
                       "'{:s}' is the basemesh, which is what a garment hides rather than a "
                       "garment. Name the garment.".format(subject.name), **fields)

    sentence = _margins_refusal(params["margins"])
    if sentence is not None:
        # Defence in depth: mpfb-mcp refuses this before sending.
        return blocked("invalid_margins", sentence, **fields)

    body, body_resolved_by, refusal = subject_resolution.resolve_asset_body(
        services, params["basemesh"], subject, "for it to hide", _NOT_DONE)
    if refusal is not None:
        return blocked(refusal[0], refusal[1], candidates=refusal[2], **fields)
    fields.update(basemesh_name=body.name, basemesh_resolved_by=body_resolved_by)

    group_name, group_resolved_by, refused = _group_settled(root_name, params, subject)
    fields.update(delete_group=group_name, delete_group_resolved_by=group_resolved_by)
    if refused is not None:
        return blocked(refused[0], refused[1], **fields)

    state = _state_refusal(body, subject)
    if state is not None:
        return blocked(state[0], state[1], **dict(fields, **state[2]))

    reading, read_refusal = delete_group.read(body, subject)
    if read_refusal is not None:
        return blocked(read_refusal[0], "{:s} So {:s}.".format(read_refusal[1], _NOT_DONE), **fields)

    margins = dict(delete_group.DEFAULT_MARGINS)
    margins.update(params["margins"] or dict())

    no_one = numpy.zeros(len(reading.points), dtype=bool)
    group = body.vertex_groups.get(group_name)
    original_name = group_name + _ORIGINAL_SUFFIX
    original = body.vertex_groups.get(original_name)
    current = no_one if group is None else reading.members(group.index)
    kept_members = current if original is None else reading.members(original.index)
    base = kept_members if params["mode"] == "merge" else no_one

    new, openings = delete_group.generate(reading, base, margins)
    slits, under, slits_here = delete_group.measure(reading, new, openings)

    if not params["dry_run"]:
        _write(body, group_name, original_name, current, new, kept_members)

    object_properties = mpfb_surface.make_clothes_properties(root_name)
    object_group = (None if object_properties is None
                    else mpfb_surface.property_value(object_properties, "delete_group", subject))
    before = int(current.sum())
    after = int(new.sum())
    written = not params["dry_run"]
    _LOG.debug("generate_delete_group: %r %d -> %d dry_run=%r", group_name, before, after,
               params["dry_run"])
    return with_performed(_answer(
        params,
        ready=True,
        generated=written,
        group_created=written and group is None,
        vertices_before=before,
        vertices_after=after,
        added=int((new & ~current).sum()),
        removed=int((current & ~new).sum()),
        masked_skin_still_visible=slits,
        unmasked_skin_under_garment=under,
        masked_skin_still_visible_authoring=slits_here,
        openings=[_opening_row(opening) for opening in openings[:_MAX_OPENINGS]],
        openings_total=len(openings),
        margins=margins,
        closed_components=len(reading.closed_component_sizes),
        original_kept_as=original_name if written or original is not None else None,
        original_vertices=int(kept_members.sum()),
        mask_modifier_present=any(
            modifier.type == "MASK" and str(modifier.vertex_group) == group_name
            for modifier in body.modifiers),
        warnings=_warnings_for(group_name, object_group, reading, openings, new,
                               not (new & ~base).any()),
        message=_message_for(params, subject, group_name, before, after, slits, under),
        **fields), written)
