"""
Concepts two or more commands model identically. **Nothing here is a command.**

This directory is the other half of the closed vocabulary. [`commands/table.py`](../commands/table.py)
is the one file a sceptic reads to know everything this add-on can be asked to
do, and that claim survives a second directory appearing beside it only because
of what is true of every module in this one: **no module here is reachable from
the wire**. There is no handler, no ``PARAMS``, no entry in ``COMMANDS``, and
nothing here is dispatched. A command imports one of these the way it imports
``os``.

**Why a directory rather than an import between commands.** Each module here is
a thing two or more commands have to agree about, where disagreeing is a defect
a caller cannot see: ``list_rigs`` predicts which file ``add_rig`` will load,
``list_assets`` reports the vocabulary ``add_asset`` resolves with, all three
preset commands build ``<user config>/human.<name>.json`` the same way, and all
four refitting commands decide the same way whether a refit would silently leave
the rig behind. One implementation is the only way to guarantee agreement;
``add_rig`` importing ``list_rigs`` would make the catalogue depend on the
acting command and put a scan behind a handler.

**That is why these functions take a leading ``services`` argument rather than
binding MPFB at import.** An add-on module that resolved MPFB at import time
would hold a services dict across a disable and re-enable, which is exactly the
stale state nobody thinks to suspect - :func:`mpfb_resolution.resolve` is called
per dispatch for that reason. ``target_categories`` takes a ``tables`` argument
for the same class of reason at a different timescale: its scan must be per
call, or a target installed since Blender started would be invisible.

**These modules carry lint findings on purpose**, and the reason has changed
since they were written. pylint has things to say about them - a missing
docstring, an ``open()`` with no ``encoding``, an unused loop variable - and
each is inherited character for character from MPFB's own source, which these
bodies are written to be readable beside. Fixing one silently moves this code
away from the thing it reproduces. They are ordinary findings now that nothing
compares these files against a second copy, so fix one *deliberately* and say
in the commit which MPFB behaviour the new spelling still reproduces.

**Seven modules**, and the count is not a coincidence: they are the seven
concepts more than one command needed. ``preset_files``, ``rig_lookup``,
``asset_sections``, ``target_categories`` and ``modifier_reading`` arrived with
FR 031's read-only commands; ``performed`` and ``refit_blocker`` with FR 032's
mutating ones. Each mirrors a shared fragment from the generated-code path that
FR 033 deleted, name for name, which is why the names are what they are.

``performed`` is the plainest of the seven and the one exception to the
``services`` rule above: it reads nothing out of MPFB, so it takes no services
dict - it is one function over a dict the command has already finished
building.
"""

__all__ = ()
