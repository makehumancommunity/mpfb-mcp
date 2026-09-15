"""
Payload for ``mpfb_list_presets``: which characters have been saved.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``refresh``, a bool.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap (unused here, but bound).

...and a further set because they come from the shared fragment
``preset_files.py``, concatenated ahead of this file: ``config_directory()``,
``mpfb_presets()``, ``scan_preset_names()`` and ``preset_record()``. That
fragment is where the name rule and the path construction live, so that this
tool cannot list a preset under a name the other two would not accept without
saying so.

**The answer is MPFB's list, annotated with the filesystem.**
``get_list_of_human_presets()`` hands back bare names out of a module global it
populated on first use, and mpfb-mcp adds nothing to it - the size and the
modification time come from ``os.stat`` here, which is the only place they exist
at all. Both are *derived* facts in the sense of
specifications/responses.md, and the tool docstring says so.

**The cache is the interesting part, and it is reported rather than worked
around.** ``_EXISTING_PRESETS`` is invalidated by exactly one thing - a save
through ``serialize_to_json_file()`` - so a preset written by MPFB's panel in
another Blender, by hand, or by an earlier session is invisible until something
rescans. ``refresh`` is the rescan, and it is opt-in like every other rescan in
this package. What is *not* opt-in is noticing: this payload also lists the
directory itself, which costs one ``os.listdir`` of some tens of files, and
reports the difference as ``missing_from_mpfb_list``. A caller who has to pass
``refresh`` to find out whether ``refresh`` would change anything has been given
a flag instead of an answer.

**Nothing is capped.** A preset collection is tens of files; the largest real
one seen during this effort held 45. A cap would cost every caller a
``truncated`` check to protect against a case that does not arise, and
specifications/responses.md' bounding convention exists for answers that do not
fit rather than for answers that might one day.

**No file is parsed.** A preset is a few kilobytes of JSON describing a whole
character, and forty of them read and summarised would be an answer nobody asked
for. ``mpfb_create_human_from_preset`` reports what a preset holds, for the one
preset that is being loaded.
"""

import os

refresh = PARAMS["refresh"]

confdir = config_directory()
confdir_exists = bool(confdir is not None and os.path.isdir(confdir))

# MPFB's list is the source, even when it is stale: it is the same list MPFB's
# own preset dropdown is built from, so a name here is a name a user sees there.
mpfb_names = []
listing_failed = None
if confdir_exists:
    try:
        mpfb_names = mpfb_presets(refresh)
    except Exception as error:  # pylint: disable=broad-except
        # update_list_of_human_presets() does a bare os.listdir(), so an
        # unreadable directory raises from inside MPFB rather than answering.
        # A broken install is one of the things this tool is for reporting.
        listing_failed = str(error)

records = [preset_record(confdir, name) for name in mpfb_names]

# The other half of the cache obligation: what MPFB's list would gain from a
# rescan. Computed from the directory rather than from the cache, so it is an
# observation rather than a prediction.
on_disk = scan_preset_names(confdir)
known = set(mpfb_names)
missing_from_mpfb_list = [name for name in on_disk if name not in known]
gone_from_disk = [record["name"] for record in records if not record["exists"]]
not_addressable = [record["name"] for record in records if not record["addressable"]]

message_parts = []
if not confdir_exists:
    message_parts.append(
        "MPFB's user config directory " + repr(confdir)
        + " does not exist, so no presets could be listed. MPFB creates it when it loads, so "
          "this usually means the install is broken rather than that nothing has been saved.")
elif listing_failed is not None:
    message_parts.append(
        "MPFB could not list the presets in '" + str(confdir) + "': " + listing_failed)
elif not records:
    message_parts.append(
        "No character presets are saved in '" + str(confdir)
        + "'. Save one with mpfb_save_preset.")
else:
    message_parts.append(
        str(len(records)) + " character preset(s) in '" + str(confdir) + "'.")

if missing_from_mpfb_list:
    message_parts.append(
        " " + str(len(missing_from_mpfb_list)) + " preset file(s) in that directory are not in "
        "MPFB's list, which it caches for the Blender session and rebuilds only when a preset "
        "is saved: missing_from_mpfb_list names them, and refresh=true picks them up. They are "
        "loadable by name either way.")
if gone_from_disk:
    message_parts.append(
        " " + str(len(gone_from_disk)) + " name(s) in MPFB's list no longer have a file; "
        "each carries exists: false, and refresh=true drops them.")
if not_addressable:
    message_parts.append(
        " " + str(len(not_addressable)) + " preset(s) carry a name mpfb_save_preset and "
        "mpfb_create_human_from_preset will not accept - MPFB's own panel is more permissive "
        "than they are. Each carries addressable: false and the reason; the file is still "
        "loadable through MPFB's own UI.")

result = dict(
    presets=records,
    count=len(records),
    config_dir=confdir,
    config_dir_exists=confdir_exists,
    refreshed=bool(refresh),
    missing_from_mpfb_list=missing_from_mpfb_list,
    files_in_config_dir=len(on_disk),
    listing_failed=listing_failed,
    message="".join(message_parts),
)
