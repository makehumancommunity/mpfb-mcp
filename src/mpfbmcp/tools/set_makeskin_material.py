"""
The ``mpfb_set_makeskin_material`` tool: a MakeSkin material from images and numbers.

An agent generating textures outside Blender had to write an MHMAT by hand and read an
operator to find out what to call
([FR 049](../../../feature-requests/done/049-makeskin-materials/README.md)).

**Takes a path to read, and that breaks no rule.** The
[name-not-a-path obligation](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)
is about where a tool *writes*, and nothing here writes to a path it is given. Its shape
is checked here: absolute, with an image extension. Whether it exists and loads is
settled on the far side, before anything changes.

**A source is one of two keys, a value one of two keys**, per
[one key per JSON type](../../../specifications/tool-interface.md#validate-before-crossing-the-socket).
``{"roughness": 0.9}`` would be the natural spelling, and it is refused for a reason:
the reader's entries are objects with ``in_effect`` beside the number, and the writer
has to accept those unchanged, so one shape serves both directions. An entry's read-only
keys are listed here and held to the bridge's list by a test, so that a misspelled
``pth`` still fails.

**No slot, value or metadata vocabulary is checked here.** It is read off MPFB's own
module on the far side and reported on every answer as ``known_slots``, ``known_values``
and ``known_metadata``. Everything the tool does is
``bridge/test/tests/ddd_mutating/set_makeskin_material_test.py``'s.
"""

from __future__ import annotations

__all__ = (
    "IMAGE_EXTENSIONS",
    "READ_ONLY_TEXTURE_KEYS",
    "READ_ONLY_VALUE_KEYS",
    "register",
)

import ntpath
import posixpath

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend

# The bridge's texture_writing.py and makeskin.py hold these for the far side;
# tests/test_set_makeskin_material.py reads those as data and requires them equal.
IMAGE_EXTENSIONS = (".bmp", ".exr", ".hdr", ".jpeg", ".jpg", ".png", ".tga", ".tif", ".tiff",
                    ".webp")
READ_ONLY_TEXTURE_KEYS = ("image_name", "wired", "resolved_path", "file_exists", "size",
                          "color_space", "packed", "unsaved_changes", "strength",
                          "strength_value")
READ_ONLY_VALUE_KEYS = ("in_effect", "overridden_by", "needs_slot", "range", "srgb_hex")


def _validated_material_name(material_name: object) -> str:
    """Any text: only ``mpfb_store_makeskin_material``'s name becomes a file's."""
    if not isinstance(material_name, str) or not material_name.strip():
        raise ValueError("material_name must be a non-empty string, got {!r}".format(material_name))
    return material_name


def _validated_path(where: str, path: object) -> str:
    """Absolute on either platform, since Blender may not be on this machine's."""
    if not isinstance(path, str) or not path.strip():
        raise ValueError("{} path must be a non-empty string, got {!r}".format(where, path))
    if not (posixpath.isabs(path) or ntpath.isabs(path)):
        raise ValueError("{} path must be absolute, got {!r}".format(where, path))
    extension = posixpath.splitext(path.replace("\\", "/"))[1].lower()
    if extension not in IMAGE_EXTENSIONS:
        raise ValueError("{} path must end in an image extension ({}), got {!r}".format(
            where, ", ".join(IMAGE_EXTENSIONS), path))
    return path


def _validated_textures(textures: object) -> dict[str, dict[str, str]] | None:
    if textures is None:
        return None
    if not isinstance(textures, dict):
        raise ValueError("textures must be an object keyed by slot, got {!r}".format(textures))
    checked: dict[str, dict[str, str]] = {}
    for slot, source in textures.items():
        where = "textures.{}".format(slot)
        if not isinstance(source, dict):
            raise ValueError("{} must be an object with path or image, got {!r}".format(
                where, source))
        unknown = sorted(key for key in source
                         if key not in ("path", "image") + READ_ONLY_TEXTURE_KEYS)
        if unknown:
            raise ValueError("{} has unknown key(s) {}; a source is path or image".format(
                where, ", ".join(unknown)))
        if ("path" in source) == ("image" in source):
            raise ValueError(
                "{} needs exactly one of path (an absolute file) and image (a name in this "
                ".blend)".format(where))
        if "path" in source:
            checked[slot] = {"path": _validated_path(where, source["path"])}
        else:
            image = source["image"]
            if not isinstance(image, str) or not image.strip():
                raise ValueError("{} image must be a non-empty string, got {!r}".format(
                    where, image))
            checked[slot] = {"image": image}
    return checked


def _validated_color(where: str, color: object) -> list[float]:
    if (not isinstance(color, list) or len(color) != 4
            or not all(arguments.is_finite_number(channel) for channel in color)):
        raise ValueError(
            "{} color must be a list of four finite numbers, scene-linear RGBA, got {!r}".format(
                where, color))
    if any(channel < 0 for channel in color):
        raise ValueError(
            "{} color components must not be negative, since Blender would store zero; got "
            "{!r}".format(where, color))
    if float(color[3]) != 1.0:
        raise ValueError(
            "{} color must have an alpha of 1.0: an MHMAT keeps three components, so another "
            "would not survive being stored; got {!r}".format(where, color))
    return [float(channel) for channel in color]


