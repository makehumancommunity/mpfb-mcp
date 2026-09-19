"""
``list_presets``: which characters have been saved, and which of them are usable.

A catalogue of **files**, not of anything MPFB computes. MPFB's
``get_list_of_human_presets()`` hands back bare names out of a module global it
populated on first use; the size and the age of each preset come from
``os.stat`` here and exist nowhere else. Both are derived facts in the sense of
[responses.md](../../../specifications/responses.md#a-response-says-which-source-answered-it),
and the answer says which is which.

**The cache is the interesting part, and it is reported rather than worked
around.** ``_EXISTING_PRESETS`` is invalidated by exactly one thing - a save
through ``serialize_to_json_file()`` - so a preset written by MPFB's panel in
another Blender, by hand, or by an earlier session is invisible until something
rescans. ``refresh`` is that rescan, and it is opt-in like every other rescan.
What is **not** opt-in is noticing: this also lists the directory itself, which
costs one ``os.listdir`` of some tens of files, and reports the difference as
``missing_from_mpfb_list``. A caller who has to pass ``refresh`` to find out
whether ``refresh`` would change anything has been given a flag instead of an
answer.

**Nothing is capped.** A preset collection is tens of files; the largest real
one seen was 45. A cap would cost every caller a ``truncated`` check to protect
against a case that does not arise.

**No file is parsed.** A preset is a few kilobytes of JSON describing a whole
character, and forty of them read and summarised would be an answer nobody
asked for. ``create_human_from_preset`` reports what a preset holds, for the one
preset being loaded.

The name rule, the path construction and the per-entry record come from
[`shared/preset_files.py`](../shared/preset_files.py), which is where the two
preset-writing commands will read them from too - so this cannot list a preset
under a name they would refuse without saying so, per entry, as
``addressable``.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "list_presets",
)

import os

from ..log import get_logger
from ..shared import preset_files
from ..validation import Param
from ..validation import TYPE_BOOLEAN

_LOG = get_logger("commands.listpresets")

PARAMS = (
    Param("refresh", TYPE_BOOLEAN, default=False,
          description="Rescan the config directory before answering. MPFB caches its preset "
                      "list for the Blender session and rebuilds it only when a preset is "
                      "saved, so a preset written elsewhere is invisible until this is true."),
)

SUMMARY = "List the saved character presets, with the file facts MPFB's own list does not carry."


def _message(confdir, confdir_exists, listing_failed, records,
             missing_from_mpfb_list, gone_from_disk, not_addressable):
    """What is worth saying about this listing before the entries are read."""
    parts = []
    if not confdir_exists:
        parts.append(
            "MPFB's user config directory {!r} does not exist, so no presets could be listed. "
            "MPFB creates it when it loads, so this usually means the install is broken rather "
            "than that nothing has been saved.".format(confdir))
    elif listing_failed is not None:
        parts.append("MPFB could not list the presets in '{:s}': {:s}".format(
            str(confdir), listing_failed))
    elif not records:
        parts.append("No character presets are saved in '{:s}'. Save one with "
                     "mpfb_save_preset.".format(str(confdir)))
    else:
        parts.append("{:d} character preset(s) in '{:s}'.".format(len(records), str(confdir)))

    if missing_from_mpfb_list:
        parts.append(
            " {:d} preset file(s) in that directory are not in MPFB's list, which it caches for "
            "the Blender session and rebuilds only when a preset is saved: "
            "missing_from_mpfb_list names them, and refresh=true picks them up. They are "
            "loadable by name either way.".format(len(missing_from_mpfb_list)))
    if gone_from_disk:
        parts.append(
            " {:d} name(s) in MPFB's list no longer have a file; each carries exists: false, "
            "and refresh=true drops them.".format(len(gone_from_disk)))
    if not_addressable:
        parts.append(
            " {:d} preset(s) carry a name mpfb_save_preset and mpfb_create_human_from_preset "
            "will not accept - MPFB's own panel is more permissive than they are. Each carries "
            "addressable: false and the reason; the file is still loadable through MPFB's own "
            "UI.".format(len(not_addressable)))
    return "".join(parts)


def list_presets(params, resolution):
    """Name every saved preset, annotated with what the filesystem says about it."""
    services = resolution.services
    refresh = params["refresh"]

    confdir = preset_files.config_directory(services)
    confdir_exists = bool(confdir is not None and os.path.isdir(confdir))

    # MPFB's list is the source, even when it is stale: it is the same list
    # MPFB's own preset dropdown is built from, so a name here is a name a user
    # sees there.
    mpfb_names = []
    listing_failed = None
    if confdir_exists:
        try:
            mpfb_names = preset_files.mpfb_presets(services, refresh)
        except Exception as error:  # pylint: disable=broad-except
            # update_list_of_human_presets() does a bare os.listdir(), so an
            # unreadable directory raises from inside MPFB rather than
            # answering. A broken install is one of the things this reports.
            listing_failed = str(error)

    records = [preset_files.preset_record(confdir, name) for name in mpfb_names]

    # The other half of the cache obligation: what MPFB's list would gain from a
    # rescan. Computed from the directory rather than from the cache, so it is
    # an observation rather than a prediction.
    on_disk = preset_files.scan_preset_names(confdir)
    known = set(mpfb_names)
    missing_from_mpfb_list = [name for name in on_disk if name not in known]
    gone_from_disk = [record["name"] for record in records if not record["exists"]]
    not_addressable = [record["name"] for record in records if not record["addressable"]]

    _LOG.debug("list_presets: %d in MPFB's list, %d on disk, refresh=%r",
               len(records), len(on_disk), refresh)

    return dict(
        presets=records,
        count=len(records),
        config_dir=confdir,
        config_dir_exists=confdir_exists,
        refreshed=bool(refresh),
        missing_from_mpfb_list=missing_from_mpfb_list,
        files_in_config_dir=len(on_disk),
        listing_failed=listing_failed,
        message=_message(confdir, confdir_exists, listing_failed, records,
                         missing_from_mpfb_list, gone_from_disk, not_addressable),
    )
