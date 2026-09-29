"""
The three procedural material settings MPFB saves in a preset, read the way it saves them.

**One implementation, imported by ``get_material_settings``,
``set_material_settings`` and ``get_character_summary``.** See
[`__init__.py`](__init__.py) for why this directory exists beside ``commands/``.
The three have to agree about four things, and each is a way for a read and a
write, or a summary and its detailed tool, to disagree silently: **which node**
a section is read from, **which sockets** count as settings, what **linked**
means, and how a scene-linear colour becomes an **sRGB hex**
([FR 040](../../../feature-requests/done/040-procedural-material-settings/README.md)).

**Every section is found the way ``HumanService``'s serializer finds it**, not
the way a tidier reading would, because the promise is that what is reported
as a setting is exactly what ``serialize_to_json_string()`` would save:

- ``eyes``: ``_populate_human_info_with_eye_material_info()``. The ``Eyes``
  relative, its slot 0, the first ``ShaderNodeGroup`` in that material, and the
  serializer's own test for "procedural": the group has an ``IrisMinorColor``
  input. ``MaterialService.identify_material()`` tests ``IrisSection4Color``
  instead, and both are reported rather than reconciled.
- ``skin``: ``_populate_human_info_with_skin_info()``. The body proxy's slot 0
  when there is a proxy, otherwise the basemesh's - LAYERED never makes material
  instances, so ``set_character_skin()`` hands the proxy the basemesh's own
  material - and every ``ShaderNodeGroup`` named ``<group>group`` for a
  ``<group>`` in :data:`SERIALIZED_SKIN_GROUPS`.
- ``color_adjustments``: ``_populate_human_info_with_bodyparts_info()`` and
  ``..._clothes_info()``. One body part per type in
  :data:`SERIALIZED_BODY_PARTS` **except the eyes**, and every garment; each
  needs an ``asset_source`` and a ``uuid``; the node is whatever
  ``MaterialService.find_color_adjustment()`` reaches - the node linked to the
  Principled BSDF's ``Base Color``, which is ``diffuseIntensity`` normally and
  ``aoMix`` on an asset whose MHMAT has an AO map. A MakeSkin body is not in
  either list, so it is not reported: a tint on it would not survive a preset.

**What ``aoMix`` means, measured on the installed ``female_casualsuit01``:** it
is MakeSkin's "AO Multiplier", a MULTIPLY ``ShaderNodeMixRGB`` whose ``Color1``
is linked from ``diffuseIntensity`` and ``Color2`` from the AO texture. Its one
writable setting is ``Factor``, the AO strength. So on such an asset MPFB's
colour adjustment is the AO strength and nothing else, and the tint on
``diffuseIntensity`` behind it can be neither written through this module nor
saved in a preset. That is MPFB's choice, followed rather than extended, and a
candidate MPFB defect.

**A MakeSkin material with no diffuse texture has no ``diffuseIntensity`` at
all**: MakeSkin creates that node only for a texture, so nothing is linked to
Base Color, and ``identify_material()`` - which recognizes MakeSkin by that node
- calls the material ``gameengine``. Every real MHMAT names a texture, so this
is a fixture's trap more than a user's.

**Which sockets count is MPFB's decision, never this module's.** The settings of
a node are ``NodeService.get_socket_default_values(node)``, the very call the
serializer makes, so the answer's keys are the preset's keys by construction.
No socket name is tabulated here. The two tuples below are **copies of lists
MPFB writes inline** in the serializer, and cannot be read from MPFB because
they are local variables; they are how MPFB *finds* a node, which is the one
kind of name the specification allows here
([names inside MPFB's node trees are read live](../../../specifications/mpfb-integration.md#names-inside-mpfbs-node-trees-are-read-live-never-tabulated)).
A group MPFB adds to its inline list shows up as a ``groups_not_serialized``
entry until the copy is updated, and the bridge test comparing this module with
the serializer fails.

**What a socket carries beside its value**, each of it a fact MPFB's own UI
does not put in front of anyone:

- **``linked``.** Most of the layered skin's region colours are driven by a link
  from ``colorgroup`` (``MpfbSkinMasterColor``), and so is ``diffuseIntensity``'s
  ``Color2``, from the diffuse texture. Writing a linked socket's default value
  succeeds and changes nothing; the serializer saves it anyway. A link is
  reported as the node and socket it comes from.
- **``ranges``.** A group node's input carries no range of its own - it is on
  the node group's interface item, found by the socket's identifier. A built-in
  node's socket carries it in its RNA ``default_value`` property's hard limits.
  ``+-FLT_MAX`` is Blender's way of saying "no limit" and is reported as ``null``.
  **Blender does not enforce a group input's range**: a default value assigned
  outside it is stored as given. A built-in node's is enforced, by clamping.
- **``values_outside_range``.** MPFB's own ``MpfbBody`` declares
  ``NavelWidthMultiplier`` as 0.001-0.2 and defaults it to 11.0, so a declared
  range can be contradicted by MPFB's own value. Such a socket is named here,
  and ``set_material_settings`` does not enforce that range.
- **``srgb_hex``.** A colour socket holds scene-linear RGBA, and an agent that
  thinks in sRGB picks colours that come out too light. The hex is **derived**,
  per [responses.md](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact):
  each channel clamped to 0.0-1.0, put through the sRGB transfer function and
  rounded to a byte, alpha dropped. It is a convenience for reading and is never
  accepted back. A socket is a colour exactly when it has a hex.

Values are reported **exactly as the preset holds them**: a colour as a list of
four floats, a float as a float, unrounded. Rounding would make the read disagree
with the file it describes, which is the one comparison this module exists to
make possible.
"""

