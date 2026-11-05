"""
``check_mesh_asset``: whether a mesh is ready to be written as an asset, in numbers.

MPFB's validator looks at vertex groups, scale and face type, and said
``all_checks_ok: true`` for a draft with inward normals and a coat through the
hakama, the body and itself. Everything measured is in
[`shared/mesh_asset_report.py`](../shared/mesh_asset_report.py), so that FR 050's
write answer can carry a summary of the same reading. This is which mesh, which
body, and which sections.

**Named for what MakeClothes writes.** The
[glossary](../../../specifications/tool-interface.md#the-glossary) keeps "clothes"
for quoting MPFB, and MakeClothes writes all three kinds of mesh asset.

**The body is found the way a panel would, in a fixed order.** A named ``basemesh``;
else one among the mesh's nearest relatives, which is how the macro and rig panels
find one; else the one selected, which is how MakeClothes' own panel does; else the
only one in the file. Several at the last two is a refusal, because a fit against
the wrong body reads as a bad fit. ``basemesh_resolved_by`` says which it was. The
mesh need not be marked as an asset, since checking one before it is marked is the
point, and ``object_type`` says what it is marked as, if anything.

**MPFB's validator returns early on mixed faces, and everything else is still
measured**, since a mesh with a mix of triangles and quads can still have its normals
checked. It took 7.9 s when there was no xref cache, since it then builds the basemesh's
tables itself.

**The order inside the handler matters.** ``write_state`` is read before the
validator, which can create the very directory that state reports on. The bridge
tests hold both to leaving nothing behind.

Changes nothing that can be observed afterwards, selection and active object included.
"""

__all__ = (
    "PARAMS",
    "SECTIONS",
    "SUMMARY",
    "check_mesh_asset",
)

import bpy

from ..log import get_logger
from ..shared import mesh_asset_report
from ..shared import mesh_overlap
from ..shared import mpfb_surface
from ..shared import subject_resolution
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_STRING

_LOG = get_logger("commands.checkmeshasset")

SECTIONS = ("validator", "components", "uv", "textures", "metadata", "write_state")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="The mesh being checked. Omit or pass null to use whatever object is "
                      "currently active."),
    Param("basemesh", TYPE_STRING, default=None, nullable=True,
          description="The body to measure it against. Omit to find it among the mesh's "
                      "relatives, then the selection, then the file."),
    Param("sections", TYPE_ARRAY, default=None, nullable=True,
          description="Which sections to measure, from: {:s}. The others are reported as null. "
                      "Omit for all of them.".format(", ".join(SECTIONS))),
)

SUMMARY = "Measure whether a mesh is ready to be written as an asset: fit, normals, UVs, textures."


def _refused(found, reason, message, subject, resolved_by, **extra):
    answer = dict(found=found, ready=False, blocked_by=reason,
                  subject_name=None if subject is None else subject.name,
                  subject_resolved_by=resolved_by, basemesh_name=None,
                  basemesh_resolved_by=None, object_type=None, requested_sections=None,
                  warnings=[], message=message)
    answer.update(dict.fromkeys(SECTIONS))
    answer.update(extra)
    return answer


def _resolved_body(services, requested, subject):
    """``(basemesh, resolved_by, refusal)``, in the order this module's docstring gives."""
    object_service = services["ObjectService"]
    if requested is not None:
        body, _resolved_by, message = subject_resolution.resolve_subject(requested)
        if body is None:
            return (None, None, ("basemesh_not_found", message, []))
        if not object_service.object_is_basemesh(body):
            return (None, None, (
                "not_a_basemesh",
                "'{:s}' is not a MakeHuman basemesh, so there is no body to measure against. "
                "Call mpfb_list_objects with 'Basemesh' to see which there are.".format(body.name),
                []))
        return (body, "argument", None)

    relative = object_service.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    if relative is not None:
        return (relative, "relative", None)

    selected = [blender_object for blender_object in bpy.context.selected_objects
                if object_service.object_is_basemesh(blender_object)]
    if len(selected) == 1:
        return (selected[0], "selection", None)
    candidates = selected or [blender_object for blender_object in bpy.data.objects
                              if object_service.object_is_basemesh(blender_object)]
    if len(candidates) == 1:
        return (candidates[0], "only_basemesh", None)
    if not candidates:
        return (None, None, (
            "basemesh_not_found",
            "'{:s}' has no MakeHuman basemesh among its relatives and this file holds none, so "
            "there is no body to measure against.".format(subject.name), []))
    return (None, None, (
        "basemesh_ambiguous",
        "'{:s}' has no basemesh among its relatives and {:d} could be meant, so nothing was "
        "measured. Pass 'basemesh' naming one of 'candidates'.".format(
            subject.name, len(candidates)),
        sorted(blender_object.name for blender_object in candidates)))


def _validated_sections(requested):
    """The sections asked for and the ones that do not exist, in :data:`SECTIONS` order."""
    if requested is None:
        return (list(SECTIONS), [])
    return ([section for section in SECTIONS if section in requested],
            [section for section in requested if section not in SECTIONS])


