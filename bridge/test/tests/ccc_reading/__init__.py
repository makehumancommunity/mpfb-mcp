"""
**One module per read-only command**, against a real MPFB. Each is named after
its command exactly: ``list_rigs_test.py`` tests ``commands/list_rigs.py``.

This layer runs after ``aaa_addon/`` and before ``ddd_mutating/``, because a
mutating test that reads its result back through one of these commands means
nothing if the read is not sound. A read-only command cannot leave anything
behind, so the cleanup rules in ``ddd_mutating/__init__.py`` are not owed here -
but a module that redirects MPFB's data roots or locations still restores them
before its ``with`` block exits, since the modules after it share one Blender.
"""

__all__ = ()