__all__ = (
    "SERIALIZED_BODY_PARTS",
    "SERIALIZED_SKIN_GROUPS",
    "color_adjustment_records",
    "eyes_section",
    "input_socket",
    "is_color",
    "material_shared_with",
    "skin_section",
    "socket_report",
    "srgb_hex",
    "value_outside",
)

import math

import bpy

# A copy of the list in HumanService._populate_human_info_with_skin_info() and
# set_character_skin(), which MPFB writes inline twice. The preset's keys under
# skin_material_settings, and each one's node is named "<key>group".
SERIALIZED_SKIN_GROUPS = ("color", "body", "face", "ears", "lips", "aureolae", "genitals",
                          "fingernails", "toenails")

# The suffix MPFB matches group node names against, from the same two places.
GROUP_SUFFIX = "group"

# A copy of the list in HumanService._populate_human_info_with_bodyparts_info().
# The serializer asks for **one** object of each type and skips the eyes when
# recording a colour adjustment, both of which this module reproduces.
SERIALIZED_BODY_PARTS = ("Eyes", "Eyelashes", "Eyebrows", "Tongue", "Teeth", "Hair")

# The serializer's own test for procedural eyes: the eye material's first group
# node has this input. identify_material() tests IrisSection4Color instead.
_SERIALIZER_EYES_DISCRIMINATOR = "IrisMinorColor"

# The body part the serializer leaves out of colour adjustments.
_EXCLUDED_BODY_PART = "Eyes"

# Blender's "unbounded": FLT_MAX, as a float64, give or take the conversion.
_UNBOUNDED = 3.0e38


def is_color(value):
    """Whether a preset value is a colour: MPFB stores a colour as a list, a float as a float."""
    return isinstance(value, (list, tuple))


def _channel_to_srgb(linear):
    linear = min(1.0, max(0.0, float(linear)))
    if linear <= 0.0031308:
        encoded = 12.92 * linear
    else:
        encoded = 1.055 * math.pow(linear, 1.0 / 2.4) - 0.055
    return int(round(min(1.0, max(0.0, encoded)) * 255.0))


def srgb_hex(linear_rgba):
    """``#rrggbb`` for a scene-linear RGBA value, alpha dropped. Derived, never recorded."""
    return "#{:02x}{:02x}{:02x}".format(*(_channel_to_srgb(channel)
                                          for channel in list(linear_rgba)[:3]))


def input_socket(node, socket_name):
    """The input ``set_socket_default_values()`` would write under ``socket_name``.

    MPFB's read keeps the **last** input of a name, since it builds a dict, and
    its write sets every input of that name. The last one is therefore the one
    whose value the preset records, and the one reported here.
    """
    found = None
    for node_input in node.inputs:
        if node_input.name == socket_name:
            found = node_input
    return found


def _bound(value):
    if value is None or abs(float(value)) >= _UNBOUNDED:
        return None
    return round(float(value), 6)


def _interface_item(node, socket):
    tree = getattr(node, "node_tree", None)
    interface = getattr(tree, "interface", None)
    if interface is None:
        return None
    for item in interface.items_tree:
        if (getattr(item, "item_type", None) == "SOCKET" and item.in_out == "INPUT"
                and item.identifier == socket.identifier):
            return item
    return None


def declared_range(node, socket):
    """``[minimum, maximum]`` for a float socket, either ``None`` when unbounded, or ``None``.

    A group node's input is looked up on its node group's interface, which is
    where Blender keeps the range; anything else through its RNA property.
    """
    if node.bl_idname == "ShaderNodeGroup":
        item = _interface_item(node, socket)
        if item is None or not hasattr(item, "min_value"):
            return None
        minimum, maximum = item.min_value, item.max_value
    else:
        prop = socket.bl_rna.properties.get("default_value")
        if prop is None or prop.type != "FLOAT" or prop.array_length != 0:
            return None
        minimum, maximum = prop.hard_min, prop.hard_max
    try:
        bounds = [_bound(minimum), _bound(maximum)]
    except TypeError:
        # A vector socket's interface item has array-valued limits.
        return None
    if bounds == [None, None]:
        return None
    return bounds