def _warnings(subject, section_values):
    warnings = []
    if subject.mode != "OBJECT":
        warnings.append(
            "'{:s}' is in {:s} mode, so the validator reads its mesh data as of when that mode "
            "was entered, not the edits since, and 'uv' cannot be read.".format(
                subject.name, str(subject.mode)))
    validator_error = section_values.get("validator_error")
    if validator_error:
        warnings.append(validator_error)
    state = section_values.get("write_state")
    if state is not None:
        if state["subdiv_viewport_levels"] > 0:
            warnings.append(
                "Viewport subdivision is at level {:d}. MPFB's exporter writes the OBJ with "
                "modifiers applied and matches the MHCLO without them, so its panel would write "
                "an OBJ the MHCLO does not describe.".format(state["subdiv_viewport_levels"]))
        if not state["xref_cache_exists"]:
            warnings.append("MPFB's basemesh xref cache is not built, which writing an asset "
                            "needs.")
    if section_values.get("metadata") is not None:
        warnings.extend(mesh_asset_report.metadata_warnings(section_values["metadata"]))
    return warnings


def _message_for(subject, body, values, warnings):
    parts = ["Checked '{:s}' against '{:s}'.".format(subject.name, body.name)]
    report = values.get("validator")
    if report is not None:
        parts.append(" MPFB's validator says all_checks_ok is {!s}, which covers vertex groups, "
                     "scale and face type only.".format(bool(report.get("all_checks_ok"))))
    components = values.get("components")
    if components is not None and components["applies"]:
        parts.append(" {:d} connected component(s).".format(components["component_count"]))
    if warnings:
        parts.append(" {:d} warning(s); see 'warnings'.".format(len(warnings)))
    return "".join(parts)


def check_mesh_asset(params, resolution):
    """Resolve the mesh and the body, then read each section asked for."""
    services = resolution.services
    root_name = resolution.module.__name__

    subject, resolved_by, message = subject_resolution.resolve_subject(
        params["name"], select="the mesh to check")
    if subject is None:
        return _refused(False, "subject_not_found", message, None, resolved_by)
    if subject.type != "MESH":
        return _refused(True, "not_a_mesh",
                        "'{:s}' is a {:s}, not a mesh, so it cannot be an asset.".format(
                            subject.name, str(subject.type)), subject, resolved_by)
    if services["ObjectService"].object_is_basemesh(subject):
        return _refused(
            True, "subject_is_basemesh",
            "'{:s}' is the basemesh, which is what an asset is measured against rather than an "
            "asset. Name the mesh to check.".format(subject.name), subject, resolved_by)

    wanted, unknown = _validated_sections(params["sections"])
    if unknown:
        return _refused(True, "unknown_section",
                        "{:s} is not a section. They are: {:s}.".format(
                            ", ".join(str(name) for name in unknown), ", ".join(SECTIONS)),
                        subject, resolved_by, known_sections=list(SECTIONS))

    body, body_resolved_by, refusal = _resolved_body(services, params["basemesh"], subject)
    if refusal is not None:
        reason, sentence, candidates = refusal
        return _refused(True, reason, sentence, subject, resolved_by, candidates=candidates)

    values = dict()
    if "write_state" in wanted:
        values["write_state"] = mesh_asset_report.write_state(services, root_name, subject, body)
    if "validator" in wanted:
        values["validator"], values["validator_error"] = mesh_asset_report.validator(
            services, subject, body)
    if "components" in wanted:
        readings, unmeasured = mesh_overlap.read_all(
            [subject, body], {body.name}, with_groups=True)
        if subject.name in readings and body.name in readings:
            values["components"] = mesh_asset_report.component_report(
                readings[subject.name], readings[body.name],
                [str(group.name) for group in subject.vertex_groups])
        else:
            values["components"] = dict(
                applies=False,
                reason="Blender has no evaluated geometry for: {:s} ({:s}).".format(
                    ", ".join(entry.object_name for entry in unmeasured),
                    ", ".join(entry.reason for entry in unmeasured)))
    texture_rows = None
    if "textures" in wanted or "uv" in wanted:
        texture_rows = mesh_asset_report.textures(subject)
    if "textures" in wanted:
        values["textures"] = texture_rows
    if "uv" in wanted:
        values["uv"] = mesh_asset_report.uv_report(subject, texture_rows)
    if "metadata" in wanted:
        values["metadata"] = mesh_asset_report.metadata(services, root_name, subject)

    warnings = _warnings(subject, values)
    _LOG.debug("check_mesh_asset: %r against %r", subject.name, body.name)
    answer = dict(
        found=True,
        ready=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=resolved_by,
        basemesh_name=body.name,
        basemesh_resolved_by=body_resolved_by,
        object_type=mpfb_surface.property_value(
            mpfb_surface.general_object_properties(services), "object_type", subject),
        requested_sections=wanted,
        warnings=warnings,
        message=_message_for(subject, body, values, warnings),
    )
    for section in SECTIONS:
        answer[section] = values.get(section)
    return answer
