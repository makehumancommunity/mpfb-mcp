"""
``set_material_settings``: write procedural material settings, as one all-or-nothing batch.

The write half of ``get_material_settings``, and keyed the way a preset is:
``eyes`` entries name a socket on the procedural eye node, ``skin`` entries a
``group`` (the preset's key, ``color``, ``body``, ...) and a socket on it, and
``color_adjustments`` entries an ``object_name`` and a socket on the node
feeding its Base Color. Every section, node and socket is found by
[`shared/material_settings.py`](../shared/material_settings.py), the module the
read uses, so a socket the read reports is one this command can address and a
refusal here names a socket the read would show.

**The third batched command, after ``set_targets`` and ``set_face_units``, and
it resolves every entry before it writes any**, per
[a batched mutating tool resolves before it writes](../../../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes).
An entry fails resolution when its section does not apply, its group or socket
is not on the live node, its socket is **linked**, its key does not match the
socket's kind (``value`` for a float, ``color`` for a colour), or a float lies
outside the socket's declared range. One failure writes nothing.

**A linked socket is refused rather than written**, because writing one succeeds
and changes nothing: its value is whatever the link delivers. On the layered
skin that is almost every region colour - ``bodygroup``'s ``SkinColor`` comes
from ``colorgroup`` - so the refusal names the socket that drives it, and when
that is another serialized group, says which ``group`` and ``socket`` to write
instead. That is a refusal naming a different, writable target as its fix.

**The range check is against a clamp on a built-in node and against nothing on
a group node**, and it is made anyway. Blender clamps a built-in socket such as
``diffuseIntensity``'s ``Factor`` to its hard range and says nothing, so an
out-of-range value would be stored as something else; a group node's input it
stores exactly as given, because the range lives only on the node group's
interface, where it is what MPFB's own UI would let a user set. **One exception,
decided against the live install**: a socket whose current value already lies
outside its declared range - MPFB's own ``MpfbBody`` defaults
``NavelWidthMultiplier`` to 11.0 and declares 0.001-0.2 - is not held to it,
since the range is then contradicted by MPFB itself and enforcing it would
refuse MPFB's own neighbourhood of values.

**A colour is four finite, non-negative numbers, scene-linear RGBA.** Blender
clamps a negative component to zero and keeps one above 1.0, so a negative is
refused and a bright one is not. Alpha is required, because MPFB stores four and
a three-component colour is a caller who forgot it rather than one who meant 1.0.

**The writes are MPFB's**: ``NodeService.set_socket_default_values()`` for the
eyes and the skin groups, and ``MaterialService.apply_color_adjustment()`` for an
asset, which are what the deserializer calls when a preset is loaded. What this
command writes and what a preset restores therefore cannot differ in how they
are written.

**On an asset with an AO map, only the AO strength can be written.** The node
on its Base Color is ``aoMix``, whose colour inputs are both linked, so a
``Color1`` there is refused as linked - to the ``diffuseIntensity`` node MPFB
neither writes nor saves for such an asset (see
[`shared/material_settings.py`](../shared/material_settings.py)).

**Nothing is borrowed, so nothing is restored.** Writing a socket's default
value needs no active object, no selection and no mode, and the command touches
none of them. A written material shared with objects outside the section - an
export copy, another character - changes for them too, and ``materials_written``
names them.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "set_material_settings",
)

import difflib
import math

import bpy

from ..log import get_logger
from ..shared import material_settings
from ..shared import mpfb_surface
from ..shared import subject_resolution
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_STRING

_LOG = get_logger("commands.setmaterialsettings")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("eyes", TYPE_ARRAY, default=(),
          description="One object per socket on the procedural eye node: 'socket' and exactly "
                      "one of 'value' (a float socket) or 'color' (four scene-linear RGBA "
                      "numbers)."),
    Param("skin", TYPE_ARRAY, default=(),
          description="One object per socket on a layered skin group: 'group' (the preset's "
                      "key, e.g. 'color'), 'socket', and 'value' or 'color'."),
    Param("color_adjustments", TYPE_ARRAY, default=(),
          description="One object per socket on a mesh asset's colour adjustment node: "
                      "'object_name', 'socket', and 'value' or 'color'."),
)

SUMMARY = ("Write a character's procedural eye, layered skin and colour-adjustment settings, "
           "as one all-or-nothing batch.")

# What each section's entries address a socket by, besides the socket itself.
_OWNER_KEYS = {"eyes": None, "skin": "group", "color_adjustments": "object_name"}


def _is_number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _entry_shape_error(section, entry):
    """Why an entry is malformed, or ``None``. mpfb-mcp checks this too; other clients may not."""
    if not isinstance(entry, dict):
        return "an entry must be an object"
    owner = _OWNER_KEYS[section]
    allowed = ("socket", "value", "color") + (() if owner is None else (owner,))
    unknown = sorted(key for key in entry if key not in allowed)
    if unknown:
        return "unknown key(s) {:s}; known keys are {:s}".format(
            ", ".join(unknown), ", ".join(allowed))
    for key in ("socket",) + (() if owner is None else (owner,)):
        if not isinstance(entry.get(key), str) or not entry.get(key).strip():
            return "'{:s}' must be a non-empty string".format(key)
    if ("value" in entry) == ("color" in entry):
        return "exactly one of 'value' and 'color' is required"
    if "value" in entry and not _is_number(entry["value"]):
        return "'value' must be a finite number"
    if "color" in entry:
        color = entry["color"]
        if not isinstance(color, list) or not all(_is_number(channel) for channel in color):
            return "'color' must be a list of four finite numbers"
        if len(color) != 4:
            return "'color' must have four components, scene-linear RGBA; alpha is required"
        if any(channel < 0 for channel in color):
            return "'color' components must not be negative"
    return None


def _error(section, index, entry, reason, message, **extra):
    error = dict(section=section, index=index, reason=reason, message=message)
    if isinstance(entry, dict):
        for key in ("group", "object_name", "socket"):
            if key in entry:
                error[key] = entry[key]
    error.update(extra)
    return error


def _fix_for_link(link, skin):
    """The group and socket that drive a linked skin socket, when a preset saves them."""
    if skin is None or not skin["applies"]:
        return None
    for group, node in skin["nodes"].items():
        if node.name == link["from_node"]:
            return dict(group=group, socket=link["from_socket"])
    return None


def _resolve_socket(section, index, entry, node, report, skin):
    """One entry against one node's report: the write it implies, or an error."""
    socket_name = entry["socket"]
    settings = report["settings"]
    if socket_name not in settings:
        return (None, _error(
            section, index, entry, "unknown_socket",
            "'{:s}' has no socket called '{:s}' that a preset saves.".format(
                node.name, socket_name),
            closest=difflib.get_close_matches(socket_name, list(settings), n=3, cutoff=0.5)))

    link = report["linked"].get(socket_name)
    if link is not None:
        fix = _fix_for_link(link, skin) if section == "skin" else None
        instead = (" Set group '{:s}' socket '{:s}' instead.".format(fix["group"], fix["socket"])
                   if fix is not None else "")
        return (None, _error(
            section, index, entry, "linked_socket",
            "'{:s}' on '{:s}' is driven by '{:s}' on '{:s}', so writing it would change "
            "nothing.{:s}".format(socket_name, node.name, link["from_socket"],
                                  link["from_node"], instead),
            linked_from=link, write_instead=fix))

    current = settings[socket_name]
    if material_settings.is_color(current) != ("color" in entry):
        wanted, given = ("color", "value") if material_settings.is_color(current) \
            else ("value", "color")
        return (None, _error(
            section, index, entry, "kind_mismatch",
            "'{:s}' is a {:s} socket, so the entry needs '{:s}' rather than '{:s}'.".format(
                socket_name, "colour" if wanted == "color" else "float", wanted, given)))

    if "value" in entry:
        value = float(entry["value"])
        bounds = report["ranges"].get(socket_name)
        if (material_settings.value_outside(value, bounds)
                and socket_name not in report["values_outside_range"]):
            return (None, _error(
                section, index, entry, "out_of_range",
                "'{:s}' on '{:s}' takes {!s} to {!s}, and {!r} is outside it.".format(
                    socket_name, node.name, bounds[0], bounds[1], value),
                range=bounds))
    else:
        value = [float(channel) for channel in entry["color"]]

    return (dict(section=section, index=index, node=node, socket=socket_name, value=value,
                 group=entry.get("group"), object_name=entry.get("object_name")), None)


