"""
``list_expressions``: which saved expressions are installed, and how to address one.

Wraps ``FaceService.list_available_expressions()``, which walks
``<root>/expressions/`` for every root ``AssetService.get_asset_roots("expressions")``
reports - in MPFB's priority order, ``mpfb_data``, ``mh_data``, ``user_data``,
``second_root`` - and keeps the **first** root's copy of any library-relative
path. That list is what MPFB's expressions-library panel draws its sliders from.

**``fragment`` is the address; ``path`` is for a human.** The applied-expressions
stack stores library-relative fragments, so a fragment is what round-trips
between machines and through a preset, and it is what ``apply_expressions``
takes. ``path`` is reported beside it so a reader can check which file that is,
exactly as ``list_assets`` does per
[how tools name things that can be added](../../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added).

**Three things MPFB's scan hides are reported rather than hidden**, because an
absent entry must be explainable:

- **the roots scanned**, whether or not anything was found, so an empty answer
  is an answer;
- **unreadable files**, which MPFB skips with only a ``_LOG.warn`` - an
  expression somebody can see in a file manager and cannot find here is
  otherwise a mystery with no evidence;
- **shadowed files**: a file whose library-relative path is also held by a
  higher-priority root is invisible to MPFB, in its panel and in every
  application. That is the case a file saved into ``user_data`` lands in when
  ``mpfb_data`` or ``mh_data`` ships the same name, and MPFB's own composer
  panel says the opposite ("user-saved expressions take priority") - see
  ``save_expression``, which refuses to write one.

Those two lists come from a walk of this command's own that **reproduces
MPFB's precedence exactly**, including its one subtlety: a file that fails to
parse is skipped *before* it claims its path, so a readable copy in a lower
root then wins. The entries themselves are MPFB's answer, unchanged.

**``faceunits01_installed`` is on every answer**, per
[a capability that depends on an optional asset pack](../../../specifications/mpfb-integration.md#a-capability-that-depends-on-an-optional-asset-pack).
An expression file can exist while the face-unit targets it names do not; the
catalogue is then a list of things that cannot be applied, and it says so here
rather than letting ``apply_expressions`` discover it. ``refresh`` busts that
probe's cache and **only** that: the file scan is not cached by MPFB at all.

**Not capped and not paged.** An expressions library is tens of files, and each
entry is small; ``face_units`` is included per entry because it is what an
expression *is*, and an agent choosing one should not need a second call.

The behaviours above are **MPFB's, reproduced rather than tidied up**.
"""

# The local bindings below are spelled with MPFB's own capitalisation.
# pylint: disable=invalid-name

__all__ = (
    "PARAMS",
    "SUMMARY",
    "list_expressions",
)

import json
import os

from ..log import get_logger
from ..validation import Param
from ..validation import TYPE_BOOLEAN

_LOG = get_logger("commands.listexpressions")

PARAMS = (
    Param("refresh", TYPE_BOOLEAN, default=False,
          description="Bust FaceService's cached probe for the faceunits01 asset pack. The "
                      "file scan itself is never cached, so this changes nothing else."),
)

SUMMARY = "List the saved expressions MPFB can apply, with the fragment each is addressed by."


def _walk(services, roots):
    """MPFB's precedence, walked again to find what its own scan drops silently.

    Returns ``(winners, unreadable, shadowed)``. ``winners`` maps a fragment to
    the absolute path that claimed it, which is what ``list_available_expressions``
    kept; the two lists are what it dropped.
    """
    FaceService = services["FaceService"]
    winners = {}
    unreadable = []
    shadowed = []
    for root in roots:
        root_norm = os.path.abspath(root)
        if not os.path.isdir(root_norm):
            continue
        for dirpath, _dirs, files in os.walk(root_norm):
            for name in sorted(files):
                if not name.lower().endswith(".json"):
                    continue
                path = os.path.abspath(os.path.join(dirpath, name))
                fragment = os.path.relpath(path, root_norm).replace(os.sep, "/")
                if fragment in winners:
                    shadowed.append(dict(fragment=fragment, path=path,
                                         shadowed_by=winners[fragment]))
                    continue
                try:
                    FaceService.load_expression(path)
                except (IOError, ValueError, json.JSONDecodeError) as error:
                    unreadable.append(dict(fragment=fragment, path=path, error=str(error)))
                    continue
                winners[fragment] = path
    return winners, unreadable, shadowed


def _entry(services, path, fragment, metadata, root_for):
    FaceService = services["FaceService"]
    try:
        face_units, _metadata = FaceService.load_expression(path)
    except (IOError, ValueError, json.JSONDecodeError):
        face_units = {}
    return dict(
        fragment=fragment,
        path=str(path),
        root=root_for(path),
        label=str(metadata.get("label", "")),
        description=str(metadata.get("description", "")),
        tags=[str(tag) for tag in (metadata.get("tags") or [])],
        author=str(metadata.get("author", "")),
        license=str(metadata.get("license", "")),
        face_units={name: round(float(value), 6) for name, value in sorted(face_units.items())},
    )


def _message_for(count, roots, unreadable, shadowed, installed):
    parts = ["{:d} expression(s) found in {:d} expressions root(s).".format(count, len(roots))]
    if not roots:
        parts = ["No expressions root exists under any of MPFB's data roots, so there is "
                 "nothing to list."]
    if unreadable:
        parts.append(" {:d} file(s) could not be parsed and are skipped by MPFB; see "
                     "unreadable.".format(len(unreadable)))
    if shadowed:
        parts.append(" {:d} file(s) are hidden behind a same-named file in a higher-priority "
                     "root and cannot be applied; see shadowed.".format(len(shadowed)))
    if not installed:
        parts.append(" The faceunits01 asset pack does not appear to be installed, so none of "
                     "these can be applied: every face-unit target they name is missing.")
    return "".join(parts)


def list_expressions(params, resolution):
    """Catalogue the installed expressions, and what MPFB's own scan dropped."""
    services = resolution.services
    FaceService = services["FaceService"]
    AssetService = services["AssetService"]

    installed = bool(FaceService.is_faceunits01_installed(force_recheck=params["refresh"]))
    roots = [str(root) for root in AssetService.get_asset_roots("expressions")]

    def root_for(path):
        for root in roots:
            root_norm = os.path.abspath(root)
            if os.path.abspath(path).startswith(root_norm + os.sep):
                return root
        return None

    entries = [
        _entry(services, path, fragment, dict(metadata or {}), root_for)
        for path, fragment, metadata in FaceService.list_available_expressions()
    ]
    _winners, unreadable, shadowed = _walk(services, roots)

    _LOG.debug("list_expressions: %d entries, %d unreadable, %d shadowed",
               len(entries), len(unreadable), len(shadowed))

    return dict(
        expressions=entries,
        count=len(entries),
        roots=roots,
        unreadable=unreadable,
        shadowed=shadowed,
        faceunits01_installed=installed,
        message=_message_for(len(entries), roots, unreadable, shadowed, installed),
    )
