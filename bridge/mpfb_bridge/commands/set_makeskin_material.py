"""
``set_makeskin_material``: give a mesh a MakeSkin material from images and numbers.

An agent generating textures had to write an MHMAT by hand, call
``populate_from_mhmat()`` and ``apply_node_tree()``, and set metadata through two
config classes, having first read ``mpfb.import_makeskin_material`` to find out how:
that operator needs a file dialog and a "replace" scene property, and reports
``{'ERROR'}`` and then returns ``{'FINISHED'}``. So no operator is called. This builds
from ``MaterialService`` and ``MakeSkinMaterial``, as ``set_asset_material`` does.

**No temporary MHMAT, where the request planned one.** A Blender image has no filename
for the template, so its slot has to go in as ``has_<slot>`` with an empty filename,
as ``create_makeskin_template_material()`` does, and ``apply_node_tree()`` takes its
template values whole or not at all. Given that form is needed anyway, every slot uses
it, and the image is assigned afterwards. That also keeps two of MPFB's behaviours
away from a caller's textures: ``set_image_in_image_node()`` reuses any loaded image
with the same *basename*, so two ``diffuse.png`` from two directories would silently
share pixels, and ``_template()`` splices a path into JSON unescaped, so a quote in one
fails the parse. The MHMAT parser has nothing left to coerce, since the numbers are
checked here against the sockets that will hold them.

**The new material is built before the old one is touched.** It is a datablock of its
own until the last step, so a failure anywhere up to there removes it and the images
this call loaded, and the mesh keeps what it had. That is the
[batch rule](../../../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes)
in its first form, and it is why a value's range can be judged on the real socket.

**Replacing pops the slots, as the import panel does**, rather than calling
``delete_all_materials()``, which renames each one and removes every material in the
file with no users, not only these. A material left with no users is then removed, so
that regenerating under one name does not walk through ``.001`` and ``.002``; one on
another object stays, and ``material_shared_with`` names who has it.

**A path already loaded is reloaded**, or a regenerated file keeps its old pixels;
``apply_material.py`` removed its images first for that reason. An image with unsaved
changes is the exception: reloading would destroy them, so it is a refusal naming the
``image`` form that keeps them.

**A path is read and never written**: see
[the obligation](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more),
which is about where a tool writes. Taking one breaks no rule, as ``add_asset`` has
always taken one.

**Borrows no selection and needs no operator**, so there is nothing to restore.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "set_makeskin_material",
)

import json
import os

import bpy

from ..log import get_logger
from ..shared import blender_data
from ..shared import makeskin
from ..shared import material_settings
from ..shared import mpfb_surface
from ..shared import subject_resolution
from ..shared import texture_writing
from ..shared.performed import with_performed
from ..validation import is_number
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_OBJECT
from ..validation import TYPE_STRING

_LOG = get_logger("commands.setmakeskinmaterial")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="The mesh. Omit or pass null to use whatever object is currently active."),
    Param("material_name", TYPE_STRING, required=True,
          description="What to call the material. Any text; mpfb_store_makeskin_material has "
                      "a narrower rule for a file's name."),
    Param("textures", TYPE_OBJECT, default=None, nullable=True,
          description="Slot to source: {'path': absolute file} or {'image': name in the file}, "
                      "exactly one."),
    Param("values", TYPE_OBJECT, default=None, nullable=True,
          description="Key to {'value': number} or, for a colour, {'color': four numbers}."),
    Param("metadata", TYPE_OBJECT, default=None, nullable=True,
          description="What an MHMAT carries as text and settings, set on the object."),
    Param("replace", TYPE_BOOLEAN, default=False,
          description="Replace the materials the mesh has. False by default, as MakeSkin's panel."),
)

SUMMARY = "Give a mesh a MakeSkin material from image files or Blender images, and numbers."

_NON_COLOR = "Non-Color"
_COLOR = "sRGB"


class _Texture:
    """One slot's source, resolved: nothing has been changed yet."""

    __slots__ = ("slot", "image", "loaded_here", "reload", "wanted_color_space")

    def __init__(self, slot, image, loaded_here, reload_it, wanted_color_space):
        self.slot = slot
        self.image = image
        self.loaded_here = loaded_here
        self.reload = reload_it
        self.wanted_color_space = wanted_color_space


