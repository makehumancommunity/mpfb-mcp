"""
The ``mpfb_set_pose_switches`` tool: change a generated Rigify rig's switches, keeping limbs in place.

The switch half of [FR 042](../../../feature-requests/done/042-posing-bones-switches-and-reset/README.md).
A switch is addressed as ``mpfb_get_pose_controls`` lists it, by ``body_part``
and ``switch``; by default each one snaps, as Rigify's own buttons do, and the
answer measures how well (``snap_error``). Why the snaps are reimplemented in
the bridge rather than called is in its command's docstring.

**Validated here is shape only**: each entry an object with known keys;
``body_part`` and ``switch`` non-empty strings, the pair named once per call;
``value`` a finite number or a ``bool``; ``raw`` a real ``bool``. ``value`` is
the one entry key here that takes two JSON types, because the switches do:
``pole_vector`` is on or off and the rest are numbers - inside an entry, so
``tests/test_vocabulary.py``'s rule about argument names is not involved.
Which switches exist, which type each takes and its range are the live rig's,
answered as ``resolution_errors``.
"""

from __future__ import annotations

__all__ = (
    "MAX_ENTRIES",
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

_KEYS = ("body_part", "switch", "value", "raw")

# A generated human_toes rig has about thirty switches in all.
MAX_ENTRIES = 200


def _validated_entry(where: str, entry: object) -> dict[str, object]:
    if not isinstance(entry, dict):
        raise ValueError("{} must be an object, got {!r}".format(where, entry))
    unknown = sorted(key for key in entry if key not in _KEYS)
    if unknown:
        raise ValueError("{} has unknown key(s) {}; known keys are {}".format(
            where, ", ".join(unknown), ", ".join(_KEYS)))
    checked: dict[str, object] = {}
    for key in ("body_part", "switch"):
        text = entry.get(key)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("{} {} must be a non-empty string, got {!r}".format(where, key, text))
        checked[key] = text
    if "value" not in entry:
        raise ValueError("{} value is required".format(where))
    value = entry["value"]
    if not isinstance(value, bool) and not arguments.is_finite_number(value):
        raise ValueError("{} value must be a finite number, or a bool for an on/off switch, "
                         "got {!r}".format(where, value))
    checked["value"] = value
    if "raw" in entry:
        checked["raw"] = arguments.validated_flag(entry["raw"], "{} raw".format(where))
    return checked


def _validated_switches(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("switches must be a list of objects or omitted, got {!r}".format(value))
    if len(value) > MAX_ENTRIES:
        raise ValueError("switches must hold at most {} entries, got {}".format(
            MAX_ENTRIES, len(value)))
    checked = []
    seen: set = set()
    for position, entry in enumerate(value):
        where = "switches[{}]".format(position)
        normalized = _validated_entry(where, entry)
        key = (normalized["body_part"], normalized["switch"])
        if key in seen:
            raise ValueError("{} names {} {}, already named earlier in this call".format(
                where, *key))
        seen.add(key)
        checked.append(normalized)
    return checked


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set Pose Switches",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_set_pose_switches(name: str | None = None,
                               switches: list[dict] | None = None) -> dict[str, object]:
        """
        Change the switches of a MakeHuman character's generated Rigify rig -
        `IK_FK`, `pole_vector`, `IK_parent`, `IK_Stretch` and the rest that
        `mpfb_get_pose_controls` lists, with what each end means and each
        parent's name. Only a generated Rigify rig has switches.

        Each entry is `{body_part, switch, value, raw}`: `value` a number
        (`IK_parent` an integer picking a parent), `true`/`false` for
        `pole_vector`.

        **By default the limb stays where it is**, as Rigify's own buttons do:
        `IK_FK` to 1.0 poses the FK controls like the IK result, to 0.0 poses
        the IK control and pole like the FK result; `pole_vector` keeps the
        chain's pose; a parent switch keeps the control's world position.
        `IK_Stretch`, `FK_limb_follow` and an `IK_FK` between 0 and 1 have no
        snap and are written as given (`snapped: false`, `snap_reason`).
        `raw: true` always writes the bare value, which can move the limb.

        Switches apply in request order, since they interact: turn
        `pole_vector` on before switching to IK and the pole is placed too.
        Nothing is written unless every entry resolves.

        `result`'s `changes` give `previous_value`/`new_value`, `snapped`,
        the limb's end before and after on the deforming bones, and
        `snap_error` - how far any of the limb's joints moved, so a snap that
        failed shows. Also
        `landmarks`, `limbs` and `limbs_made_stretched`/`_unreachable` as in
        `mpfb_set_pose_bones`.
        """
        return backend.send(
            "set_pose_switches",
            params={
                "name": arguments.validated_subject(name),
                "switches": _validated_switches(switches),
            },
        )
