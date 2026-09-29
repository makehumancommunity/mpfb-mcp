"""
``get_material_settings``: the procedural material settings a preset would save.

Three materials MPFB builds without a file - procedural eyes, the layered skin
and the MakeSkin colour adjustment on hair and garments - come out the same
every time, and MPFB serializes all three when it saves a preset. This command
reads them **the way the serializer does**, section for section, so that what it
calls a setting is what ``HumanService.serialize_to_json_string()`` would write,
under the same keys: ``eyes_material_settings``, ``skin_material_settings`` and
``color_adjustments``. The bridge test for this command compares the two.

Everything about finding the nodes, choosing the sockets, reading ranges and
links and deriving the sRGB hex is in
[`shared/material_settings.py`](../shared/material_settings.py), which
``set_material_settings`` and ``get_character_summary`` use too, so the three
cannot disagree about which socket is which.

**Every section is always present**, and one that does not apply says why in
``reason`` rather than being empty: an empty ``settings`` would read as "a
material with nothing to set", which is a different claim from "no procedural
eyes". A section left out by ``section`` is ``null``, which is the
[`null` versus empty rule](../../../specifications/responses.md#response-shape):
not computed, rather than none.

**``section`` exists because of a measurement, not in advance of one**
([FR 040](../../../feature-requests/done/040-procedural-material-settings/README.md),
requirement 7). A character with procedural eyes, a layered skin and six mesh
assets answers 22 KB, of which the skin's nine groups are 16 KB; the request set
16 KB as the line past which a filter is owed, per
[how tools bound a large answer](../../../specifications/responses.md#how-tools-bound-a-large-answer).

Changes nothing and loads nothing. Reading a node's default values is a read of
the ``.blend``; no selection, mode or active object is borrowed.
"""

__all__ = (
    "PARAMS",
    "SECTIONS",
    "SUMMARY",
    "get_material_settings",
)

from ..log import get_logger
from ..shared import material_settings
from ..shared import mpfb_surface
from ..shared import subject_resolution
from ..validation import Param
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getmaterialsettings")

# The preset's three keys, shortened the way the request and the write name them.
SECTIONS = ("eyes", "skin", "color_adjustments")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("section", TYPE_STRING, default=None, nullable=True, choices=SECTIONS,
          description="Read one section only; the others are reported as null. Omit or pass "
                      "null for all three."),
)

SUMMARY = ("Read a character's procedural eye, layered skin and colour-adjustment settings, "
           "as a preset would save them.")

# What a command that writes needs and an answer must not carry: the nodes.
_NODE_KEYS = ("node", "nodes")


def reportable(section):
    """``section`` without the node references a writing command keeps, or ``None``."""
    if section is None:
        return None
    return {key: value for key, value in section.items() if key not in _NODE_KEYS}


def _message_for(basemesh, eyes, skin, records):
    parts = ["Material settings of '{:s}':".format(basemesh.name)]
    if eyes is not None:
        parts.append(" procedural eyes" if eyes["applies"]
                     else " no procedural eyes ({:s})".format(eyes["reason"]))
    if skin is not None:
        parts.append("{:s} layered skin".format(";" if eyes is not None else "")
                     if skin["applies"]
                     else "{:s} no layered skin ({:s})".format(
                         ";" if eyes is not None else "", skin["reason"]))
    if records is not None:
        applying = [record for record in records if record["applies"]]
        parts.append("{:s} {:d} of {:d} mesh asset(s) carry a colour adjustment a preset "
                     "saves".format(";" if (eyes is not None or skin is not None) else "",
                                    len(applying), len(records)))
    parts.append(".")
    linked = 0
    for section in [eyes] + ([] if skin is None or not skin["applies"]
                             else list(skin["groups"].values())):
        if section is not None and section.get("linked"):
            linked += len(section["linked"])
    if linked:
        parts.append(" {:d} socket(s) are linked and cannot be written; see 'linked'.".format(
            linked))
    return "".join(parts)


def get_material_settings(params, resolution):
    """Read the three sections a preset saves, the way it saves them."""
    services = resolution.services
    requested_name = params["name"]
    requested_section = params["section"]

    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, requested_name, not_a_character="it has no material settings to read")

    if basemesh is None:
        _LOG.debug("get_material_settings: no basemesh resolved from %r", requested_name)
        return dict(
            found=False,
            blocked_by="subject_not_found",
            subject_name=None if subject is None else subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=None,
            requested_section=requested_section,
            eyes=None,
            skin=None,
            color_adjustments=None,
            message=message,
        )

    def wanted(section):
        return requested_section is None or requested_section == section

    eyes = reportable(material_settings.eyes_section(services, basemesh)) \
        if wanted("eyes") else None
    skin = reportable(material_settings.skin_section(services, basemesh)) \
        if wanted("skin") else None
    records = None
    if wanted("color_adjustments"):
        records = [reportable(record) for record in material_settings.color_adjustment_records(
            services, mpfb_surface.general_object_properties(services), basemesh)]

    _LOG.debug("get_material_settings: %r, section %r", basemesh.name, requested_section)

    return dict(
        found=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        requested_section=requested_section,
        eyes=eyes,
        skin=skin,
        color_adjustments=records,
        message=_message_for(basemesh, eyes, skin, records),
    )
