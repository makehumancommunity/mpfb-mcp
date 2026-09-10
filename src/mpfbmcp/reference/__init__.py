"""
Vendored reference data: addresses this package hands out, and nothing else.

Two ordinary modules, ``urls`` and ``docs``, holding tables that are read *by*
this package rather than sent to Blender. That is the whole reason they are a
real sub-package rather than files under ``codegen/payloads/`` or a new data
directory: a payload is source that crosses the socket and is never imported
here, and these are the exact opposite of that.

**Nothing here fetches anything.** The tables carry addresses, and retrieving
one is the MCP client's job - see
[the network boundary](../../../specifications/architecture.md#mpfb-mcp-opens-no-network-connection-except-the-one-to-the-add-on).

**Both tables drift**, and neither can be checked at run time without the
network: ``urls`` is a copy of MPFB's ``ui/weburls.py``, which MPFB edits, and
``docs`` names files in the mpfb2 repository, which are renamed and removed.
``tests/test_reference_drift.py`` checks both against a sibling ``../mpfb2``
checkout when there is one, and skips when there is not.
"""

from __future__ import annotations

__all__ = ()
