"""
The ``mpfb_apply_expressions`` tool: wear one saved expression, or several.

Changes MPFB's applied-expressions stack on the basemesh and lets MPFB rebuild
the face from it - the mechanism MPFB's expressions-library panel and its preset
loader use. **Batched**, the ``mpfb_set_targets`` idiom: MPFB's own path is one
full stack rebuild per slider, and reproducing a saved face row by row across
the socket would be one rebuild per expression. This makes one.

**Validated here is shape.** Each entry is a dict with
exactly ``fragment`` (a non-empty string) and ``weight`` (0.0-1.0), and a
fragment may appear once per call. Whether a fragment names a real file is
answered in Blender, where ``find_asset_absolute_path`` will resolve it the same
way the rebuild does, per
[validate before crossing the socket](../../../specifications/tool-interface.md#validate-before-crossing-the-socket).
``mode`` is checked here as well as there, and that is **not** the vocabulary
exception that section allows: no MPFB function ever sees it. It is this
package's own two-value vocabulary, choosing how the command builds the stack,
so it cannot drift from MPFB and is a shape like any other - and there is no
reading of an unknown mode that is safe to guess.

Only ``fragment`` is taken, not ``path``, although ``mpfb_list_expressions``
reports both. That departs from
[an acting tool accepts every identifier its catalogue reports](../../../specifications/tool-interface.md#an-acting-tool-accepts-every-identifier-its-catalogue-reports)
on purpose: what this tool writes is a stack row, and a stack row *is* a
fragment. A path would have to be turned back into one, and MPFB's own
conversion returns the bare basename for a file outside every root - which would
store a row that silently resolves to some other file, or to none, on the next
rebuild.

**It destroys composed work, and says so.** The rebuild clears every face unit
first, so anything composed on top of the stack with ``mpfb_set_face_units`` is
gone afterwards; the units that were are returned as ``discarded_face_units``.
The tool does not refuse: ``mpfb_save_expression`` is how an agent keeps the
work, and the description says so. See the command's docstring,
``bridge/mpfb_bridge/commands/apply_expressions.py``, for that decision and the
rest of the reasoning.
"""

from __future__ import annotations

__all__ = (
    "MAX_ENTRIES",
    "MODES",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

_ENTRY_KEYS = ("fragment", "weight")

MODES = ("merge", "replace")

# Generous, but not unbounded: an expressions library is tens of files, so a
# caller sending more than this made a mistake worth catching locally.
MAX_ENTRIES = 100


def _validated_mode(mode: object) -> str:
    if mode not in MODES:
        # Checked here as well as in Blender: see the module docstring.
        raise ValueError("mode must be one of {}, got {!r}".format(", ".join(MODES), mode))
    return mode  # type: ignore[return-value]


def _validated_expressions(value: object) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expressions must be a list of objects or omitted, got {!r}".format(
            value))
    if len(value) > MAX_ENTRIES:
        raise ValueError(
            "expressions must hold at most {} entries, got {}".format(MAX_ENTRIES, len(value)))

    checked = []
    seen = set()
    for position, entry in enumerate(value):
        where = "expressions[{}]".format(position)
        if not isinstance(entry, dict):
            raise ValueError("{} must be an object, got {!r}".format(where, entry))
        unknown = sorted(key for key in entry if key not in _ENTRY_KEYS)
        if unknown:
            raise ValueError(
                "{} has unknown key(s) {}; known keys are {}".format(
                    where, ", ".join(unknown), ", ".join(_ENTRY_KEYS)))

        fragment = entry.get("fragment")
        if not isinstance(fragment, str):
            raise ValueError("{} fragment must be a string, got {!r}".format(where, fragment))
        if not fragment.strip():
            raise ValueError("{} fragment must not be empty or whitespace".format(where))
        if fragment in seen:
            # Two weights for one row in one call has no reading that is more
            # likely right than the other.
            raise ValueError("{} repeats fragment {!r}; each may appear once".format(
                where, fragment))
        seen.add(fragment)

        weight = entry.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            # A bool is an int in Python, so True would otherwise be stored as
            # 1.0 under the guise of a number the caller never wrote.
            raise ValueError(
                "{} weight must be a number between 0.0 and 1.0, got {!r}".format(where, weight))
        if not 0.0 <= float(weight) <= 1.0:
            raise ValueError(
                "{} weight must be between 0.0 and 1.0, got {!r}".format(where, weight))

        checked.append({"fragment": fragment, "weight": float(weight)})
    return checked


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Apply Expressions",
            readOnlyHint=False,
            # The rebuild discards any face composed on top of the stack.
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_apply_expressions(name: str | None = None,
                               expressions: list[dict] | None = None,
                               mode: str = "merge",
                               refit: bool = True) -> dict[str, object]:
        """
        Put a MakeHuman character into saved expressions, through MPFB's
        applied-expressions stack - the mechanism its expressions-library panel
        and presets use, so the result survives `mpfb_save_preset`.

        `expressions` is a list of `{fragment, weight}`: `fragment` as
        `mpfb_list_expressions` reports it, `weight` in 0.0-1.0. **Weight 0.0
        removes** that expression. `mode` is `"merge"` (default: add or update
        these rows, keep the rest) or `"replace"` (the stack becomes exactly
        these rows) - **`replace` with an empty list takes every expression
        off.** Weights from several rows add up per face unit and are clamped
        at 1.0.

        **Nothing is written unless every fragment resolves**; the refusal
        (`blocked_by: "unresolved_fragments"`) names the misses and the closest
        existing fragments. It also refuses without the `faceunits01` pack.

        **The face is rebuilt from the stack**, so units composed on top of it
        with `mpfb_set_face_units` are discarded and named in
        `discarded_face_units` - call `mpfb_save_expression` first to keep them.
        `refit` (default true, as MPFB's library panel) refits clothes and rig.

        `result` carries `changed` (the stack or the face moved), `requested`
        (per row: `action` of added / updated /
        removed / unchanged / absent, and `resolved_path`), the resulting stack
        and face as `mpfb_get_expression` reports them (`applied_expressions`,
        `aggregate`, `clamped_face_units`, `matches_stack`), `stack_before`,
        `removed_by_replace` and `panel_synced` (MPFB's library sliders updated).
        """
        # `result` (built in bridge/mpfb_bridge/commands/apply_expressions.py)
        # is plain JSON-safe data.
        return backend.send(
            "apply_expressions",
            params={
                "name": arguments.validated_subject(name),
                "expressions": _validated_expressions(expressions),
                "mode": _validated_mode(mode),
                # Not truthiness: refit="false" is a true value.
                "refit": arguments.validated_flag(refit, "refit"),
            },
        )
