"""
``list_rigs``: every rig this Blender could add, and what adding one would do.

**The whole point of this command is the ``identifier`` field.** A rig's bare
name is not always what an adding function takes: a Rigify rig is added as
``rigify.human`` and a custom one as ``custom.my_rig``, and the two are consumed
by *different, non-interchangeable* functions - hence ``add_function`` beside
it. Reporting only the name would leave the caller to reassemble the string,
which is exactly the guesswork this command exists to remove.

It also **predicts**, per entry, which weights file would be loaded and whose
they are. That prediction and the action it predicts read one implementation,
[`shared/rig_lookup.py`](../shared/rig_lookup.py), because a prediction that can
drift from the action is worse than no prediction at all. ``add_rig`` is still
on the generated path and still reads the fragment; ``tests/test_fragment_drift.py``
is what keeps the two halves in step until it follows.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
Four of its decisions look arbitrary and are not:

- **The directory is the authority on which rigs exist, not MPFB's UI enum.**
  A rig file with no enum entry is still addable and is listed, with a null
  label. The enums are read for their text only, out of JSON resource files,
  and never imported.
- **Rigify rigs stay in the list when Rigify is off**, flagged unavailable with
  a reason. Dropping them would turn an explainable refusal into an unexplained
  absence.
- **The custom scan covers the two roots ``get_custom_rigs()`` itself scans, in
  its order.** MakeHuman's user data directory is deliberately absent: MPFB does
  not look there for rigs, and listing it would send a user to put files where
  nothing reads them. A directory that does not exist is still reported and
  flagged, since "we looked here and there was nothing" is the answer a user
  missing their custom rig actually needs.
- **Unrecognised files are a set difference against what ``get_custom_rigs()``
  accepted**, never a second implementation of its acceptance rules. The one
  thing subtracted on top is the ``weights.<name>.json`` companion pattern that
  ``add_custom_rig()`` itself defines.

Nothing is loaded into the scene and no object is touched: a directory listing,
some ``os.path.isfile()`` calls, and at most two small JSON reads for the UI
labels. The rig definition files themselves are deliberately *not* parsed - they
are large flat bone tables and nothing reported here needs their contents.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "list_rigs",
)

import json
import os

from ..log import get_logger
from ..shared import rig_lookup
from ..validation import Param
from ..validation import TYPE_BOOLEAN

_LOG = get_logger("commands.listrigs")

PARAMS = (
    Param("refresh", TYPE_BOOLEAN, default=False,
          description="Rescan the custom rig directories before answering. MPFB caches that "
                      "scan in a module global, so a rig installed since Blender started is "
                      "invisible until this is true."),
)

SUMMARY = "List every rig that can be added, with the identifier each adding function takes."

# MPFB's own rig enums, as UI resource files rather than as an API. They are
# read for their labels only, and never imported: MPFB UI modules run scans at
# import time, and importing an MPFB submodule stays forbidden for add-on code.
LABEL_SOURCES = {
    "standard": "ui/rigging/standardrig/properties/standard_rig.json",
    "rigify": "ui/rigging/rigifyrig/properties/rigify_rig.json",
}

RIGIFY_MISSING_REASON = (
    "Rigify is not enabled in this Blender. HumanService.add_builtin_rig() raises "
    "NotImplementedError for a rigify rig rather than degrading, so this rig cannot be added "
    "until the Rigify add-on is enabled."
)


def _read_label_table(services, relative_path):
    """A bare rig name mapped to its ``(label, description)`` from MPFB's enum.

    Wrapped whole: these are UI resource files whose location and shape may
    move, and a missing label is decoration lost, not an answer lost.
    """
    try:
        absolute = rig_lookup.as_path(
            services["LocationService"].get_mpfb_root(relative_path))
        if absolute is None or not os.path.isfile(absolute):
            return dict()
        with open(absolute, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        table = dict()
        for item in data["items"]:
            table[str(item[0])] = (str(item[1]), str(item[2]))
        return table
    except Exception:  # pylint: disable=broad-except
        return dict()


def _builtin_entries(services):
    """Every ``rig.*.json`` under the two bundled families, and what was scanned."""
    entries = []
    scanned = []
    rigs_dir = rig_lookup.rigs_directory(services)
    if rigs_dir is None:
        return (entries, scanned)
    for family, subdir, prefix in rig_lookup.BUILTIN_FAMILIES:
        subdir_path = os.path.join(rigs_dir, subdir)
        scanned.append({
            "path": subdir_path,
            "family": family,
            "exists": os.path.isdir(subdir_path),
        })
        if not os.path.isdir(subdir_path):
            continue
        labels = _read_label_table(services, LABEL_SOURCES[family])
        for filename in sorted(os.listdir(subdir_path)):
            # The same directories hold weights.*.json, so filtering on the
            # rig. prefix is what keeps a weights file from being listed as a
            # rig of its own.
            if not filename.startswith("rig.") or not filename.endswith(".json"):
                continue
            name = filename[len("rig."):-len(".json")]
            if not name:
                continue
            identifier = prefix + name
            has_weights, weights_path, weights_from = rig_lookup.builtin_weights(
                services, identifier, subdir_path)
            label, description = labels.get(name, (None, None))
            entries.append({
                "name": name,
                "identifier": identifier,
                "family": family,
                "path": os.path.join(subdir_path, filename),
                "label": label,
                "description": description,
                "has_weights": has_weights,
                "weights_path": weights_path,
                "weights_from": weights_from,
                "add_function": "add_builtin_rig",
            })
    return (entries, scanned)


def _custom_rig_dirs(services):
    """The two roots ``get_custom_rigs()`` scans, in its order. See the docstring."""
    location_service = services["LocationService"]
    dirs = []
    seen = []
    for getter in (location_service.get_user_data, location_service.get_second_root):
        try:
            root = rig_lookup.as_path(getter())
        except Exception:  # pylint: disable=broad-except
            root = None
        if root is None:
            continue
        rigs_dir = os.path.normpath(os.path.join(root, "rigs"))
        if rigs_dir in seen:
            continue
        seen.append(rigs_dir)
        dirs.append({
            "path": rigs_dir,
            "family": "custom",
            "exists": os.path.isdir(rigs_dir),
        })
    return dirs


def _custom_entries(records):
    """One entry per rig ``get_custom_rigs()`` accepted."""
    entries = []
    for record in records:
        name = str(record.get("name") or "")
        rig_path = rig_lookup.as_path(record.get("path"))
        if not name or rig_path is None:
            continue
        # add_custom_rig() does not use the fallback table at all: it looks only
        # for weights.<short name>.json beside the rig file. Reporting a
        # fallback here would promise weights that would never be loaded, which
        # is why the shared module keeps the two resolutions apart.
        has_weights, weights_path, weights_from = rig_lookup.custom_weights(rig_path, name)
        entries.append({
            "name": name,
            "identifier": rig_lookup.CUSTOM_PREFIX + name,
            "family": "custom",
            "path": rig_path,
            # Custom rigs have no UI enum, so no text to report. Null rather
            # than the bare name: a name is not a label.
            "label": None,
            "description": None,
            "has_weights": has_weights,
            "weights_path": weights_path,
            "weights_from": weights_from,
            # identifying_bones is deliberately dropped: it is a bone-name table
            # MPFB matches against, not something a caller acts on.
            "add_function": "add_custom_rig",
        })
    return entries


def _unrecognized_custom_files(dirs, records):
    """The ``.json`` files in the user rig directories MPFB did not accept."""
    accepted = []
    for record in records:
        record_path = rig_lookup.as_path(record.get("path"))
        if record_path is not None:
            accepted.append(os.path.normpath(record_path))
    unrecognized = []
    for entry in dirs:
        if not entry["exists"]:
            continue
        for filename in sorted(os.listdir(entry["path"])):
            if not filename.endswith(".json") or filename.startswith("weights."):
                continue
            candidate = os.path.normpath(os.path.join(entry["path"], filename))
            if candidate in accepted:
                continue
            unrecognized.append(candidate)
    return unrecognized


def _message(rigs, rigify_available, unrecognized):
    parts = ["{:d} rigs can be added by this Blender".format(len(rigs))]
    if not rigify_available:
        parts.append(", but Rigify is not enabled, so the rigify ones are unavailable")
    if unrecognized:
        parts.append(
            ". {:d} .json files in the scanned user rigs directories were not recognized as "
            "rig definitions".format(len(unrecognized)))
    parts.append(". Pass a rig's 'identifier', not its 'name', to the function named by its "
                 "'add_function'.")
    return "".join(parts)


def list_rigs(params, resolution):
    """Catalogue every addable rig, and predict what adding each would load."""
    services = resolution.services
    rigify_available = bool(services["SystemService"].check_for_rigify())

    rigs, builtin_dirs = _builtin_entries(services)
    custom_records = rig_lookup.custom_rig_records(services, params["refresh"])
    # Kept apart until the response is assembled: the diff below must run over
    # the user rigs directories only. Run it over the bundled ones as well and
    # it would report every rig.*.json MPFB ships as an unrecognized custom rig.
    custom_dirs = _custom_rig_dirs(services)
    rigs.extend(_custom_entries(custom_records))

    for entry in rigs:
        # The one thing that makes a listed rig unusable. Rigify rigs stay in
        # the list when Rigify is off - dropping them would turn an explainable
        # refusal into an unexplained absence.
        unavailable = entry["family"] == "rigify" and not rigify_available
        entry["available"] = not unavailable
        entry["unavailable_reason"] = RIGIFY_MISSING_REASON if unavailable else None

    rigs.sort(key=lambda entry: (rig_lookup.FAMILIES.index(entry["family"]), entry["name"]))

    unrecognized = _unrecognized_custom_files(custom_dirs, custom_records)

    _LOG.debug("list_rigs: %d rigs, rigify_available=%r, %d unrecognized",
               len(rigs), rigify_available, len(unrecognized))

    return {
        "rigs": rigs,
        "count": len(rigs),
        "rigify_available": rigify_available,
        "rig_dirs": builtin_dirs + custom_dirs,
        "unrecognized_custom_rig_files": unrecognized,
        "families": list(rig_lookup.FAMILIES),
        "message": _message(rigs, rigify_available, unrecognized),
    }
