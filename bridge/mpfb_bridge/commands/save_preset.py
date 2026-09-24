"""
``save_preset``: write the current character to a preset file.

**This is the first thing in this add-on that writes outside the ``.blend``, and
everything unusual here follows from that.** Blender's undo stack does not reach
a file, there is no confirmation channel across the socket, and the caller
cannot see the directory. So: every precondition is settled before
``serialize_to_json_file()`` is called, the absolute path is in the answer
whatever happens, and an existing file is never replaced unless the caller said
so.

**The name is a name and never a path.** The rule is
[`shared/preset_files.py`](../shared/preset_files.py)'s whitelist, shared with
``list_presets``, and mpfb-mcp carries the same rule on its own side of the
socket because a name that becomes a path is a *shape* and is knowable before a
request is built. The copy here is the last statement before ``open()``: a
listening socket is reachable by anything on this machine, not only by a tool
that already checked.

**One command where MPFB has two operators.** ``mpfb.save_new_human_presets``
refuses when the file exists; ``mpfb.overwrite_human_presets`` is reachable only
from a dropdown of presets that do. They differ in nothing else - both call
``serialize_to_json_file(basemesh, file_name, True)`` - and a pair of commands
distinguished only by a precondition is a pair an agent will pick wrongly.
``overwrite`` is that precondition, defaulting to refusing.

**``save_clothes=True`` is passed, and it does nothing.**
``serialize_to_json_string()`` never reads the argument;
``_populate_human_info_with_clothes_info()`` runs unconditionally, so clothes
are always saved and the documented default of ``False`` describes behaviour
that does not exist. ``True`` is passed anyway because both of MPFB's own
operators pass it: the day the argument starts working, this should keep doing
what the panel does rather than suddenly start dropping garments.

**The generated-Rigify warning is deliberately not reproduced.** Both operators
report a ``WARNING`` when ``identify_rig()`` contains ``"generated"``, and the
warning overstates what happens: ``_populate_human_info_with_rig_info()`` infers
the meta rig, falls back to ``rigify.human_toes``, and records *that*. Nothing
fails and nothing is lost except the generated rig itself, which
``generate_rigify_rig`` rebuilds. The answer reports ``rig_identified_as``
beside ``rig_saved_as`` so the substitution is visible on the call where it
happened. This is a
[deliberate divergence from MPFB's UI](../../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it).

**A rig ``identify_rig()`` cannot name is the opposite case and must not be
silent.** ``_populate_human_info_with_rig_info()`` raises ``ValueError("Could
not identify rig type. Custom rigs cannot be serialized.")`` for ``None``,
``"unknown"`` and ``"unkown"`` - MPFB checks both spellings - and that message
is wrong: a custom rig present in user data serializes perfectly well, as
``custom.<name>``. So the condition is checked here, before anything is written,
and refused with the real cause named.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.
"""

# The local binding below is spelled with MPFB's own capitalisation, which is
# what the program this replaced used.
# pylint: disable=invalid-name

__all__ = (
    "PARAMS",
    "SUMMARY",
    "save_preset",
)

import json
import os

from ..log import get_logger
from ..shared import mpfb_surface
from ..shared import preset_files
from ..shared import subject_resolution
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.savepreset")

PARAMS = (
    Param("preset_name", TYPE_STRING, required=True,
          description="The preset's name, never a path. Letters, digits, underscore, hyphen and "
                      "dot only; it becomes <user config>/human.<name>.json."),
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("overwrite", TYPE_BOOLEAN, default=False,
          description="Replace an existing preset of this name. False by default: there is no "
                      "undo for a file across this socket."),
)

SUMMARY = "Save a character as a named preset in MPFB's user config directory."

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
# rather than here. create_human_from_preset reports that as
# deserialization_failed with the objects it left behind. Widening this check
# would be tidier and would make a preset MPFB's own panel writes unwritable
# here, which is the trade specifications/mpfb-integration.md decides the other
# way: follow MPFB, and report where it goes wrong.
UNIDENTIFIED_RIG_TYPES = (None, "unknown", "unkown")

# The keys serialize_to_json_string() writes that are worth reading back, so the
# answer says what was saved rather than only that something was.
BODYPART_KEYS = ("eyes", "eyelashes", "eyebrows", "tongue", "teeth", "hair")


def _contents_summary(path):
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


class _Request:
    """One call's resolved state, so the refusals can be read in one place."""

    __slots__ = ("confdir", "file_path", "name_rejection", "previous_file",
                 "subject", "subject_resolved_by", "subject_message", "basemesh",
                 "armature", "rig_identified_as", "is_human_project")


