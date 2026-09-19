"""
What a bridge test needs before it can ask a command anything.

Not a test module - the name has no ``_test`` suffix, so pytest does not collect
it. It holds the four things every command's test module needs and none of them
should own:

- **dispatching a request**, through ``command_server.dispatch()`` rather than
  straight to a handler, because that is what a caller gets: the parameter
  contract, the ``requires_mpfb`` precondition and the handler, in that order;
- **MPFB, or a skip that says why** - this suite runs against whatever Blender
  the developer has, which may have no MPFB in it at all, and a test that
  silently passed there would be worse than no test;
- **a character to look at**, built with ``HumanService.create_human()`` and
  removed however the test ends, which is MPFB's own arrangement in
  ``mpfb2/test/tests/eee_ui/_helpers/scene_fixtures.py``;
- **a deterministic asset tree**, built by the test and pointed at through
  MPFB's own ``LocationService``, because a suite whose result depends on which
  asset packs a machine happens to have is a suite that cannot fail usefully.

**The trees here are moved from ``tests/blender_stubs.py`` rather than
reinvented.** That module already builds exactly these shapes - a rig tree with
a weights file that belongs to a different rig, an asset library with two roots
holding the same ``fedora.mhclo``, a config directory of presets MPFB's own
match accepts and three near misses it refuses. What changes on this side of
the socket is that MPFB really walks them instead of a stub reporting what it
would have found.

**How a tree is pointed at.** ``LocationService`` computes its directories once,
in its constructor, from a preference and from where the add-on is installed;
there is no setter, and re-reading the preference would mean re-registering
MPFB. So :func:`redirected_locations` assigns the private fields on the service
instance and puts them back afterwards. That is a reach into MPFB's internals
and it is the narrow kind: it changes no behaviour, it is undone in a
``finally``, and the alternative - asking the developer to install fixture
assets into their own MPFB - is how a suite becomes unrunnable.
"""

__all__ = (
    "Character",
    "answer",
    "dispatch",
    "linked_plain_object",
    "only_these_data_roots",
    "redirected_locations",
    "resolution_module",
    "result",
    "services_or_skip",
    "typed_child",
    "supplied_resolution",
    "write",
)

import contextlib
import os
import sys

import bpy
import pytest

from . import bridge_module
from . import dynamic_import


def services_or_skip():
    """MPFB's services, or skip this test saying why it could not run."""
    resolution = dynamic_import("mpfb_resolution", "resolve")()
    if not resolution.is_ok:
        pytest.skip("MPFB is {:s} in this Blender: {:s}".format(
            resolution.state, resolution.message))
    return resolution.services


def resolution_module():
    """The add-on's ``mpfb_resolution`` module, for a test that replaces its scan."""
    return bridge_module("mpfb_resolution")


@contextlib.contextmanager
def supplied_resolution(state):
    """Run the block with MPFB resolving to ``state``, whatever this Blender has.

    Supplied rather than waited for: a developer's Blender very likely has a
    perfectly good MPFB in it, and the states worth testing are the other two.
    """
    module = resolution_module()
    resolution_class = dynamic_import("mpfb_resolution", "Resolution")
    original = module.resolve
    module.resolve = lambda: resolution_class(state, None, None, [])
    try:
        yield
    finally:
        module.resolve = original


def dispatch(command, params=None):
    """Dispatch one request and return its envelope.

    The dispatcher answers out of the table it was *started* with, so the server
    is started on an OS-assigned port - port 0, so this cannot collide with a
    bridge the developer happens to be running on 9877.
    """
    commands = dynamic_import("commands", "COMMANDS")
    command_server = bridge_module("command_server")
    if command_server.is_running():
        command_server.stop()
    command_server.start("127.0.0.1", 0, commands)
    try:
        request = {"command": command}
        if params is not None:
            request["params"] = params
        return command_server.dispatch(request)
    finally:
        command_server.stop()


# Kept under both names: `answer` reads better where the envelope is the
# subject, `dispatch` where the request is.
answer = dispatch


def result(command, params=None):
    """The ``result`` of one successful dispatch, or a failure naming the envelope."""
    envelope = dispatch(command, params)
    assert envelope["status"] == "ok", \
        "{:s} should have succeeded, got {!r}".format(command, envelope)
    return envelope["result"]


