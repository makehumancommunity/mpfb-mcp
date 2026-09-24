"""
The ``mpfb_list_expressions`` tool: which saved expressions are installed.

The catalogue for ``mpfb_apply_expressions``, over the JSON files MPFB's
``FaceService.list_available_expressions()`` finds under ``expressions/`` in
every data root - which is also what MPFB's expressions-library panel draws its
sliders from. Each entry carries both identifiers, and ``fragment`` is the one
to pass, per
[how tools name things that can be added](../../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added):
the applied-expressions stack stores fragments, so a fragment is what survives a
move to another machine and a preset round trip.

Uncapped and unpaged, deliberately: an expressions library is tens of files. A
caller should not look for ``truncated``.

The reasoning behind what the answer carries - the roots, the files MPFB's scan
drops, the shadowing rule - is in the command's docstring,
``bridge/mpfb_bridge/commands/list_expressions.py``.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import backend


def _validated_refresh(refresh: object) -> bool:
    if not isinstance(refresh, bool):
        # Deliberately not truthiness: `refresh="false"` is a true value.
        raise ValueError("refresh must be a bool, got {!r}".format(refresh))
    return refresh


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="List Expressions",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_list_expressions(refresh: bool = False) -> dict[str, object]:
        """
        List the saved expressions MPFB can apply - named, weighted
        combinations of ARKit face units such as a smile - as
        `mpfb_apply_expressions` takes them. Changes nothing.

        `result`'s `expressions` is one entry each: **`fragment`, the identifier
        to pass** (library-relative, portable across machines), `path` (the
        absolute file, for checking), `root`, `label`, `description`, `tags`,
        `author`, `license` and `face_units` (what the expression sets). Not
        capped or paged.

        `roots` lists the directories scanned, in MPFB's priority order,
        whether or not anything was found. `unreadable` names files MPFB
        skips because they do not parse. `shadowed` names files hidden behind a
        same-named file in a higher-priority root: MPFB cannot apply them.

        `faceunits01_installed` is always present: without that asset pack no
        expression can be applied. `refresh` (default false) re-probes for the
        pack; the file scan itself is never cached.
        """
        # `result` (built in bridge/mpfb_bridge/commands/list_expressions.py) is
        # plain JSON-safe data.
        return backend.send(
            "list_expressions",
            params={"refresh": _validated_refresh(refresh)},
        )
