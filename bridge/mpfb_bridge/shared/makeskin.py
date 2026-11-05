"""
What a MakeSkin material is: its vocabulary, how one is recognised, and how one reads.

One implementation, for ``get_makeskin_material``, ``set_makeskin_material`` (which
answers with the same reading, so that what it says it did is what the reader would
say), ``store_makeskin_material`` and FR 050's writer.

**Every name here is read from MPFB, none is kept.** The slots are
``_TEXTURE_NAMES``, the colour rule ``_NONCOLOR``, the numbers
``_NODE_SOCKET_VALUES``, which node a slot brings with it the ``create`` entries of
``makeskin.json``, and the metadata every ``MHMAT_KEYS`` entry with a property on the
object - which is the test ``populate_from_object()`` applies. So a slot MPFB adds
appears here without an edit, by the rule that
[names inside MPFB's node trees are read live](../../../specifications/mpfb-integration.md#names-inside-mpfbs-node-trees-are-read-live-never-tabulated).

**Recognition cannot be ``identify_material()`` alone.** It recognises MakeSkin by
the ``diffuseIntensity`` node, which the template creates only with a diffuse
texture, so an untextured MakeSkin material is called ``gameengine``. Hence
:func:`recognized`: MPFB's verdict, or a ``gameengine`` verdict on a tree holding
nothing but nodes the template names. A plain Principled material from Blender
passes too, and rightly: it is node for node what an untextured MakeSkin template
builds, and MakeSkin's panel stores one without complaint. ``recognized_by`` says
which test answered.

**A value is reported with whether it does anything** (``in_effect``), because
nothing else says so: ``populate_from_object()`` writes ``roughness 0.7`` beside a
roughness map. It is not in effect when its socket is linked, or when it scales a
map the material does not have, or, for ``diffuseColor``, when the diffuse texture's
mix factor leaves none of it showing.

**MPFB spells one key differently from its own file format, and misses one socket.**
``_NODE_SOCKET_VALUES`` writes the displacement strength as
``displacementmapIntensity`` where the MHMAT key is ``displacementMapIntensity``, and
looks for the mix node's factor by a name Blender 5.1 reports as ``Factor``. So
:func:`file_settings` hands the store the numbers read here, and both reach the file.
The first spelling is the MHMAT key's throughout this package's answers.

Takes ``services`` first, since the vocabulary is MPFB's, except the readers that are
given a :class:`Vocabulary` already.
"""

__all__ = (
    "READ_ONLY_TEXTURE_KEYS",
    "READ_ONLY_VALUE_KEYS",
    "Vocabulary",
    "empty_slots",
    "file_settings",
    "is_color_value",
    "metadata_issue",
    "read_metadata",
    "read_textures",
    "read_values",
    "recognized",
    "socket_in_charge",
    "socket_of",
    "texture_node",
    "vocabulary",
)

import json
import os

import bpy

from . import material_settings
from . import mpfb_surface
from . import texture_writing

# What a reader's texture and value entries carry beside what a writer takes. A
# writer ignores these, so that an answer can be sent back unchanged; anything else
# it does not know is a misspelling. mpfbmcp's set_makeskin_material tool carries a
# copy, which its test module holds to these two by reading this module as data.
READ_ONLY_TEXTURE_KEYS = ("image_name", "wired", "resolved_path", "file_exists", "size",
                          "color_space", "packed", "unsaved_changes", "strength",
                          "strength_value")
READ_ONLY_VALUE_KEYS = ("in_effect", "overridden_by", "needs_slot", "range", "srgb_hex")

# The key MPFB's value table spells otherwise, and the socket Blender names otherwise.
_ROW_KEY_SPELLINGS = {"displacementmapIntensity": "displacementMapIntensity"}
_SOCKET_SPELLINGS = {"Fac": "Factor"}

# A key the object's properties hold and a material's name is not one a caller sets
# as metadata: material_name is, and the store's argument of the same name wins.
_NOT_METADATA = ("name",)

