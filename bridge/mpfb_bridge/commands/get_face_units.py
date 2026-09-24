"""
``get_face_units``: what a character's face is doing right now.

Reads the 52 ARKit ``!ex-`` shape keys ``FaceService.read_current_expression()``
always returns, one entry per unit, and answers ``0.0`` for a unit whose shape
key has never been touched exactly the way MPFB does - so a neutral face and a
face whose targets were once loaded and zeroed read identically. What
distinguishes them, when it can be known at all, is ``shapekey_present``: a unit
backed by a real shape key on the mesh versus one MPFB is reporting a default
for because there is nothing on the mesh to read.

**Two things are reported on every call, found or not, because neither depends
on resolving a subject.** ``known_face_units`` is the vocabulary
``mpfb_set_face_units`` will accept, grouped by ``FACEUNIT_REGIONS`` exactly as
MPFB's own composer panel lays out its slider boxes - returned here rather than
carried in every tool description, which is what keeps this package's
description budget from paying 52 names twice. ``faceunits01_installed`` is the
one signal that tells a caller whether an all-zero answer means "neutral face"
or "the asset pack behind these units was never installed", which MPFB's own
``set_expression``/``read_current_expression`` give no way to tell apart -
MPFB's panels handle it by not drawing themselves, which an MCP tool inherits
nothing from. See
[mpfb-integration.md](../../../specifications/mpfb-integration.md#mpfb-caches-what-it-scans-and-a-tool-says-what-that-costs-and-what-it-hides)
for the caching rule ``refresh`` busts.

Changes nothing. In particular this never loads a target or creates a shape
key - unlike ``mpfb_set_face_units``, reading a face unit that has never been
touched costs nothing and touches no file.

The behaviours above are **MPFB's, reproduced rather than tidied up**: the
zero-for-missing convention, the region grouping and the installed-probe cache
all come straight from ``FaceService``, read off the handle the bootstrap
already provides rather than copied into a fragment of this add-on's own.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_face_units",
)

from ..log import get_logger
from ..shared import mpfb_surface
from ..shared import subject_resolution
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getfaceunits")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("include_zero", TYPE_BOOLEAN, default=False,
          description="Include every one of the 52 ARKit face units, not only the ones "
                      "currently non-zero."),
    Param("refresh", TYPE_BOOLEAN, default=False,
          description="Bust FaceService's cached probe for the faceunits01 asset pack before "
                      "answering. Nothing invalidates that cache automatically, so a pack "
                      "installed since this Blender started reads as absent without it."),
)

SUMMARY = "Read the ARKit face units currently applied to a character's face."


def _shapekey_present(target_service, basemesh, face_unit_name):
    shape_key_name = target_service.expression_name_to_shapekey_name(face_unit_name)
    if basemesh.data.shape_keys is None or basemesh.data.shape_keys.key_blocks is None:
        return False
    return basemesh.data.shape_keys.key_blocks.get(shape_key_name) is not None


def _message_for(basemesh, count, total, installed):
    parts = ["Read {:d} of 52 ARKit face unit(s) from basemesh '{:s}'".format(
        total, basemesh.name)]
    if count < total:
        parts.append(", {:d} of them non-zero".format(count))
    parts.append(".")
    if not installed:
        parts.append(
            " The faceunits01 asset pack does not appear to be installed, so every value below "
            "is 0.0 regardless of whether the character's face has been composed before; this "
            "may be reporting an absent pack rather than a neutral face.")
    return "".join(parts)


def get_face_units(params, resolution):
    """Read one character's live ARKit face-unit values, and the vocabulary itself."""
    services = resolution.services
    face_service = services["FaceService"]
    target_service = services["TargetService"]
    # Required, not read with a fallback: the 52 units are on every answer, and
    # a stale copy of them presented as MPFB's would be worse than a failure.
    arkit_faceunits = mpfb_surface.required_module_level(
        services, "FaceService", "ARKIT_FACEUNITS")
    faceunit_regions = mpfb_surface.required_module_level(
        services, "FaceService", "FACEUNIT_REGIONS")

    requested_name = params["name"]
    include_zero = params["include_zero"]
    refresh = params["refresh"]

    installed = bool(face_service.is_faceunits01_installed(force_recheck=refresh))
    known_face_units = {
        region: list(names) for region, names in faceunit_regions.items()
    }

    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, requested_name, not_a_character="it has no face to read")

    if basemesh is None:
        _LOG.debug("get_face_units: no basemesh resolved from %r", requested_name)
        return dict(
            found=False,
            subject_name=None if subject is None else subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=None,
            face_units=[],
            face_unit_count=0,
            total_count=len(arkit_faceunits),
            include_zero=include_zero,
            known_face_units=known_face_units,
            faceunits01_installed=installed,
            message=message,
        )

    current = face_service.read_current_expression(basemesh)

    entries = []
    for face_unit_name in arkit_faceunits:
        weight = float(current.get(face_unit_name, 0.0))
        if weight == 0.0 and not include_zero:
            continue
        entries.append(dict(
            face_unit=face_unit_name,
            weight=round(weight, 6),
            shapekey_present=_shapekey_present(target_service, basemesh, face_unit_name),
        ))

    total = len(arkit_faceunits)
    _LOG.debug("get_face_units: %d/%d units reported, installed=%r",
               len(entries), total, installed)

    return dict(
        found=True,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        face_units=entries,
        face_unit_count=len(entries),
        total_count=total,
        include_zero=include_zero,
        known_face_units=known_face_units,
        faceunits01_installed=installed,
        message=_message_for(basemesh, len(entries), total, installed),
    )
