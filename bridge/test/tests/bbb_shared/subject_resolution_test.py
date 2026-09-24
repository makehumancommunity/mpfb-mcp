"""
``shared/subject_resolution.py``, called directly.

Eighteen commands resolve their subject through this module, and
``eee_composite/subject_resolution_test.py`` checks that they all agree. This
module checks what they agree *on*: the three sentences, where each command's
phrases go in them, and the family walk. The subject step needs ``bpy`` and no
MPFB, so its tests run in a Blender with no MPFB at all; the basemesh step asks
MPFB and skips without it.

One property is asserted here because no command's test could see it:
**``resolved_by`` is returned on a miss too**, since a command reports it in
the answer that says nothing was found.
"""

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import linked_plain_object
from .._fixtures import nothing_active
from .._fixtures import services_or_skip
from .._fixtures import typed_child


def _module():
    return bridge_module("shared.subject_resolution")


def _removed(blender_object):
    import bpy  # pylint: disable=import-outside-toplevel
    bpy.data.objects.remove(blender_object, do_unlink=True)


def test_nothing_active_is_a_miss_resolved_by_active():
    with nothing_active():
        subject, resolved_by, message = _module().resolve_subject(None)
    assert subject is None
    assert resolved_by == "active"
    assert message == ("No object name was given and no object is active in this Blender "
                       "session. Select a MakeHuman object, or call mpfb_list_objects and pass "
                       "one of its names.")


def test_the_active_object_is_the_view_layers():
    import bpy  # pylint: disable=import-outside-toplevel
    plain = linked_plain_object("BridgeTestActiveSubject")
    try:
        with nothing_active():
            bpy.context.view_layer.objects.active = plain
            subject, resolved_by, message = _module().resolve_subject(None)
        assert subject == plain
        assert resolved_by == "active"
        assert message is None
    finally:
        _removed(plain)


def test_what_did_not_happen_goes_into_both_subject_misses():
    with nothing_active():
        _subject, _by, active_miss = _module().resolve_subject(
            None, not_done="nothing was changed")
    _subject, _by, name_miss = _module().resolve_subject(
        "BridgeTestNoSuchObject", not_done="nothing was changed")
    assert "in this Blender session, so nothing was changed. Select" in active_miss
    assert "in this .blend file, so nothing was changed. Call" in name_miss


def test_select_says_what_the_caller_is_told_to_select():
    with nothing_active():
        _subject, _by, message = _module().resolve_subject(None, select="an object")
    assert "Select an object, or call mpfb_list_objects" in message


def test_a_name_is_looked_up_in_the_file_not_the_scene():
    import bpy  # pylint: disable=import-outside-toplevel
    orphan = bpy.data.objects.new("BridgeTestOutsideScene", None)
    try:
        subject, resolved_by, message = _module().resolve_subject("BridgeTestOutsideScene")
        assert subject == orphan, "an object in no scene is still a subject"
        assert resolved_by == "name"
        assert message is None
    finally:
        _removed(orphan)


def test_an_unknown_name_is_a_miss_resolved_by_name():
    subject, resolved_by, message = _module().resolve_subject("BridgeTestNoSuchObject")
    assert subject is None
    assert resolved_by == "name"
    assert message == ("No object named 'BridgeTestNoSuchObject' exists in this .blend file. "
                       "Call mpfb_list_objects to see what the current scene holds.")


def test_any_object_in_the_family_resolves_to_the_basemesh():
    services = services_or_skip()
    with Character() as character:
        garment = typed_child(services, character.basemesh, "BridgeTestSubjectShirt", "Clothes")
        for name in (character.basemesh.name, garment.name):
            basemesh, subject, resolved_by, message = _module().resolve_basemesh(
                services, name, not_a_character="unused")
            assert basemesh == character.basemesh
            assert subject.name == name
            assert resolved_by == "name"
            assert message is None


def test_an_object_with_no_basemesh_is_returned_with_the_sentence():
    services = services_or_skip()
    plain = linked_plain_object("BridgeTestNoBasemesh")
    try:
        basemesh, subject, resolved_by, message = _module().resolve_basemesh(
            services, plain.name, not_a_character="there is nothing to test",
            not_done="nothing was tested")
        assert basemesh is None
        assert subject == plain, "the subject is returned, so the command can name it"
        assert resolved_by == "name"
        assert message == ("'BridgeTestNoBasemesh' has no MakeHuman basemesh among its nearest "
                           "relatives, so there is nothing to test. Call mpfb_get_object_info "
                           "to see what it is related to.")
    finally:
        _removed(plain)


def test_a_subject_miss_stops_before_the_family_walk():
    services = services_or_skip()
    basemesh, subject, resolved_by, message = _module().resolve_basemesh(
        services, "BridgeTestNoSuchObject", not_a_character="unused",
        not_done="nothing was tested")
    assert (basemesh, subject, resolved_by) == (None, None, "name")
    assert message.startswith(
        "No object named 'BridgeTestNoSuchObject' exists in this .blend file, so nothing was "
        "tested.")
