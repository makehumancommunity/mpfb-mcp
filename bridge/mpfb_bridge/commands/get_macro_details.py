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

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
, and three of its decisions are the ones a reimplementation would undo:

- **Nothing is recalculated.** ``reapply_macro_details()`` is deliberately not
  called, so a character whose properties and shape have drifted apart is
  *reported* as drifted rather than quietly repaired by a command the caller
  believed to be read-only. The drift is the finding.
- **The macro shape keys are read undecoded**, and their decoded spellings are
  reported beside them. Every macro shape key is stored under an encoded name
  like ``$md-$as-$fe-$yn``, which is also what ``macro_target_stack`` reports -
  so a decoded-only listing would agree with the stack on nothing and the
  comparison the answer invites would report drift on a healthy character.
- **The values come through ``TargetService``**, not off the properties by
  hand, so the shape of the dict is MPFB's and stays MPFB's. The property set is
  reached only for ``is_human_project``, which ``TargetService`` has no
  accessor for.

``HumanObjectProperties`` is a ``BlenderConfigSet`` living on humanservice.py's
module rather than a service in ``SERVICES``, so it is reached through the
module of a service that already imported it - never by importing an MPFB
submodule, several of which create directories on import.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_macro_details",
)

import sys

import bpy

from ..log import get_logger
from ..validation import Param
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getmacrodetails")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family - the basemesh, its rig, a garment. "
                      "Omit or pass null to use whatever object is currently active."),
)

SUMMARY = "Read one character's macro phenotype: the eleven sliders, and the shape keys they imply."

RACE_NAMES = ("asian", "caucasian", "african")

# How far the three race weights may stray from summing to 1.0 before it is
# worth saying so. MPFB treats them as independent and does not normalise.
_RACE_SUM_TOLERANCE = 0.001


def _as_float(value):
    """One property value as a plain float, or ``None``.

    Blender hands back its own float type for a ``FloatProperty``. It survives
    ``json.dumps``, but coercing here keeps the answer's contract - a number,
    never a Blender object - true whatever MPFB stores in future.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _macro_details_of(target_service, basemesh):
    """The nested dict MPFB itself uses, with every value coerced to a float."""
    raw = target_service.get_macro_info_dict_from_basemesh(basemesh)
    details = dict()
    for key in raw:
        if key == "race":
            details["race"] = dict(
                (race_name, _as_float(raw["race"].get(race_name)))
                for race_name in raw["race"]
            )
        else:
            details[key] = _as_float(raw[key])
    return details


def _race_sum_of(macro_details):
    total = 0.0
    for race_name in RACE_NAMES:
        weight = macro_details.get("race", dict()).get(race_name)
        if weight is not None:
            total += weight
    return round(total, 6)


def _target_stack_entries(target_service, macro_details):
    """What the current values mean in target terms, named both ways.

    ``calculate_target_stack_from_macro_info_dict()`` answers with file
    fragments such as ``macrodetails/caucasian-female-young``. The shape key
    MPFB builds from one is the encoded ``$md-$ca-$fe-$yn``, and the two are
    reported side by side precisely so that neither is mistaken for an address a
    tool accepts: a macro target is reached by moving a slider, never by name.
    """
    entries = []
    for component in target_service.calculate_target_stack_from_macro_info_dict(macro_details):
        fragment = str(component[0])
        entries.append(dict(
            target_fragment=fragment,
            shapekey_name=str(target_service.macrodetail_filename_to_shapekey_name(
                fragment, encode_name=True)),
            weight=_as_float(component[1]),
        ))
    return entries


def _is_human_project_of(services, basemesh):
    """MPFB's own flag for "this was built as a character", or ``None``."""
    humanservice_module = sys.modules[services["HumanService"].__module__]
    human_properties = getattr(humanservice_module, "HumanObjectProperties", None)
    if human_properties is None:
        return None
    return bool(human_properties.get_value("is_human_project", entity_reference=basemesh))


def _resolve_basemesh(services, requested_name):
    """The basemesh to read, the object asked about, and the sentence on a miss."""
    if requested_name is None:
        # The view layer rather than bpy.context.active_object, for the reason
        # given in get_object_info: this runs from a timer, not an operator.
        subject = bpy.context.view_layer.objects.active
        if subject is None:
            return (None, None,
                    "No object name was given and no object is active in this Blender session. "
                    "Select a MakeHuman object, or call mpfb_list_objects and pass one of its "
                    "names.")
    else:
        # bpy.data.objects rather than the scene: object names are unique across
        # the whole .blend, and an object outside the current scene still has
        # readable macro details.
        subject = bpy.data.objects.get(requested_name)
        if subject is None:
            return (None, None,
                    "No object named '{:s}' exists in this .blend file. Call mpfb_list_objects "
                    "to see what the current scene holds.".format(str(requested_name)))

    # The same call MPFB's own macro panel makes, which is what lets the caller
    # pass the name of the rig or of a shirt rather than having to know which
    # object owns the properties.
    basemesh = services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
        subject, "Basemesh")
    if basemesh is None:
        return (None, subject,
                "'{:s}' has no MakeHuman basemesh among its nearest relatives, so it is not part "
                "of a character with macro details. Call mpfb_get_object_info to see what it is "
                "related to.".format(subject.name))
    return (basemesh, subject, None)


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
    if abs(race_sum - 1.0) > _RACE_SUM_TOLERANCE:
        parts.append(
            " The three race weights sum to {:s} rather than 1.0. That is legal in MPFB, which "
            "treats them as independent, but it scales the phenotype.".format(str(race_sum)))
    return "".join(parts)


def get_macro_details(params, resolution):
    """Read one character's macro phenotype, and say whether it still fits its shape."""
    services = resolution.services
    target_service = services["TargetService"]

    requested_name = params["name"]
    subject_resolved_by = "active" if requested_name is None else "name"
    basemesh, subject, message = _resolve_basemesh(services, requested_name)

    if basemesh is None:
        _LOG.debug("get_macro_details: no basemesh resolved from %r", requested_name)
        return dict(
            found=False,
            subject_name=None if subject is None else subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=None,
            message=message,
        )

    macro_details = _macro_details_of(target_service, basemesh)
    race_sum = _race_sum_of(macro_details)
    stack = _target_stack_entries(target_service, macro_details)
    current_macro_shapekeys = [
        str(name) for name in target_service.get_current_macro_targets(basemesh, decode_names=False)
    ]
    current_macro_shapekeys_decoded = [
        str(target_service.decode_shapekey_name(name)) for name in current_macro_shapekeys
    ]
    has_shapekeys = bool(target_service.has_any_shapekey(basemesh))

    return dict(
        found=True,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        basemesh_in_current_scene=basemesh.name in bpy.context.scene.objects,
        is_human_project=_is_human_project_of(services, basemesh),
        has_shapekeys=has_shapekeys,
        macro_details=macro_details,
        default_macro_details=target_service.get_default_macro_info_dict(),
        race_sum=race_sum,
        race_normalized=abs(race_sum - 1.0) <= _RACE_SUM_TOLERANCE,
        macro_target_stack=stack,
        macro_target_count=len(stack),
        current_macro_shapekeys=current_macro_shapekeys,
        current_macro_shapekeys_decoded=current_macro_shapekeys_decoded,
        message=_message_for(
            basemesh, has_shapekeys, len(stack), len(current_macro_shapekeys), race_sum),
    )
