"""
Concepts two or more commands model identically. **Nothing here is a command.**

This directory is the other half of the closed vocabulary. [`commands/table.py`](../commands/table.py)
is the one file a sceptic reads to know everything this add-on can be asked to
do, and that claim survives a second directory appearing beside it only because
of what is true of every module in this one: **no module here is reachable from
the wire**. There is no handler, no ``PARAMS``, no entry in ``COMMANDS``, and
nothing here is dispatched. A command imports one of these the way it imports
``os``.

It mirrors [`src/mpfbmcp/codegen/shared/`](../../../src/mpfbmcp/codegen/shared)
name for name, for the same reason ``commands/`` mirrors ``tools/``: during the
migration a fragment and the module that replaces it must be findable from each
other, and after the migration the fragment is deleted and this stays. A
fragment is standalone source concatenated ahead of a payload, reading
``_MPFB_SERVICES`` bound by the bootstrap; a module here is imported, and is
handed MPFB as the ``services`` dict every command handler already receives.

**That is why these functions take a leading ``services`` argument rather than
binding MPFB at import**, and the shape is worth the mild awkwardness twice
over. An add-on module that resolved MPFB at import time would hold a services
dict across a disable and re-enable, which is exactly the stale state nobody
thinks to suspect - :func:`mpfb_resolution.resolve` is called per dispatch for
that reason. And keeping the *bodies* character for character identical to the
fragment's is what lets
[`tests/test_fragment_drift.py`](../../../tests/test_fragment_drift.py) compare
the two with ``ast`` on every unit run, with no Blender, for as long as both
exist. The pairing guarantee those fragments were written for -
``list_rigs`` predicting what ``add_rig`` will load, ``list_assets`` reporting
the vocabulary ``add_asset`` resolves with - has to survive a stage boundary
with one half migrated and the other not, and "these two agree" is worth
asserting rather than intending.

**These modules carry their fragment's lint findings on purpose.** pylint has
things to say about them - a missing docstring, an ``open()`` with no
``encoding``, an unused loop variable - and every one of them is inherited
character for character from the fragment. Fixing it here alone breaks the
drift check; fixing it in both is a change to a payload's behaviour made during
a migration, which is exactly what
[FR 031](../../../feature-requests/done/031-introspection-and-catalogues-migrated/README.md)
forbids, because a tidy-up is indistinguishable from a defect in the comparison
the migration rests on. They become ordinary findings, fixable in one place, on
the day the fragment is deleted.

Five modules, one per migrating fragment: ``preset_files``, ``rig_lookup``,
``asset_sections``, ``target_categories`` and ``modifier_reading``. The two
fragments that did not migrate - ``performed.py`` and ``refit_blocker.py`` -
belong to mutating tools and arrive with them.
"""

__all__ = ()