def _resolve(services, params):
    """Everything that has to be true before a byte is written."""
    request = _Request()
    object_service = services["ObjectService"]

    request.confdir = preset_files.config_directory(services)
    request.file_path = None
    request.name_rejection = preset_files.preset_name_rejection(params["preset_name"])
    if request.name_rejection is None:
        request.file_path = preset_files.preset_path(request.confdir, params["preset_name"])

    request.previous_file = None
    if request.file_path is not None:
        facts = preset_files.file_facts(request.file_path)
        request.previous_file = facts if facts["exists"] else None

    # The same walk MPFB's own save operator makes: the caller may name a
    # garment or the character's rig, and the object actually serialized is
    # reported back rather than the argument echoed. A miss is recorded, not
    # returned, because _refusal() judges the name and the file too and decides
    # which refusal comes first.
    (request.basemesh, request.subject, request.subject_resolved_by,
     request.subject_message) = subject_resolution.resolve_basemesh(
         services, params["name"],
         not_done="nothing was saved",
         not_a_character="there is no character to save")

    # The rig, resolved before anything is written so that an unserializable one
    # is a refusal rather than a ValueError from inside MPFB.
    request.armature = None
    request.rig_identified_as = None
    if request.basemesh is not None:
        request.armature = object_service.find_object_of_type_amongst_nearest_relatives(
            request.basemesh, "Skeleton")
        if request.armature is not None:
            try:
                request.rig_identified_as = services["RigService"].identify_rig(request.armature)
            except Exception:  # pylint: disable=broad-except
                request.rig_identified_as = None

    request.is_human_project = None
    human_properties = mpfb_surface.human_object_properties(services)
    if request.basemesh is not None and human_properties is not None:
        try:
            request.is_human_project = bool(human_properties.get_value(
                "is_human_project", entity_reference=request.basemesh))
        except Exception:  # pylint: disable=broad-except
            request.is_human_project = None
    return request


def _mistaken_for_the_preset(params, request):
    """The miss sentence, plus what a caller who passed the preset as ``name`` needs.

    FR 037 swapped ``name`` in this command rather than retiring it: it was the
    preset and is now the character. A caller still using the old spelling is
    therefore not refused as sending an unknown parameter - they are told no
    object has that name, and this sentence connects the two. Only then: an
    object that exists but belongs to no character is a different mistake.
    """
    if params["name"] is None or request.subject is not None:
        return request.subject_message
    return ("{:s} If '{:s}' is the preset's own name, pass it as preset_name; name is the "
            "character.".format(request.subject_message, str(params["name"])))


def _blocked(params, request, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=request.basemesh is not None,
        ready=False,
        saved=False,
        blocked_by=reason,
        preset_name=params["preset_name"],
        subject_name=None if request.subject is None else request.subject.name,
        subject_resolved_by=request.subject_resolved_by,
        basemesh_name=None if request.basemesh is None else request.basemesh.name,
        config_dir=request.confdir,
        # Always present, on a refusal as much as on a success: the caller
        # cannot see the directory, and "which file would this have been" is the
        # first thing they need in order to fix a name or pass overwrite.
        path=request.file_path,
        overwrote=False,
        previous_file=request.previous_file,
        message=message,
    )
    answer.update(extra)
    return with_performed(answer, False)


def _refusal(services, params, request):  # pylint: disable=too-many-return-statements
    """The first refusal that applies, or ``None``."""
    def blocked(reason, text, **extra):
        return _blocked(params, request, reason, text, **extra)

    if request.basemesh is None:
        return blocked("subject_not_found",
                       _mistaken_for_the_preset(params, request))
    if request.name_rejection is not None:
        # Defence in depth: mpfb-mcp refuses this before a request is built (see
        # mpfbmcp/preset_names.py), so reaching it here means something else
        # spoke to this socket. It is the last statement before a path is
        # assembled.
        return blocked(
            "invalid_name",
            request.name_rejection + " A preset is always human.<name>.json in MPFB's user "
            "config directory, so a name that could become a path is refused rather than "
            "resolved.")
    if request.confdir is None or not os.path.isdir(request.confdir):
        return blocked(
            "config_dir_missing",
            "MPFB's user config directory {!r} does not exist, so there is nowhere to write a "
            "preset. MPFB creates it when it loads, so this means the install is broken rather "
            "than that nothing has been saved yet. Nothing was created here: a command that made "
            "the directory would hide the problem.".format(request.confdir))
    if mpfb_surface.human_object_properties(services) is None:
        return blocked(
            "properties_unreachable",
            "MPFB's HumanObjectProperties could not be read off the HumanService module, so "
            "whether '{:s}' is an MPFB character cannot be established. Call mpfb_get_status; "
            "this usually means a partially initialized install.".format(request.basemesh.name))
    if not request.is_human_project:
        return blocked(
            "not_a_human_project",
            "'{:s}' is not marked as an MPFB human project, so MPFB refuses to serialize it - "
            "serialize_to_json_string() raises for exactly this. An imported or hand-built mesh "
            "tagged as a basemesh looks like this. Only characters created within MPFB "
            "(mpfb_create_human, or MPFB's own panels) can be saved as presets.".format(
                request.basemesh.name),
            is_human_project=False)
    if request.armature is not None and request.rig_identified_as in UNIDENTIFIED_RIG_TYPES:
        return blocked(
            "rig_not_identifiable",
            "The armature '{:s}' is not a rig MPFB recognises (identify_rig said {!r}), and a "
            "preset records the rig by identifier, so nothing was saved. For a custom rig this "
            "means its definition is no longer in your user data directory - MPFB identifies one "
            "by matching bone names against the definitions it can find. MPFB's own message for "
            "this says custom rigs cannot be serialized, which is wrong: a custom rig that is "
            "still installed is saved as custom.<name>. Detach the armature, or reinstall the "
            "rig definition.".format(request.armature.name, request.rig_identified_as),
            rig_object_name=request.armature.name,
            rig_identified_as=request.rig_identified_as)
    if request.previous_file is not None and not params["overwrite"]:
        return blocked(
            "preset_exists",
            "A preset named '{!s}' already exists, written {!s}, and overwrite is false, so "
            "nothing was written. Pass overwrite=true to replace it, or choose another name - "
            "there is no undo for a file across this socket. previous_file carries its size and "
            "age.".format(params["preset_name"], request.previous_file["modified"]))
    return None