def _not_applicable_error(section, index, entry, where, reason):
    return _error(section, index, entry, "section_not_applicable",
                  "{:s} does not apply to this character ({:s}), so there is nothing to "
                  "write.".format(where, reason), section_reason=reason)


def _resolve(requested, eyes, skin, records):
    """Every entry resolved to a write, or the errors that stop the batch."""
    writes = []
    errors = []
    seen = set()
    by_object = {record["object_name"]: record for record in records or []}
    for section in ("eyes", "skin", "color_adjustments"):
        for index, entry in enumerate(requested[section]):
            shape = _entry_shape_error(section, entry)
            if shape is not None:
                errors.append(_error(section, index, entry, "invalid_entry", shape))
                continue
            owner = _OWNER_KEYS[section]
            key = (section, None if owner is None else entry[owner], entry["socket"])
            if key in seen:
                errors.append(_error(section, index, entry, "duplicate_entry",
                                     "The same socket is named twice in this call."))
                continue
            seen.add(key)

            if section == "eyes":
                if not eyes["applies"]:
                    errors.append(_not_applicable_error(section, index, entry,
                                                        "Procedural eyes", eyes["reason"]))
                    continue
                write, error = _resolve_socket(section, index, entry, eyes["node"], eyes, skin)
            elif section == "skin":
                if not skin["applies"]:
                    errors.append(_not_applicable_error(section, index, entry,
                                                        "A layered skin", skin["reason"]))
                    continue
                group = entry["group"]
                if group not in skin["groups"]:
                    errors.append(_error(
                        section, index, entry, "unknown_group",
                        "The layered skin has no group '{:s}' that a preset saves.".format(group),
                        known_groups=sorted(skin["groups"])))
                    continue
                write, error = _resolve_socket(section, index, entry, skin["nodes"][group],
                                               skin["groups"][group], skin)
            else:
                record = by_object.get(entry["object_name"])
                if record is None:
                    errors.append(_error(
                        section, index, entry, "object_not_found",
                        "'{:s}' is not a mesh asset of this character.".format(
                            entry["object_name"]),
                        known_object_names=sorted(by_object)))
                    continue
                if not record["applies"]:
                    errors.append(_not_applicable_error(
                        section, index, entry,
                        "A colour adjustment on '{:s}'".format(record["object_name"]),
                        record["reason"]))
                    continue
                write, error = _resolve_socket(section, index, entry, record["node"], record,
                                               skin)
            if error is not None:
                errors.append(error)
            else:
                writes.append(write)
    return (writes, errors)


