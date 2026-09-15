"""
Payload for ``mpfb_save_preset``: write the current character to a preset file.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag four names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``, ``subject``
  and ``overwrite``.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap, and used here to reach
  ``HumanObjectProperties``, which MPFB keeps at module level rather than on a
  service.
- ``with_performed()`` - from the shared fragment ``performed.py``, named by
  every mutating payload. It stamps the uniform ``performed`` flag onto the
  finished answer, in the last line of this file.

...and a further set from the shared fragment ``preset_files.py``:
``preset_name_rejection()``, ``config_directory()``, ``preset_path()`` and
``file_facts()``.

**This is the first thing in this package that writes outside the ``.blend``,
and everything unusual here follows from that.** Blender's undo stack does not
reach a file, there is no confirmation channel across MCP, and the caller cannot
see the directory. So: every precondition is settled before
``serialize_to_json_file()`` is called, the absolute path is in the answer
whatever happens, and an existing file is never replaced unless the caller said
so.

**One tool where MPFB has two operators.** ``mpfb.save_new_human_presets``
refuses when the file exists; ``mpfb.overwrite_human_presets`` is reachable only
from a dropdown of presets that do. They differ in nothing else - both call
``serialize_to_json_file(basemesh, file_name, True)`` - and a pair of MCP tools
distinguished only by a precondition is a pair an agent will pick wrongly.
``overwrite`` is that precondition, defaulting to refusing.

**``save_clothes=True`` is passed, and it does nothing.**
``serialize_to_json_string()`` never reads the argument;
``_populate_human_info_with_clothes_info()`` runs unconditionally, so clothes
are always saved and the documented default of ``False`` describes behaviour
that does not exist. Confirmed against the running install rather than read off
the source, and filed as a defect. ``True`` is passed anyway because both of
MPFB's own operators pass it: the day the argument starts working, this tool
should keep doing what the panel does rather than suddenly start dropping
garments.

**The generated-Rigify warning is deliberately not reproduced.** Both operators
report a ``WARNING`` when ``identify_rig()`` contains ``"generated"``, and the
warning overstates what happens. ``_populate_human_info_with_rig_info()`` is
built for the case: it infers the meta rig with
``RigService.infer_metarig_type_from_generated()``, falls back to
``rigify.human_toes``, and records *that*. Nothing fails and nothing is lost
except the generated rig itself, which ``mpfb_generate_rigify_rig()`` rebuilds.
A warning on every save of a Rigify character would be noise an agent learns to
ignore; the tool description says it once, and the response reports
``rig_identified_as`` beside ``rig_saved_as`` so the substitution is visible on
the call where it happened. This is a
[deliberate divergence from MPFB's UI](../../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it).

**A rig ``identify_rig()`` cannot name is the opposite case and must not be
silent.** ``_populate_human_info_with_rig_info()`` raises ``ValueError("Could
not identify rig type. Custom rigs cannot be serialized.")`` for ``None``,
``"unknown"`` and ``"unkown"`` - MPFB checks both spellings - and that message
is wrong: a custom rig present in user data serializes perfectly well, as
``custom.<name>``. So the condition is checked here, before anything is written,
and refused with the real cause named. Letting MPFB's text reach an agent would
send it looking for a limitation that does not exist.
"""

import json
import os

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
HumanService = _MPFB_SERVICES["HumanService"]
RigService = _MPFB_SERVICES["RigService"]

# A BlenderConfigSet kept at module level rather than in SERVICES, so it is read
# through the module of a service that has already resolved - never by importing
# an MPFB submodule.
HUMANSERVICE_MODULE = sys.modules[HumanService.__module__]
HumanObjectProperties = getattr(HUMANSERVICE_MODULE, "HumanObjectProperties", None)

# Exactly what _populate_human_info_with_rig_info() treats as unidentifiable,
# reproduced rather than improved on - including the typo, which MPFB checks
# alongside the correct spelling and which is therefore load-bearing somewhere.
# ``None`` is in the list because MPFB's guard has it; FR 019 established that
# identify_rig() cannot actually return it, so it is dead here too and is kept
# only so that this condition and MPFB's stay the same condition.
#
# Note what the list does **not** hold, and what that means. identify_rig() also
# answers "rigify.unknown" and "rigify_generated.unknown", neither of which MPFB
# tests for - so an unrecognised Rigify armature is serialized under a rig
# identifier no adding function can load, and the preset fails at load time
# rather than here. mpfb_create_human_from_preset reports that as
# deserialization_failed with the objects it left behind. Widening this check
# would be tidier and would make a preset MPFB's own panel writes unwritable
# here, which is the trade specifications/mpfb-integration.md decides the other
# way: follow MPFB, and report where it goes wrong.
UNIDENTIFIED_RIG_TYPES = (None, "unknown", "unkown")

