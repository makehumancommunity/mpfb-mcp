"""
The loader that lets a shared fragment be sent once per Blender session.

This is the second and last part of a generated program written as a string
rather than as a file under ``payloads/`` or ``shared/``, and for the same
reason as ``bootstrap.py``: it is what *runs* the files, so it cannot be one of
them.

**Why it exists is a measurement.** The blender_mcp add-on reads one 4 KB chunk
of a request per timer tick, so a generated program costs about 250 ms per 4 KB
against a Blender that has been talked to recently and about 1 s per 4 KB
against one that has not - regardless of what the program does (see
specifications/architecture.md#what-a-call-costs-is-the-size-of-its-program).
The fragments the four modeling-target tools carry are 26 KB of that, and they
are byte-identical from one call to the next. Sending them once and referring to
them afterwards takes five to six chunks off every subsequent call.

**What is cached is source, not results.** That distinction is the whole safety
argument. A cache of *answers* about the disk can go stale, and a stale modeling
category table means a modifier written to the wrong shape key; a cache of
*code*, keyed by a hash of that code, cannot be stale by construction, and the
code still runs on every call - so a target installed since Blender started is
still seen, which is a property ``mpfb_list_targets`` exists partly to have.

The key is ``<name>@<fingerprint>``, so two mpfb-mcp servers against one Blender
share a fragment exactly when their copies of it are identical, and a fragment
edited between two runs of the same server is a different entry rather than the
same one gone wrong.

A fragment Blender does not have is a **request, not a failure**: the program
raises with ``MPFB_MCP_SHARED_CACHE_MISS`` in the message, and
``mpfbmcp.shared_cache`` re-sends the call with the source in it.
"""

from __future__ import annotations

__all__ = (
    "SHARED_CACHE_MISS_MARKER",
    "SHARED_SOURCE_LOADER",
)

# Must match MPFB_MCP_SHARED_CACHE_MISS in the loader below. Pinned by a test
# that reads both rather than by this comment.
SHARED_CACHE_MISS_MARKER = "MPFB_MCP_SHARED_CACHE_MISS"

SHARED_SOURCE_LOADER = '''
import types

# mpfb-mcp's own scratch module inside Blender. Never an attribute grafted onto
# one of MPFB's modules, and never a datablock property: a scene property would
# reach the user's .blend file, mark it dirty, and outlive the Blender session
# it describes.
MPFB_MCP_SESSION_MODULE = "mpfb_mcp_session_state"

# What the tool side matches to know a fragment has to be sent again.
MPFB_MCP_SHARED_CACHE_MISS = "MPFB_MCP_SHARED_CACHE_MISS"


def _mpfb_mcp_session_state():
    module = sys.modules.get(MPFB_MCP_SESSION_MODULE)
    if module is None or not hasattr(module, "shared_sources"):
        module = types.ModuleType(MPFB_MCP_SESSION_MODULE)
        module.__doc__ = (
            "Shared fragment source left inside Blender by mpfb-mcp, keyed by a hash of "
            "itself. Safe to delete at any time: the next call that needs a fragment "
            "this Blender does not have carries it again.")
        module.shared_sources = dict()
        sys.modules[MPFB_MCP_SESSION_MODULE] = module
    return module


def _mpfb_mcp_shared(name, fingerprint, source):
    """Run one shared fragment, from this program or from the session cache.

    Executed into globals(), so what the fragment defines is bound exactly as it
    would be had the fragment been concatenated here - which is what happened
    until the transport cost of concatenating it was measured. Compiled under
    the fragment's own name, so a traceback from inside it names the file and
    the line within that file rather than an offset into the whole program.
    """
    cache = _mpfb_mcp_session_state().shared_sources
    key = name + "@" + fingerprint
    if source is None:
        source = cache.get(key)
        if source is None:
            raise RuntimeError(
                MPFB_MCP_SHARED_CACHE_MISS + ": this Blender does not hold '" + key
                + "'. Resend the program with that fragment's source in it.")
    else:
        cache[key] = source
    exec(compile(source, "<shared: " + name + ">", "exec"), globals())
'''.strip()