def value_outside(value, bounds):
    """Whether a float lies outside ``[minimum, maximum]``, either end possibly open."""
    if bounds is None:
        return False
    minimum, maximum = bounds
    return (minimum is not None and value < minimum) or (maximum is not None and value > maximum)


def _link_of(socket):
    if not socket.is_linked or not socket.links:
        return None
    link = socket.links[0]
    return dict(from_node=link.from_node.name, from_socket=link.from_socket.name)


def socket_report(services, node):
    """What one node's settings are, and what each socket carries beside its value.

    ``settings`` is ``get_socket_default_values(node)`` - the preset's dict for
    this node - and the other four are keyed by the same socket names, holding
    an entry only where there is something to say.
    """
    raw = services["NodeService"].get_socket_default_values(node)
    settings = {}
    hexes = {}
    ranges = {}
    linked = {}
    outside = []
    for socket_name, value in raw.items():
        socket = input_socket(node, socket_name)
        if is_color(value):
            value = [float(channel) for channel in value]
            hexes[socket_name] = srgb_hex(value)
        else:
            value = float(value)
            bounds = None if socket is None else declared_range(node, socket)
            if bounds is not None:
                ranges[socket_name] = bounds
                if value_outside(value, bounds):
                    outside.append(socket_name)
        settings[socket_name] = value
        link = None if socket is None else _link_of(socket)
        if link is not None:
            linked[socket_name] = link
    return dict(
        node_name=node.name,
        settings=settings,
        srgb_hex=hexes,
        ranges=ranges,
        linked=linked,
        values_outside_range=outside,
    )


def material_shared_with(material, own_objects):
    """Every object outside ``own_objects`` whose material slots hold ``material``, by name.

    A write to a node changes the material, and so every object using it. The
    section's own objects are left out, since the section already names them.
    """
    if material is None:
        return []
    own = set(blender_object.name for blender_object in own_objects if blender_object is not None)
    shared = []
    for blender_object in bpy.data.objects:
        if blender_object.name in own:
            continue
        if any(slot.material == material for slot in blender_object.material_slots):
            shared.append(blender_object.name)
    return sorted(shared)


def _not_applicable(reason, **known):
    section = dict(applies=False, reason=reason)
    section.update(known)
    return section


def _slot_zero_material(blender_object):
    if not blender_object.material_slots:
        return None
    return blender_object.material_slots[0].material


def eyes_section(services, basemesh):
    """The procedural eye material's settings, or why there are none.

    ``node`` is the group node itself, for a command that writes to it; it is
    removed before anything is reported.
    """
    object_service = services["ObjectService"]
    material_service = services["MaterialService"]
    node_service = services["NodeService"]

    eyes = object_service.find_object_of_type_amongst_nearest_relatives(basemesh, "Eyes")
    if eyes is None:
        return _not_applicable("no_eyes", object_name=None, material_name=None,
                               material_identified_as=None)
    material = _slot_zero_material(eyes) if material_service.has_materials(eyes) else None
    if material is None or material.node_tree is None:
        return _not_applicable("no_material", object_name=eyes.name, material_name=None,
                               material_identified_as=None)

    identified = material_service.identify_material(material)
    known = dict(object_name=eyes.name, material_name=material.name,
                 material_identified_as=identified)
    if identified in ("makeskin", "gameengine"):
        return _not_applicable("not_procedural", **known)
    node = node_service.find_first_node_by_type_name(material.node_tree, "ShaderNodeGroup")
    if node is None:
        return _not_applicable("not_procedural", **known)
    if _SERIALIZER_EYES_DISCRIMINATOR not in node_service.get_socket_default_values(node):
        return _not_applicable("not_procedural", **known)

    section = dict(applies=True, reason=None, **known)
    section.update(socket_report(services, node))
    section["material_shared_with"] = material_shared_with(material, [eyes])
    section["node"] = node
    return section


