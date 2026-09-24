"""
``get_character_summary``: one character, one answer, never a second opinion.

Before an agent changes a character it has to know what the character already
is. That used to be five or six calls - the phenotype, the basemesh's
``get_object_info``, the rig's, the target stack, the face units, the
expression stack - each answering a different question at length. This is one
call that answers the question "what is this character, so that I can plan a
change to it", in an answer small enough to read every time.

**Every section is read by the implementation its detailed command uses**, out
of [`shared/`](../shared/__init__.py), and reported under that command's field
names:

- ``phenotype`` - [`macro_reading.py`](../shared/macro_reading.py), as
  ``get_macro_details``. The subject is resolved there too, so it resolves
  exactly as that command's does.
- ``rig``, ``assets`` and ``skin`` - [`asset_info.py`](../shared/asset_info.py),
  as ``get_object_info``: the rig's entry is the one ``get_object_info`` gives
  the rig among the basemesh's relatives, the assets are those relatives, and
  the skin is the basemesh's own ``asset_info``.
- ``targets`` - [`target_rollup.py`](../shared/target_rollup.py), as
  ``get_target_stack`` answers for its **default** arguments.
- ``face`` - ``FaceService.read_current_expression()`` as ``get_face_units``
  reads it, and
  [`expression_divergence.py`](../shared/expression_divergence.py) as
  ``get_expression`` reports it.

**So it reports no fact a detailed command does not.** It selects and it
counts; it does not derive. A finding that joined two sections - "the rig
cannot be refitted *and* there are garments on it" - was considered and left
out ([FR 034](../../../feature-requests/034-character-summary/README.md)): it
would be the one part of the answer the caller could not confirm with another
tool. And it is **never composed by calling the other commands' handlers**,
which would make its shape the union of five answers it then pruned, couple it
to their parameter defaults, and make one command a client of another -
something ``table.py``'s claim to be the whole vocabulary does not survive.

**Which object is "the rig"** is MPFB's answer, not this command's:
``find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")``, the
call MPFB's own refit and rig panels make. A garment's ``Subrig`` is never it.

**One cut, and it is said out loud.** The rollup is what grows with a
character: a heavily modelled one carries sixty non-zero categories and twenty
left/right differences, which alone is over the 8 KB this answer is meant to
fit in. So ``modifiers`` and ``asymmetries`` are capped at
:data:`MODIFIER_CAP` and :data:`ASYMMETRY_CAP`, keeping the entries whose
values are furthest from zero and reporting them in ``get_target_stack``'s own
order, so a capped list is still a sub-list of the detailed one.
``modifier_count`` and ``asymmetry_count`` count the whole rollup and
``rollup_truncated`` is always present, per
[how tools bound a large answer](../../../specifications/responses.md#how-tools-bound-a-large-answer);
the whole rollup is ``get_target_stack``'s. Nothing else is capped: a character
wears tens of things, not thousands.

Changes nothing: no recalculation, no refit, no selection change, and no cache
populated that a detailed command would not also populate - the only one it
touches is ``FaceService``'s ``faceunits01`` probe, which it reads and never
busts. A caller who suspects that cache calls ``mpfb_get_face_units`` with
``refresh``.
"""

__all__ = (
    "ASYMMETRY_CAP",
    "MODIFIER_CAP",
    "PARAMS",
    "SUMMARY",
    "get_character_summary",
)

import sys

from ..log import get_logger
from ..shared import asset_info
from ..shared import macro_reading
from ..shared import target_categories
from ..shared import target_rollup
from ..shared.expression_divergence import divergence
from ..validation import Param
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getcharactersummary")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family - the basemesh, its rig, a garment. "
                      "Omit or pass null to use whatever object is currently active."),
)

SUMMARY = ("Summarize one character before changing it: phenotype, rig, equipped assets, skin, "
           "detail morphs and face, each as its detailed command reports it.")

# How many rollup entries the summary carries. Measured rather than guessed, on
# FR 034's worst-case character: everything else in the answer comes to about
# 4 KB on the wire, a modifier is ~105 B and an asymmetry ~115 B. At 30 and 10
# the whole was 8,179 B, a name's length away from the 8 KB target; these leave
# about a tenth of it spare.
MODIFIER_CAP = 25
ASYMMETRY_CAP = 8

_PHENOTYPE_FIELDS = ("macro_details", "race_sum", "race_normalized", "macro_drift")
_ASSET_FIELDS = ("asset_source", "material_type", "material_source")
_RIG_FIELDS = ("rig_type", "rig_definition_path")
_SKIN_FIELDS = ("material_type", "material_source", "mhmat_path")
_STACK_ROW_FIELDS = ("fragment", "weight", "resolved")


def _pick(dictionary, keys):
    return {key: dictionary.get(key) for key in keys}


def _largest(entries, cap, magnitude):
    """At most ``cap`` of ``entries``, the largest by ``magnitude``, in their own order."""
    if len(entries) <= cap:
        return list(entries)
    ranked = sorted(range(len(entries)), key=lambda index: (-magnitude(entries[index]), index))
    return [entries[index] for index in sorted(ranked[:cap])]


def _rig(lookup, basemesh):
    """MPFB's own answer to "which is this character's rig", as get_object_info reports it."""
    rig = lookup.services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
        basemesh, "Skeleton")
    if rig is None:
        return None
    entry = asset_info.related_entry(lookup, rig)
    row = dict(name=entry["name"], in_current_scene=entry["in_current_scene"])
    row.update(_pick(entry["asset_info"] or dict(), _RIG_FIELDS))
    row["rigify_role"] = asset_info.rigify_role(lookup, rig)
    return row


