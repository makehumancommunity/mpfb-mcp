"""
Payload for ``mpfb_get_target_stack``: what is actually on this character.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap and the
``target_categories.py`` and ``modifier_reading.py`` shared fragments (see
``mpfbmcp.codegen.assemble``). A linter will flag several names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``,
  ``include_macro``, ``include_expressions``, ``name_contains``, ``limit`` and
  ``offset``.
- ``_MPFB_SERVICES`` and ``sys`` - from the raising bootstrap.
- ``TARGET_SECTIONS``, ``KNOWN_SECTIONS``, ``TARGET_INDEX``, ``find_category``,
  ``target_names_for``, ``category_is_opposed`` - from the shared fragment,
  whose docstring explains what a category is and why it is rebuilt here.
- ``modifier_reading()`` - from the shared fragment ``modifier_reading.py``,
  shared with ``mpfb_symmetrize_targets`` so that the number reported here is
  the number that tool acts on.

Changes nothing. In particular it never calls ``reapply_macro_details()`` or
``reapply_all_details()``: a character whose numbers and whose shape have
drifted apart is reported as drifted rather than quietly repaired by a tool the
caller believed to be read-only.

**The shape keys are read from ``key_blocks`` directly rather than through
``TargetService.get_target_stack()``**, which excludes any shape key whose
lowercased name *contains* ``"basis"`` - not merely equals it. A user target
called ``basis-nose-widen`` is therefore invisible to ``has_target()``,
``get_target_value()`` and every write MPFB can perform on it. Suppressing it
here as well would hide a real shape key that is really deforming the mesh; so
it is listed, with ``visible_to_targetservice`` saying that MPFB cannot address
it. Every *write* still goes through ``TargetService``, or the read and the
write halves would disagree about what exists.

The answer has two views of the same facts. ``targets`` is one entry per shape
key, which is what ``mpfb_set_targets``' raw ``targets`` list addresses.
``modifiers`` rolls those up into the ``target.json`` categories MPFB's own
sliders manipulate, computed the way ``_get_opposed_modifier_value()`` computes
them - by the shared fragment, so ``mpfb_symmetrize_targets`` cannot read a
category differently - which is the view that round-trips back into
``mpfb_set_targets``' ``modifiers`` list and the view that matches what the
user sees in the panel.
"""

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
TargetService = _MPFB_SERVICES["TargetService"]

MACRO_PREFIX = "$md"
EXPRESSION_PREFIX = "!ex-"

# MPFB's own threshold, from _set_opposed_modifier_value() and prune_shapekeys().
EPSILON = 0.0001


def encoded(name):
    try:
        return str(TargetService.encode_shapekey_name(name))
    except Exception:  # pylint: disable=broad-except
        return str(name)


def decoded(name):
    try:
        return str(TargetService.decode_shapekey_name(name))
    except Exception:  # pylint: disable=broad-except
        return str(name)


def shapekey_values(basemesh):
    """Every shape key on the mesh, in order, as (name, value) pairs.

    Read straight off key_blocks - see this module's docstring for why not
    through TargetService.
    """
    pairs = []
    keys = basemesh.data.shape_keys
    if keys is None or keys.key_blocks is None:
        return pairs
    for block in keys.key_blocks:
        pairs.append((str(block.name), float(block.value)))
    return pairs


def kind_of(shapekey_name, known_to_target_json):
    if shapekey_name.lower() == "basis":
        return "basis"
    if shapekey_name.startswith(MACRO_PREFIX):
        return "macro"
    if shapekey_name.startswith(EXPRESSION_PREFIX):
        return "expression"
    if known_to_target_json:
        return "detail"
    try:
        if TargetService.shapekey_is_target(shapekey_name):
            return "detail"
    except Exception:  # pylint: disable=broad-except
        pass
    return "unknown"


