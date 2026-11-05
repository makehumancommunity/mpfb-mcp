"""
``shared/view_layer.py``, called directly.

**The view layer is the user's setting**, so what is asserted here is that it ends every call as it
began: when the work finished, when it raised, around nested exclusion and with an object in two
collections. Blender's ``exclude`` is recursive and remembers what a child was before a parent went, and
the module's stack exists for that memory, so the assertion that matters most reads it the only way it
can be read: by doing what a user would do next, which is including the parent, and looking at the child.

Also here, as a test of Blender rather than of this package: ``hide_set()`` is lost by the exclude
itself. FR 054's scoping saw it in one run of two and could not say whose fault it was.
"""

import bpy
import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import services_or_skip


def _view_layer_module():
    return bridge_module("shared.view_layer")


def _layer(*path):
    found = bpy.context.view_layer.layer_collection
    for name in path:
        found = found.children[name]
    return found


def _in_view_layer(blender_object):
    bpy.context.view_layer.update()
    return blender_object.name in bpy.context.view_layer.objects


@pytest.fixture(name="tree")
def _tree():
    """``Parent`` holding ``Holder`` and ``Sibling``, an object in each, and all put away after."""
    parent = bpy.data.collections.new("BridgeTestParent")
    holder = bpy.data.collections.new("BridgeTestHolder")
    sibling = bpy.data.collections.new("BridgeTestSibling")
    bpy.context.scene.collection.children.link(parent)
    parent.children.link(holder)
    parent.children.link(sibling)
    member = bpy.data.objects.new("BridgeTestMember", None)
    bystander = bpy.data.objects.new("BridgeTestBystander", None)
    holder.objects.link(member)
    sibling.objects.link(bystander)
    active_before = bpy.context.view_layer.active_layer_collection
    yield dict(parent=parent, holder=holder, sibling=sibling, member=member, bystander=bystander)
    bpy.context.view_layer.active_layer_collection = active_before
    for blender_object in list(bpy.data.objects):
        if blender_object.name.startswith("BridgeTest"):
            bpy.data.objects.remove(blender_object)
    for collection in (holder, sibling, parent):
        bpy.data.collections.remove(collection)


def _included(member):
    return _view_layer_module().included(member, lambda: [member])


def test_nothing_is_touched_when_nothing_is_excluded(tree):
    with _included(tree["member"]) as inclusion:
        assert inclusion.names == []
    assert inclusion.moved == []
    assert not _layer("BridgeTestParent").exclude


def test_an_excluded_collection_is_included_for_the_block_and_excluded_again(tree):
    holder = _layer("BridgeTestParent", "BridgeTestHolder")
    holder.exclude = True
    assert not _in_view_layer(tree["member"])
    with _included(tree["member"]) as inclusion:
        assert inclusion.names == ["BridgeTestHolder"]
        assert _in_view_layer(tree["member"])
        tree["member"].select_set(True)
    assert holder.exclude
    assert not _in_view_layer(tree["member"])


def test_it_is_excluded_again_when_the_block_raises(tree):
    holder = _layer("BridgeTestParent", "BridgeTestHolder")
    holder.exclude = True
    with pytest.raises(RuntimeError, match="the work failed"):
        with _included(tree["member"]):
            raise RuntimeError("the work failed")
    assert holder.exclude
    assert not _in_view_layer(tree["member"])


def test_an_excluded_parent_is_included_and_its_other_child_stays_out(tree):
    _layer("BridgeTestParent").exclude = True
    with _included(tree["member"]) as inclusion:
        assert inclusion.names == ["BridgeTestParent", "BridgeTestHolder"]
        assert _in_view_layer(tree["member"])
        assert not _in_view_layer(tree["bystander"]), "only what is needed"
    assert _layer("BridgeTestParent").exclude
    assert not _in_view_layer(tree["member"])
    assert not _in_view_layer(tree["bystander"])


