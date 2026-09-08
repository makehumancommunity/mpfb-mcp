"""
The ``mpfb_generate_rigify_rig`` tool: the second half of a Rigify character.

``mpfb_add_rig`` with a ``rigify.*`` identifier produces only a **meta rig** -
MPFB's panel then offers a separate Generate button, and MPFB's own randomizer
runs it *last*, after the clothes, so that their weights and sub-rigs exist when
the meta rig becomes the real one. Exposing generation as a tool of its own
rather than as a flag on adding is what lets an agent follow that order; a flag
could not express it.

Two things about ``RigService.generate_rigify_rig()`` shape this tool.

It is **not undoable and not a no-op on failure**. It renames the meta rig,
deselects everything, may run Rigify's face upgrade, and only then asks Rigify
whether the meta rig is valid - returning ``None`` if it is not, having already
done all of that. So a rejection comes back as ``generated: false`` alongside
what did happen, never as an error envelope implying nothing changed.

And ``meta_rig_action: "delete"`` is a decision with a consequence that outlives
the call: a generated Rigify rig with no meta rig in the scene is exactly the
state ``HumanService.refit()`` cannot handle, so the character can never be
refitted to a changed body shape again. The default is ``"hide"``, which is
MPFB's own, and the response reports ``refit_will_be_possible`` either way.

The one vocabulary validated on this side of the socket is
``meta_rig_action``. It is a closed enum of MPFB's own
(``ui/rigging/rigifyrig/properties/meta_rig_action.json``) rather than something
read off the filesystem, and ``generate_rigify_rig()`` silently defaults an
unknown value to ``"hide"`` - which would make a typo indistinguishable from a
choice, on the one argument whose wrong value cannot be undone.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import codegen
from mpfbmcp.connection import send_code

# MPFB's own enum, in MPFB's own order. Kept here rather than resolved in
# Blender because it is a fixed vocabulary in MPFB's source, not a scan of
# anything - the opposite of the rig identifiers, which are a directory listing.
_META_RIG_ACTIONS = ("keep", "hide", "delete")


def _validated_name(name: object) -> str | None:
    """Reject locally what would otherwise round-trip to Blender to fail there."""
    if name is None:
        return None
    if not isinstance(name, str):
        raise ValueError("name must be a string or omitted, got {!r}".format(name))
    if not name.strip():
        raise ValueError(
            "name must not be empty or whitespace; omit it to use the active object")
    return name


def _validated_rig_name(rig_name: object) -> str | None:
    if rig_name is None:
        return None
    if not isinstance(rig_name, str):
        raise ValueError("rig_name must be a string or omitted, got {!r}".format(rig_name))
    if not rig_name.strip():
        raise ValueError(
            "rig_name must not be empty or whitespace; omit it to let MPFB derive a unique name "
            "from the meta rig's")
    return rig_name


def _validated_meta_rig_action(action: object) -> str:
    """The one closed vocabulary this package validates locally.

    MPFB warns and falls back to "hide" for anything it does not recognise, so a
    typo would silently keep a meta rig the caller asked to delete - or, worse,
    read as a deliberate choice.
    """
    if not isinstance(action, str) or action not in _META_RIG_ACTIONS:
        raise ValueError(
            "meta_rig_action must be one of {}, got {!r}".format(
                ", ".join(_META_RIG_ACTIONS), action))
    return action


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Generate Rigify Rig",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_generate_rigify_rig(
        name: str | None = None,
        rig_name: str | None = None,
        meta_rig_action: str = "hide",
    ) -> dict[str, object]:
        """
        Turn a character's Rigify **meta rig** into a generated, poseable Rigify
        rig - the second step of the two `mpfb_add_rig` starts when it is given
        a `rigify.*` identifier.

        **Attach the character's clothes and other mesh assets before calling
        this.** Generation re-parents and re-weights whatever is on the
        character at the moment it runs, and nothing handles an asset added
        afterwards. `mesh_assets_present` reports what was there.

        `name` is any object in the character's family - the basemesh, the meta
        rig itself, a garment. Omit it to use the active object. Unlike the
        other character tools this resolves to the **meta rig** rather than the
        basemesh, and `metarig_name` says which armature was used.

        `rig_name` is the generated rig's basename. Omit it for MPFB's own
        fallback, which derives a unique name from the meta rig's.

        `meta_rig_action` (default `"hide"`, MPFB's own) is what becomes of the
        meta rig afterwards: `"keep"` leaves it visible, `"hide"` keeps it in
        the scene but out of the viewport and renders, `"delete"` removes it.
        **Prefer `"hide"`.** Deleting the meta rig makes the character
        permanently unrefittable: `mpfb_refit_human` can only refit a generated
        Rigify rig through its meta rig, and with none in the scene it refits
        the clothes, leaves the rig behind and says nothing. The response
        reports `refit_will_be_possible` either way.

        **This tool is not undoable and cannot restore your selection.**
        Generation's own last act is to select and activate the rig it made, so
        `active_object_after` reports what is active now instead.

        Returns blender_mcp's response envelope. On `status: "ok"` and
        `generated: true`, `result` carries `rig_object_name`, `metarig_name`,
        `metarig_disposition` (`kept`/`hidden`/`deleted`),
        `refit_will_be_possible`, `mesh_assets_present` and
        `active_object_after`.

        **`generated: false` does not mean nothing happened.** When Rigify
        judges the meta rig invalid it returns after MPFB has already deselected
        everything, activated the meta rig and possibly renamed it or run
        Rigify's face upgrade. That case reports `metarig_renamed` and
        `metarig_name_after` beside the refusal.

        Other situations answer with `generated: false` and a `blocked_by`:
        `subject_not_found`; `no_armature_found`; `not_a_metarig` (the character
        is rigged, but not with a Rigify meta rig); `already_generated` (this
        character is already on a generated rig - generation moved it there, so
        its meta rig is no longer among its relatives); `rigify_unavailable`;
        and `not_object_mode`.

        **Branch on `performed`.** Every mutating tool here reports that field
        under the same name, a real boolean, true exactly when the character was
        changed. It equals `generated` here - and as above, `generated: false`
        still does not mean nothing happened to the scene.
        """
        code = codegen.assemble(
            "generate_rigify_rig.py",
            bootstrap="raising",
            shared=["performed.py"],
            params={
                "name": _validated_name(name),
                "rig_name": _validated_rig_name(rig_name),
                "meta_rig_action": _validated_meta_rig_action(meta_rig_action),
            },
        )
        # `result` (built in codegen/payloads/generate_rigify_rig.py) is plain
        # JSON-safe data, so strict_json=True surfaces a clear error if that ever
        # stops being true.
        return send_code(code, strict_json=True)
