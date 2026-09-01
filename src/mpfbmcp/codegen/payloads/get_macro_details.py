"""
Payload for ``mpfb_get_macro_details``: a character's phenotype, as stored.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``, which is None
  when the caller wants whatever object is currently active.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap.

The subject may be any object in the character's family; the basemesh is
resolved from it the way MPFB's own panels do, and the answer names the object
the values were actually read from rather than echoing the argument. Failing to
resolve one is a successful answer, not an error.

Values are read through ``TargetService`` rather than off the properties by
hand, so that the shape of the dict is MPFB's and stays MPFB's. The property set
is reached here only for ``is_human_project``, which ``TargetService`` has no
accessor for.

Everything below only reads. Nothing is selected, activated or recalculated -
in particular ``reapply_macro_details()`` is *not* called, so a character whose
properties and shape have drifted apart is reported as drifted rather than
quietly repaired by a tool the caller believed to be read-only.
"""

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
TargetService = _MPFB_SERVICES["TargetService"]
HumanService = _MPFB_SERVICES["HumanService"]

# HumanObjectProperties is a BlenderConfigSet living on humanservice.py's module
# rather than a service in SERVICES, so it is reached through the module of a
# service that already imported it - never by importing an MPFB submodule, some
# of which create directories on import.
HUMANSERVICE_MODULE = sys.modules[HumanService.__module__]
HumanObjectProperties = getattr(HUMANSERVICE_MODULE, "HumanObjectProperties", None)

RACE_NAMES = ("asian", "caucasian", "african")


def as_float(value):
    # Blender hands back its own float type for a FloatProperty. It survives
    # json.dumps, but coercing here keeps the response's contract - a number,
    # never a Blender object - true whatever MPFB stores in future.
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def macro_details_of(basemesh):
    """The nested dict MPFB itself uses, with every value coerced to a float."""
    raw = TargetService.get_macro_info_dict_from_basemesh(basemesh)
    details = dict()
    for key in raw:
        if key == "race":
            details["race"] = dict(
                (race_name, as_float(raw["race"].get(race_name)))
                for race_name in raw["race"]
            )
        else:
            details[key] = as_float(raw[key])
    return details


def race_sum_of(macro_details):
    total = 0.0
    for race_name in RACE_NAMES:
        weight = macro_details.get("race", dict()).get(race_name)
        if weight is not None:
            total += weight
    return round(total, 6)


def target_stack_entries(macro_details):
    """What the current values mean in target terms, named both ways.

    calculate_target_stack_from_macro_info_dict() answers with file fragments
    such as "macrodetails/caucasian-female-young". The shape key MPFB builds
    from one is the encoded "$md-$ca-$fe-$yn", and the two are reported side by
    side precisely so that neither is mistaken for an address a tool accepts:
    a macro target is reached by moving a slider, never by name.
    """
    entries = []
    for component in TargetService.calculate_target_stack_from_macro_info_dict(macro_details):
        fragment = str(component[0])
        entries.append(dict(
            target_fragment=fragment,
            shapekey_name=str(TargetService.macrodetail_filename_to_shapekey_name(
                fragment, encode_name=True)),
            weight=as_float(component[1]),
        ))
    return entries


def is_human_project_of(basemesh):
    if HumanObjectProperties is None:
        return None
    return bool(HumanObjectProperties.get_value("is_human_project", entity_reference=basemesh))


requested_name = PARAMS["name"]
subject_resolved_by = "active" if requested_name is None else "name"
subject = None
message = None

if requested_name is None:
    # The view layer rather than bpy.context.active_object: this code runs in
    # the add-on's execution context, not from a viewport operator. It is None
    # whenever nothing is active, which is an answer, not a crash.
    subject = bpy.context.view_layer.objects.active
    if subject is None:
        message = ("No object name was given and no object is active in this Blender session. "
                   "Select a MakeHuman object, or call mpfb_list_objects and pass one of its "
                   "names.")
else:
    # bpy.data.objects rather than the scene: object names are unique across the
    # whole .blend, and an object outside the current scene still has readable
    # macro details.
    subject = bpy.data.objects.get(requested_name)
    if subject is None:
        message = ("No object named '" + str(requested_name) + "' exists in this .blend file. "
                   "Call mpfb_list_objects to see what the current scene holds.")

basemesh = None
if subject is not None:
    # The same call MPFB's own macro panel makes, which is what lets the caller
    # pass the name of the rig or of a shirt - the names mpfb_list_objects hands
    # out - rather than having to know which object owns the properties.
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    if basemesh is None:
        message = ("'" + subject.name + "' has no MakeHuman basemesh among its nearest relatives, "
                   "so it is not part of a character with macro details. Call "
                   "mpfb_get_object_info to see what it is related to.")

if basemesh is None:
    result = dict(
        found=False,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None,
        message=message,
    )
else:
    macro_details = macro_details_of(basemesh)
    race_sum = race_sum_of(macro_details)
    stack = target_stack_entries(macro_details)
    # Read *undecoded*, so that these names are the ones really on the mesh and
    # are the same vocabulary as the stack's ``shapekey_name`` above. Decoding
    # them here made the two lists the docstring tells a caller to compare
    # incomparable: every macro shape key is stored under an encoded name like
    # ``$md-$as-$fe-$yn``, so a decoded listing agreed with the stack on nothing
    # and the comparison reported drift on a perfectly healthy character.
    current_macro_shapekeys = [
        str(name) for name in TargetService.get_current_macro_targets(basemesh, decode_names=False)
    ]
    current_macro_shapekeys_decoded = [
        str(TargetService.decode_shapekey_name(name)) for name in current_macro_shapekeys
    ]
    has_shapekeys = bool(TargetService.has_any_shapekey(basemesh))

    # Built by concatenation rather than the repo's usual .format(): a payload
    # file must contain no empty brace pair anywhere, since that is what a
    # substitution point looks like, and nothing is ever substituted into a
    # payload. tests/test_codegen.py enforces it.
    message_parts = ["Read macro details from basemesh '" + basemesh.name + "'."]
    if not has_shapekeys:
        message_parts.append(
            " This mesh carries macro properties but has no shape keys at all, so the values "
            "below describe nothing: it was tagged as a basemesh rather than built by MPFB.")
    elif len(stack) != len(current_macro_shapekeys):
        # Not a proof of drift - the two lists can differ in content at equal
        # length - but the cheap half of the check, and the half worth saying
        # out loud, since the caller can compare the lists themselves.
        message_parts.append(
            " The macro targets these values imply and the macro shape keys actually on the mesh "
            "differ in number, so the character's properties and its shape have drifted apart. "
            "Calling mpfb_set_macro_details repairs that.")
    if abs(race_sum - 1.0) > 0.001:
        message_parts.append(
            " The three race weights sum to " + str(race_sum) + " rather than 1.0. That is legal "
            "in MPFB, which treats them as independent, but it scales the phenotype.")

    result = dict(
        found=True,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        basemesh_in_current_scene=basemesh.name in bpy.context.scene.objects,
        is_human_project=is_human_project_of(basemesh),
        has_shapekeys=has_shapekeys,
        macro_details=macro_details,
        default_macro_details=TargetService.get_default_macro_info_dict(),
        race_sum=race_sum,
        race_normalized=abs(race_sum - 1.0) <= 0.001,
        macro_target_stack=stack,
        macro_target_count=len(stack),
        current_macro_shapekeys=current_macro_shapekeys,
        current_macro_shapekeys_decoded=current_macro_shapekeys_decoded,
        message="".join(message_parts),
    )
