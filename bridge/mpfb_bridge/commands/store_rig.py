"""
``store_rig``: an authored rig into the user library, as a ``custom.*`` rig found as itself.

**MakeRig's "Save rig to library" is reimplemented, never called**
([FR 060](../../../feature-requests/done/060-authoring-rigs/README.md),
[mpfb-integration.md](../../../specifications/mpfb-integration.md#a-third-party-add-ons-ui-operators-are-reimplemented-never-called)).
Its body is ``Rig.from_given_armature_context()``, ``RigService.get_weights()`` and two
``json.dump()``s, and those are what run here. The departures:

- **Identification is settled before anything is written, and a collision is refused**
  where the operator warns about twelve hard-coded bone names and writes anyway.
  ``RigService.identify_rig()`` checks every built-in rule first and reaches the custom rigs
  only when none matched, then takes the first custom rig, in ``os.listdir`` order, whose
  identifying bones are all present. So three things would make a stored rig not be found as
  itself, each a refusal: a built-in rule claims the armature (``identified_as_builtin``);
  another custom rig's identifying bones are all in this one (``identification_shadowed``,
  with ``shadowed_by``), since then directory order decides; and this rig's identifying bones
  are all in another custom rig (``would_shadow``), which would make *that* one ambiguous. A
  rig of the same name in another data root is ``name_shadowed``.
- **Identifying bones are picked when none are named**: the smallest set of this rig's bones
  that no built-in rig file and no other custom rig holds all of. A generated Rigify rig's
  bones are not on disk to compare with; the ``ORG-``/``DEF-`` names it is identified by are
  not names an authored rig has.
- **Nothing is overwritten by default, there is a ``dry_run``, and the two files are one
  artifact**: staged beside the destination and moved, the rig file last, since it is what
  MPFB's scan finds. ``path`` is in every answer.
- **The custom rig cache is rescanned**, not only invalidated, which is what
  ``shared/rig_lookup.py`` does for ``refresh``, so ``mpfb_list_rigs`` and ``mpfb_add_rig``
  see the rig at once and MPFB's own panel finds its cache full rather than empty.
- **Masks are excluded by default, as the operator excludes them** (``all_masks=False``,
  since the commit that introduced custom rigs, with no comment), and ``include_masks``
  writes them. ``get_weights()`` defaults to including them and MakeRig's other save path
  calls it ``save_masks``, so the opt-in is MPFB's own choice exposed. An ``mhmask-*`` group
  on an authoring body is as likely left over from a rig that body once had as chosen, and
  including it by default would ship a preserve-volume modifier nobody asked for.
  ``masks_on_body`` and ``masks_written`` are on every answer either way.

**What the round trip loses is reported.** MPFB's format has no ``use_deform``, so
``deform_flags_lost`` names every non-deforming bone that will come back deforming; the
key is a feature request upstream rather than an extension here. ``features_not_carried``
is ``get_rig_definition``'s reading. ``unweighted_bones`` names deforming bones with no
weights, read by ``shared/rig_weights.py`` as ``weight_rig`` and ``check_rig_weights`` read them
(FR 061), so the three cannot disagree. And ``ends_rematched`` names every end whose strategy MPFB's save changed:
``from_given_armature_context()`` matches each end afresh and keeps a saved strategy only if
it is no worse, so a fixed position (``snap: false``) comes back as a vertex or a mean.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "store_rig",
)

import itertools
import json
import os
import tempfile

import bpy

from ..log import get_logger
from ..shared import artifact_names
from ..shared import mpfb_surface
from ..shared import rig_definition
from ..shared import rig_lookup
from ..shared import rig_weights
from ..shared import selection
from ..shared import subject_resolution
from ..shared import view_layer
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.storerig")

# The most bones an identifying set is picked from; a rig needing more is refused.
_MAX_IDENTIFYING = 3

# How many candidate sets the pick looks at before giving up, so a large rig cannot stall.
_MAX_CANDIDATES = 200000

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("rig_name", TYPE_STRING, required=True,
          description="The library name: letters, digits and '_'. The rig becomes custom.<rig_name>."),
    Param("include_weights", TYPE_BOOLEAN, default=True,
          description="Also write weights.<rig_name>.json from the body's groups."),
    Param("identifying_bones", TYPE_ARRAY, default=None, nullable=True,
          description="The bones MPFB identifies the rig by. Omit to have the smallest set no "
                      "other rig holds picked."),
    Param("include_masks", TYPE_BOOLEAN, default=False,
          description="Write the body's mhmask-* groups with the weights, which MPFB's panel "
                      "leaves out."),
    Param("overwrite", TYPE_BOOLEAN, default=False,
          description="Replace a rig of this name in the user library."),
    Param("dry_run", TYPE_BOOLEAN, default=False,
          description="Settle every refusal and report what would be written, writing nothing."),
)

SUMMARY = ("Store an authored rig in the user library as custom.<rig_name>, with its weights, "
           "refusing any name or identification that would not find it as itself.")


def _answer(subject, resolved_by, basemesh, params, **fields):
    answer = dict(
        found=basemesh is not None,
        ready=False,
        stored=False,
        blocked_by=None,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        rig_name=params["rig_name"],
        identifier="custom." + str(params["rig_name"]),
        path=None,
        weights_path=None,
        dry_run=params["dry_run"],
    )
    answer.update(fields)
    return answer


def _builtin_bone_sets(services):
    """``{identifier: set of bone names}`` for every built-in rig file on disk."""
    rigs_dir = rig_lookup.rigs_directory(services)
    sets = {}
    if rigs_dir is None:
        return sets
    for _family, subdir, prefix in rig_lookup.BUILTIN_FAMILIES:
        directory = os.path.join(rigs_dir, subdir)
        if not os.path.isdir(directory):
            continue
        for filename in sorted(os.listdir(directory)):
            if filename.startswith("rig.") and filename.endswith(".json"):
                try:
                    _header, definition = rig_definition.rig_file_definition(
                        os.path.join(directory, filename))
                except (OSError, ValueError):
                    continue
                sets[prefix + filename[len("rig."):-len(".json")]] = set(definition)
    return sets


def _custom_bone_sets(records, rig_name):
    """``{name: (identifying bones, bone names)}`` for every other custom rig MPFB found."""
    sets = {}
    for record in records or []:
        name = str(record.get("name") or "")
        if not name or name == rig_name:
            continue
        try:
            _header, definition = rig_definition.rig_file_definition(
                mpfb_surface.as_path(record.get("path")))
        except (OSError, ValueError, TypeError):
            definition = {}
        sets[name] = (list(record.get("identifying_bones") or []), set(definition))
    return sets


def _picked(bones, others):
    """The smallest set of ``bones`` no set in ``others`` holds all of, or None."""
    ordered = sorted(bones)
    looked = 0
    for size in range(1, _MAX_IDENTIFYING + 1):
        for candidate in itertools.combinations(ordered, size):
            looked += 1
            if looked > _MAX_CANDIDATES:
                return None
            if not any(set(candidate) <= other for other in others):
                return list(candidate)
    return None


def _rematched(saved, header_bones):
    """Each end whose strategy the save changed, as ``{end, before, after}``."""
    changed = []
    for bone_name, info in saved.items():
        written = header_bones.get(bone_name)
        if written is None:
            continue
        for key in ("head", "tail"):
            before = rig_definition.end_signature(info[key])
            after = rig_definition.end_signature(written[key])
            if before != after:
                changed.append({"end": "{:s}.{:s}".format(bone_name, key),
                                "before": before[0], "after": after[0]})
    return changed


def _second_root_rig(services, rig_name, own_path):
    """A same-named rig file MPFB would also scan, in another data root, or None."""
    location_service = services["LocationService"]
    roots = []
    for getter in ("get_user_data", "get_second_root"):
        function = getattr(location_service, getter, None)
        root = mpfb_surface.as_path(function()) if function is not None else None
        if root and root not in roots:
            roots.append(root)
    for root in roots:
        candidate = os.path.join(root, "rigs", rig_name + ".json")
        if os.path.normpath(candidate) != os.path.normpath(own_path) and os.path.isfile(candidate):
            return candidate
    return None


def _header(services, armature):
    """``Rig.from_given_armature_context()``'s header, with the armature active as it requires."""
    with selection.restored_all():
        services["ObjectService"].activate_blender_object(armature)
        rig = rig_definition.rig_class(services).from_given_armature_context(
            armature, is_subrig=False, operator=None, rigify_ui=False)
    return None if rig is None else rig.rig_header