def test_what_a_parent_remembers_of_its_children_survives(tree):
    """A child excluded on its own stays out when the user later includes the parent."""
    _layer("BridgeTestParent", "BridgeTestHolder").exclude = True
    _layer("BridgeTestParent").exclude = True
    with _included(tree["member"]) as inclusion:
        assert inclusion.names == ["BridgeTestParent", "BridgeTestHolder"]
        assert _in_view_layer(tree["member"])
        assert not _in_view_layer(tree["bystander"])
    assert _layer("BridgeTestParent").exclude
    assert _layer("BridgeTestParent", "BridgeTestHolder").exclude

    _layer("BridgeTestParent").exclude = False
    assert _layer("BridgeTestParent", "BridgeTestHolder").exclude, \
        "the holder was excluded on its own before all this, and Blender must still know that"
    assert not _layer("BridgeTestParent", "BridgeTestSibling").exclude, \
        "the sibling was excluded only by its parent, and must come back with it"


def test_an_object_in_two_excluded_collections_needs_only_the_first(tree):
    tree["sibling"].objects.link(tree["member"])
    _layer("BridgeTestParent", "BridgeTestHolder").exclude = True
    _layer("BridgeTestParent", "BridgeTestSibling").exclude = True
    with _included(tree["member"]) as inclusion:
        assert inclusion.names == ["BridgeTestHolder"]
        assert not _in_view_layer(tree["bystander"])
    assert _layer("BridgeTestParent", "BridgeTestHolder").exclude
    assert _layer("BridgeTestParent", "BridgeTestSibling").exclude


def test_an_object_in_one_excluded_and_one_included_collection_needs_nothing(tree):
    tree["sibling"].objects.link(tree["member"])
    _layer("BridgeTestParent", "BridgeTestHolder").exclude = True
    with _included(tree["member"]) as inclusion:
        assert inclusion.names == []


def test_what_the_block_creates_joins_the_anchor_and_is_named(tree):
    member = tree["member"]
    _layer("BridgeTestParent", "BridgeTestHolder").exclude = True
    created = []

    def family():
        return [member] + created

    with _view_layer_module().included(member, family) as inclusion:
        new = bpy.data.objects.new("BridgeTestCreated", None)
        bpy.context.scene.collection.objects.link(new)
        created.append(new)
    assert [collection.name for collection in new.users_collection] == ["BridgeTestHolder"]
    assert inclusion.moved == [{"object": new.name, "collection": "BridgeTestHolder"}]
    assert not _in_view_layer(new), "it went out with the character"


def test_what_the_block_creates_outside_the_family_stays_where_it_is(tree):
    _layer("BridgeTestParent", "BridgeTestHolder").exclude = True
    with _included(tree["member"]) as inclusion:
        widget = bpy.data.objects.new("BridgeTestWidget", None)
        bpy.context.scene.collection.objects.link(widget)
    assert inclusion.moved == []
    assert bpy.context.scene.collection in widget.users_collection


def test_nothing_moves_when_nothing_was_included(tree):
    member = tree["member"]
    created = []
    with _view_layer_module().included(member, lambda: [member] + created) as inclusion:
        new = bpy.data.objects.new("BridgeTestCreated", None)
        bpy.context.scene.collection.objects.link(new)
        created.append(new)
    assert inclusion.moved == []
    assert bpy.context.scene.collection in new.users_collection


def test_the_active_collection_is_put_back(tree):
    view_layer = bpy.context.view_layer
    view_layer.active_layer_collection = _layer("BridgeTestParent", "BridgeTestSibling")
    _layer("BridgeTestParent", "BridgeTestHolder").exclude = True
    with _included(tree["member"]):
        view_layer.active_layer_collection = _layer("BridgeTestParent", "BridgeTestHolder")
    assert view_layer.active_layer_collection.name == "BridgeTestSibling"


def test_the_scene_collection_as_active_is_put_back_too(tree):
    view_layer = bpy.context.view_layer
    view_layer.active_layer_collection = view_layer.layer_collection
    _layer("BridgeTestParent", "BridgeTestHolder").exclude = True
    with _included(tree["member"]):
        view_layer.active_layer_collection = _layer("BridgeTestParent", "BridgeTestHolder")
    assert view_layer.active_layer_collection == view_layer.layer_collection


def test_hide_set_is_lost_by_the_exclude_itself(tree):
    """No tool in sight: this is Blender, and why an excluded object's hide state is not restored."""
    member = tree["member"]
    holder = _layer("BridgeTestParent", "BridgeTestHolder")
    bpy.context.view_layer.update()
    member.hide_set(True)
    assert member.hide_get()
    holder.exclude = True
    bpy.context.view_layer.update()
    holder.exclude = False
    bpy.context.view_layer.update()
    assert not member.hide_get()


