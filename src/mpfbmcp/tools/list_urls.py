"""
The ``mpfb_list_urls`` tool: where to send somebody who needs a page rather than a call.

An agent driving MPFB through these tools can find out what is installed and
what a character is made of. What it cannot do is look anything *up*, and the
failure mode when it needs to is not an error but a guessed URL presented as
fact. This tool hands out addresses so nothing has to be assembled.

**It answers in four states, and none of them is an error envelope.** MPFB read
live; MPFB absent; MPFB loaded but not initialized; and Blender unreachable
altogether. The last is the reason this module exists in the shape it does: a
links tool that fails when MPFB is missing is useless in the one situation where
"where do I download MPFB" is the question. So this is the only tool in the
package that catches a connection failure and answers anyway.

**Two things about that catch are load-bearing.** It catches ``ConnectionError``
only - the transport failure both wire clients raise - and never a payload or
command that raised *inside* Blender, which is a defect and must still surface
as an error envelope; swallowing one into a "fallback" answer would hide it
permanently. And it lives here rather than in ``connection.py``,
``bridge_connection.py`` or ``shared_cache.py``, because the other twenty-three
tools depend on a connection failure being an error. This is one tool's
exception, not a change to the wire layer.

**On the bridge, one narrow case answers differently, and the difference is
deliberate.** ``bridge_connection.send_command()`` raises ``ConnectionError``
when the bridge is unreachable - the same situation, caught by the same
``except`` - but an **incompatible protocol version** comes back as an *error
envelope* instead, and so reaches the caller as an error where the generated
path would have answered with vendored URLs. FR 032 decided it that way on
purpose: a handshake refusal means mpfb-mcp and the add-on are different
versions of the same software, which is a configuration fault the operator has
to fix and which papering over with a fallback answer would hide for as long as
it lasts. An unreachable Blender is somebody else's circumstance; a version
mismatch is this install's defect, and the two should not look alike.

**The merge lives on this side of the socket**, in ``mpfbmcp.reference.urls``:
the payload reports raw key -> URL pairs and the reason for any miss, and the
answer is assembled here. That is what lets the unreachable-Blender case give
the same answer shape as the live one from one implementation - see the payload
docstring for why sending the table into Blender instead would be worse.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import backend
from mpfbmcp.reference import urls

# The fourth state, which the payload's three cannot express because the payload
# never ran. Kept beside them in `mpfb_status.state` rather than in a field of
# its own, so a caller branches on one value.
_UNREACHABLE = "unreachable"


def _answer(*, live_urls, state, package, version, weburls_module, weburls_read,
            reason, skipped_keys, blender_reachable) -> dict[str, object]:
    """The one response shape, built the same way in all four states."""
    answer = urls.merge(live_urls)
    answer["source_of_truth"] = "mpfb" if weburls_read else "builtin_fallback"
    answer["fallback_reason"] = reason
    answer["blender_reachable"] = blender_reachable
    answer["skipped_keys"] = skipped_keys
    answer["mpfb_status"] = {
        "state": state,
        "package": package,
        "version": version,
        "weburls_module": weburls_module,
        "weburls_read": weburls_read,
    }
    return answer


def _from_payload(payload: dict[str, object]) -> dict[str, object]:
    urls_read = payload.get("urls") if payload.get("weburls_read") else None
    return _answer(
        live_urls=urls_read,
        state=payload.get("state"),
        package=payload.get("package"),
        version=payload.get("version"),
        weburls_module=payload.get("weburls_module"),
        weburls_read=bool(payload.get("weburls_read")),
        reason=payload.get("reason"),
        skipped_keys=payload.get("skipped_keys"),
        blender_reachable=True,
    )


def _from_unreachable_blender(failure: Exception) -> dict[str, object]:
    return _answer(
        live_urls=None,
        state=_UNREACHABLE,
        package=None,
        version=None,
        weburls_module=None,
        weburls_read=False,
        # The socket error's own message, which names the host and port, so a
        # caller can see whether the address is wrong or Blender is simply not
        # running. It is the reason for the degradation, not a failure of it.
        reason="Blender could not be reached, so MPFB's own addresses could not be read; the "
               "addresses below are mpfb-mcp's vendored copy of them. " + str(failure),
        skipped_keys=None,
        blender_reachable=False,
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="List MPFB Web Addresses",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            # The one tool here whose answer is about things outside this
            # Blender, even though it opens no connection to any of them.
            openWorldHint=True,
        )
    )
    def mpfb_list_urls() -> dict[str, object]:
        """
        Addresses for the MPFB and MakeHuman community sites: downloading MPFB,
        asset packs, documentation, forum, issue tracker. Takes no arguments,
        changes nothing, and **fetches nothing** - it hands back URLs for the
        client to retrieve.

        Use it rather than composing a makehumancommunity.org address. Reach
        for it when `mpfb_list_assets` finds little (`URL_ASSET_PACKS`) or
        `mpfb_get_status` reports the system assets pack missing
        (`URL_SYSTEM_ASSETS`). For MPFB's *developer* documentation, one
        document per service and file format, use `mpfb_list_docs` instead.

        **It answers even when MPFB or Blender is unreachable**, which is when
        these links matter most - so check `source_of_truth` before quoting a
        URL: `"mpfb"` was read from the running MPFB, `"builtin_fallback"` is
        mpfb-mcp's vendored copy with `fallback_reason` saying why. Neither is
        an error.

        `result` carries:

          - `urls`: every link, each `{key, url, title, description, keywords,
            source}`. `key` is MPFB's own constant name (`URL_ASSET_PACKS`).
            `source` is `"mpfb"` for one of MPFB's constants, `"mpfb_mcp"` for
            an ecosystem link this package adds (MakeHuman itself, the
            community asset repository). `title`, `description` and `keywords`
            are mpfb-mcp's text rather than MPFB's, and are `null` for a
            constant MPFB has added since.
          - `source_of_truth`, `fallback_reason`, `blender_reachable`, and
            `mpfb_status` (`state`: `ok`, `absent`, `not_initialized` or
            `unreachable`; plus `package`, `version`, `weburls_module`,
            `weburls_read`).
          - `fallback_stale` and `fallback_differences`: whether the vendored
            copy disagrees with the running MPFB, and per key how (`changed`,
            `added_by_mpfb`, `missing_from_mpfb`). Both `null` when there was
            nothing live to compare against, which is not agreement.
          - `count`, `vendored_mpfb_key_count`, `skipped_keys`.

        **Not capped and not paged**: around twenty entries, all of them, every
        call. No `truncated` or `total_count` to check.
        """
        try:
            envelope = backend.send("list_urls")
        except ConnectionError as failure:
            # Only the transport failure, and **both transports raise it in the
            # same situations** - which is what made this tool migratable at
            # all. A payload or command that raised inside Blender arrives as
            # an error *envelope* below and is passed through untouched,
            # because it is a defect here rather than a missing MPFB.
            return {"status": "ok", "result": _from_unreachable_blender(failure)}

        if envelope.get("status") != "ok" or not isinstance(envelope.get("result"), dict):
            # Including a **protocol handshake refusal**, which is the one case
            # where this tool answers differently on the two transports. See
            # this module's docstring for why that is deliberate.
            return envelope
        return {"status": "ok", "result": _from_payload(envelope["result"])}
