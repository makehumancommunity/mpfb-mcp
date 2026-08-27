"""The ``mpfb_create_human`` tool: wraps MPFB's ``HumanService.create_human()``."""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp.connection import send_code
from mpfbmcp.mpfb_codegen import build_create_human_code

# create_human()'s own default scale (0.1 = decimeters). Kept here rather than
# guessed so the tool's default matches MPFB's regardless of MPFB version.
_DEFAULT_SCALE = 0.1


def _clamp01(name: str, value: float) -> float:
    if not 0.0 <= value <= 1.0:
        raise ValueError("{:s} must be between 0.0 and 1.0, got {!r}".format(name, value))
    return value


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Create MakeHuman Character",
            destructiveHint=True,
        )
    )
    def mpfb_create_human(
        gender: float = 0.5,
        age: float = 0.5,
        muscle: float = 0.5,
        weight: float = 0.5,
        proportions: float = 0.5,
        height: float = 0.5,
        cupsize: float = 0.5,
        firmness: float = 0.5,
        race_asian: float = 0.33,
        race_caucasian: float = 0.33,
        race_african: float = 0.33,
        scale: float = _DEFAULT_SCALE,
    ) -> dict[str, object]:
        """
        Create a new MakeHuman character via MPFB's HumanService.create_human().

        All macro-detail sliders (gender, age, muscle, weight, proportions,
        height, cupsize, firmness, race_*) are 0.0-1.0, matching MPFB's own
        macro target range; 0.5 is neutral/average, matching MPFB's default.
        `scale` is the basemesh scale factor (0.1 = decimeters, MPFB's default).

        Requires the blender_mcp add-on server to be running inside Blender,
        with the MPFB extension installed and enabled. Uses `create_human()`'s
        own defaults for mask_helpers, detailed_helpers, extra_vertex_groups
        and feet_on_ground - this proof-of-concept does not expose them.

        Returns the blender_mcp add-on's response envelope: `status` ("ok" or
        "error"), and on success `result` with `object_name`, `vertex_count`,
        `location` and the `macro_detail_dict` that was applied.
        """
        macro_detail_dict = {
            "gender": _clamp01("gender", gender),
            "age": _clamp01("age", age),
            "muscle": _clamp01("muscle", muscle),
            "weight": _clamp01("weight", weight),
            "proportions": _clamp01("proportions", proportions),
            "height": _clamp01("height", height),
            "cupsize": _clamp01("cupsize", cupsize),
            "firmness": _clamp01("firmness", firmness),
            "race": {
                "asian": _clamp01("race_asian", race_asian),
                "caucasian": _clamp01("race_caucasian", race_caucasian),
                "african": _clamp01("race_african", race_african),
            },
        }

        code = build_create_human_code(macro_detail_dict, scale)
        # `result` (built in mpfb_codegen.py) is always plain JSON-safe data,
        # so strict_json=True to surface a clear error if that ever stops
        # being true, rather than silently falling back to `repr`.
        return send_code(code, strict_json=True)