# ----------------------------------------------------------------------
# run(), which needs a character for the family walk


@pytest.fixture(name="character")
def _character():
    """A character alone in an excluded collection, and that collection removed afterwards."""
    services_or_skip()
    collection = bpy.data.collections.new("BridgeTestCast")
    bpy.context.scene.collection.children.link(collection)
    with Character() as character:
        basemesh = character.basemesh
        for owner in list(basemesh.users_collection):
            owner.objects.unlink(basemesh)
        collection.objects.link(basemesh)
        yield character, collection
    bpy.data.collections.remove(collection)


def _answer():
    return {"message": "Did it."}


def test_an_ordinary_call_says_nothing_was_included(character):
    answer = _view_layer_module().run(services_or_skip(), character[0].basemesh.name, _answer)
    assert answer["temporarily_included"] == []
    assert answer["objects_moved_to_collection"] == []
    assert answer["message"] == "Did it."


def test_an_included_call_says_so(character):
    the_character, _collection = character
    layer = _layer("BridgeTestCast")
    layer.exclude = True
    answer = _view_layer_module().run(services_or_skip(), the_character.basemesh.name, _answer)
    assert answer["temporarily_included"] == ["BridgeTestCast"]
    assert "'BridgeTestCast'" in answer["message"]
    assert layer.exclude


def test_the_view_layer_is_put_back_when_the_work_raises(character):
    layer = _layer("BridgeTestCast")
    layer.exclude = True

    def failing():
        raise RuntimeError("the work failed")

    with pytest.raises(RuntimeError, match="the work failed"):
        _view_layer_module().run(services_or_skip(), character[0].basemesh.name, failing)
    assert layer.exclude


def test_a_subject_that_resolves_to_nothing_goes_to_the_work(character):
    assert character
    answer = _view_layer_module().run(services_or_skip(), "no-such-object", _answer)
    assert answer["message"] == "Did it.", "saying the subject is missing is the command's job"
    assert answer["temporarily_included"] == []


def test_an_object_in_no_collection_is_refused_and_no_work_is_done(character):
    the_character, collection = character
    collection.objects.unlink(the_character.basemesh)
    ran = []
    answer = _view_layer_module().run(services_or_skip(), the_character.basemesh.name,
                                      lambda: ran.append(True))
    collection.objects.link(the_character.basemesh)
    assert not ran
    assert answer["blocked_by"] == "not_in_view_layer"
    assert answer["performed"] is False
    assert answer["not_in_view_layer"][0]["reason"] == "outside_this_view_layer"
    assert "no collection" in answer["message"]


def test_an_object_in_another_scene_is_refused_naming_its_collection(character):
    the_character, collection = character
    bpy.context.scene.collection.children.unlink(collection)
    other = bpy.data.scenes.new("BridgeTestOtherScene")
    other.collection.children.link(collection)
    try:
        answer = _view_layer_module().run(services_or_skip(), the_character.basemesh.name, _answer,
                                          refused_with=dict(refit_performed=False))
    finally:
        other.collection.children.unlink(collection)
        bpy.data.scenes.remove(other)
        bpy.context.scene.collection.children.link(collection)
    assert answer["blocked_by"] == "not_in_view_layer"
    assert answer["refit_performed"] is False
    assert answer["not_in_view_layer"][0]["collections"] == ["BridgeTestCast"]
    assert "'BridgeTestCast'" in answer["message"]


def test_the_hide_state_of_what_was_in_the_view_layer_is_put_back(character):
    the_character, _collection = character
    basemesh = the_character.basemesh
    basemesh.hide_set(True)

    def showing():
        basemesh.hide_set(False)
        return _answer()

    try:
        _view_layer_module().run(services_or_skip(), basemesh.name, showing)
        assert basemesh.hide_get()
    finally:
        basemesh.hide_set(False)


def test_generating_is_left_with_its_hide_state_too(character):
    the_character, _collection = character
    basemesh = the_character.basemesh

    def hiding():
        basemesh.hide_set(True)
        return _answer()

    try:
        _view_layer_module().run(services_or_skip(), basemesh.name, hiding, generates=True)
        assert basemesh.hide_get(), "generating hides the meta rig on purpose"
    finally:
        basemesh.hide_set(False)
