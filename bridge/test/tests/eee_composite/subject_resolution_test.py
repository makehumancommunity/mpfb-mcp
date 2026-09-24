"""
All eighteen commands that take a subject, asked about the same three misses.

The claim is about eighteen commands at once, which is why it is here: every
command that takes a subject resolves it the same way, because all of them go
through ``shared/subject_resolution.py``
([FR 036](../../../../feature-requests/done/036-subject-resolver-and-duplication/README.md)).
Before that request there were sixteen local copies, and only seven of the
eighteen commands tested even one miss. This test is what keeps the resolver
shared once the reason for sharing it has been forgotten: a command that grew a
resolver of its own again would still pass its own module, and fail here.

The three misses are the three sentences:

- **nothing active**, a state no command can make, so the fixture makes it;
- **a name that does not exist** anywhere in the file;
- **a plain object with no basemesh** among its relatives. ``get_object_info``
  and ``generate_rigify_rig`` stop at the subject, so for them this is not a
  miss at all, and that is asserted too.

For each, every command must report the same ``found``, subject name and
``subject_resolved_by``, and a message that begins with the shared sentence.
Every *mutating* command - the ones whose answer carries ``performed`` - must
also refuse with ``blocked_by: "subject_not_found"`` and ``performed: false``:
five of the fourteen used to answer with no slug at all
([FR 038](../../../../feature-requests/done/038-subject-not-found-everywhere/README.md)).
What follows the shared part is each command's own, and is deliberately not
compared.

**Nothing may be written, even if a resolver regressed.** The two save
commands would write outside the ``.blend`` if one of these misses were ever
resolved to a character, so they run with MPFB's user directories redirected
into ``tmp_path``, per the rule in ``ddd_mutating/__init__.py``.
"""

import os

from .. import dynamic_import
from .._fixtures import linked_plain_object
from .._fixtures import nothing_active
from .._fixtures import redirected_locations
from .._fixtures import result
from .._fixtures import services_or_skip

CUBE = "BridgeTestSubjectCube"
NO_SUCH = "BridgeTestSubjectNoSuchObject"

# The commands that stop at the subject rather than going on to a basemesh.
SUBJECT_ONLY = ("get_object_info", "generate_rigify_rig")


def _calls(subject):
    """The eighteen commands, each with the least that passes its parameter contract."""
    return {
        "get_object_info": dict(name=subject),
        "get_macro_details": dict(name=subject),
        "get_character_summary": dict(name=subject),
        "get_target_stack": dict(name=subject),
        "get_face_units": dict(name=subject),
        "get_expression": dict(name=subject),
        "set_macro_details": dict(name=subject, changes=[
            dict(argument="gender", property="gender", value=0.4)]),
        "refit_human": dict(name=subject),
        "set_targets": dict(name=subject, modifiers=[
            dict(section="nose", category="unused", side="unsided", value=0.2)]),
        "symmetrize_targets": dict(name=subject, direction="left_to_right", dry_run=True),
        "set_face_units": dict(name=subject, face_units=[dict(face_unit="jawOpen",
                                                              value=0.3)]),
        "apply_expressions": dict(name=subject, expressions=[]),
        "save_expression": dict(expression_name="bridge_test_never_written", name=subject),
        "save_preset": dict(preset_name="bridge_test_never_written", name=subject),
        "add_rig": dict(name=subject, identifier="default"),
        "generate_rigify_rig": dict(name=subject),
        "add_asset": dict(name=subject, fragment="none/none.mhclo", object_type="Clothes"),
        "set_skin": dict(name=subject),
    }


def _answers(tmp_path, subject):
    services = services_or_skip()
    with redirected_locations(services, user_config=str(tmp_path / "config"),
                              user_data=str(tmp_path / "data")):
        answers = {command: result(command, params)
                   for command, params in _calls(subject).items()}
    assert not os.path.exists(tmp_path / "config") or not os.listdir(tmp_path / "config")
    assert not os.path.exists(tmp_path / "data" / "expressions") \
        or not os.listdir(tmp_path / "data" / "expressions")
    return answers


