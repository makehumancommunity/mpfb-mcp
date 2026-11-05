"""
The ``mpfb_generate_delete_group`` tool: which of a body's vertices a garment hides.

A delete group fails in two opposite ways, and on the gi it took eleven runs of a ray-casting
script to get between them
([FR 051](../../../feature-requests/done/051-delete-groups/README.md)). MPFB's own operator calls
its result "very rough" and refuses any garment with a modifier.

``margins``' keys are this package's own vocabulary, so a shape, and are checked here as well as
there. ``mode`` is ``arguments.validated_mode``'s. Everything about what is generated and measured is
in the bridge's ``shared/delete_group.py``.
"""

from __future__ import annotations

__all__ = (
    "MARGIN_KINDS",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

MARGIN_KINDS = ("cuff", "hem", "trunk")


def _validated_margins(value: object) -> dict[str, float] | None:
    """An object of known kinds and finite positive numbers, or ``None``."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("margins must be an object of kinds to metres, got {}".format(
            type(value).__name__))
    if not value:
        raise ValueError("margins must not be empty: omit it for the defaults")
    for kind, margin in value.items():
        if kind not in MARGIN_KINDS:
            raise ValueError("margins knows only {}, got {!r}".format(", ".join(MARGIN_KINDS), kind))
        if not arguments.is_finite_number(margin) or margin <= 0.0:
            raise ValueError("margins' {!r} must be a finite number above 0, got {!r}".format(
                kind, margin))
    return value


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Generate Delete Group",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_generate_delete_group(
        name: str | None = None,
        basemesh: str | None = None,
        delete_group: str | None = None,
        mode: str = "merge",
        margins: dict[str, float] | None = None,
        dry_run: bool = False,
    ) -> dict[str, object]:
        """
        Generate the vertex group on a body that hides it under a garment, with
        no margins to find by trial and error. **Too small and skin pokes
        through; too large and dark slits open where someone can see in**, so the
        answer says how each stands. It is worked out on this body at rest: skin
        on another body or in a pose is found by trying the asset there
        (`mpfb_write_mesh_asset`'s `try_with`).

        `name` is the garment, and may carry modifiers. `basemesh` is the body,
        otherwise found among its relatives, then the selection, then the file.
        `delete_group` is the group, by default the garment's own; none is
        assumed, and an equipped asset's is `Delete.<name>`. Adds no modifier
        (`mask_modifier_present`). `dry_run` reports all of it and writes nothing.

        **`mode`**: `merge` keeps the members from before the first run, `replace`
        starts empty. That earlier group is kept as `<group>.original`
        (`original_kept_as`), so every run starts over rather than growing: rerun
        freely. It is the only undo, and putting it back is generic Blender work.

        `result`:

        - `vertices_before`, `vertices_after`, `added`, `removed`.
        - **`masked_skin_still_visible`**: removed faces a sight line reaches,
          within 20 cm of an opening, with the garment in front of them. These are
          slits.
        - **`unmasked_skin_under_garment`**: standing faces the garment covers and
          no sight line reaches. These can poke through elsewhere, and include what
          a limb's margin keeps on purpose. Both are counted on what MPFB masks
          **once the asset is loaded**, about a ring less than this group, and
          neither is a verdict: nonzero is normal.
        - `masked_skin_still_visible_authoring`: the first count on the group as it
          stands, which is what a Mask modifier shows on this body.
        - **`openings`**, longest first, capped (`openings_total`), per boundary
          loop: `kind`, `reason`, `centre`, `margin`, `limbs`, `vertices`,
          `perimeter`, `open_share`, `kept_by_margin`. A `cuff` or `hem` has a limb
          through it, which moves, so a margin decides. A `trunk` opening (neck,
          armhole, keyhole) has what can be seen decide. `covered` has another
          layer over or under it and is no opening.
        - `closed_components`, parts with no boundary, which get no margin.

        `margins` overrides a kind's metres (`trunk`, `cuff`, `hem`; `margins` in
        the answer is what was used) and never a classification.

        Refusals: `subject_not_found`, `not_a_mesh`, `subject_is_basemesh`,
        `basemesh_not_found`, `not_a_basemesh`, `basemesh_ambiguous` with
        `candidates`, `delete_group_required`, `group_is_a_kept_original`,
        `group_name_too_long`, `not_in_object_mode`, `no_body_group`,
        `no_joint_groups`, `mesh_not_evaluated`, `garment_has_no_faces`,
        `body_topology_changed`, and `rig_not_at_rest`: `mpfb_reset_pose` puts it
        back and its `restore_with` returns it. A turned or moved character is fine.
        """
        return backend.send(
            "generate_delete_group",
            params={
                "name": arguments.validated_subject(name),
                "basemesh": arguments.validated_text(
                    basemesh, "basemesh", "omit it to have the body found"),
                "delete_group": arguments.validated_text(
                    delete_group, "delete_group", "omit it to take the garment's"),
                "mode": arguments.validated_mode(mode),
                "margins": _validated_margins(margins),
                "dry_run": arguments.validated_flag(dry_run, "dry_run"),
            },
        )