def value_lookup(values):
    """A has_target()/get_target_value() pair over an already-read stack.

    has_target() checks the encoded name as well as the given one, while
    get_target_value() matches the raw name only - so the two are reproduced
    separately rather than collapsed into one helper that would paper over the
    difference.
    """
    by_name = dict(values)

    def present(target_name):
        if not target_name:
            return False
        if target_name in by_name:
            return True
        return encoded(target_name) in by_name

    def value_of(target_name):
        if not target_name:
            return 0.0
        if target_name in by_name:
            return by_name[target_name]
        encoded_name = encoded(target_name)
        if encoded_name in by_name:
            return by_name[encoded_name]
        return 0.0

    return (present, value_of)


def sides_of(category):
    if category.get("has_left_and_right"):
        return ("left", "right")
    return ("unsided",)


def build_modifiers(present, value_of):
    """Every category with a non-zero reading, plus the sided ones that differ."""
    modifiers = []
    asymmetries = []
    for section_name in KNOWN_SECTIONS:
        section = TARGET_SECTIONS[section_name]
        for category in section["categories"]:
            readings = dict()
            for side in sides_of(category):
                readings[side] = modifier_reading(category, side, present, value_of)
            for side in sides_of(category):
                if abs(readings[side]) > EPSILON:
                    modifiers.append({
                        "section": section_name,
                        "category": str(category["name"]),
                        "side": side,
                        "value": round(readings[side], 6),
                        "opposed": category_is_opposed(category),
                    })
            if category.get("has_left_and_right"):
                difference = readings["left"] - readings["right"]
                if abs(difference) > EPSILON:
                    asymmetries.append({
                        "section": section_name,
                        "category": str(category["name"]),
                        "left": round(readings["left"], 6),
                        "right": round(readings["right"], 6),
                        "difference": round(difference, 6),
                    })
    return (modifiers, asymmetries)


requested_name = PARAMS["name"]
include_macro = PARAMS["include_macro"]
include_expressions = PARAMS["include_expressions"]
name_contains = PARAMS["name_contains"]
limit = PARAMS["limit"]
offset = PARAMS["offset"]

needle = name_contains.strip().lower() if name_contains is not None else None

subject_resolved_by = "active" if requested_name is None else "name"
subject = None
message = None

if requested_name is None:
    # The view layer rather than bpy.context.active_object: this code runs in
    # the add-on's execution context, not from a viewport operator.
    subject = bpy.context.view_layer.objects.active
    if subject is None:
        message = ("No object name was given and no object is active in this Blender session. "
                   "Select a MakeHuman object, or call mpfb_list_objects and pass one of its "
                   "names.")
else:
    subject = bpy.data.objects.get(requested_name)
    if subject is None:
        message = ("No object named '" + str(requested_name) + "' exists in this .blend file. "
                   "Call mpfb_list_objects to see what the current scene holds.")

basemesh = None
if subject is not None:
    # Any object in the character's family resolves to the basemesh that owns
    # the shape keys - the caller may well be holding the name of the rig or of
    # a garment, since that is what mpfb_list_objects hands out.
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    if basemesh is None:
        message = ("'" + subject.name + "' has no MakeHuman basemesh among its nearest relatives, "
                   "so it has no target stack. Call mpfb_get_object_info to see what it is "
                   "related to.")

if basemesh is None:
    result = dict(
        found=False,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None,
        has_shapekeys=False,
        targets=[],
        modifiers=[],
        asymmetries=[],
        counts_by_kind=dict(),
        counts_by_section=dict(),
        count=0,
        total_count=0,
        truncated=False,
        offset=offset,
        limit=limit,
        message=message,
    )
