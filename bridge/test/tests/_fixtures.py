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
    "DETAIL_TARGET_JSON",
    "LONG_USER_TARGET",
    "answer",
    "build_asset_library",
    "build_rig_tree",
    "build_target_tree",
    "dispatch",
    "linked_plain_object",
    "only_these_data_roots",
    "redirected_locations",
    "resolution_module",
    "result",
    "services_or_skip",
    "supplied_resolution",
    "typed_child",
    "write",
    "write_mhclo",
    "write_mhmat",
)

import contextlib
import json
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


# What a fake target file holds. Nothing in this suite loads one - a read-only
# command sees a filename and a directory, never the vertex deltas - so the
# content only has to be non-empty.
TARGET_CONTENT = "dummy target data"


def write(path, content=""):
    """Create one file, and the directories above it. Returns the path."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def write_mhmat(path, name=None):
    """A real MHMAT file, carrying only the lines anything here reads back."""
    return write(path, "# MakeHuman Material Definition\nname {:s}\n".format(
        name or os.path.splitext(os.path.basename(path))[0]))


def write_mhclo(path, material=True, uuid=None):
    """A real MHCLO file, carrying only the metadata lines a catalogue reads.

    Moved from ``tests/blender_stubs.py``'s ``write_mhclo()``, trimmed to what a
    read-only command can see: the geometry is left out because nothing here
    imports the asset, and ``material`` decides whether the file names one -
    which is what ``list_asset_materials``' ``default_material_reason`` turns on.
    """
    base = os.path.splitext(path)[0]
    lines = ["# MakeHuman clothes file", "name " + os.path.basename(base)]
    if material:
        material_name = os.path.basename(base) + ".mhmat"
        lines.append("material " + material_name)
        write_mhmat(os.path.join(os.path.dirname(path), material_name))
    if uuid:
        lines.append("uuid " + uuid)
    lines.append("verts 0")
    return write(path, "\n".join(lines) + "\n")


def build_asset_library(root):
    """An asset library with the shapes a real one has, under one directory.

    Moved from ``tests/blender_stubs.py``'s ``MeshAssetTestCase`` rather than
    reinvented, and it keeps that fixture's deliberate asymmetries because each
    is a branch some command takes:

    - ``fedora`` is the ordinary asset, with **two alternative materials** beside
      it, which is what ``list_asset_materials`` is for;
    - ``plain`` names **no material at all**, which is the
      ``mhclo_names_no_material`` branch;
    - a **second root** holds another ``fedora.mhclo``, because
      ``find_asset_absolute_path()`` matches on basename and the ambiguity that
      produces is a fact about MPFB rather than about any one command;
    - the sections are spread across ``clothes``, ``hair``, ``eyes`` and
      ``skins``, so a subdir filter has something to exclude.

    Returns ``(system_root, user_root)`` - two data roots, to be handed to
    :func:`only_these_data_roots`.
    """
    system_root = os.path.join(root, "system", "assets")
    user_root = os.path.join(root, "user", "assets")

    write_mhclo(os.path.join(system_root, "clothes", "fedora", "fedora.mhclo"),
                uuid="fedora-uuid")
    write_mhmat(os.path.join(system_root, "clothes", "fedora", "fedora_red.mhmat"))
    write_mhmat(os.path.join(system_root, "clothes", "fedora", "fedora_blue.mhmat"))
    write_mhclo(os.path.join(system_root, "clothes", "plain", "plain.mhclo"), material=False)
    write_mhclo(os.path.join(system_root, "hair", "ponytail", "ponytail.mhclo"))
    write_mhclo(os.path.join(system_root, "eyes", "lowpoly", "lowpoly.mhclo"))
    write_mhmat(os.path.join(system_root, "skins", "young", "young.mhmat"))

    # The same basename under a second root: two packs shipping fedora.mhclo.
    write_mhclo(os.path.join(user_root, "clothes", "fedora", "fedora.mhclo"))

    return (system_root, user_root)


def build_rig_tree(root):
    """``<mpfb data>/rigs`` with the asymmetries a real install has.

    Moved from ``tests/blender_stubs.py``'s ``RigTestCase``, and it keeps that
    fixture's three deliberate oddities, each of which is a branch:

    - ``default`` has weights of its own and ``default_no_toes`` does not,
      which is what makes MPFB's weights **fallback table** observable rather
      than assumed;
    - ``weights.orphan.json`` sits beside no rig, so a weights file must not be
      listed as a rig;
    - no UI enum is written, so every entry's ``label`` is null - which is the
      state of any rig a user drops in, and the reason the *directory* rather
      than the enum is the authority.

    Returns the ``<mpfb data>`` directory the tree hangs under.
    """
    mpfb_data = os.path.join(root, "mpfb-data")
    standard = os.path.join(mpfb_data, "rigs", "standard")
    rigify = os.path.join(mpfb_data, "rigs", "rigify")
    for name in ("default", "default_no_toes", "cmu_mb"):
        write(os.path.join(standard, "rig." + name + ".json"), '{"bones": {}}\n')
    write(os.path.join(standard, "weights.default.json"), "{}\n")
    write(os.path.join(standard, "weights.orphan.json"), "{}\n")
    write(os.path.join(rigify, "rig.human.json"), '{"bones": {}}\n')
    write(os.path.join(rigify, "weights.human.json"), "{}\n")
    return mpfb_data


# MPFB's own ``target.json`` shape, trimmed to five sections that between them
# cover every category kind a command has to get right. Lifted from
# ``tests/blender_stubs.py``'s ``DETAIL_TARGET_JSON`` rather than rewritten:
#
# - ``arms`` holds a **sided, opposed** category (four target files behind one
#   slider) and an unsided opposed one;
# - ``nose`` holds an unsided opposed category;
# - ``chin`` holds a category with **no "opposites" key at all**, which is the
#   0.0-1.0 kind;
# - ``ears`` is sided and has only its **left-hand files on disk**, so a
#   resolution failure is in the fixture rather than only in theory;
# - ``measure`` has **no categories**, and is the section that must answer
#   "no matches" rather than falling through to the user-target listing.
DETAIL_TARGET_JSON = {
    'arms': {
        'categories': [
            {
                'has_left_and_right': True,
                'label': 'lowerarm-scale-depth-decr-incr',
                'name': 'lowerarm-scale-depth-decr-incr',
                'opposites': {
                    'negative-left': 'l-lowerarm-scale-depth-decr',
                    'negative-right': 'r-lowerarm-scale-depth-decr',
                    'negative-unsided': '',
                    'positive-left': 'l-lowerarm-scale-depth-incr',
                    'positive-right': 'r-lowerarm-scale-depth-incr',
                    'positive-unsided': '',
                },
                'targets': [
                    'l-lowerarm-scale-depth-decr',
                    'r-lowerarm-scale-depth-incr',
                    'r-lowerarm-scale-depth-decr',
                    'l-lowerarm-scale-depth-incr',
                ],
            },
            {
                'has_left_and_right': False,
                'label': 'upperarm-fat-decr-incr',
                'name': 'upperarm-fat-decr-incr',
                'opposites': {
                    'negative-left': '',
                    'negative-right': '',
                    'negative-unsided': 'upperarm-fat-decr',
                    'positive-left': '',
                    'positive-right': '',
                    'positive-unsided': 'upperarm-fat-incr',
                },
                'targets': [
                    'upperarm-fat-decr',
                    'upperarm-fat-incr',
                ],
            },
        ],
        'include_per_default': True,
        'label': 'Arms',
        'unsorted': [],
    },
    'chin': {
        'categories': [
            {
                'has_left_and_right': False,
                'label': 'chin-triangle',
                'name': 'chin-triangle',
                'targets': [
                    'chin-triangle',
                ],
            },
        ],
        'include_per_default': True,
        'label': 'Chin',
        'unsorted': [],
    },
    'ears': {
        'categories': [
            {
                'has_left_and_right': True,
                'label': 'ear-lobe-decr-incr',
                'name': 'ear-lobe-decr-incr',
                'opposites': {
                    'negative-left': 'l-ear-lobe-decr',
                    'negative-right': 'r-ear-lobe-decr',
                    'negative-unsided': '',
                    'positive-left': 'l-ear-lobe-incr',
                    'positive-right': 'r-ear-lobe-incr',
                    'positive-unsided': '',
                },
                'targets': [
                    'l-ear-lobe-decr',
                    'l-ear-lobe-incr',
                    'r-ear-lobe-decr',
                    'r-ear-lobe-incr',
                ],
            },
        ],
        'include_per_default': True,
        'label': 'Ears',
        'unsorted': [],
    },
    'measure': {
        'categories': [],
        'include_per_default': False,
        'label': 'measure',
        'unsorted': [],
    },
    'nose': {
        'categories': [
            {
                'has_left_and_right': False,
                'label': 'nose-scale-depth-decr-incr',
                'name': 'nose-scale-depth-decr-incr',
                'opposites': {
                    'negative-left': '',
                    'negative-right': '',
                    'negative-unsided': 'nose-scale-depth-decr',
                    'positive-left': '',
                    'positive-right': '',
                    'positive-unsided': 'nose-scale-depth-incr',
                },
                'targets': [
                    'nose-scale-depth-decr',
                    'nose-scale-depth-incr',
                ],
            },
        ],
        'include_per_default': True,
        'label': 'Nose',
        'unsorted': [],
    },
}

# Over 60 characters once the extension is stripped, and built from words in
# MPFB's encoding table, so its shape key name provably differs from its
# filename. Addressing it by filename fails *silently*, which is the whole
# reason ``list_targets`` reports ``shapekey_name``.
LONG_USER_TARGET = (
    "young-female-average-caucasian-uncommon-proportions-weight-height-experiment")


def build_target_tree(root):
    """A bundled target index and the user directories beside it.

    Moved from ``tests/blender_stubs.py``'s ``DetailTargetTestCase`` rather
    than reinvented, and it keeps every one of that fixture's awkward shapes,
    because each is a branch some command exists to get right:

    - a section name present in **both** the bundled index and a user
      directory, which MPFB merges rather than keeping apart;
    - a section that exists only as a user directory;
    - a ``.target.gz`` in a user targets directory, which MPFB's own scan
      matches only ``*.target`` and therefore cannot see;
    - a target whose name **contains "basis"**, which ``TargetService`` cannot
      address at all;
    - a name long enough that its shape key name is encoded and no longer
      equals its filename;
    - a bundled directory ``target.json`` never mentions, and one holding no
      target file at all.

    Returns a dict of the paths a test needs to assert against.
    """
    mpfb_data = os.path.join(root, "mpfb", "data")
    system_targets = os.path.join(mpfb_data, "targets")
    target_json_path = os.path.join(system_targets, "target.json")
    write(target_json_path, json.dumps(DETAIL_TARGET_JSON))

    # Gzipped, as every bundled target on a real install is.
    for name in ("l-lowerarm-scale-depth-decr", "l-lowerarm-scale-depth-incr",
                 "r-lowerarm-scale-depth-decr", "r-lowerarm-scale-depth-incr",
                 "upperarm-fat-decr"):
        write(os.path.join(system_targets, "arms", name + ".target.gz"), TARGET_CONTENT)
    # The one bundled target that is *not* gzipped, which is the case
    # _set_opposed_modifier_value() would hand a non-existent path.
    write(os.path.join(system_targets, "arms", "upperarm-fat-incr.target"), TARGET_CONTENT)
    for name in ("nose-scale-depth-decr", "nose-scale-depth-incr"):
        write(os.path.join(system_targets, "nose", name + ".target.gz"), TARGET_CONTENT)
    write(os.path.join(system_targets, "chin", "chin-triangle.target.gz"), TARGET_CONTENT)
    # Left only: the right-hand files of this category are deliberately absent.
    for name in ("l-ear-lobe-decr", "l-ear-lobe-incr"):
        write(os.path.join(system_targets, "ears", name + ".target.gz"), TARGET_CONTENT)
    # A bundled directory target.json never mentions, and one holding nothing.
    write(os.path.join(system_targets, "asym", "asym-brow-1-l.target.gz"), TARGET_CONTENT)
    os.makedirs(os.path.join(system_targets, "_images"), exist_ok=True)

    user_data = os.path.join(root, "user", "data")
    user_targets = os.path.join(user_data, "targets")
    user_custom = os.path.join(user_data, "custom")

    # A user directory sharing its name with a bundled section: MPFB appends
    # these into that section rather than making a second one.
    write(os.path.join(user_targets, "arms", "elvs_arm_bulk.target"), TARGET_CONTENT)
    # A section that exists only as a user directory.
    write(os.path.join(user_targets, "animal", "cat_ears.target"), TARGET_CONTENT)
    write(os.path.join(user_targets, "animal", LONG_USER_TARGET + ".target"), TARGET_CONTENT)
    # A gzipped target in a user targets directory: on disk, loadable, and
    # invisible to MPFB's own scan, which matches only "*.target".
    write(os.path.join(user_targets, "animal", "winged.target.gz"), TARGET_CONTENT)
    # Contains "basis", so MPFB's own get_target_stack() cannot see the shape
    # key this produces - and neither can any MPFB read or write.
    write(os.path.join(user_targets, "animal", "basis-nose-widen.target"), TARGET_CONTENT)
    # The custom section proper. The gzipped one is where MPFB's category name
    # ("vwide.gz") and the catalogue's shapekey_name ("vwide") diverge.
    write(os.path.join(user_custom, "closed_eyes.target"), TARGET_CONTENT)
    write(os.path.join(user_custom, "vwide.target.gz"), TARGET_CONTENT)

    return {
        "mpfb_data": mpfb_data,
        "system_targets": system_targets,
        "target_json_path": target_json_path,
        "user_data": user_data,
        "user_targets": user_targets,
        "user_custom": user_custom,
    }


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
