"""
Payload for ``mpfb_list_rigs``: names every rig this Blender could add.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``refresh``, a bool.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap (unused here, but bound).

...and a further set as undefined because they come from the shared fragment
``rig_lookup.py``, which the tool module names in its ``assemble()`` call and
which is concatenated ahead of this file: ``as_path()``, ``BUILTIN_FAMILIES``,
``FAMILIES``, ``rigs_directory()``, ``builtin_weights()``,
``custom_rig_records()`` and ``custom_weights()``. That fragment exists because
this payload *predicts* what ``mpfb_add_rig`` will do - which rig file gets
loaded, and whose weights - and a prediction that can drift from the action it
predicts is worse than no prediction at all.

The whole point of this payload is the ``identifier`` field. A rig's bare name
is not always what an adding function takes: a Rigify rig is added as
``rigify.human`` and a custom one as ``custom.my_rig``, and the two are consumed
by *different*, non-interchangeable functions - hence ``add_function`` beside
it. Reporting only the name would leave the caller to reassemble the string,
which is exactly the guesswork this tool exists to remove.

Nothing is loaded into the scene and no object is touched: a directory listing,
some ``os.path.isfile()`` calls, and at most two small JSON reads for the UI
labels. The rig definition files themselves are deliberately *not* parsed - they
are large flat bone tables and nothing reported here needs their contents, so
``is_subrig`` (present in the Rigify definitions) is left out rather than paid
for on every call.
"""

import json
import os

# LocationService, AssetService and RigService are bound by the shared fragment.
SystemService = _MPFB_SERVICES["SystemService"]

# MPFB's own rig enums, as UI resource files rather than as an API. They are
# read for their labels only, and never imported: MPFB UI modules run scans at
# import time, and importing an MPFB submodule is forbidden anyway (see
# specifications/architecture.md). The *directory* is the authority on which
# rigs exist - a rig file with no enum entry is still addable and is listed.
LABEL_SOURCES = {
    "standard": "ui/rigging/standardrig/properties/standard_rig.json",
    "rigify": "ui/rigging/rigifyrig/properties/rigify_rig.json",
}

RIGIFY_MISSING_REASON = (
    "Rigify is not enabled in this Blender. HumanService.add_builtin_rig() raises "
    "NotImplementedError for a rigify rig rather than degrading, so this rig cannot be added "
    "until the Rigify add-on is enabled."
)


def read_label_table(relative_path):
    # Maps a bare rig name to its (label, description) from MPFB's UI enum.
    # Wrapped whole: these are UI resource files whose location and shape may
    # move, and a missing label is decoration lost, not an answer lost.
    try:
        absolute = as_path(LocationService.get_mpfb_root(relative_path))
        if absolute is None or not os.path.isfile(absolute):
            return dict()
        with open(absolute, "r") as handle:
            data = json.load(handle)
        table = dict()
        for item in data["items"]:
            table[str(item[0])] = (str(item[1]), str(item[2]))
        return table
    except Exception:  # pylint: disable=broad-except
        return dict()


def builtin_entries():
    entries = []
    scanned = []
    rigs_dir = rigs_directory()
    if rigs_dir is None:
        return (entries, scanned)
    for family, subdir, prefix in BUILTIN_FAMILIES:
        subdir_path = os.path.join(rigs_dir, subdir)
        scanned.append({
            "path": subdir_path,
            "family": family,
            "exists": os.path.isdir(subdir_path),
        })
        if not os.path.isdir(subdir_path):
            continue
        labels = read_label_table(LABEL_SOURCES[family])
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
            has_weights, weights_path, weights_from = builtin_weights(identifier, subdir_path)
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


def custom_rig_dirs():
    # Only the two roots get_custom_rigs() itself scans, and in its order. The
    # MakeHuman user data dir is deliberately absent: MPFB does not look there
    # for rigs, and listing it would send a user to put files where nothing
    # reads them. A directory that does not exist is still reported, flagged,
    # since "we looked here and there was nothing" is the answer a user missing
    # their custom rig actually needs.
    dirs = []
    seen = []
    for getter in (LocationService.get_user_data, LocationService.get_second_root):
        try:
            root = as_path(getter())
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


def custom_entries(records):
    entries = []
    for record in records:
        name = str(record.get("name") or "")
        rig_path = as_path(record.get("path"))
        if not name or rig_path is None:
            continue
        # add_custom_rig() does not use the fallback table at all: it looks only
        # for weights.<short name>.json beside the rig file. Reporting a
        # fallback here would promise weights that would never be loaded, which
        # is why the fragment keeps the two resolutions apart.
        has_weights, weights_path, weights_from = custom_weights(rig_path, name)
        entries.append({
            "name": name,
            "identifier": "custom." + name,
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


def unrecognized_custom_files(dirs, records):
    # A set difference against what get_custom_rigs() accepted, never a second
    # implementation of its acceptance rules - re-deriving them here would drift
    # from them, a difference cannot. The one thing subtracted on top is the
    # weights.<name>.json companion pattern that add_custom_rig() itself
    # defines: those sit in the same directory on every real install, and
    # reporting them would bury a genuinely unrecognized file in noise.
    accepted = []
    for record in records:
        record_path = as_path(record.get("path"))
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


rigify_available = bool(SystemService.check_for_rigify())

rigs, builtin_dirs = builtin_entries()
custom_records = custom_rig_records(PARAMS["refresh"])
# Kept apart until the response is assembled: the diff below must run over the
# user rigs directories only. Run it over the bundled ones as well and it would
# report every rig.*.json MPFB ships as an unrecognized custom rig.
custom_dirs = custom_rig_dirs()
rigs.extend(custom_entries(custom_records))

for entry in rigs:
    # The one thing that makes a listed rig unusable. Rigify rigs stay in the
    # list when Rigify is off - dropping them would turn an explainable refusal
    # into an unexplained absence.
    unavailable = entry["family"] == "rigify" and not rigify_available
    entry["available"] = not unavailable
    entry["unavailable_reason"] = RIGIFY_MISSING_REASON if unavailable else None

rigs.sort(key=lambda entry: (FAMILIES.index(entry["family"]), entry["name"]))

rig_dirs = builtin_dirs + custom_dirs
unrecognized = unrecognized_custom_files(custom_dirs, custom_records)

# Built by concatenation rather than the repo's usual .format(): a payload file
# must contain no empty brace pair anywhere, since that is what a substitution
# point looks like, and nothing is ever substituted into a payload.
message_parts = [str(len(rigs)) + " rigs can be added by this Blender"]
if not rigify_available:
    message_parts.append(", but Rigify is not enabled, so the rigify ones are unavailable")
if unrecognized:
    message_parts.append(
        ". " + str(len(unrecognized)) + " .json files in the scanned user rigs directories were "
        "not recognized as rig definitions")
message_parts.append(". Pass a rig's 'identifier', not its 'name', to the function named by its "
                     "'add_function'.")

result = {
    "rigs": rigs,
    "count": len(rigs),
    "rigify_available": rigify_available,
    "rig_dirs": rig_dirs,
    "unrecognized_custom_rig_files": unrecognized,
    "families": list(FAMILIES),
    "message": "".join(message_parts),
}