def _validated_values(values: object) -> dict[str, dict[str, object]] | None:
    if values is None:
        return None
    if not isinstance(values, dict):
        raise ValueError("values must be an object keyed by value name, got {!r}".format(values))
    checked: dict[str, dict[str, object]] = {}
    for key, entry in values.items():
        where = "values.{}".format(key)
        if not isinstance(entry, dict):
            raise ValueError(
                '{} must be an object, {{"value": number}} or {{"color": four numbers}}, as '
                "mpfb_get_makeskin_material reports it; got {!r}".format(where, entry))
        unknown = sorted(key_name for key_name in entry
                         if key_name not in ("value", "color") + READ_ONLY_VALUE_KEYS)
        if unknown:
            raise ValueError("{} has unknown key(s) {}; it holds value or color".format(
                where, ", ".join(unknown)))
        if ("value" in entry) == ("color" in entry):
            raise ValueError("{} needs exactly one of value and color".format(where))
        if "color" in entry:
            checked[key] = {"color": _validated_color(where, entry["color"])}
        elif not arguments.is_finite_number(entry["value"]):
            raise ValueError("{} value must be a finite number, got {!r}".format(
                where, entry["value"]))
        else:
            checked[key] = {"value": float(entry["value"])}
    return checked


def _validated_metadata(metadata: object) -> dict[str, object] | None:
    if metadata is None:
        return None
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object, got {!r}".format(metadata))
    for key, value in metadata.items():
        if isinstance(value, bool):
            continue
        if not isinstance(value, str):
            raise ValueError("metadata.{} must be text or true/false, got {!r}".format(key, value))
        if "\n" in value or "\r" in value:
            # An MHMAT is one key per line, so a line break would write a second key.
            raise ValueError("metadata.{} must be one line of text".format(key))
    return metadata


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Set MakeSkin Material",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        )
    )
    def mpfb_set_makeskin_material(
        material_name: str,
        name: str | None = None,
        textures: dict[str, dict[str, object]] | None = None,
        values: dict[str, dict[str, object]] | None = None,
        metadata: dict[str, object] | None = None,
        replace: bool = False,
    ) -> dict[str, object]:
        """
        Give a mesh a MakeSkin material from image files or Blender images, and
        numbers. Any mesh is accepted; `name` is it, `material_name` what to call
        the material. For a material to keep, follow with
        `mpfb_store_makeskin_material`.

        - `textures` maps a slot to its source: `{"diffuse": {"path":
          "/abs/file.png"}}` or `{"diffuse": {"image": "name in this .blend"}}`,
          exactly one of the two. A path is absolute, is only read, and **is
          reloaded if Blender has it loaded**, so a regenerated file shows its new
          pixels (`reloaded` lists those slots). An image has no file until it is
          stored (`unsaved_slots`). Colour space follows the slot, non-colour for
          all but `diffuse` and `emissionColorMap`; changing it on an image other
          materials use is in `color_space_changes`.
        - `values` maps a key to `{"value": 0.9}`, or for `diffuseColor` to
          `{"color": [r, g, b, 1.0]}`, scene-linear. A plain number is refused.
          A value whose node exists only with a certain map needs that map named.
        - `metadata` is what an MHMAT carries, set on the object: `description`,
          `license`, `author`, `tag`, `backfaceCull` and so on.

        Slots, value keys and metadata keys are MPFB's, and every answer lists
        them as `known_slots`, `known_values` and `known_metadata`.

        **All or nothing**: everything resolves before the mesh is touched, and
        one bad entry refuses the call with `blocked_by: "resolution_failed"` and
        one row per entry in `resolution_errors` (`where`, `error`, `message`).
        `specular_with_roughness` refuses the two maps that drive one socket, as
        MakeSkin's panel does.

        **A mesh with a material is refused (`material_exists`) unless `replace`
        is true**; `materials_destroyed` names what went, and
        `material_shared_with` the objects still holding it.

        On `applied: true`, `result` carries `material_name` (Blender adds a
        suffix if the name is taken) beside `requested_material_name`, and
        `textures`, `values` and `metadata` as `mpfb_get_makeskin_material` reads
        them, with `metadata_changes`.

        Other refusals: `subject_not_found`, `not_a_mesh`, `not_object_mode`,
        `material_failed`.
        """
        return backend.send(
            "set_makeskin_material",
            params={
                "name": arguments.validated_subject(name),
                "material_name": _validated_material_name(material_name),
                "textures": _validated_textures(textures),
                "values": _validated_values(values),
                "metadata": _validated_metadata(metadata),
                "replace": arguments.validated_flag(replace, "replace"),
            },
        )