def _error(where, error, message, **extra):
    row = dict(where=where, error=error, message=message)
    row.update(extra)
    return row


def _image_loaded_from(path):
    """An editable image in this file that came from ``path``, or ``None``."""
    for image in bpy.data.images:
        if (image.source == "FILE" and image.library is None
                and texture_writing.image_file_path(image) == path):
            return image
    return None


def _probe(path):
    """A freshly loaded image, or ``None`` when Blender could not read any pixels from it.

    ``load()`` raises for a file it cannot open and returns an image of no size for
    one it cannot decode, so a corrupt PNG takes the second way and nothing would
    otherwise say so.
    """
    try:
        image = bpy.data.images.load(path, check_existing=False)
    except RuntimeError:
        return None
    if not texture_writing.has_pixels(image):
        bpy.data.images.remove(image)
        return None
    return image


def _resolve_path(where, slot, path, wanted_color_space):
    """``(_Texture, error)`` for a path source."""
    if not isinstance(path, str) or not os.path.isabs(path):
        return (None, _error(where, "path_not_absolute",
                             "A path must be absolute, got {!r}.".format(path)))
    if os.path.splitext(path)[1].lower() not in texture_writing.IMAGE_EXTENSIONS:
        return (None, _error(where, "not_an_image_path",
                             "'{:s}' does not end in an image extension: {:s}.".format(
                                 path, ", ".join(texture_writing.IMAGE_EXTENSIONS))))
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        return (None, _error(where, "file_not_found", "No file exists at '{:s}'.".format(path)))

    existing = _image_loaded_from(path)
    if existing is not None and existing.is_dirty:
        return (None, _error(
            where, "image_has_unsaved_changes",
            "'{:s}' is loaded as '{:s}' with unsaved changes, which reloading the file would "
            "destroy. Pass {{\"image\": \"{:s}\"}} to use the image as it is.".format(
                path, str(existing.name), str(existing.name))))
    probe = _probe(path)
    if probe is None:
        return (None, _error(where, "image_unreadable",
                             "Blender could not read any pixels from '{:s}'.".format(path)))
    if existing is not None:
        bpy.data.images.remove(probe)
        return (_Texture(slot, existing, False, True, wanted_color_space), None)
    return (_Texture(slot, probe, True, False, wanted_color_space), None)


def _resolve_image(where, slot, name, wanted_color_space):
    """``(_Texture, error)`` for an image already in the file."""
    image = bpy.data.images.get(name) if isinstance(name, str) else None
    if image is None:
        return (None, _error(where, "image_not_found",
                             "No image named {!r} exists in this .blend file.".format(name)))
    if not texture_writing.has_pixels(image):
        return (None, _error(where, "image_has_no_pixels",
                             "'{:s}' holds no pixels Blender can read.".format(str(image.name))))
    return (_Texture(slot, image, False, False, wanted_color_space), None)


def _discard_loaded(textures):
    for texture in textures:
        if texture.loaded_here and texture.image is not None:
            bpy.data.images.remove(texture.image)
            texture.image = None


def _resolved_textures(words, requested):
    """``(textures, errors)``. The caller removes what was loaded here if anything fails."""
    textures = []
    errors = []
    by_path = dict()
    for slot, source in (requested or dict()).items():
        where = "textures.{!s}".format(slot)
        if slot not in words.slots:
            errors.append(_error(where, "unknown_slot",
                                 "'{!s}' is not a MakeSkin slot; see known_slots.".format(slot)))
            continue
        if not isinstance(source, dict) or (("path" in source) == ("image" in source)):
            errors.append(_error(where, "source_shape",
                                 "A source is an object with exactly one of path and image."))
            continue
        wanted = _NON_COLOR if slot in words.non_color else _COLOR
        if "path" in source:
            path = source["path"]
            normalized = os.path.normpath(path) if isinstance(path, str) else None
            if normalized in by_path:
                # Two slots naming one file are one image, and it holds one colour space.
                texture = _Texture(slot, by_path[normalized].image, False, False, wanted)
                textures.append(texture)
                continue
            texture, error = _resolve_path(where, slot, path, wanted)
            if texture is not None:
                by_path[normalized] = texture
        else:
            texture, error = _resolve_image(where, slot, source["image"], wanted)
        if error is not None:
            errors.append(error)
        else:
            textures.append(texture)
    errors.extend(_color_space_conflicts(textures))
    return (textures, errors)