def _hex_or_none(value):
    return material_settings.srgb_hex(value) if material_settings.is_color(value) else None


def _apply(services, writes):
    """Every write, one MPFB call per node, and the changes in request order."""
    node_service = services["NodeService"]
    by_node = {}
    for write in writes:
        by_node.setdefault(write["node"].as_pointer(), []).append(write)

    before = {}
    for pointer, node_writes in by_node.items():
        node = node_writes[0]["node"]
        before[pointer] = node_service.get_socket_default_values(node)

    for pointer, node_writes in by_node.items():
        values = {write["socket"]: write["value"] for write in node_writes}
        first = node_writes[0]
        if first["section"] == "color_adjustments":
            services["MaterialService"].apply_color_adjustment(
                bpy.data.objects[first["object_name"]], values)
        else:
            node_service.set_socket_default_values(first["node"], values)

    changes = []
    for write in sorted(writes, key=lambda write: (
            ("eyes", "skin", "color_adjustments").index(write["section"]), write["index"])):
        pointer = write["node"].as_pointer()
        after = node_service.get_socket_default_values(write["node"])
        previous = _preset_value(before[pointer][write["socket"]])
        new = _preset_value(after[write["socket"]])
        change = dict(section=write["section"], index=write["index"])
        if write["group"] is not None:
            change["group"] = write["group"]
        if write["object_name"] is not None:
            change["object_name"] = write["object_name"]
        change.update(
            socket=write["socket"],
            node_name=write["node"].name,
            previous_value=previous,
            new_value=new,
            previous_srgb_hex=_hex_or_none(previous),
            new_srgb_hex=_hex_or_none(new),
        )
        changes.append(change)
    return changes