def _subject_name(command, answer):
    return answer["name"] if command == "get_object_info" else answer["subject_name"]


def _refused_if_mutating(command, answer):
    """A mutating command's miss carries the slug a caller branches on."""
    if "performed" not in answer:
        return
    assert answer.get("blocked_by") == "subject_not_found", (command, answer.get("blocked_by"))
    assert answer["performed"] is False, command


def _resolved_by(command, answer):  # pylint: disable=unused-argument
    # One key in all eighteen since FR 037; get_object_info said resolved_from.
    return answer["subject_resolved_by"]


def test_all_eighteen_are_covered():
    """Every command that takes a subject is in :func:`_calls`, and nothing else is.

    A subject is an optional ``name`` - omitted, it is the active object. A
    required ``name`` names something else, an asset. Until FR 037 the two save
    commands took theirs as ``subject``, because their ``name`` was the file's.
    """
    commands = dynamic_import("commands", "COMMANDS")
    taking_a_subject = set(
        command_name for command_name, command in commands.items()
        if any(param.name == "name" and param.nullable for param in command.params))
    assert taking_a_subject == set(_calls(None))


def test_nothing_active(tmp_path):
    """The first sentence, and every command resolved by "active"."""
    with nothing_active():
        answers = _answers(tmp_path, None)
    for command, answer in answers.items():
        assert answer["found"] is False, command
        _refused_if_mutating(command, answer)
        assert _subject_name(command, answer) is None, command
        assert _resolved_by(command, answer) == "active", command
        assert answer["message"].startswith(
            "No object name was given and no object is active in this Blender session"), \
            (command, answer["message"])
        assert answer["message"].endswith(
            ", or call mpfb_list_objects and pass one of its names."), \
            (command, answer["message"])


# The one addition two commands make to the shared second sentence. In the save
# commands FR 037 changed what ``name`` means - it was the file and is now the
# character - so a name that resolves to nothing may be the file's, passed under
# the old spelling, and the sentence says where that goes instead.
_OLD_SPELLING = {
    "save_preset": " If '{:s}' is the preset's own name, pass it as preset_name; name is the "
                   "character.",
    "save_expression": " If '{:s}' is the expression's own name, pass it as expression_name; "
                       "name is the character.",
}


def test_a_name_that_does_not_exist(tmp_path):
    """The second sentence, and every command resolved by "name"."""
    answers = _answers(tmp_path, NO_SUCH)
    for command, answer in answers.items():
        assert answer["found"] is False, command
        _refused_if_mutating(command, answer)
        assert _subject_name(command, answer) is None, command
        assert _resolved_by(command, answer) == "name", command
        message = answer["message"]
        if command in _OLD_SPELLING:
            suffix = _OLD_SPELLING[command].format(NO_SUCH)
            assert message.endswith(suffix), (command, message)
            message = message[:-len(suffix)]
        assert message.startswith(
            "No object named '{:s}' exists in this .blend file".format(NO_SUCH)), \
            (command, message)
        assert message.endswith(
            "Call mpfb_list_objects to see what the current scene holds."), \
            (command, message)


def test_an_object_with_no_basemesh(tmp_path):
    """The third sentence from sixteen commands, and a found subject from two."""
    import bpy  # pylint: disable=import-outside-toplevel
    cube = linked_plain_object(CUBE)
    try:
        answers = _answers(tmp_path, CUBE)
    finally:
        bpy.data.objects.remove(cube, do_unlink=True)
    for command, answer in answers.items():
        assert _subject_name(command, answer) == CUBE, command
        assert _resolved_by(command, answer) == "name", command
        if command in SUBJECT_ONLY:
            assert answer["found"] is True, \
                "{:s} stops at the subject, and the cube is one".format(command)
            continue
        assert answer["found"] is False, command
        _refused_if_mutating(command, answer)
        assert answer["basemesh_name"] is None, command
        assert answer["message"].startswith(
            "'{:s}' has no MakeHuman basemesh among its nearest relatives, so ".format(CUBE)), \
            (command, answer["message"])
        assert answer["message"].endswith(
            ". Call mpfb_get_object_info to see what it is related to."), \
            (command, answer["message"])