def _write(rigs_dir, files):
    """Stage every file beside the destination, then move them in, the last one last."""
    os.makedirs(rigs_dir, exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".mpfb-bridge-", dir=rigs_dir)
    try:
        staged = []
        for path, content in files:
            target = os.path.join(staging, os.path.basename(path))
            with open(target, "w", encoding="utf-8") as json_file:
                json.dump(content, json_file, indent=4, sort_keys=True)
            staged.append((target, path))
        for target, path in staged:
            os.replace(target, path)
    finally:
        for leftover in os.listdir(staging):
            os.remove(os.path.join(staging, leftover))
        os.rmdir(staging)


def _store_rig(params, resolution):  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
    services = resolution.services
    rig_service = services["RigService"]
    basemesh, subject, resolved_by, message = subject_resolution.resolve_basemesh(
        services, params["name"], not_done="nothing was stored",
        not_a_character="there is no rig to store")
    rig_name = params["rig_name"]
    paths = {}

    def blocked(reason, text, **extra):
        return with_performed(_answer(subject, resolved_by, basemesh, params, blocked_by=reason,
                                      message=text, **dict(paths, **extra)), False)

    if basemesh is None:
        return blocked("subject_not_found", message)
    rejection = artifact_names.rig_name_rejection(rig_name)
    if rejection is not None:
        return blocked("invalid_name", rejection + " Nothing was stored.")
    rigs_dir = mpfb_surface.as_path(services["LocationService"].get_user_data("rigs"))
    rig_file = os.path.join(rigs_dir, rig_name + ".json")
    weights_file = os.path.join(rigs_dir, "weights." + rig_name + ".json")
    paths = {"path": rig_file,
             "weights_path": weights_file if params["include_weights"] else None}

    armature = services["ObjectService"].find_object_of_type_amongst_nearest_relatives(
        basemesh, "Skeleton")
    if armature is None:
        return blocked("not_rigged", "'{:s}' has no rig, so there is nothing to store. Build one "
                                     "with mpfb_create_rig.".format(basemesh.name))
    given = params["identifying_bones"]
    if given is not None and (not isinstance(given, list) or not given or not all(
            isinstance(item, str) and item for item in given) or len(set(given)) != len(given)):
        return blocked("invalid_shape", "identifying_bones must be a non-empty list of distinct "
                                        "bone names, or omitted.")
    bones = set(armature.data.bones.keys())
    if given is not None:
        unknown = [name for name in given if name not in bones]
        if unknown:
            return blocked("unknown_bone_names",
                           "{:d} identifying bone(s) are not bones of '{:s}', so nothing was "
                           "stored: {:s}.".format(len(unknown), armature.name, ", ".join(unknown)),
                           unknown_bone_names=unknown)
    if bpy.context.mode != "OBJECT":
        return blocked("not_object_mode",
                       "Blender is in {:s} mode, and reading the armature means entering and "
                       "leaving edit mode on it, so nothing was stored.".format(
                           str(bpy.context.mode)))

    shadowing = _second_root_rig(services, rig_name, rig_file)
    if shadowing is not None:
        return blocked("name_shadowed",
                       "A rig called '{:s}' is already in another data root, at '{:s}', and MPFB "
                       "scans both, so one stored here might never be the one found. Nothing was "
                       "stored. Choose another name.".format(rig_name, shadowing),
                       shadowed_by=shadowing)
    previous = artifact_names.file_facts(rig_file)
    file_before = previous if previous["exists"] else None
    if file_before is not None and not params["overwrite"]:
        return blocked("rig_exists",
                       "'{:s}' already exists, written {!s}, and overwrite is false, so nothing "
                       "was stored. Pass overwrite=true to replace it, or choose another name."
                       .format(rig_file, file_before["modified"]), file_before=file_before)

    identified = rig_service.identify_rig(armature)
    if identified != "unknown" and not identified.startswith("custom."):
        return blocked("identified_as_builtin",
                       "MPFB identifies '{:s}' as the built-in '{:s}', and it checks the built-in "
                       "rigs before any custom one, so a rig stored from it would never be found "
                       "as custom.{:s}. Nothing was stored. Rename the bone that built-in rig is "
                       "identified by.".format(armature.name, identified, rig_name),
                       identified_as=identified)

    records = rig_lookup.custom_rig_records(services, True)
    customs = _custom_bone_sets(records, rig_name)
    builtins = _builtin_bone_sets(services)
    # Before any pick: whether another rig already claims this armature does not depend on which
    # bones this one is identified by, and is the more useful thing to say about a plain copy.
    shadowed_by = sorted(name for name, (ident, _held) in customs.items()
                         if ident and set(ident) <= bones)
    if shadowed_by:
        return blocked("identification_shadowed",
                       "Every identifying bone of {:s} is in this rig, and MPFB takes the first "
                       "custom rig that matches in directory order, so this one could be "
                       "identified as that and nothing was stored. Rename a bone so it no longer "
                       "holds all of theirs.".format(", ".join("custom." + n for n in shadowed_by)),
                       shadowed_by=shadowed_by)
    if given is not None:
        identifying = list(given)
        chosen_by = "argument"
    else:
        identifying = _picked(bones, list(builtins.values())
                              + [held for _ident, held in customs.values()])
        chosen_by = "picked"
        if identifying is None:
            return blocked("no_identifying_bones",
                           "No set of up to {:d} of this rig's bones is absent from every other "
                           "rig, so MPFB could not tell it apart and nothing was stored. Rename a "
                           "bone, or name identifying_bones.".format(_MAX_IDENTIFYING))
    would_shadow = sorted(name for name, (_ident, held) in customs.items()
                          if set(identifying) <= held)
    if would_shadow:
        return blocked("would_shadow",
                       "Every identifying bone of this rig ({:s}) is also in {:s}, which MPFB could "
                       "then identify as this one, so nothing was stored. Name identifying_bones "
                       "that only this rig has.".format(
                           ", ".join(identifying), ", ".join("custom." + n for n in would_shadow)),
                       would_shadow=would_shadow, identifying_bones=identifying)

    header = _header(services, armature)
    if header is None:
        return blocked("no_armature_context",
                       "MPFB could not find the basemesh '{:s}' belongs to from '{:s}', so the "
                       "rig could not be read and nothing was stored.".format(
                           basemesh.name, armature.name))
    header["identifying_bones"] = identifying

    masks = sorted(group.name for group in basemesh.vertex_groups
                   if group.name.startswith("mhmask-"))
    weights = None
    unweighted = []
    if params["include_weights"]:
        weights = rig_service.get_weights([armature], basemesh, all_groups=False,
                                          all_masks=params["include_masks"])
        deforming = rig_weights.deforming_bones(armature)
        unweighted = rig_weights.unweighted_bones(
            rig_weights.read_weights(basemesh, set(deforming)), deforming)
    saved, _count = rig_definition.armature_definition(services, armature)
    deform_lost = sorted(bone.name for bone in armature.data.bones if not bone.use_deform)
    features = {}
    for bone_name in sorted(bones):
        named = rig_definition.features_from_armature(armature, bone_name)
        if named:
            features[bone_name] = named
    rematched = _rematched(saved, header["bones"])

    files = [(weights_file, weights)] if weights is not None else []
    files.append((rig_file, header))
    if not params["dry_run"]:
        try:
            _write(rigs_dir, files)
        except OSError as error:
            return blocked("write_failed",
                           "Writing '{:s}' failed, and nothing was moved into place: {!s}".format(
                               rig_file, error))
        rig_lookup.custom_rig_records(services, True)
    identified_after = rig_service.identify_rig(armature) if not params["dry_run"] else None
    stored = not params["dry_run"]

    parts = ["{:s} '{:s}' as custom.{:s}, identified by {:s}.".format(
        "Stored" if stored else "Would store", armature.name, rig_name, ", ".join(identifying))]
    if deform_lost:
        parts.append(" {:d} non-deforming bone(s) will come back deforming, since MPFB's format "
                     "has no use_deform; see deform_flags_lost.".format(len(deform_lost)))
    if unweighted:
        parts.append(" {:d} deforming bone(s) have no weights; see unweighted_bones.".format(
            len(unweighted)))
    if rematched:
        parts.append(" MPFB's save changed {:d} end(s)' strategy; see ends_rematched.".format(
            len(rematched)))
    if masks and not params["include_masks"]:
        parts.append(" {:d} mask group(s) on the body were left out, as MPFB's panel leaves "
                     "them; include_masks writes them.".format(len(masks)))
    if stored and identified_after != "custom." + rig_name:
        parts.append(" MPFB now identifies the armature as '{!s}', not as this rig.".format(
            identified_after))
    _LOG.debug("store_rig: %r dry_run=%r", rig_file, params["dry_run"])
    return with_performed(_answer(
        subject, resolved_by, basemesh, params,
        ready=True,
        stored=stored,
        written=stored,
        overwrote=stored and file_before is not None,
        file_before=file_before,
        rig_object_name=armature.name,
        bone_count=len(bones),
        identifying_bones=identifying,
        identifying_bones_chosen_by=chosen_by,
        identified_as_after=identified_after,
        masks_on_body=masks,
        masks_written=masks if (params["include_masks"] and weights is not None) else [],
        deform_flags_lost=deform_lost,
        unweighted_bones=unweighted,
        features_not_carried=features,
        ends_rematched=rematched,
        cache_refreshed=stored,
        try_with={"mpfb_create_human": {},
                  "mpfb_add_rig": {"name": None, "identifier": "custom." + rig_name}},
        message="".join(parts),
        **paths), stored)


def store_rig(params, resolution):
    """Store the rig, with the character in the view layer."""
    return view_layer.run(resolution.services, params["name"],
                          lambda: _store_rig(params, resolution))