else:
    values = shapekey_values(basemesh)
    present, value_of = value_lookup(values)

    entries = []
    for shapekey_name, value in values:
        placement = TARGET_INDEX.get(shapekey_name)
        entry_kind = kind_of(shapekey_name, placement is not None)
        if entry_kind == "basis":
            # Blender's own rest shape, not a target, and never addressable.
            continue
        entries.append({
            "shapekey_name": shapekey_name,
            "decoded_name": decoded(shapekey_name),
            "value": round(value, 6),
            "kind": entry_kind,
            "section": None if placement is None else placement["section"],
            "category": None if placement is None else placement["category"],
            "side": None if placement is None else placement["side"],
            "polarity": None if placement is None else placement["polarity"],
            # True only for a category the bundled index really names: a
            # synthesized user category is a modifier MPFB's panel shows but
            # target.json has never heard of.
            "listed_in_target_json": placement is not None and not placement["synthesized"],
            # False means MPFB itself cannot see this shape key: its
            # get_target_stack() excludes any name *containing* "basis", so
            # every write and every value read through TargetService misses it.
            "visible_to_targetservice": "basis" not in shapekey_name.lower(),
        })

    # Counted over everything on the mesh, before any filter or cap, so a
    # filtered answer still says what it was filtered out of.
    counts_by_kind = dict()
    counts_by_section = dict()
    for entry in entries:
        counts_by_kind[entry["kind"]] = counts_by_kind.get(entry["kind"], 0) + 1
        section_key = entry["section"] or "(none)"
        counts_by_section[section_key] = counts_by_section.get(section_key, 0) + 1

    matched = []
    for entry in entries:
        if entry["kind"] == "macro" and not include_macro:
            continue
        if entry["kind"] == "expression" and not include_expressions:
            continue
        if needle is not None:
            haystacks = [entry["shapekey_name"].lower(), entry["decoded_name"].lower()]
            if not any(needle in haystack for haystack in haystacks):
                continue
        matched.append(entry)

    # Sorted before paging: key_blocks order is insertion order, so two pages of
    # one query would otherwise skip and repeat entries as the stack changes.
    matched.sort(key=lambda entry: (
        entry["kind"], entry["section"] or "", entry["category"] or "",
        entry["shapekey_name"]))

    total_count = len(matched)
    paged = matched[offset:offset + limit]
    count = len(paged)

    modifiers, asymmetries = build_modifiers(present, value_of)

    invisible = [entry["shapekey_name"] for entry in entries
                 if not entry["visible_to_targetservice"]]

    # Built by concatenation rather than the repo's usual .format(): a payload
    # file must contain no empty brace pair anywhere, since that is what a
    # substitution point looks like. tests/test_codegen.py enforces it.
    message_parts = [
        str(total_count) + " shape key(s) matched on basemesh '" + basemesh.name + "', "
        + str(count) + " returned"]
    if total_count > count:
        message_parts.append(" - the rest were not returned, so this is not the whole stack")
    message_parts.append(
        ". 'modifiers' is the same information rolled up into the categories MPFB's own sliders "
        "manipulate, and is what mpfb_set_targets takes; 'targets' entries are addressed by "
        "'shapekey_name'.")
    if not include_macro and counts_by_kind.get("macro"):
        message_parts.append(
            " " + str(counts_by_kind["macro"]) + " macro shape key(s) were left out; pass "
            "include_macro to see them, or call mpfb_get_macro_details.")
    if not include_expressions and counts_by_kind.get("expression"):
        message_parts.append(
            " " + str(counts_by_kind["expression"]) + " expression shape key(s) were left out; "
            "pass include_expressions to see them.")
    if invisible:
        message_parts.append(
            " Note that " + str(len(invisible)) + " shape key(s) contain 'basis' in their name "
            "and are therefore invisible to MPFB itself, which cannot read or change them: "
            + ", ".join(invisible) + ".")

    result = dict(
        found=True,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        has_shapekeys=len(values) > 0,
        targets=paged,
        # Not paged, and deliberately not filtered by name_contains: this is the
        # rollup view, small by construction (only categories with a non-zero
        # reading appear), and it is what a caller writes back.
        modifiers=modifiers,
        modifier_count=len(modifiers),
        asymmetries=asymmetries,
        counts_by_kind=counts_by_kind,
        counts_by_section=counts_by_section,
        count=count,
        total_count=total_count,
        # Always present, and the field to read before concluding a target is
        # not on this character: a capped answer must never look complete.
        truncated=total_count > count,
        offset=offset,
        limit=limit,
        message="".join(message_parts),
    )
