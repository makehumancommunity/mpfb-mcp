"""
Concepts two or more commands model identically. **Nothing here is a command.**

This directory is the other half of the closed vocabulary. [`commands/table.py`](../commands/table.py)
is the one file a sceptic reads to know everything this add-on can be asked to
do, and that claim survives a second directory appearing beside it only because
of what is true of every module in this one: **no module here is reachable from
the wire**. There is no handler, no ``PARAMS``, no entry in ``COMMANDS``, and
nothing here is dispatched. A command imports one of these the way it imports
``os``.

**Why a directory rather than an import between commands.** Each module here
is something two or more commands have to agree about, or one concept they
would otherwise each write for themselves: ``list_rigs`` predicts which file
``add_rig`` will load, all three preset commands build
``<user config>/human.<name>.json`` the same way, all twenty commands that
take a subject resolve it the same way, and all six refitting commands decide
the same way whether a refit would silently leave the rig behind. One
implementation is the only way to guarantee agreement; ``add_rig`` importing
``list_rigs`` would make the catalogue depend on the acting command and put a
scan behind a handler.

**What belongs here is decided by a rule, not a count**
([architecture.md](../../../specifications/architecture.md#shared-modules-and-what-warrants-one)).
Code whose drift would mislead a caller is always shared. An identical helper
that can be named as one concept is shared too, since an import costs nothing:
that is what ``blender_data`` is. A convention whose body differs per command -
``_blocked``, ``_refusal``, ``_message_for`` - is not. And where the condition is
shared, the wording stays with each command, as ``refit_blocker`` established
and ``subject_resolution`` follows. The modules are named for their concept;
there is no ``utils`` here, and a helper with no natural home stays duplicated
until it has one.

**Most functions here take a leading ``services`` argument rather than binding
MPFB at import.** An add-on module that resolved MPFB at import time would hold
a services dict across a disable and re-enable, which is exactly the stale state
nobody thinks to suspect - :func:`mpfb_resolution.resolve` is called per
dispatch for that reason. ``target_categories`` takes a ``tables`` argument for
the same class of reason at a different timescale: its scan must be per call,
or a target installed since Blender started would be invisible. ``asset_info``
takes a ``Lookup`` built from ``services`` once per call.

The modules that read nothing out of MPFB's services take no ``services`` at
all: ``performed`` is one function over a dict the command has already finished
building, ``artifact_names`` works on a name and a path, ``expression_panel``
takes MPFB's root package name, ``selection`` and ``blender_data`` read plain
Blender state, and ``subject_resolution``'s subject step reads the view layer
and ``bpy.data`` - only its basemesh step takes ``services``.

**These modules carry lint findings on purpose**, and the reason has changed
since they were written. pylint has things to say about them - a missing
docstring, an ``open()`` with no ``encoding``, an unused loop variable - and
each is inherited character for character from MPFB's own source, which these
bodies are written to be readable beside. Fixing one silently moves this code
away from the thing it reproduces. Fix one *deliberately*, and say in the
commit which MPFB behaviour the new spelling still reproduces.

How the modules got here is in
[HISTORY.md](../../../feature-requests/HISTORY.md): seven mirror a shared fragment
of the generated-code path FR 033 deleted, three arrived with the expression
library, three with the character summary, four with
[FR 036](../../../feature-requests/done/036-subject-resolver-and-duplication/README.md), and
``material_settings`` with
[FR 040](../../../feature-requests/done/040-procedural-material-settings/README.md), which
both material settings commands and the character summary must agree about.
"""

__all__ = ()