def _message_for(params, request, contents, rig_saved_as):
    """What happened, said once, in the order a reader wants it."""
    parts = ["Saved '{:s}' as preset '{!s}' in '{!s}'.".format(
        request.basemesh.name, params["preset_name"], request.file_path)]
    if request.previous_file is not None:
        parts.append(
            " It replaced an existing preset of {!s} bytes written {!s}; that file is gone and "
            "cannot be restored from here.".format(
                request.previous_file["size_bytes"], request.previous_file["modified"]))
    if (request.armature is not None and rig_saved_as
            and rig_saved_as != request.rig_identified_as):
        # The generated-Rigify substitution, reported as the fact it is rather
        # than as the warning MPFB's operators emit.
        parts.append(
            " The rig on this character identifies as '{!s}' and the preset records '{!s}': a "
            "generated Rigify rig is saved as the meta rig it came from, so loading this preset "
            "yields the meta rig and mpfb_generate_rigify_rig finishes it.".format(
                request.rig_identified_as, rig_saved_as))
    if contents is not None and contents["clothes"]:
        parts.append(" {:d} garment(s) were saved with it.".format(len(contents["clothes"])))
    return "".join(parts)


def save_preset(params, resolution):
    """Write one character to one file, having settled everything else first."""
    services = resolution.services
    request = _resolve(services, params)

    refused = _refusal(services, params, request)
    if refused is not None:
        _LOG.debug("save_preset: refused %r for %r", refused["blocked_by"], params["preset_name"])
        return refused

    # Everything above is settled, so this is the first statement that changes
    # anything. MPFB's own path is safe here - serialize_to_json_string() runs
    # to completion before the file is opened - but the ordering is this
    # command's own guarantee rather than an inherited one.
    failure = None
    try:
        # save_clothes=True matches both of MPFB's operators, which pass True
        # positionally. The argument is dead today - see this module's
        # docstring - so this is a bet on it starting to work rather than a
        # behavioural choice.
        services["HumanService"].serialize_to_json_file(
            request.basemesh, request.file_path, save_clothes=True)
    except Exception as error:  # pylint: disable=broad-except
        failure = str(error)

    if failure is not None:
        now = preset_files.file_facts(request.file_path)
        return _blocked(
            params, request, "serialize_failed",
            "MPFB raised while serializing '{:s}': {:s} The file is opened only after the whole "
            "character has been serialized to a string, so an existing preset is normally "
            "untouched; current_file reports what is at that path now.".format(
                request.basemesh.name, failure),
            current_file=now if now["exists"] else None,
            rig_identified_as=request.rig_identified_as)

    written = preset_files.file_facts(request.file_path)
    contents = _contents_summary(request.file_path)
    rig_saved_as = None if contents is None else contents["rig"]

    _LOG.debug("save_preset: wrote %r, %s bytes", request.file_path, written["size_bytes"])

    result = dict(
        found=True,
        ready=True,
        saved=True,
        blocked_by=None,
        preset_name=params["preset_name"],
        subject_name=request.subject.name,
        subject_resolved_by=request.subject_resolved_by,
        basemesh_name=request.basemesh.name,
        config_dir=request.confdir,
        path=request.file_path,
        size_bytes=written["size_bytes"],
        modified=written["modified"],
        overwrote=request.previous_file is not None,
        previous_file=request.previous_file,
        is_human_project=True,
        rig_object_name=None if request.armature is None else request.armature.name,
        rig_identified_as=request.rig_identified_as,
        rig_saved_as=rig_saved_as,
        contents=contents,
        message=_message_for(params, request, contents, rig_saved_as),
    )

    # The verb is "saved". See shared/performed.py.
    return with_performed(result, result["saved"])