_TEMPLATE_PLACEHOLDER = "$has_"
_BUMP_OR_NORMAL = "$bump_or_normal"


def _template(services):
    """``makeskin.json`` as data. Its placeholders are quoted, so it parses unfilled."""
    path = os.path.join(str(services["LocationService"].get_mpfb_data("node_trees")),
                        "makeskin.json")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _template_nodes(template):
    nodes = template.get("nodes") or []
    return list(nodes.values()) if isinstance(nodes, dict) else list(nodes)


def _slots_creating(create, slots):
    """Which slots bring a node with this ``create`` entry into being: ``[]`` meaning always."""
    if create == _BUMP_OR_NORMAL:
        return [slot for slot in ("bumpmap", "normalmap") if slot in slots]
    if isinstance(create, str) and create.startswith(_TEMPLATE_PLACEHOLDER):
        slot = create[len(_TEMPLATE_PLACEHOLDER):]
        return [slot] if slot in slots else []
    return []


class Vocabulary:
    """MPFB's MakeSkin vocabulary, read once for one call.

    ``slots`` are texture slots; ``non_color`` the ones read as data. ``values``
    maps an MHMAT key to its ``(node, socket)`` rows in MPFB's order, the last of
    them that exists being the one in charge. ``strength_of`` maps a slot to the
    value that scales it. ``slots_for_node`` says which slots bring a node into the
    tree. ``metadata`` maps an MHMAT key to its property's full name on the object.
    """

    __slots__ = ("properties", "slots", "non_color", "values", "strength_of", "slots_for_node",
                 "template_node_names", "metadata")

    def __init__(self, services, root_name):
        self.properties = mpfb_surface.make_skin_properties(root_name)
        if self.properties is None:
            raise mpfb_surface.MissingFromMpfb(
                "MPFB's MakeSkin properties are not loaded, and this command cannot answer without "
                "them. Check mpfb_get_status.")
        self.slots = tuple(mpfb_surface.required_makeskin_level(services, "_TEXTURE_NAMES"))
        self.non_color = frozenset(mpfb_surface.required_makeskin_level(services, "_NONCOLOR"))

        self.values = dict()
        for key, node_name, socket_name in mpfb_surface.required_makeskin_level(
                services, "_NODE_SOCKET_VALUES"):
            spelled = _ROW_KEY_SPELLINGS.get(key, key)
            self.values.setdefault(spelled, []).append((node_name, socket_name))

        self.strength_of = dict()
        for slot in self.slots:
            for key in self.values:
                if key.lower() == slot.lower() + "intensity":
                    self.strength_of[slot] = key

        nodes = _template_nodes(_template(services))
        self.template_node_names = frozenset(str(node["name"]) for node in nodes)
        self.slots_for_node = {str(node["name"]): _slots_creating(node.get("create"), self.slots)
                               for node in nodes}
        self.metadata = self._metadata_keys(services)

    def _metadata_keys(self, services):
        """Every MHMAT key with a property on the object, as ``populate_from_object()`` tests."""
        keys = mpfb_surface.required_makeskin_level(services, "MHMAT_KEYS")
        aliases = getattr(self.properties, "_alias_to_prop", None)
        if aliases is None:
            raise mpfb_surface.MissingFromMpfb(
                "MPFB's MakeSkin properties no longer keep their aliases where this add-on reads "
                "them. Check mpfb_get_status and upgrade the MPFB Bridge.")
        short_names = set(self.properties.get_keys())
        metadata = dict()
        for key in keys:
            name = str(key.key_name)
            if name in _NOT_METADATA or not self.properties.has_key(name):
                continue
            if name in short_names:
                metadata[name] = self.properties.get_fullname_key_from_shortname_key(name)
            else:
                metadata[name] = aliases[name]
        return metadata

    def property_rna(self, key):
        """The RNA of the object property behind one metadata key."""
        return bpy.types.Object.bl_rna.properties[self.metadata[key]]


def vocabulary(services, root_name):
    """:class:`Vocabulary`, read now: a disabled and re-enabled MPFB leaves nothing stale."""
    return Vocabulary(services, root_name)