def _assets(lookup, basemesh):
    """One row per equipped mesh asset, by type and then name."""
    rows = []
    for entry in asset_info.related_objects(lookup, basemesh):
        if entry["object_type"] not in lookup.mesh_asset_types:
            continue
        row = dict(name=entry["name"], object_type=entry["object_type"],
                   in_current_scene=entry["in_current_scene"])
        row.update(_pick(entry["asset_info"] or dict(), _ASSET_FIELDS))
        rows.append(row)
    rows.sort(key=lambda row: (row["object_type"], row["name"]))
    return rows


def _targets(services, basemesh):
    """get_target_stack's rollup and counts for its default arguments, capped."""
    target_service = services["TargetService"]
    tables = target_categories.build_tables(services)
    values = target_rollup.shapekey_values(basemesh)
    present, value_of = target_rollup.value_lookup(target_service, values)
    entries = target_rollup.shapekey_entries(target_service, tables, values)
    counts_by_kind, _counts_by_section = target_rollup.counts_of(entries)
    modifiers, asymmetries = target_rollup.build_modifiers(tables, present, value_of)
    return dict(
        modifiers=_largest(modifiers, MODIFIER_CAP, lambda entry: abs(entry["value"])),
        modifier_count=len(modifiers),
        asymmetries=_largest(asymmetries, ASYMMETRY_CAP,
                             lambda entry: abs(entry["difference"])),
        asymmetry_count=len(asymmetries),
        rollup_truncated=len(modifiers) > MODIFIER_CAP or len(asymmetries) > ASYMMETRY_CAP,
        counts_by_kind=counts_by_kind,
        total_count=len(target_rollup.matching(entries)),
    )


def _face(services, basemesh):
    """The non-zero face units as get_face_units reads them, and the stack as get_expression does."""
    face_service = services["FaceService"]
    arkit_faceunits = sys.modules[face_service.__module__].ARKIT_FACEUNITS
    current = face_service.read_current_expression(basemesh)
    face_units = []
    for face_unit_name in arkit_faceunits:
        weight = float(current.get(face_unit_name, 0.0))
        if weight != 0.0:
            face_units.append(dict(face_unit=face_unit_name, weight=round(weight, 6)))

    compared = divergence(services, basemesh)
    return dict(
        faceunits01_installed=bool(face_service.is_faceunits01_installed(force_recheck=False)),
        face_units=face_units,
        applied_expressions=[_pick(row, _STACK_ROW_FIELDS)
                             for row in compared["applied_expressions"]],
        matches_stack=compared["matches_stack"],
        unexplained_face_units=compared["unexplained_face_units"],
    )


def _message_for(basemesh, rig, assets, targets, face):
    parts = ["Character '{:s}'".format(basemesh.name)]
    parts.append(": no rig" if rig is None else ": rig '{:s}'".format(rig["name"]))
    parts.append(", {:d} equipped asset(s), {:d} modeling categories set".format(
        len(assets), targets["modifier_count"]))
    if face["applied_expressions"]:
        parts.append(", {:d} saved expression(s) applied".format(
            len(face["applied_expressions"])))
    parts.append(".")
    if targets["rollup_truncated"]:
        parts.append(" The rollup is cut to its largest entries; mpfb_get_target_stack has "
                     "all of it.")
    if face["unexplained_face_units"] and face["faceunits01_installed"]:
        parts.append(" {:d} face unit(s) were composed on top of the expression stack and "
                     "will be lost by the next mpfb_apply_expressions call.".format(
                         len(face["unexplained_face_units"])))
    return "".join(parts)


def get_character_summary(params, resolution):
    """Summarize one character from the implementations its detailed commands use."""
    services = resolution.services

    requested_name = params["name"]
    subject_resolved_by = "active" if requested_name is None else "name"
    basemesh, subject, message = macro_reading.resolve_basemesh(
        services, requested_name, not_a_character="it is not part of a character")

    if basemesh is None:
        _LOG.debug("get_character_summary: no basemesh resolved from %r", requested_name)
        return dict(
            found=False,
            subject_name=None if subject is None else subject.name,
            subject_resolved_by=subject_resolved_by,
            subject_in_current_scene=(
                None if subject is None else asset_info.in_current_scene(subject)),
            basemesh_name=None,
            basemesh_in_current_scene=None,
            phenotype=None,
            rig=None,
            assets=[],
            skin=None,
            targets=None,
            face=None,
            message=message,
        )

    lookup = asset_info.Lookup(services)
    phenotype = _pick(macro_reading.read_phenotype(services, basemesh), _PHENOTYPE_FIELDS)
    rig = _rig(lookup, basemesh)
    assets = _assets(lookup, basemesh)
    skin = _pick(asset_info.asset_info_for(
        lookup, basemesh, services["ObjectService"].get_object_type(basemesh)), _SKIN_FIELDS)
    targets = _targets(services, basemesh)
    face = _face(services, basemesh)

    _LOG.debug("get_character_summary: %r, rig %r, %d assets, %d modifiers",
               basemesh.name, None if rig is None else rig["name"], len(assets),
               targets["modifier_count"])

    return dict(
        found=True,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        subject_in_current_scene=asset_info.in_current_scene(subject),
        basemesh_name=basemesh.name,
        basemesh_in_current_scene=asset_info.in_current_scene(basemesh),
        phenotype=phenotype,
        rig=rig,
        assets=assets,
        skin=skin,
        targets=targets,
        face=face,
        message=_message_for(basemesh, rig, assets, targets, face),
    )
