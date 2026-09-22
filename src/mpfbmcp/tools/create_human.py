"""The ``mpfb_create_human`` tool: wraps MPFB's ``HumanService.create_human()``."""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import backend

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
        Create a new MakeHuman character - a basemesh with a phenotype -
        through MPFB's `HumanService.create_human()`. The starting point for
        building a character: shape it further with `mpfb_set_targets`, rig it
        with `mpfb_add_rig` **before** dressing it with `mpfb_add_asset`, and
        give it a skin with `mpfb_set_skin`, without which it stays grey.

        The eleven macro sliders (`gender`, `age`, `muscle`, `weight`,
        `proportions`, `height`, `cupsize`, `firmness`, `race_asian`,
        `race_caucasian`, `race_african`) are 0.0-1.0 and are **the same
        sliders under the same names** as `mpfb_set_macro_details` takes, so a
        character can be created and then adjusted without relearning the
        vocabulary. The two differ in what an omitted slider means: here every
        one has a default and the character is built from the full set, while
        there an omitted slider is left alone. Set the phenotype in this call
        when you know it; use `mpfb_set_macro_details` to change one
        afterwards.

        0.5 is neutral for every slider except the three race weights, whose
        neutral is 0.33 each. `age` runs 0.0 = baby, 0.1875 = child, 0.5 =
        young adult, 1.0 = old; `gender` 0.0 = fully female, 1.0 = fully male.
        **The three race weights are independent and MPFB does not normalize
        them**, so the defaults sum to 0.99 and setting one to 1.0 does not
        reduce the other two.

        `scale` is the basemesh scale factor (0.1 = decimeters, MPFB's own
        default). Change it only deliberately: `mpfb_set_skin`'s enhanced skin
        types read it to pick subsurface radii.

        `create_human()`'s own defaults are used for `mask_helpers`,
        `detailed_helpers`, `extra_vertex_groups` and `feet_on_ground`; this
        proof-of-concept does not expose them.

        On `status: "ok"`, `result` carries `object_name` - the Blender object
        name of the new basemesh, and the address every later tool needs, since
        Blender uniquifies a name already in use - plus `vertex_count`,
        `location` and the `macro_detail_dict` that was applied, in MPFB's own
        nested shape. `performed` is true: creation either succeeds or raises,
        so this tool has no separate verb of its own.
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

        # `result` (built in codegen/payloads/create_human.py, or by
        # bridge/mpfb_bridge/commands/create_human.py) is always plain JSON-safe
        # data, so strict_json=True to surface a clear error if that ever stops
        # being true, rather than silently falling back to `repr`.
        return backend.send(
            "create_human.py",
            bootstrap="raising",
            # The uniform `performed` flag, which every mutating tool reports.
            # A fragment on the generated path; a module the command imports on
            # the bridge, named the same way either way.
            shared=["performed.py"],
            params={"macro_detail_dict": macro_detail_dict, "scale": scale},
            strict_json=True,
        )
