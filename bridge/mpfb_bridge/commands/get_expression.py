"""
``get_expression``: which saved expressions a character is wearing, and whether
that explains its face.

Reads the applied-expressions stack MPFB keeps on the basemesh as the custom
property ``mpfb_applied_expressions`` - one ``{asset, weight}`` row per
expression, sorted by asset - and reports it as ``{fragment, weight}`` rows,
each resolved against the disk the way a rebuild would resolve it.

**The reason this command exists is the comparison**, which MPFB makes nowhere:
does the stack account for the face? The composer writes the ``!ex-`` shape
keys directly and the library re-derives them from the stack, clearing first,
so a face composed on top of the stack is destroyed by the next library call
and nothing says so. ``matches_stack`` and ``unexplained_face_units`` are that
comparison, computed by
[`shared/expression_divergence.py`](../shared/expression_divergence.py) so that
``apply_expressions`` and ``set_face_units`` report exactly the same thing.
When the set is non-empty the answer names ``mpfb_save_expression`` as what
keeps it.

**Two things MPFB drops silently are reported.** A stack row whose file is gone
(``resolved: false``, counted in ``unresolved_count``): a character loaded from
a preset built on another machine is quietly wearing less expression than its
stack claims. And a unit whose sum across rows left ``[0, 1]``
(``clamped_face_units``): MPFB clamps without saying so, and a caller raising a
weight that has saturated sees nothing change.

**The live face-unit values are not restated.** They are
``get_face_units``' answer, and two commands reporting the same 52 numbers is
two answers that can disagree. This reports the aggregate the stack implies and
the difference from what is live - the live value appears only for a unit that
differs.

Changes nothing: reads a custom property, loads each stack row's JSON, reads
shape key values. It never loads a target.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_expression",
)

from ..log import get_logger
from ..shared import subject_resolution
from ..shared.expression_divergence import divergence
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getexpression")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use "
                      "whatever object is currently active."),
    Param("refresh", TYPE_BOOLEAN, default=False,
          description="Bust FaceService's cached probe for the faceunits01 asset pack before "
                      "answering."),
)

SUMMARY = ("Read a character's applied-expressions stack, and whether it explains the "
           "character's live face.")


def _message_for(basemesh, compared, installed):
    rows = compared["applied_expressions"]
    if rows:
        parts = ["Basemesh '{:s}' is wearing {:d} saved expression(s).".format(
            basemesh.name, len(rows))]
    else:
        parts = ["Basemesh '{:s}' is wearing no saved expression.".format(basemesh.name)]
    if compared["unresolved_count"]:
        parts.append(" {:d} of them cannot be found or read on this machine and contribute "
                     "nothing to the face.".format(compared["unresolved_count"]))
    if compared["clamped_face_units"]:
        parts.append(" {:d} face unit(s) sum past 1.0 across the stack and are clamped; see "
                     "clamped_face_units.".format(len(compared["clamped_face_units"])))
    if compared["matches_stack"]:
        parts.append(" The live face is exactly what the stack produces.")
    elif not installed:
        parts.append(" The live face differs from what the stack produces, but the "
                     "faceunits01 asset pack does not appear to be installed, so no face-unit "
                     "shape key can exist to display it.")
    else:
        parts.append(
            " {:d} face unit(s) differ from what the stack produces - composed on top of it, "
            "most likely with mpfb_set_face_units. The next mpfb_apply_expressions call, or "
            "any preset load, will overwrite them; mpfb_save_expression keeps them as an "
            "expression file.".format(len(compared["unexplained_face_units"])))
    return "".join(parts)


def get_expression(params, resolution):
    """Report the stack, its aggregate, and what the stack does not explain."""
    services = resolution.services
    requested_name = params["name"]
    installed = bool(services["FaceService"].is_faceunits01_installed(
        force_recheck=params["refresh"]))

    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, requested_name, not_a_character="it has no expression to read")
    if basemesh is None:
        _LOG.debug("get_expression: no basemesh resolved from %r", requested_name)
        return dict(
            found=False,
            subject_name=None if subject is None else subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=None,
            applied_expressions=[],
            unresolved_count=0,
            aggregate={},
            clamped_face_units=[],
            matches_stack=None,
            unexplained_face_units=[],
            faceunits01_installed=installed,
            message=message,
        )

    compared = divergence(services, basemesh)
    _LOG.debug("get_expression: %d rows, matches_stack=%r",
               len(compared["applied_expressions"]), compared["matches_stack"])

    answer = dict(
        found=True,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        faceunits01_installed=installed,
        message=_message_for(basemesh, compared, installed),
    )
    answer.update(compared)
    return answer
