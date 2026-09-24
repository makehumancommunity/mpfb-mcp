"""
A character's phenotype, read exactly as it is stored.

**One implementation, imported by both commands that report it.** See
[`__init__.py`](__init__.py) for why this directory exists beside
``commands/``. ``get_macro_details`` reports everything here;
``get_character_summary`` reports a subset of it under the same names, and a
summary that read the phenotype its own way would be a second opinion the
caller has no means of settling. Which basemesh is read is not decided here:
both commands resolve their subject through
[`subject_resolution.py`](subject_resolution.py), like every other command
that takes one.

The eleven macro sliders - gender, age, muscle, weight, the three race weights
and the rest - are what make a MakeHuman character the body it is. They live as
properties on the basemesh, and the shape keys MPFB derives from them live
beside those properties without being tied to them. This reads both, and says
when they disagree.

The behaviours below are **MPFB's, reproduced rather than tidied up**, and
three of them are the ones a reimplementation would undo:

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

**``macro_drift`` is the one comparison made here rather than left to the
caller** ([FR 034](../../../feature-requests/done/034-character-summary/README.md)).
It is true when the macro shape keys on the mesh are not the ones the current
values imply: a different set of names, or a shape key whose value is not the
weight the stack gives it. The second half matters more than it looks. Moving
one slider from 0.5 to 0.6 without a recalculation usually changes no *name* -
both genders' targets are still in play - only their weights, so a comparison
of the two name lists alone would miss the commonest drift there is. The
values are compared within :data:`DRIFT_TOLERANCE`, since a shape key stores a
32-bit float. A mesh with no shape keys at all drifts whenever its values
imply any target, which is every mesh: the values describe a shape that is not
there.

``HumanObjectProperties`` is a ``BlenderConfigSet`` living on humanservice.py's
module rather than a service in ``SERVICES``, so it is reached through the
module of a service that already imported it - never by importing an MPFB
submodule, several of which create directories on import.
"""

__all__ = (
    "DRIFT_TOLERANCE",
    "RACE_NAMES",
    "RACE_SUM_TOLERANCE",
    "macro_details_of",
    "race_sum_of",
    "read_phenotype",
)

import sys

RACE_NAMES = ("asian", "caucasian", "african")

# How far the three race weights may stray from summing to 1.0 before it is
# worth saying so. MPFB treats them as independent and does not normalise.
RACE_SUM_TOLERANCE = 0.001

# How far a macro shape key's value may sit from the weight the stack gives it
# and still count as the one the values imply. A shape key stores a 32-bit
# float, so a weight of 0.165 reads back as 0.16500000655651093.
DRIFT_TOLERANCE = 0.0001


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


def macro_details_of(target_service, basemesh):
    """The nested dict MPFB itself uses, with every value coerced to a float.

    Public because ``set_macro_details`` reports the phenotype after a write,
    and what it reports must be what ``get_macro_details`` would read on the
    next call.
    """
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


def race_sum_of(macro_details):
    """The three race weights added up, rounded so that a sum is comparable."""
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


def _drifted(basemesh, stack, current_macro_shapekeys):
    """Whether the macro shape keys on the mesh are not the ones ``stack`` implies."""
    if sorted(entry["shapekey_name"] for entry in stack) != sorted(current_macro_shapekeys):
        return True
    key_blocks = basemesh.data.shape_keys.key_blocks if basemesh.data.shape_keys else None
    for entry in stack:
        block = key_blocks.get(entry["shapekey_name"]) if key_blocks is not None else None
        if block is None or entry["weight"] is None:
            return True
        if abs(float(block.value) - entry["weight"]) > DRIFT_TOLERANCE:
            return True
    return False


def read_phenotype(services, basemesh):
    """Everything about ``basemesh``'s phenotype that either command reports.

    A dict of ``macro_details``, ``default_macro_details``, ``race_sum``,
    ``race_normalized``, ``macro_target_stack``, ``current_macro_shapekeys``,
    ``current_macro_shapekeys_decoded``, ``has_shapekeys``,
    ``is_human_project`` and ``macro_drift``, under the names the answers use.
    """
    target_service = services["TargetService"]

    macro_details = macro_details_of(target_service, basemesh)
    race_sum = race_sum_of(macro_details)
    stack = _target_stack_entries(target_service, macro_details)
    current_macro_shapekeys = [
        str(name) for name in target_service.get_current_macro_targets(basemesh, decode_names=False)
    ]
    return dict(
        macro_details=macro_details,
        default_macro_details=target_service.get_default_macro_info_dict(),
        race_sum=race_sum,
        race_normalized=abs(race_sum - 1.0) <= RACE_SUM_TOLERANCE,
        macro_target_stack=stack,
        current_macro_shapekeys=current_macro_shapekeys,
        current_macro_shapekeys_decoded=[
            str(target_service.decode_shapekey_name(name)) for name in current_macro_shapekeys
        ],
        has_shapekeys=bool(target_service.has_any_shapekey(basemesh)),
        is_human_project=_is_human_project_of(services, basemesh),
        macro_drift=_drifted(basemesh, stack, current_macro_shapekeys),
    )
