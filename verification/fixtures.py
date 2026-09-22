# SPDX-License-Identifier: GPL-3.0-or-later

"""
The install gate, and the one character the whole run acts on.

**Nothing here names an asset by filename.** FR 013's fixtures did, which was a
reasonable cost for a session written against one developer's Blender and is not
one for a check meant to run on anybody's. What the run needs - a skin, a
garment, a rig - it asks the catalogue tools for and takes the first workable
answer; where the install has none, the item that needed it reports ``skipped``
with the reason and the run still passes.

**The gate runs before anything else** so that a Blender without MPFB is one
clear line rather than twenty tracebacks. It checks exactly what every item
needs: that MPFB is loaded and initialized. Everything else - Rigify, a custom
rig, a skin, an MHCLO asset - is a per-item prerequisite and is discovered by
the item that wants it, because a missing one is a skip rather than a stop.

**One character, built once.** Every subsequent item acts on it, in the order
MPFB documents: create, model, rig, dress, generate, undress. The run's cost is
dominated by what it builds, and FR 013's directory built fifty characters
because each of its eight checklists had to be independently runnable. With one
script there is nothing to be independent of.

**The character keeps the name MPFB gave it.** It used to be renamed to
something the report could point at, which needed a channel into Blender the
harness no longer has (FR 033). So every item addresses it by the name
``mpfb_create_human`` answered with - ``Human``, or ``Human.001`` where the
scene already held one - which is what a real client would have to do anyway.
"""

from __future__ import annotations

__all__ = (
    "check_install",
    "create_character",
    "first_asset",
)


def check_install(tools: dict) -> dict:
    """Is MPFB there and initialized? Reported as what was found, never as an error.

    ``mpfb_get_status`` classifies rather than fails, which is what makes it
    usable as a gate: ``state`` is ``absent``, ``not_initialized`` or ``ok``, and
    only the last one can run anything below.
    """
    envelope = tools["mpfb_get_status"]()
    if envelope.get("status") != "ok":
        return dict(usable=False, state=None, envelope=envelope)
    status = envelope["result"]
    return dict(
        usable=status.get("state") == "ok",
        state=status.get("state"),
        message=status.get("message"),
        mpfb_version=status.get("version"),
        blender=(status.get("blender") or dict()).get("version"),
        rigify_available=status.get("rigify_available"),
        envelope=envelope,
    )


def create_character(tools: dict) -> tuple:
    """Build the run's character with the tool's own defaults.

    Returns the envelope beside the object's name, because the ``performed``
    audit is made on the envelope and every later item addresses the character
    by name. The name is MPFB's own - see the module docstring: giving the
    character a name of the harness's choosing needed a channel into Blender
    that FR 033 removed, and the tool answers with the name anyway.
    """
    envelope = tools["mpfb_create_human"]()
    if envelope.get("status") != "ok":
        return envelope, None
    return envelope, envelope["result"]["object_name"]


def first_asset(tools: dict, asset_subdir: str) -> dict | None:
    """The first asset this install has in a subdir, or None if it has none.

    ``limit=1`` and ``refresh`` left at its default ``false``: the run must not
    rescan the library, and one entry is all any item here wants. The answer is
    still MPFB's own deterministic ordering, so two runs against one install
    pick the same asset.
    """
    envelope = tools["mpfb_list_assets"](asset_subdir=asset_subdir, limit=1)
    if envelope.get("status") != "ok":
        return None
    assets = envelope["result"].get("assets") or []
    return assets[0] if assets else None