def recognized(services, words, material):
    """``(is_makeskin, identified_as, recognized_by)``. See this module's docstring."""
    identified_as = str(services["MaterialService"].identify_material(material))
    if identified_as == "makeskin":
        return (True, identified_as, "identify_material")
    if identified_as == "gameengine" and material.node_tree is not None:
        names = set(str(node.name) for node in material.node_tree.nodes)
        if "Principled BSDF" in names and names <= words.template_node_names:
            return (True, identified_as, "template_nodes")
    return (False, identified_as, None)


def texture_node(tree, slot):
    """The image node of one slot, or ``None``: a node name is the slot and ``Texture``."""
    return tree.nodes.get(slot + "Texture")


def socket_of(node, socket_name):
    """One named input of a node, or ``None``, by the name Blender reports now or used to."""
    socket = material_settings.input_socket(node, socket_name)
    if socket is None and socket_name in _SOCKET_SPELLINGS:
        socket = material_settings.input_socket(node, _SOCKET_SPELLINGS[socket_name])
    return socket


def _wired(node):
    return any(output.is_linked for output in node.outputs)


def _strength(words, tree, slot):
    key = words.strength_of.get(slot)
    if key is None:
        return None
    charge = socket_in_charge(words, tree, key)
    if charge is None:
        return None
    return (key, round(float(charge[1].default_value), 6))


def read_textures(words, tree):
    """Each slot holding an image, in the shape a writer takes. See the tool's description.

    ``path`` when the file holds what the image holds, ``image`` otherwise, so a
    read-back sent to the writer reproduces the live pixels rather than an older
    file: an image with unsaved changes has a file and answers with ``image``.
    """
    textures = dict()
    for slot in words.slots:
        node = texture_node(tree, slot)
        if node is None or node.image is None:
            continue
        image = node.image
        path = texture_writing.image_file_path(image)
        entry = dict()
        if texture_writing.is_in_sync_with_its_file(image):
            entry["path"] = path
        else:
            entry["image"] = str(image.name)
        entry.update(
            image_name=str(image.name),
            wired=_wired(node),
            resolved_path=path,
            file_exists=path is not None and os.path.isfile(path),
            size=[int(side) for side in image.size],
            color_space=str(image.colorspace_settings.name),
            packed=image.packed_file is not None,
            unsaved_changes=bool(image.is_dirty),
        )
        strength = _strength(words, tree, slot)
        if strength is not None:
            entry.update(strength_value=strength[0], strength=strength[1])
        textures[slot] = entry
    return textures


def empty_slots(words, tree):
    """Slots whose node exists and holds no image, as MakeSkin's blank template leaves them."""
    return [slot for slot in words.slots
            if texture_node(tree, slot) is not None and texture_node(tree, slot).image is None]


def socket_in_charge(words, tree, key):
    """``(node, socket)`` a value is read from and written to, or ``None``.

    The last row whose node exists, as ``populate_from_object()`` lets a later row
    overwrite an earlier one.
    """
    found = None
    for node_name, socket_name in words.values[key]:
        node = tree.nodes.get(node_name)
        socket = None if node is None else socket_of(node, socket_name)
        if socket is not None:
            found = (node, socket)
    return found


def is_color_value(socket):
    """Whether a socket's value is a colour rather than a float."""
    return socket.type == "RGBA"


def _upstream_slot(words, socket, seen=None):
    """The slot whose texture drives a linked socket, walking back through the tree."""
    seen = set() if seen is None else seen
    for link in socket.links:
        node = link.from_node
        if node.name in seen:
            continue
        seen.add(node.name)
        if node.name.endswith("Texture") and node.name[:-len("Texture")] in words.slots:
            return node.name[:-len("Texture")]
        for node_input in node.inputs:
            if node_input.is_linked:
                slot = _upstream_slot(words, node_input, seen)
                if slot is not None:
                    return slot
    return None


