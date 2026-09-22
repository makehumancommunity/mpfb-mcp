# SPDX-License-Identifier: GPL-3.0-or-later

"""
Pinning a test module to the generated path, now that it is not the default.

**FR 032 flipped the default backend to the bridge**, and that quietly changed
what a large part of this suite was testing. Dozens of tests mock
``mpfbmcp.backend.send_code`` and then assert about the program that reached it
- the assembled source, the bootstrap, the shared fragments, the ``PARAMS``
prelude. Every one of those is a claim about the **generated path**, and with
the bridge as the default the call no longer goes anywhere near the mock: it
tries to open a socket instead.

The fix is to say what those tests already meant. :func:`pin` sets
``MPFB_MCP_BACKEND=blender_mcp`` for the module that calls it, so the mocked
send is the one the tool reaches, and :func:`unpin` puts the environment back.
Used as ``setUpModule`` / ``tearDownModule``, which is one line each and keeps
the statement at the top of the file where a reader meets it.

**It is a pin, not a default.** A test that is about the *bridge* overrides it
per-test through ``fake_bridge.BridgeTestCase.set_env_var``, which records the
value it found - the pin - and restores it afterwards. So the two live together:
a module says "these tests are about generated code" and one class inside it
says "this one is not".

This module holds no tests. It exists so that the paragraph above is written
once rather than twenty-six times.
"""

from __future__ import annotations

__all__ = (
    "pin",
    "unpin",
)

import os

from mpfbmcp import backend

# What was in the environment before the pin, so that a suite run with
# MPFB_MCP_BACKEND already set does not have it silently discarded.
_PREVIOUS: dict[str, str | None] = {}


def pin() -> None:
    """Point this module's tests at the generated path. Use as ``setUpModule``."""
    _PREVIOUS["value"] = os.environ.get(backend.BACKEND_VARIABLE)
    os.environ[backend.BACKEND_VARIABLE] = backend.BACKEND_BLENDER_MCP


def unpin() -> None:
    """Put the environment back. Use as ``tearDownModule``."""
    previous = _PREVIOUS.pop("value", None)
    if previous is None:
        os.environ.pop(backend.BACKEND_VARIABLE, None)
    else:
        os.environ[backend.BACKEND_VARIABLE] = previous
