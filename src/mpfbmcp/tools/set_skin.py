"""
The ``mpfb_set_skin`` tool: give a character a skin instead of leaving it grey.

Until now every character mpfb-mcp produced wore whatever material
``create_human()`` left on it, which is clay. ``mpfb_list_assets`` has named
every skin on the machine since FR 005; this is the other end of that.

A skin is **not** an asset in the sense ``mpfb_add_asset`` uses the word. It is
a material applied to objects that already exist rather than a mesh imported as
one, which is why it has a tool of its own and why it reaches MPFB through
``HumanService.set_character_skin()`` rather than ``add_mhclo_asset()``.

Two of that function's defaults are **not** MPFB's product defaults, and this
tool follows the product rather than the signature. Both divergences are
deliberate, and both are named in the tool docstring, because a caller comparing
against what they saw in MPFB's own skin library panel would otherwise get a
different material and have nothing to explain it:

- ``skin_type`` defaults to ``ENHANCED_SSS`` in the signature and to
  ``MAKESKIN`` in ``ui/apply_assets/assetlibrary/properties/skin_type.json``,
  which is the panel the user actually sees. This tool defaults to ``MAKESKIN``.
- ``material_instances`` defaults to ``True`` in the signature, while
  ``loadlibraryskin.py`` forces it to ``False`` for ``LAYERED``, ``GAMEENGINE``
  *and* ``MAKESKIN``. The service's own guard names only the first two, so the
  ``MAKESKIN`` coercion is the UI's alone - and since ``MAKESKIN`` is the
  default type, the **default call creates no material instances**. This tool
  coerces the same way and reports both the requested and the used value.

``skin_type`` is the one place in this package where a *vocabulary* is checked
on this side of the socket as well as inside Blender, against
[Validate before crossing the socket](../../../specifications/tool-interface.md#validate-before-crossing-the-socket)'s
usual rule. The reason is specific: ``set_character_skin()`` tests its five
types with five separate ``if`` statements, having already deleted every
material on the character - so an unrecognised value destroys the skin, builds
nothing in its place, and then raises from somewhere else entirely. The
authoritative check still happens in the payload, before the call and before
anything is destroyed; the local one only means a typo never travels.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import codegen
from mpfbmcp.connection import send_code

# MPFB's five skin models, from ui/apply_assets/assetlibrary/properties/skin_type.json.
# Kept here only so that a typo cannot reach a function that deletes materials
# before it looks at this argument; the payload checks it again and reports
# known_skin_types, which is the answer a caller should correct itself from.
SKIN_TYPES = ("MAKESKIN", "GAMEENGINE", "ENHANCED", "ENHANCED_SSS", "LAYERED")

# The one type that builds a material out of nothing:
# MaterialService.create_v2_skin_material() takes mhmat_file=None, and
# HumanService._set_skin() returns early for a missing MHMAT unless the type is
# this one.
NEEDS_NO_FILE = "LAYERED"


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


def _validated_optional_text(value: object, argument: str, hint: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            "{:s} must be a string or omitted, got {!r}".format(argument, value))
    if not value.strip():
        # An explicitly empty value and an omitted one arise from different
        # mistakes, and here the difference decides whether a file is wanted at
        # all - so the empty one is never quietly treated as the omission.
        raise ValueError("{:s} must not be empty or whitespace; {:s}".format(argument, hint))
    return value


def _validated_skin_type(skin_type: object) -> str:
    """The one local vocabulary check in this package, and why it is here.

    ``set_character_skin()`` opens with
    ``MaterialService.delete_all_materials(..., also_destroy_groups=True)`` on
    the basemesh and the body proxy, and only then tests the five types - with
    five separate ``if`` statements rather than a chain with an ``else``. An
    unrecognised value therefore destroys the character's materials, creates
    nothing, and surfaces as a ``ValueError`` raised from
    ``create_and_assign_material_slots()`` about a mesh with no materials. The
    payload checks this again before anything is deleted; this check only keeps
    a typo from crossing the socket at all.
    """
    if not isinstance(skin_type, str):
        raise ValueError("skin_type must be a string, got {!r}".format(skin_type))
    normalized = skin_type.strip().upper()
    if normalized not in SKIN_TYPES:
        raise ValueError(
            "skin_type must be one of {:s}, got {!r}. MPFB builds a different node tree for "
            "each, and an unrecognised value would delete the character's materials without "
            "building anything in their place.".format(", ".join(SKIN_TYPES), skin_type))
    return normalized


def _validated_source(
        path: object, fragment: object, skin_type: str) -> tuple[str | None, str | None]:
    """Exactly one of the catalogue's two identifiers - or neither, for LAYERED.

    The exactly-one rule is
    [An acting tool accepts every identifier its catalogue reports](../../../specifications/tool-interface.md#an-acting-tool-accepts-every-identifier-its-catalogue-reports).
    The exception is not a relaxation of it: ``LAYERED`` is the single skin type
    that has a material to build when handed no file at all, so "neither" is a
    meaningful request there and a mistake everywhere else.
    """
    checked_path = _validated_optional_text(
        path, "path", "pass mpfb_list_assets' 'path' for a skin, or use 'fragment' instead")
    checked_fragment = _validated_optional_text(
        fragment, "fragment", "pass mpfb_list_assets' 'fragment' for a skin, or use 'path'")
    if checked_path is not None and checked_fragment is not None:
        raise ValueError(
            "Give either path or fragment, not both. They can name different files, and "
            "silently preferring one would apply a skin the caller did not ask for.")
    if checked_path is None and checked_fragment is None and skin_type != NEEDS_NO_FILE:
        raise ValueError(
            "Give either path or fragment. Both are reported by mpfb_list_assets for every "
            "entry in the 'skins' subdir: 'path' is the absolute file, 'fragment' is the "
            "portable identifier resolved against this Blender's asset roots. Only "
            "skin_type='{:s}' can build a material with no MHMAT at all.".format(NEEDS_NO_FILE))
    return (checked_path, checked_fragment)


def _validated_flag(argument: str, value: object) -> bool:
    if not isinstance(value, bool):
        # Deliberately not truthiness: "false" and 0 are how a caller signals a
        # bool it did not manage to build, and material_instances="false" would
        # otherwise create the per-region slots it was asking not to have.
        raise ValueError("{:s} must be a bool, got {!r}".format(argument, value))
    return value


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set Character Skin",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_set_skin(
        name: str | None = None,
        path: str | None = None,
        fragment: str | None = None,
        skin_type: str = "MAKESKIN",
        material_instances: bool = True,
    ) -> dict[str, object]:
        """
        Give a MakeHuman character a skin, with the same result MPFB's own skin
        library panel produces.

        **This destroys every material already on the character.** MPFB opens by
        deleting all materials on the basemesh *and* on the body proxy, node
        groups included, before building the new one. A hand-built material on
        the body is gone and there is no undo across the socket.
        `materials_destroyed` names what went, per object.

        Name the skin with **either** `path` **or** `fragment`, never both -
        both are reported by `mpfb_list_assets` for every entry whose
        `object_type` is `Material` (the `skins` subdir). `fragment` is resolved
        by **basename**, preferring a match whose directory also matches and
        otherwise taking the first hit, so `resolved_path` always reports which
        file was actually loaded. Give **neither** only with
        `skin_type="LAYERED"`, which is the one type that builds a material from
        nothing.

        `skin_type` is `MAKESKIN` (default), `GAMEENGINE`, `ENHANCED`,
        `ENHANCED_SSS` or `LAYERED`. They are five entirely different node trees
        built from the same MHMAT: a plain PBR material for export, MakeSkin's,
        the enhanced one with and without subsurface scattering, and the
        multilayered one. All five cost about the same to *build* - measured
        within 33 ms of each other - so pick on the look you want, not on speed;
        MPFB's warning that `LAYERED` is unsuitable for animation is about
        render cost. **The default follows MPFB's settings panel, not
        `set_character_skin()`'s own signature**, which defaults to
        `ENHANCED_SSS` - so what this tool produces by default is what the panel
        produces by default.

        `material_instances` (default true) asks for the per-vertex-group
        material slots - fingernails, lips, ears, nipples, toenails, genitals.
        **MPFB's UI forces it off for `LAYERED`, `GAMEENGINE` and `MAKESKIN`,
        and so does this tool**, which means the default call creates no
        instances at all. The response reports `material_instances_requested`
        beside `material_instances_used`, with a sentence when they differ; a
        silent coercion would read as a bug.

        `name` is any object in the character's family - the basemesh, its rig,
        a garment, anything `mpfb_list_objects` reports. Omit it to use the
        active object. `basemesh_name` names the character actually changed, and
        `bodyproxy_name` names the second object that was changed with it: MPFB
        applies the skin to the body proxy too, and nothing else would tell you.

        Returns blender_mcp's response envelope. On `status: "ok"` and
        `applied: true`, `result` carries `resolved_path` and `material_source`
        (the fragment MPFB recorded - note it is written **only** when an MHMAT
        was given, so a `LAYERED` skin with no file leaves the previous value in
        place, which `material_source_before` makes visible), `skin_type_used`,
        `material_instances_requested`/`_used`, `materials_destroyed`,
        `material_slots` (per object, which is how instancing differs
        observably), `material_identified_as`, `active_body_slot`, and two facts
        nothing in Blender would show you: `settings_file_created`, true when
        the enhanced skin types copied `enhanced_settings.default.json` into
        your user config directory - the only file mpfb-mcp ever writes outside
        the `.blend` - and `scale_assumption` (`METER`/`DECIMETER`/`CENTIMETER`),
        which the enhanced types derive from the character's `scale_factor` and
        which changes the subsurface radii. `scale_assumption` is null for the
        three types that do not use it. Note where the bands fall: the
        `scale_factor` property *declares* a default of 1.0, but
        `create_human()` writes 0.1 onto every character it makes, so an
        ordinary MPFB character reports `METER`. `DECIMETER` needs a
        `scale_factor` above 0.9 and `CENTIMETER` one above 9.

        Six situations answer with `applied: false` and a `blocked_by` naming
        which, rather than failing, and change nothing on the way to finding
        out: the subject resolves to no basemesh (`subject_not_found`);
        `skin_type` is not one of the five (`unknown_skin_type`, with
        `known_skin_types`); no `path` or `fragment` was given for a type that
        needs one (`no_material_given`); the file does not exist or the fragment
        resolved to nothing (`skin_not_found`); anything not in OBJECT mode
        (`not_object_mode`); and a failure inside MPFB itself
        (`skin_failed`), which is reported rather than raised precisely because
        the materials are already gone by then.
        """
        checked_skin_type = _validated_skin_type(skin_type)
        checked_path, checked_fragment = _validated_source(path, fragment, checked_skin_type)
        code = codegen.assemble(
            "set_skin.py",
            bootstrap="raising",
            params={
                "name": _validated_name(name),
                "path": checked_path,
                "fragment": checked_fragment,
                "skin_type": checked_skin_type,
                "material_instances": _validated_flag(
                    "material_instances", material_instances),
            },
            # Shared with mpfb_list_assets' payload, which reported this skin's
            # fragment under the object_type "Material". The only thing that
            # maps that type back to the "skins" asset subdir a fragment is
            # resolved against is MPFB's section table, and a second copy of it
            # here would make a just-listed skin look uninstalled.
            shared=["asset_sections.py"],
        )
        # `result` (built in codegen/payloads/set_skin.py) is plain JSON-safe
        # data, so strict_json=True surfaces a clear error if that ever stops
        # being true.
        return send_code(code, strict_json=True)