def _effect(words, tree, key, node, socket):
    """``(in_effect, overridden_by, needs_slot)`` for one value."""
    if socket.is_linked:
        return (False, _upstream_slot(words, socket), None)
    for slot, strength_key in words.strength_of.items():
        if strength_key == key:
            slot_node = texture_node(tree, slot)
            if slot_node is None or slot_node.image is None or not _wired(slot_node):
                return (False, None, slot)
    if key == "diffuseColor" and node.name == "diffuseIntensity":
        factor = socket_of(node, "Fac")
        if factor is not None and not factor.is_linked and float(factor.default_value) >= 1.0:
            return (False, "diffuse", None)
    return (True, None, None)


def read_values(words, tree):
    """``(values, values_absent)``: what the tree has a socket for, and what it has none for.

    ``values`` is in the shape a writer takes. ``values_absent`` maps each other
    key to the slots that would bring its node into the tree.
    """
    values = dict()
    absent = dict()
    for key, rows in words.values.items():
        charge = socket_in_charge(words, tree, key)
        if charge is None:
            absent[key] = sorted(set(
                slot for node_name, _socket in rows
                for slot in words.slots_for_node.get(node_name, [])))
            continue
        node, socket = charge
        in_effect, overridden_by, needs_slot = _effect(words, tree, key, node, socket)
        entry = dict()
        if is_color_value(socket):
            color = [round(float(channel), 6) for channel in socket.default_value]
            entry.update(color=color, srgb_hex=material_settings.srgb_hex(color))
        else:
            entry.update(value=round(float(socket.default_value), 6),
                         range=material_settings.declared_range(node, socket))
        entry.update(in_effect=in_effect, overridden_by=overridden_by, needs_slot=needs_slot)
        values[key] = entry
    return (values, absent)


def read_metadata(words, blender_object):
    """``(metadata, metadata_unset)``: the object's values, and those never set on it.

    ``metadata`` is exactly what a writer takes. ``metadata_unset`` lists the keys
    that hold MPFB's default rather than anything somebody chose.
    """
    metadata = dict()
    unset = []
    for key, full_name in words.metadata.items():
        value = words.properties.get_value(key, entity_reference=blender_object)
        metadata[key] = value if isinstance(value, bool) else ("" if value is None else str(value))
        if not blender_object.is_property_set(full_name):
            unset.append(key)
    return (metadata, sorted(unset))


def metadata_issue(words, key, value):
    """``(error, sentence, known)`` for one metadata entry, or ``None`` when it may be written."""
    if key not in words.metadata:
        return ("unknown_metadata", "'{:s}' is not metadata MakeSkin writes into a file.".format(
            str(key)), None)
    rna = words.property_rna(key)
    if rna.type == "BOOLEAN":
        if not isinstance(value, bool):
            return ("metadata_wrong_type",
                    "'{:s}' is true or false, got {!r}.".format(key, value), None)
        return None
    if not isinstance(value, str):
        return ("metadata_wrong_type", "'{:s}' is text, got {!r}.".format(key, value), None)
    if "\n" in value or "\r" in value:
        # An MHMAT is one key per line, so a line break would write a second key.
        return ("metadata_wrong_type", "'{:s}' must be one line of text.".format(key), None)
    if rna.type == "ENUM":
        known = [item.identifier for item in rna.enum_items]
        if value not in known:
            return ("unknown_metadata_value",
                    "'{:s}' is one of {:s}, got {!r}.".format(key, ", ".join(known), value), known)
    return None


def file_settings(words, tree):
    """Each value's number as an MHMAT holds it, for the store to put in ``_settings``.

    Read here rather than left to ``populate_from_object()``, which misses two of
    them (see this module's docstring). A value the tree has no socket for is
    ``None``, which ``as_mhmat()`` writes as a comment.
    """
    settings = dict()
    for key in words.values:
        charge = socket_in_charge(words, tree, key)
        if charge is None:
            settings[key] = None
        elif is_color_value(charge[1]):
            settings[key] = [float(channel) for channel in charge[1].default_value]
        else:
            settings[key] = float(charge[1].default_value)
    return settings