class Character:
    """One MPFB character, deleted again however the test ends.

    MPFB's own fixtures record the object names before the call and remove
    whatever is new, rather than tracking what ``create_human()`` returned: a
    character is several objects and only the basemesh comes back.
    """

    def __init__(self, **keywords):
        self.basemesh = None
        self.keywords = keywords
        self._before = None

    def __enter__(self):
        services = services_or_skip()
        self._before = set(blender_object.name for blender_object in bpy.data.objects)
        self.basemesh = services["HumanService"].create_human(**self.keywords)
        assert self.basemesh is not None, "HumanService.create_human() produced nothing"
        return self

    def __exit__(self, *args):
        for blender_object in list(bpy.data.objects):
            if blender_object.name not in self._before:
                bpy.data.objects.remove(blender_object, do_unlink=True)


def linked_plain_object(name):
    """An ordinary Blender object in the scene, carrying no MPFB type."""
    plain = bpy.data.objects.new(name, bpy.data.meshes.new(name + "Mesh"))
    bpy.context.scene.collection.objects.link(plain)
    return plain


def typed_child(services, parent, name, object_type):
    """One MPFB-typed object parented to another, for a family to be walked.

    ``create_human()`` builds a character of **one** object: no rig, no clothes,
    nothing related. So a test about the relationship walk has to make a
    relative, and the two ways of doing that are equipping a real asset - which
    is a mutating tool's territory and stage 4's - or writing MPFB's own
    ``object_type`` property, which is exactly what MPFB does when it equips
    one. This is the second. The object is a bare mesh and is not pretending to
    be a working garment; what it is for is being *found*.
    """
    objectservice_module = sys.modules[services["ObjectService"].__module__]
    general_properties = getattr(objectservice_module, "GeneralObjectProperties", None)
    assert general_properties is not None, \
        "MPFB no longer publishes GeneralObjectProperties, so a relative cannot be made"

    child = linked_plain_object(name)
    child.parent = parent
    general_properties.set_value("object_type", object_type, entity_reference=child)
    assert services["ObjectService"].get_object_type(child) == object_type, \
        "MPFB should read back the type just written"
    return child


def write(path, content=""):
    """Create one file, and the directories above it. Returns the path."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


# The LocationService fields a fixture may point somewhere else, by the keyword
# a test names them with. Private fields on MPFB's singleton: see this module's
# docstring for why there is no supported setter to use instead.
_REDIRECTABLE = {
    "user_home": "_user_home",
    "user_data": "_user_data",
    "user_config": "_user_config",
    "mpfb_data": "_mpfb_data",
    "second_root": "_second_root",
    "mh_user_data": "_mh_user_data",
}


@contextlib.contextmanager
def redirected_locations(services, **directories):
    """Point MPFB's location service at a fixture tree, and put it back.

    Pass the directories a test wants to control by their MPFB names -
    ``user_data``, ``mpfb_data``, ``second_root`` and so on. **Everything not
    named keeps the value the developer's install has**, which is occasionally
    what a test wants and usually is not: ``AssetService.get_available_data_roots()``
    is the union of four of these, so a test needing a deterministic asset
    library has to redirect all four and not merely the one it writes into.
    :func:`only_these_data_roots` is that, spelled once.
    """
    location_service = services["LocationService"]
    unknown = sorted(set(directories) - set(_REDIRECTABLE))
    assert not unknown, "Not a redirectable location: {:s}".format(", ".join(unknown))

    original = {}
    try:
        for name, directory in directories.items():
            field = _REDIRECTABLE[name]
            original[field] = getattr(location_service, field)
            setattr(location_service, field, directory)
        yield location_service
    finally:
        for field, value in original.items():
            setattr(location_service, field, value)


def only_these_data_roots(services, user_data=None, mpfb_data=None,
                          second_root=None, mh_user_data=None):
    """:func:`redirected_locations` over every root an asset search walks.

    A root given as ``None`` is pointed at a directory that does not exist, and
    ``get_available_data_roots()`` drops it - so the caller gets exactly the
    roots it named, in MPFB's own order, whatever the developer has installed.
    """
    missing = os.path.join(os.sep, "mpfb-bridge-test", "no-such-data-root")
    return redirected_locations(
        services,
        user_data=user_data or missing,
        mpfb_data=mpfb_data or missing,
        second_root=second_root or missing,
        mh_user_data=mh_user_data or missing)