def skin_section(services, basemesh):
    """The layered skin's groups, keyed as the preset keys them, or why there are none.

    ``nodes`` maps each preset key to its group node, for a command that writes;
    it is removed before anything is reported.
    """
    object_service = services["ObjectService"]
    material_service = services["MaterialService"]
    node_service = services["NodeService"]

    proxy = object_service.find_object_of_type_amongst_nearest_relatives(basemesh, "Proxymeshes")
    body = proxy if proxy is not None else basemesh
    material = _slot_zero_material(body)
    if material is None or material.node_tree is None:
        return _not_applicable("no_material", object_name=body.name, material_name=None,
                               material_identified_as=None)

    identified = material_service.identify_material(material)
    known = dict(object_name=body.name, material_name=material.name,
                 material_identified_as=identified)
    if not identified or "layered" not in identified:
        return _not_applicable("not_layered", **known)

    live = {}
    for node in node_service.find_nodes_by_type_name(material.node_tree, "ShaderNodeGroup"):
        if node.name.endswith(GROUP_SUFFIX):
            live[node.name] = node

    groups = {}
    nodes = {}
    for group in SERIALIZED_SKIN_GROUPS:
        node = live.get(group + GROUP_SUFFIX)
        if node is not None:
            groups[group] = socket_report(services, node)
            nodes[group] = node
    listed = set(group + GROUP_SUFFIX for group in SERIALIZED_SKIN_GROUPS)

    if not groups:
        return _not_applicable("not_layered", **known)

    section = dict(applies=True, reason=None, **known)
    section["groups"] = groups
    section["groups_missing"] = [group for group in SERIALIZED_SKIN_GROUPS if group not in groups]
    section["groups_not_serialized"] = sorted(name for name in live if name not in listed)
    section["material_shared_with"] = material_shared_with(material, [basemesh, proxy])
    section["nodes"] = nodes
    return section


def _serialized_objects(services, basemesh):
    """Every object the serializer records a colour adjustment for, by name."""
    object_service = services["ObjectService"]
    serialized = {}
    for body_part in SERIALIZED_BODY_PARTS:
        if body_part == _EXCLUDED_BODY_PART:
            continue
        found = object_service.find_object_of_type_amongst_nearest_relatives(basemesh, body_part)
        if found is not None:
            serialized[found.name] = found
    for garment in object_service.find_all_objects_of_type_amongst_nearest_relatives(
            basemesh, "Clothes"):
        serialized[garment.name] = garment
    return serialized


def _general_value(general_properties, property_name, blender_object):
    if general_properties is None:
        return None
    value = general_properties.get_value(property_name, entity_reference=blender_object)
    return None if value is None or value == "" else value


def _color_adjustment_record(services, general_properties, blender_object, serialized):
    object_service = services["ObjectService"]
    material_service = services["MaterialService"]
    node_service = services["NodeService"]

    object_type = object_service.get_object_type(blender_object)
    uuid = _general_value(general_properties, "uuid", blender_object)
    material = material_service.get_material(blender_object)
    record = dict(
        object_name=blender_object.name,
        object_type=object_type,
        uuid=None if uuid is None else str(uuid),
        material_name=None if material is None else material.name,
        material_identified_as=(None if material is None or material.node_tree is None
                                else material_service.identify_material(material)),
        node_name=None,
        applies=False,
        reason=None,
    )

    if object_type == _EXCLUDED_BODY_PART:
        record["reason"] = "eyes_excluded"
    elif blender_object.name not in serialized:
        record["reason"] = "not_serialized"
    elif _general_value(general_properties, "asset_source", blender_object) is None:
        record["reason"] = "no_asset_source"
    elif uuid is None:
        record["reason"] = "no_uuid"
    elif material is None or material.node_tree is None:
        record["reason"] = "no_material"
    if record["reason"] is not None:
        return record

    principled = node_service.find_first_node_by_type_name(
        material.node_tree, "ShaderNodeBsdfPrincipled")
    node = None if principled is None else node_service.find_node_linked_to_socket(
        material.node_tree, principled, "Base Color")
    if principled is None:
        record["reason"] = "no_principled_bsdf"
        return record
    if node is None:
        record["reason"] = "nothing_on_base_color"
        return record
    record["node_name"] = node.name
    report = socket_report(services, node)
    if not report["settings"]:
        # find_color_adjustment() returns an empty dict, and the serializer
        # records nothing for a falsy one.
        record["reason"] = "no_settings_on_node"
        return record

    record["applies"] = True
    record.update(report)
    record["material_shared_with"] = material_shared_with(material, [blender_object])
    record["node"] = node
    return record


def color_adjustment_records(services, general_properties, basemesh):
    """One record per mesh asset in the family, ordered by type and name.

    Every mesh asset gets a record, not only those the serializer keeps, so that
    an asset whose tint would not survive a preset says why rather than being
    missing. ``general_properties`` is MPFB's ``GeneralObjectProperties``, as
    ``mpfb_surface.general_object_properties()`` reads it. ``node`` is removed
    before anything is reported, as in the two sections above.
    """
    serialized = _serialized_objects(services, basemesh)
    records = [
        _color_adjustment_record(services, general_properties, blender_object, serialized)
        for blender_object in services["ObjectService"].find_related_mesh_assets(basemesh)]
    records.sort(key=lambda record: (str(record["object_type"]), record["object_name"]))
    return records