def _color_space_conflicts(textures):
    """One image in two slots wanting different colour spaces cannot be both."""
    wanted_by_image = dict()
    for texture in textures:
        wanted_by_image.setdefault(texture.image.name, []).append(texture)
    errors = []
    for image_name, sharing in wanted_by_image.items():
        if len(set(texture.wanted_color_space for texture in sharing)) > 1:
            errors.append(_error(
                "textures.{:s}".format(sharing[0].slot), "color_space_conflict",
                "'{:s}' is named for {:s}, which read it in different colour spaces, and an "
                "image holds one.".format(image_name,
                                          " and ".join(texture.slot for texture in sharing))))
    return errors


def _metadata_errors(words, requested):
    errors = []
    for key, value in (requested or dict()).items():
        issue = makeskin.metadata_issue(words, key, value)
        if issue is not None:
            row = _error("metadata.{!s}".format(key), issue[0], issue[1])
            if issue[2] is not None:
                row["known_values"] = issue[2]
            errors.append(row)
    return errors


def _other_users(image, skipping):
    """Every material in the file using an image, but for the one being built."""
    users = []
    for material in bpy.data.materials:
        if material == skipping or material.node_tree is None:
            continue
        if any(node.type == "TEX_IMAGE" and node.image == image
               for node in material.node_tree.nodes):
            users.append(str(material.name))
    return sorted(users)


def _build(services, words, material_name, textures):
    """A material holding the template and the images, on no object yet."""
    MakeSkinMaterial = mpfb_surface.module_level(  # pylint: disable=invalid-name
        services, "HumanService", "MakeSkinMaterial", fallback=None)
    named = set(texture.slot for texture in textures)
    template_values = dict()
    for slot in words.slots:
        template_values["has_" + slot] = "true" if slot in named else "false"
        template_values[slot + "_filename"] = json.dumps("")
    material = services["MaterialService"].create_empty_material(material_name, None)
    try:
        MakeSkinMaterial().apply_node_tree(material, template_values)
        for texture in textures:
            makeskin.texture_node(material.node_tree, texture.slot).image = texture.image
    except Exception:
        bpy.data.materials.remove(material)
        raise
    return material


def _value_errors(words, tree, requested):
    """Whether each number has a socket, of the right kind, and fits it. Writes nothing."""
    errors = []
    _present, absent = makeskin.read_values(words, tree)
    for key, entry in (requested or dict()).items():
        where = "values.{!s}".format(key)
        if key not in words.values:
            errors.append(_error(where, "unknown_value",
                                 "'{!s}' is not a number MakeSkin's node tree reads; see "
                                 "known_values.".format(key)))
            continue
        if key in absent:
            errors.append(_error(where, "value_has_no_socket",
                                 "'{:s}' is held by a node that exists only with a texture in "
                                 "{:s}.".format(key, " or ".join(absent[key])),
                                 needs_slots=absent[key]))
            continue
        errors.extend(_value_shape_errors(words, tree, where, key, entry))
    return errors


def _value_shape_errors(words, tree, where, key, entry):
    node, socket = makeskin.socket_in_charge(words, tree, key)
    if makeskin.is_color_value(socket):
        color = entry.get("color") if isinstance(entry, dict) else None
        if (not isinstance(color, list) or len(color) != 4
                or not all(is_number(channel) for channel in color)):
            return [_error(where, "value_wrong_kind",
                           "'{:s}' is a colour: {{\"color\": four numbers}}.".format(key))]
        if float(color[3]) != 1.0:
            return [_error(where, "alpha_not_kept",
                           "'{:s}' must have an alpha of 1.0: an MHMAT keeps three components, "
                           "so another would not survive a store.".format(key))]
        return []
    value = entry.get("value") if isinstance(entry, dict) else None
    if not is_number(value):
        return [_error(where, "value_wrong_kind",
                       "'{:s}' is a number: {{\"value\": number}}.".format(key))]
    bounds = material_settings.declared_range(node, socket)
    if material_settings.value_outside(value, bounds):
        return [_error(where, "value_out_of_range",
                       "'{:s}' must be within {!r}, since Blender would store something else "
                       "without a word.".format(key, bounds), range=bounds)]
    return []


