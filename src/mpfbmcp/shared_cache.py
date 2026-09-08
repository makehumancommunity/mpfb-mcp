"""
Sending a program whose shared fragments Blender may already have.

The four modeling-target tools carry 26 KB of shared fragments that are
byte-identical from one call to the next, and a generated program costs about
250 ms per 4 KB on the wire whatever it contains (see
specifications/architecture.md#what-a-call-costs-is-the-size-of-its-program).
This module is the tool side of the arrangement that stops paying for them
twice: ``codegen``'s loader keeps a fragment's source inside Blender under a
hash of itself, and ``send()`` below decides whether a given call has to carry
that source or may refer to it.

Three things about it are decisions rather than details.

**What is cached is source, not results.** The obvious cache to build here was
of the *answer* - MPFB's modeling category table, which is what the 26 KB is
mostly there to construct. It was measured first, and the construction turned
out to take about 4 ms: what a call was paying for was never the scan but the
description of it. Caching the description instead is both the larger saving and
the safe one, because a cache of code keyed by that code's hash cannot go stale,
while a cache of what is on disk can - and a stale category table means a
modifier written to the wrong shape key. Every call still runs the scan, so
``mpfb_list_targets`` still sees a target installed since Blender started, which
MPFB's own panels cannot.

**A cold call carries the sources rather than making a second round trip.** The
alternative - a small priming call followed by the real one - costs an extra
round trip on the cold path and saves nothing on the warm one. Carrying them
means a cold call costs exactly what every call used to cost.

**The retry exists because the memo can be wrong.** ``_PRIMED`` records what
this process has sent to this address, and Blender restarting invalidates that
without telling anyone. So a miss is an ordinary outcome: the loader raises with
a marker, this module drops the memo, re-assembles with the sources and sends
once more. Never twice, because a second miss means the cache is not being
written at all and the caller is better served by that error than by a loop.
"""

from __future__ import annotations

__all__ = (
    "CACHE_MISS_MARKER",
    "send",
)

from mpfbmcp import codegen
from mpfbmcp.codegen.shared_loader import SHARED_CACHE_MISS_MARKER as CACHE_MISS_MARKER
from mpfbmcp.connection import get_connection_params, send_code

# (host, port, "<fragment>@<fingerprint>") triples this process has sent the
# source of. Not a claim about Blender's state - only about what was sent -
# which is why a miss below is treated as ordinary rather than as a
# contradiction.
_PRIMED: set[tuple[str, int, str]] = set()


def _keys(shared: list[str]) -> list[tuple[str, int, str]]:
    host, port = get_connection_params()
    return [(host, port, codegen.shared_key(name)) for name in shared]


def _is_cache_miss(response: dict[str, object]) -> bool:
    return (response.get("status") == "error"
            and CACHE_MISS_MARKER in str(response.get("message") or ""))


def send(payload: str, params: dict[str, object], *, shared: list[str],
         bootstrap: str = "raising") -> dict[str, object]:
    """Assemble and send one payload, carrying its fragments' source if needed.

    Always ``strict_json``: every payload reaching here builds plain JSON-safe
    data, and a value that stops being so should surface as a clear error rather
    than as a repr.
    """
    keys = _keys(shared)
    carry_sources = not all(key in _PRIMED for key in keys)

    for attempt in (1, 2):
        code = codegen.assemble(
            payload, bootstrap=bootstrap, params=params,
            cached_shared=shared, carry_sources=carry_sources)
        response = send_code(code, strict_json=True)
        if carry_sources:
            _PRIMED.update(keys)
        if attempt == 2 or not _is_cache_miss(response):
            return response
        # The memo was wrong: Blender restarted, or something cleared the
        # session module. Say so by sending the sources again.
        _PRIMED.difference_update(keys)
        carry_sources = True

    raise AssertionError("unreachable: the loop above returns on both attempts")