# The keys serialize_to_json_string() writes that are worth reading back, so the
# answer says what was saved rather than only that something was. Read from the
# file that was just written, which is the only report that cannot disagree with
# what is on disk.
BODYPART_KEYS = ("eyes", "eyelashes", "eyebrows", "tongue", "teeth", "hair")


def contents_summary(path):
    """What the file that was just written actually holds, in a few fields.

    Parsed from the written file rather than assembled from the scene: the
    response is a claim about a file, and reading it back is the only version of
    that claim that can be wrong in the same way the file is.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            human_info = json.load(handle)
    except Exception:  # pylint: disable=broad-except
        return None
    if not isinstance(human_info, dict):
        return None
    bodyparts = dict()
    for key in BODYPART_KEYS:
        value = human_info.get(key) or None
        if value:
            bodyparts[key] = str(value)
    return dict(
        rig=human_info.get("rig") or None,
        proxy=human_info.get("proxy") or None,
        bodyparts=bodyparts,
        clothes=list(human_info.get("clothes") or []),
        skin_mhmat=human_info.get("skin_mhmat") or None,
        skin_material_type=human_info.get("skin_material_type") or None,
        eyes_material_type=human_info.get("eyes_material_type") or None,
        target_count=len(human_info.get("targets") or []),
        expression_count=len(human_info.get("expressions") or []),
        makeup_count=len(human_info.get("makeup") or []),
    )


def blocked(reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=basemesh is not None,
        ready=False,
        saved=False,
        blocked_by=reason,
        name=requested_name,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        config_dir=confdir,
        # Always present, on a refusal as much as on a success: the caller
        # cannot see the directory, and "which file would this have been" is the
        # first thing they need in order to fix a name or pass overwrite.
        path=file_path,
        overwrote=False,
        previous_file=previous_file,
        message=message,
    )
    answer.update(extra)
    return answer


requested_name = PARAMS["name"]
requested_subject = PARAMS["subject"]
overwrite = PARAMS["overwrite"]

confdir = config_directory()
file_path = None
name_rejection = preset_name_rejection(requested_name)
if name_rejection is None:
    file_path = preset_path(confdir, requested_name)

previous_file = None
if file_path is not None:
    facts = file_facts(file_path)
    previous_file = facts if facts["exists"] else None

subject_resolved_by = "active" if requested_subject is None else "name"
subject = None
subject_message = None

if requested_subject is None:
    # The view layer rather than bpy.context.active_object: this code runs in
    # the add-on's execution context, not from a viewport operator.
    subject = bpy.context.view_layer.objects.active
    if subject is None:
        subject_message = (
            "No object name was given and no object is active in this Blender session, so "
            "nothing was saved. Select a MakeHuman object, or call mpfb_list_objects and pass "
            "one of its names.")
else:
    subject = bpy.data.objects.get(requested_subject)
    if subject is None:
        subject_message = (
            "No object named '" + str(requested_subject) + "' exists in this .blend file, so "
            "nothing was saved. Call mpfb_list_objects to see what the current scene holds.")

basemesh = None
if subject is not None:
    # The same walk MPFB's own save operator makes: the caller may name a
    # garment or the character's rig, and the object actually serialized is
    # reported back rather than the argument echoed.
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    if basemesh is None:
        subject_message = (
            "'" + subject.name + "' has no MakeHuman basemesh among its nearest relatives, so "
            "there is no character to save. Call mpfb_get_object_info to see what this object "
            "is related to.")

# The rig, resolved before anything is written so that an unserializable one is
# a refusal rather than a ValueError from inside MPFB.
armature = None
rig_identified_as = None
if basemesh is not None:
    armature = ObjectService.find_object_of_type_amongst_nearest_relatives(basemesh, "Skeleton")
    if armature is not None:
        try:
            rig_identified_as = RigService.identify_rig(armature)
        except Exception:  # pylint: disable=broad-except
            rig_identified_as = None

is_human_project = None
if basemesh is not None and HumanObjectProperties is not None:
    try:
        is_human_project = bool(HumanObjectProperties.get_value(
            "is_human_project", entity_reference=basemesh))
    except Exception:  # pylint: disable=broad-except
        is_human_project = None

if basemesh is None:
    result = blocked("subject_not_found", subject_message)
elif name_rejection is not None:
    # Defence in depth: the tool module refuses this before the program is built
    # (see mpfbmcp/preset_names.py), so reaching it here means something
    # bypassed the tool. It is the last statement before a path is assembled.
    result = blocked(
        "invalid_name",
        name_rejection + " A preset is always human.<name>.json in MPFB's user config "
        "directory, so a name that could become a path is refused rather than resolved.")
elif confdir is None or not os.path.isdir(confdir):
    result = blocked(
        "config_dir_missing",
        "MPFB's user config directory " + repr(confdir) + " does not exist, so there is "
        "nowhere to write a preset. MPFB creates it when it loads, so this means the install "
        "is broken rather than that nothing has been saved yet. Nothing was created here: a "
        "tool that made the directory would hide the problem.")
elif HumanObjectProperties is None:
    result = blocked(
        "properties_unreachable",
        "MPFB's HumanObjectProperties could not be read off " + str(HUMANSERVICE_MODULE.__name__)
        + ", so whether '" + basemesh.name + "' is an MPFB character cannot be established. "
        "Call mpfb_get_status; this usually means a partially initialized install.")
elif not is_human_project:
    result = blocked(
        "not_a_human_project",
        "'" + basemesh.name + "' is not marked as an MPFB human project, so MPFB refuses to "
        "serialize it - serialize_to_json_string() raises for exactly this. An imported or "
        "hand-built mesh tagged as a basemesh looks like this. Only characters created within "
        "MPFB (mpfb_create_human, or MPFB's own panels) can be saved as presets.",
        is_human_project=False)
elif armature is not None and rig_identified_as in UNIDENTIFIED_RIG_TYPES:
    result = blocked(
        "rig_not_identifiable",
        "The armature '" + armature.name + "' is not a rig MPFB recognises (identify_rig said "
        + repr(rig_identified_as) + "), and a preset records the rig by identifier, so nothing "
        "was saved. For a custom rig this means its definition is no longer in your user data "
        "directory - MPFB identifies one by matching bone names against the definitions it can "
        "find. MPFB's own message for this says custom rigs cannot be serialized, which is "
        "wrong: a custom rig that is still installed is saved as custom.<name>. Detach the "
        "armature, or reinstall the rig definition.",
        rig_name=armature.name,
        rig_identified_as=rig_identified_as)
elif previous_file is not None and not overwrite:
    result = blocked(
        "preset_exists",
        "A preset named '" + str(requested_name) + "' already exists, written "
        + str(previous_file["modified"]) + ", and overwrite is false, so nothing was written. "
        "Pass overwrite=true to replace it, or choose another name - there is no undo for a "
        "file across this socket. previous_file carries its size and age.")
else:
    # Everything above is settled, so this is the first statement that changes
    # anything. MPFB's own path is safe here - serialize_to_json_string() runs
    # to completion before the file is opened - but the ordering is this
    # payload's own guarantee rather than an inherited one.
    failure = None
    try:
        # save_clothes=True matches both of MPFB's operators, which pass True
        # positionally. The argument is dead today - see this module's docstring
        # and the defect report - so this is a bet on it starting to work rather
        # than a behavioural choice.
        HumanService.serialize_to_json_file(basemesh, file_path, save_clothes=True)
    except Exception as error:  # pylint: disable=broad-except
        failure = str(error)

    if failure is not None:
        now = file_facts(file_path)
        result = blocked(
            "serialize_failed",
            "MPFB raised while serializing '" + basemesh.name + "': " + failure
            + " The file is opened only after the whole character has been serialized to a "
              "string, so an existing preset is normally untouched; current_file reports what "
              "is at that path now.",
            current_file=now if now["exists"] else None,
            rig_identified_as=rig_identified_as)
    else:
        written = file_facts(file_path)
        contents = contents_summary(file_path)
        rig_saved_as = None if contents is None else contents["rig"]

        message_parts = [
            "Saved '" + basemesh.name + "' as preset '" + str(requested_name) + "' in '"
            + str(file_path) + "'."]
        if previous_file is not None:
            message_parts.append(
                " It replaced an existing preset of " + str(previous_file["size_bytes"])
                + " bytes written " + str(previous_file["modified"])
                + "; that file is gone and cannot be restored from here.")
        if armature is not None and rig_saved_as and rig_saved_as != rig_identified_as:
            # The generated-Rigify substitution, reported as the fact it is
            # rather than as the warning MPFB's operators emit.
            message_parts.append(
                " The rig on this character identifies as '" + str(rig_identified_as)
                + "' and the preset records '" + str(rig_saved_as)
                + "': a generated Rigify rig is saved as the meta rig it came from, so loading "
                  "this preset yields the meta rig and mpfb_generate_rigify_rig finishes it.")
        if contents is not None and contents["clothes"]:
            message_parts.append(
                " " + str(len(contents["clothes"])) + " garment(s) were saved with it.")

        result = dict(
            found=True,
            ready=True,
            saved=True,
            blocked_by=None,
            name=requested_name,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            config_dir=confdir,
            path=file_path,
            size_bytes=written["size_bytes"],
            modified=written["modified"],
            overwrote=previous_file is not None,
            previous_file=previous_file,
            is_human_project=True,
            rig_name=None if armature is None else armature.name,
            rig_identified_as=rig_identified_as,
            rig_saved_as=rig_saved_as,
            contents=contents,
            message="".join(message_parts),
        )


# The verb is "saved". See codegen/shared/performed.py.
result = with_performed(result, result.get("saved", False))