def _write_values(words, tree, requested):
    """Every socket a key has a row for, so that the two ``diffuseColor`` holds agree."""
    for key, entry in (requested or dict()).items():
        new = entry["color"] if "color" in entry else entry["value"]
        for node_name, socket_name in words.values[key]:
            node = tree.nodes.get(node_name)
            socket = None if node is None else makeskin.socket_of(node, socket_name)
            if socket is not None and not socket.is_linked:
                socket.default_value = new


def _commit_images(textures, material):
    """Reload what regenerated, and read each image as its slot says. Returns what it did."""
    reloaded = []
    color_space_changes = []
    done = set()
    for texture in textures:
        image = texture.image
        if image.name not in done:
            done.add(image.name)
            if texture.reload:
                image.reload()
                reloaded.append(texture.slot)
            before = str(image.colorspace_settings.name)
            if before != texture.wanted_color_space:
                image.colorspace_settings.name = texture.wanted_color_space
                used_by = _other_users(image, material)
                if used_by:
                    color_space_changes.append(dict(
                        image_name=str(image.name), slot=texture.slot, previous_value=before,
                        new_value=texture.wanted_color_space, used_by=used_by))
    return (reloaded, color_space_changes)


def _remove_old_materials(blender_object):
    """Pop every slot, removing what that leaves with no users. Returns who else has any."""
    materials = blender_object.data.materials
    previous = [material for material in materials if material is not None]
    shared_with = set()
    for material in previous:
        shared_with.update(material_settings.material_shared_with(material, [blender_object]))
    while len(materials) > 0:
        materials.pop(index=0)
    for material in previous:
        if material.users == 0:
            bpy.data.materials.remove(material)
    return sorted(shared_with)


def _write_metadata(words, blender_object, requested):
    """Set each key on the object, returning one change row each."""
    changes = []
    for key, value in (requested or dict()).items():
        full_name = words.metadata[key]
        previous = words.properties.get_value(key, entity_reference=blender_object)
        words.properties.set_value(full_name, value, entity_reference=blender_object)
        changes.append(dict(key=key, previous_value=previous, new_value=value))
    return changes


def _answer(words, reason, message, found, ready, subject, resolved_by, params, **extra):
    answer = dict(
        found=found, ready=ready, applied=False, blocked_by=reason,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=resolved_by,
        requested_material_name=params["material_name"], material_name=None,
        materials_destroyed=[], material_shared_with=[], resolution_errors=[],
        textures=dict(), values=dict(), values_absent=dict(), metadata=dict(), metadata_unset=[],
        metadata_changes=[], reloaded=[], color_space_changes=[], unsaved_slots=[],
        known_slots=list(words.slots), known_values=sorted(words.values),
        known_metadata=sorted(words.metadata), message=message)
    answer.update(extra)
    return answer


def _message_for(subject, material, unsaved_slots, reloaded, destroyed, changes):
    parts = ["'{:s}' now has the MakeSkin material '{:s}'.".format(subject.name,
                                                                   str(material.name))]
    if destroyed:
        parts.append(" It replaced {:s}.".format(", ".join(destroyed)))
    if reloaded:
        parts.append(" Reloaded from disk: {:s}.".format(", ".join(reloaded)))
    if unsaved_slots:
        parts.append(" The image for {:s} holds pixels no file does until "
                     "mpfb_store_makeskin_material stores it, and they are lost with this .blend "
                     "unless saved.".format(", ".join(unsaved_slots)))
    if changes:
        parts.append(" Changing a colour space reached other materials; see "
                     "color_space_changes.")
    return "".join(parts)


