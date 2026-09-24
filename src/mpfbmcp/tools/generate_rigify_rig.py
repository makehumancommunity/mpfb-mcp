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

from mpfbmcp import arguments
from mpfbmcp import backend

# MPFB's own enum, in MPFB's own order. Kept here rather than resolved in
# Blender because it is a fixed vocabulary in MPFB's source, not a scan of
# anything - the opposite of the rig identifiers, which are a directory listing.
_META_RIG_ACTIONS = ("keep", "hide", "delete")


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
        Turn a character's Rigify **meta rig** into a generated, poseable
        Rigify rig - the second step of the two `mpfb_add_rig` starts when
        given a `rigify.*` identifier.

        **Attach the character's clothes and other mesh assets before calling
        this.** Generation re-parents and re-weights whatever is on the
        character at the moment it runs, and nothing handles an asset added
        afterwards. `mesh_assets_present` reports what was there.

        Unlike the other character tools, `name` resolves to the **meta rig**
        rather than to the basemesh, and `metarig_name` says which armature was
        used. `rig_name` is the generated rig's basename; omit it for MPFB's
        own fallback, which derives a unique name from the meta rig's.

        `meta_rig_action` (default `"hide"`, MPFB's own) is what becomes of the
        meta rig afterwards: `"keep"` leaves it visible, `"hide"` keeps it in
        the scene but out of viewport and renders, `"delete"` removes it.
        **Prefer `"hide"`.** Deleting the meta rig makes the character
        permanently unrefittable: `mpfb_refit_human` can only refit a generated
        Rigify rig through its meta rig, and with none in the scene it refits
        the clothes, leaves the rig behind and says nothing.
        `refit_will_be_possible` reports this either way.

        **This tool is not undoable and cannot restore your selection.**
        Generation's own last act is to select and activate the rig it made, so
        `active_object_after` reports what is active now instead.

        On `generated: true`, `result` carries `rig_object_name`,
        `metarig_name`, `metarig_disposition` (`kept`/`hidden`/`deleted`),
        `refit_will_be_possible`, `mesh_assets_present` and
        `active_object_after`.

        **`generated: false` does not mean nothing happened**, though
        `performed` follows it. When Rigify judges the meta rig invalid it
        returns after MPFB has already deselected everything, activated the
        meta rig and possibly renamed it or run Rigify's face upgrade; that
        case reports `metarig_renamed` and `metarig_name_after` beside the
        refusal. Other refusals carry a `blocked_by`: `subject_not_found`,
        `no_armature_found`, `not_a_metarig` (rigged, but not with a Rigify
        meta rig), `already_generated` (generation moved this character onto
        its generated rig, so its meta rig is no longer among its relatives),
        `rigify_unavailable` and `not_object_mode`.
        """
        # `result` (built in bridge/mpfb_bridge/commands/generate_rigify_rig.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "generate_rigify_rig",
            params={
                "name": arguments.validated_subject(name),
                "rig_name": arguments.validated_text(
                    rig_name, "rig_name",
                    "omit it to let MPFB derive a unique name from the meta rig's"),
                "meta_rig_action": _validated_meta_rig_action(meta_rig_action),
            },
        )
