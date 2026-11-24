"""
The ``mpfb_check_rig_weights`` tool: a rig's weighting, measured, with an opt-in bend test.

Nothing in MPFB reads a weighting back, and before this the only evidence that an authored rig's
weights held up was a bend looked at in a render
([FR 061](../../../feature-requests/done/061-rig-weights-that-hold-up/README.md)). It reads any rig,
so that a shipped one on a similar body can be the baseline; it gives numbers and no verdict, as
``mpfb_check_intersections`` does.

``sections`` is this package's own vocabulary, like ``mpfb_check_mesh_asset``'s, and is checked
here as well as there, held to the bridge's by reading its list as data. What is measured, and
how the bend test chooses its bones and axes, is in the bridge command's docstring and
``shared/rig_weights.py``.
"""

from __future__ import annotations

__all__ = (
    "SECTIONS",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

SECTIONS = ("coverage", "influences", "bones", "helpers", "symmetry", "bend")


def _validated_sections(value: object) -> list[str] | None:
    """A list of distinct :data:`SECTIONS`, or ``None`` for all but ``bend``."""
    checked = arguments.validated_names(value, "sections", "all but bend")
    if checked is None:
        return None
    unknown = [name for name in checked if name not in SECTIONS]
    if unknown:
        raise ValueError("sections knows only {}, got {}".format(
            ", ".join(SECTIONS), ", ".join(unknown)))
    return checked


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Check Rig Weights",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_check_rig_weights(
        name: str | None = None,
        sections: list[str] | None = None,
    ) -> dict[str, object]:
        """
        Measure the weights of whichever rig moves a character: shipped, library or
        authored. Changes nothing, `bend` included. **Numbers, not a verdict: compare
        against a shipped rig (`default`, `game_engine`) on a similar body**, read by this
        same tool. Weights count only in groups of deforming bones, above 0.0001; masks and
        MPFB's own groups never count.

        `sections` narrows `result`, the others `null`; omit it for all but `bend`.
        `thresholds` names every limit used.

        - `coverage`: `unweighted` vertices as `body`, `joint_cube`, per `helpers` group
          and `total`; `unweighted_bones` (deforming, no group); `orphan_groups` (named
          after a bone that does not deform) and `other_groups` (no bone of this rig,
          no mask, not MPFB's: a garment's delete group, another rig's).
        - `influences`: `histogram` of deform influences per vertex, `max_influences`,
          `unnormalised` (total outside 1 +- 0.01) and `worst_unnormalised`.
        - `bones`: per deforming bone `vertex_count`, `weight_sum`, `reach` (farthest
          vertex weighted over 0.1 from the bone's segment), `reach_limit` and
          `far_vertices` beyond it; worst first, capped, totals over all
          (`far_vertices_total`). A root that took the thighs shows here.
        - `helpers`: per helper group the `dominant_bone`, `dominant_share` and `rigid`
          (one bone at 0.99 or more). An eye weighted to its eyelid is not rigid.
        - `symmetry`: per `.L`/`.R` pair (and centre bone) through MPFB's `hm08.mirror`,
          `max_difference` and `mean_difference`, `worst` first, and
          `bones_without_partner`.
        - `bend` (opt-in; 0.4 s for the call on `default`): eight movements of the left
          side, each from rest and put back, on the deforming bone whose head is on that
          joint, about an axis in the character frame, measured on the skin within 10 cm. Per movement: `collapse` (mean distance to the
          bone line, bent over rest; under 1.0 pinches), `edge_stretch` (`p99`, `max`),
          `self_intersections` (`rest`, `bent`) and `stray` (vertices that moved but sit
          beyond every moved bone's reach). `tested: false` with `not_tested`
          (`no_bone_on_joint`, `constrained` - a generated Rigify rig's `DEF-` bones -
          or `no_axis`). `preserve_volume` is the armature modifier's.

        Refusals: `subject_not_found`, `not_rigged`, `unknown_section`, and for `bend`
        `rig_not_at_rest`, `no_armature_modifier`, `not_object_mode`.
        """
        return backend.send(
            "check_rig_weights",
            params={
                "name": arguments.validated_subject(name),
                "sections": _validated_sections(sections),
            },
        )