def _preset_value(value):
    if isinstance(value, (list, tuple)):
        return [float(channel) for channel in value]
    return float(value)


def _materials_written(writes, eyes, skin, records):
    """One entry per material written: which object's it is, and who else uses it."""
    written = []
    sections = set(write["section"] for write in writes)
    if "eyes" in sections:
        written.append(dict(material_name=eyes["material_name"], object_name=eyes["object_name"],
                            material_shared_with=eyes["material_shared_with"]))
    if "skin" in sections:
        written.append(dict(material_name=skin["material_name"], object_name=skin["object_name"],
                            material_shared_with=skin["material_shared_with"]))
    objects = []
    for write in writes:
        if write["section"] == "color_adjustments" and write["object_name"] not in objects:
            objects.append(write["object_name"])
    by_object = {record["object_name"]: record for record in records or []}
    for object_name in objects:
        record = by_object[object_name]
        written.append(dict(material_name=record["material_name"], object_name=object_name,
                            material_shared_with=record["material_shared_with"]))
    return written


def _base(subject, subject_resolved_by, basemesh):
    return dict(
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
    )


def set_material_settings(params, resolution):  # pylint: disable=too-many-locals
    """Resolve every entry, then write all of them through MPFB or none."""
    services = resolution.services
    requested_name = params["name"]
    requested = {section: list(params[section]) for section in _OWNER_KEYS}
    requested_count = sum(len(entries) for entries in requested.values())

    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, requested_name,
        not_done="nothing was changed",
        not_a_character="it has no material settings to write")

    if basemesh is None:
        _LOG.debug("set_material_settings: no basemesh resolved from %r", requested_name)
        answer = dict(found=False, ready=False, blocked_by="subject_not_found")
        answer.update(_base(subject, subject_resolved_by, None))
        answer.update(changes=[], change_count=0, resolution_errors=[], materials_written=[],
                      message=message)
        return with_performed(answer, False)

    answer = dict(found=True, ready=True, blocked_by=None)
    answer.update(_base(subject, subject_resolved_by, basemesh))

    if requested_count == 0:
        answer.update(changes=[], change_count=0, resolution_errors=[], materials_written=[],
                      message="Neither 'eyes', 'skin' nor 'color_adjustments' named anything, "
                              "so nothing was changed. Call mpfb_get_material_settings to see "
                              "what can be set.")
        return with_performed(answer, False)

    # Only the sections named are read. A linked eye or asset socket is never
    # driven by a skin group, so the skin is not needed to word their refusals.
    eyes = material_settings.eyes_section(services, basemesh) if requested["eyes"] else None
    skin = material_settings.skin_section(services, basemesh) if requested["skin"] else None
    records = material_settings.color_adjustment_records(
        services, mpfb_surface.general_object_properties(services), basemesh) \
        if requested["color_adjustments"] else None

    writes, errors = _resolve(requested, eyes, skin, records)
    if errors:
        answer.update(
            changes=[], change_count=0, resolution_errors=errors, materials_written=[],
            message="{:d} of {:d} entr{:s} could not be resolved, so **nothing at all was "
                    "written**. Fix the entries in 'resolution_errors' and send the whole batch "
                    "again.".format(len(errors), requested_count,
                                    "y" if requested_count == 1 else "ies"))
        return with_performed(answer, False)

    changes = _apply(services, writes)
    materials = _materials_written(writes, eyes, skin, records)
    shared = sorted(set(name for material in materials
                        for name in material["material_shared_with"]))

    _LOG.debug("set_material_settings: %d change(s) to %r", len(changes), basemesh.name)

    answer.update(
        changes=changes,
        change_count=len(changes),
        resolution_errors=[],
        materials_written=materials,
        message="Wrote {:d} socket(s) on {:d} material(s) of '{:s}'.{:s}".format(
            len(changes), len(materials), basemesh.name,
            "" if not shared else " The same material(s) are also used by {:s}, which changed "
                                  "too.".format(", ".join(shared))),
    )
    return with_performed(answer, changes)