def set_makeskin_material(params, resolution):  # pylint: disable=too-many-return-statements,too-many-locals
    """Resolve everything, build beside the mesh, then swap."""
    services = resolution.services
    words = makeskin.vocabulary(services, resolution.module.__name__)

    def blocked(reason, message, found=True, subject=None, resolved_by=None, **extra):
        return with_performed(
            _answer(words, reason, message, found, False, subject, resolved_by, params, **extra),
            False)

    subject, resolved_by, message = subject_resolution.resolve_subject(
        params["name"], not_done="no material was changed", select="a mesh")
    if subject is None:
        return blocked("subject_not_found", message, found=False, resolved_by=resolved_by)

    def refused(reason, text, **extra):
        return blocked(reason, text, subject=subject, resolved_by=resolved_by, **extra)

    def unresolved(errors):
        return refused(
            "resolution_failed",
            "{:d} entr{:s} could not be resolved, so **nothing was changed**. Fix those in "
            "'resolution_errors' and send the whole call again.".format(
                len(errors), "y" if len(errors) == 1 else "ies"),
            resolution_errors=errors)

    if subject.type != "MESH":
        return refused("not_a_mesh", "'{:s}' is a {:s}, not a mesh, so it cannot hold a "
                                     "material.".format(subject.name, str(subject.type)))
    if subject.mode != "OBJECT" or bpy.context.mode != "OBJECT":
        return refused(
            "not_object_mode",
            "'{:s}' is in {:s} mode, and a material's slots cannot be changed outside OBJECT "
            "mode, so nothing was changed. Leave edit mode and call again.".format(
                subject.name, str(subject.mode)))
    if not params["material_name"].strip():
        return refused("invalid_material_name", "material_name must not be empty.")

    present = blender_data.material_names(subject)
    if present and not params["replace"]:
        shared = sorted(set(
            name for material_name in present
            for name in material_settings.material_shared_with(
                bpy.data.materials[material_name], [subject])))
        return refused(
            "material_exists",
            "'{:s}' already has {:s}, and replace is false, so nothing was changed. Pass "
            "replace=true to replace it. mpfb_get_makeskin_material reads what it holds.".format(
                subject.name, ", ".join(present)),
            materials_present=present, material_shared_with=shared)

    requested_textures = params["textures"] or dict()
    if "specularmap" in requested_textures and "roughnessmap" in requested_textures:
        return refused(
            "specular_with_roughness",
            "A specular map and a roughness map both drive the Principled BSDF's Roughness, and "
            "only one can. MakeSkin's panel refuses the pair too; give one of them.")

    textures, errors = _resolved_textures(words, requested_textures)
    errors.extend(_metadata_errors(words, params["metadata"]))
    if errors:
        _discard_loaded(textures)
        return unresolved(errors)

    material = None
    try:
        material = _build(services, words, params["material_name"], textures)
        errors = _value_errors(words, material.node_tree, params["values"])
        if errors:
            _discard_loaded(textures)
            bpy.data.materials.remove(material)
            return unresolved(errors)
        _write_values(words, material.node_tree, params["values"])
    except Exception as error:  # pylint: disable=broad-except
        # Broad on purpose: this runs MPFB's template code, and the mesh still has what it
        # had, which the caller should be told rather than handed a traceback.
        if material is not None:
            bpy.data.materials.remove(material)
        _discard_loaded(textures)
        return refused("material_failed",
                       "MPFB raised while building the material, and '{:s}' keeps what it had: "
                       "{:s}".format(subject.name, str(error)))

    # Everything above is settled, and this is the first statement that changes the mesh.
    material_shared_with = _remove_old_materials(subject)
    subject.data.materials.append(material)
    material.name = params["material_name"]
    reloaded, color_space_changes = _commit_images(textures, material)
    metadata_changes = _write_metadata(words, subject, params["metadata"])
    words.properties.set_value("name", str(material.name), entity_reference=subject)

    tree = material.node_tree
    read_textures = makeskin.read_textures(words, tree)
    values, values_absent = makeskin.read_values(words, tree)
    metadata, metadata_unset = makeskin.read_metadata(words, subject)
    unsaved_slots = sorted(slot for slot, entry in read_textures.items() if "image" in entry)
    _LOG.debug("set_makeskin_material: %r on %r", material.name, subject.name)
    answer = _answer(
        words, None,
        _message_for(subject, material, unsaved_slots, reloaded, present, color_space_changes),
        True, True, subject, resolved_by, params,
        material_name=str(material.name),
        materials_destroyed=present,
        material_shared_with=material_shared_with,
        textures=read_textures,
        values=values,
        values_absent=values_absent,
        metadata=metadata,
        metadata_unset=metadata_unset,
        metadata_changes=metadata_changes,
        reloaded=reloaded,
        color_space_changes=color_space_changes,
        unsaved_slots=unsaved_slots)
    answer["applied"] = True
    return with_performed(answer, True)
