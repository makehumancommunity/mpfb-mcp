"""
``get_macro_details``: a character's phenotype, exactly as it is stored.

The eleven macro sliders - gender, age, muscle, weight, the three race weights
and the rest - are what make a MakeHuman character the body it is. They live as
properties on the basemesh, and the shape keys MPFB derives from them live
beside those properties without being tied to them. This reports both, and says
when they disagree.

**The subject may be any object in the character's family.** The basemesh is
resolved from it the way MPFB's own macro panel does, so a caller may pass the
name of the rig or of a shirt - the names ``list_objects`` hands out - rather
than having to know which object owns the properties. The answer names the
object the values were actually read from. Failing to resolve one is a
successful answer, not an error.

**How the phenotype is read is not in this module.** It is in
[`shared/macro_reading.py`](../shared/macro_reading.py), with the three
decisions a reimplementation would undo - nothing is recalculated, the macro
shape keys are read undecoded, the values come through ``TargetService`` -
because ``get_character_summary`` reports a subset of this answer
([FR 034](../../../feature-requests/done/034-character-summary/README.md)). The
subject is resolved by [`shared/subject_resolution.py`](../shared/subject_resolution.py),
as every command's is. What is left here is the answer's shape and its message.

``macro_drift`` is the one field that answers the comparison
``macro_target_stack`` and ``current_macro_shapekeys`` invite, rather than
leaving it to the caller; it arrived with FR 034, so that the summary reports
nothing this command does not.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_macro_details",
)

import bpy

from ..log import get_logger
from ..shared import macro_reading
from ..shared import subject_resolution
from ..validation import Param
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getmacrodetails")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family - the basemesh, its rig, a garment. "
                      "Omit or pass null to use whatever object is currently active."),
)

SUMMARY = "Read one character's macro phenotype: the eleven sliders, and the shape keys they imply."


def _message_for(basemesh, has_shapekeys, stack_length, shapekey_count, race_sum):
    """What is worth saying about this reading before the numbers are read."""
    parts = ["Read macro details from basemesh '{:s}'.".format(basemesh.name)]
    if not has_shapekeys:
        parts.append(
            " This mesh carries macro properties but has no shape keys at all, so the values "
            "below describe nothing: it was tagged as a basemesh rather than built by MPFB.")
    elif stack_length != shapekey_count:
        # Not a proof of drift - the two lists can differ in content at equal
        # length - but the cheap half of the check, and the half worth saying
        # out loud, since the caller can compare the lists themselves.
        parts.append(
            " The macro targets these values imply and the macro shape keys actually on the mesh "
            "differ in number, so the character's properties and its shape have drifted apart. "
            "Calling mpfb_set_macro_details repairs that.")
    if abs(race_sum - 1.0) > macro_reading.RACE_SUM_TOLERANCE:
        parts.append(
            " The three race weights sum to {:s} rather than 1.0. That is legal in MPFB, which "
            "treats them as independent, but it scales the phenotype.".format(str(race_sum)))
    return "".join(parts)


def get_macro_details(params, resolution):
    """Read one character's macro phenotype, and say whether it still fits its shape."""
    services = resolution.services

    requested_name = params["name"]
    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, requested_name,
        not_a_character="it is not part of a character with macro details")

    if basemesh is None:
        _LOG.debug("get_macro_details: no basemesh resolved from %r", requested_name)
        return dict(
            found=False,
            subject_name=None if subject is None else subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=None,
            message=message,
        )

    phenotype = macro_reading.read_phenotype(services, basemesh)
    stack = phenotype["macro_target_stack"]

    return dict(
        found=True,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        basemesh_in_current_scene=basemesh.name in bpy.context.scene.objects,
        is_human_project=phenotype["is_human_project"],
        has_shapekeys=phenotype["has_shapekeys"],
        macro_details=phenotype["macro_details"],
        default_macro_details=phenotype["default_macro_details"],
        race_sum=phenotype["race_sum"],
        race_normalized=phenotype["race_normalized"],
        macro_target_stack=stack,
        macro_target_count=len(stack),
        current_macro_shapekeys=phenotype["current_macro_shapekeys"],
        current_macro_shapekeys_decoded=phenotype["current_macro_shapekeys_decoded"],
        macro_drift=phenotype["macro_drift"],
        message=_message_for(
            basemesh, phenotype["has_shapekeys"], len(stack),
            len(phenotype["current_macro_shapekeys"]), phenotype["race_sum"]),
    )
