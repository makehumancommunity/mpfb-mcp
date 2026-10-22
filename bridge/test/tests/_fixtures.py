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
    "build_attributed_library",
    "build_rig_tree",
    "build_target_tree",
    "dispatch",
    "expression_library",
    "linked_plain_object",
    "material_character",
    "material_data_roots",
    "mpfb_root",
    "mpfb_ui_module",
    "nothing_active",
    "only_these_data_roots",
    "posing_state",
    "rigged_character",
    "with_helpers",
    "redirected_locations",
    "resolution_module",
    "rest_pose",
    "result",
    "services_or_skip",
    "supplied_resolution",
    "typed_child",
    "write",
    "write_expression",
    "write_mhclo",
    "write_mhmat",
    "write_pack",
    "write_png",
    "write_subrigged_mhclo",
    "write_target",
)

import contextlib
import gzip
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


@contextlib.contextmanager
def nothing_active():
    """Run the block with no active object, and put the previous one back.

    The state a caller is in after deselecting everything, and one no command
    can produce: every command that creates something makes it active.
    """
    view_layer = bpy.context.view_layer
    previous = view_layer.objects.active
    view_layer.objects.active = None
    try:
        yield
    finally:
        try:
            view_layer.objects.active = previous
        except ReferenceError:
            # The block deleted it, which is the block's own business.
            pass


# What a fake target file holds: MPFB's own format, one
# "<vertex index> <x> <z> <-y>" line per moved vertex. Three lines, moving three
# low-numbered vertices every hm08 basemesh has by a tenth of a unit.
#
# **This used to be the string "dummy target data", and FR 032 is why it is
# not.** A read-only command sees a filename and a directory and never the
# vertex deltas, so any non-empty content was enough for the fifteen modules
# before this one. A *mutating* command calls ``TargetService.load_target()``,
# which parses every line - and which opens a ".target.gz" with ``gzip``. So the
# content has to be real, and :func:`write_target` has to actually compress the
# ones whose name says they are compressed.
TARGET_CONTENT = "0 0.1 0.0 0.0\n1 0.1 0.0 0.0\n2 0.1 0.0 0.0\n"


def write(path, content=""):
    """Create one file, and the directories above it. Returns the path."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def write_target(path, content=None):
    """One target file, gzipped when its name ends in ".gz".

    ``write()`` cannot do this: a ".target.gz" written as plain text is a file
    every read-only command reports correctly and every mutating command fails
    to open, with a ``BadGzipFile`` from inside MPFB rather than anything this
    suite would recognise. Splitting the two keeps ``write()`` a plain-text
    helper and puts the one rule that matters where a target is made.
    """
    if not str(path).endswith(".gz"):
        return write(path, TARGET_CONTENT if content is None else content)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with gzip.open(path, "wb") as handle:
        handle.write((TARGET_CONTENT if content is None else content).encode("utf-8"))
    return path


def write_mhmat(path, name=None, lines=()):
    """A real MHMAT file, carrying only the lines anything here reads back.

    ``lines`` are appended as given - ``"diffuseTexture shirt.png"`` - for a
    test whose material needs a texture MPFB will build a node for.
    """
    return write(path, "# MakeHuman Material Definition\nname {:s}\n{:s}".format(
        name or os.path.splitext(os.path.basename(path))[0],
        "".join(line + "\n" for line in lines)))


def write_png(path, rgba=(0.5, 0.5, 0.5, 1.0)):
    """A four-pixel PNG, written by Blender, for an MHMAT to name as a texture."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    image = bpy.data.images.new(os.path.basename(path), 2, 2)
    try:
        image.pixels[:] = list(rgba) * 4
        image.filepath_raw = path
        image.file_format = "PNG"
        image.save()
    finally:
        bpy.data.images.remove(image)
    return path


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


# The three lines MPFB's Mhclo parser needs before it will believe the vertex
# block, and the values a real garment carries for a basemesh at MPFB's own
# scale. Spelled out once rather than in each module that equips something.
_MHCLO_SCALE_LINES = (
    "x_scale 5399 11998 1.0000",
    "y_scale 5399 11998 1.0000",
    "z_scale 5399 11998 1.0000",
)


def write_loadable_mhclo(path, material=True, uuid=None, mhmat_lines=()):
    """An MHCLO a mutating command can actually **equip**, and its OBJ beside it.

    Different from :func:`write_mhclo` in the one way that matters here, and the
    two exist side by side rather than one replacing the other:
    :func:`write_mhclo` is metadata for a *catalogue* to read, with ``verts 0``
    and no mesh at all, and it is all a read-only command ever sees. A command
    that equips a garment imports the OBJ and fits it vertex by vertex, so it
    needs a real one.

    Three vertices and one face, which is the smallest mesh MPFB's importer and
    ``ClothesService`` will both accept. It is not pretending to be a garment;
    what it is for is being equipped, refitted and removed.

    **Write it under a directory that will be a redirected data root.** A
    garment equipped from outside every data root can never be refitted:
    ``ClothesService.fit_clothes_to_human()`` re-reads the MHCLO through
    ``AssetService``, which searches the roots rather than remembering where the
    file came from. See this package's ``ddd_mutating/__init__.py``.
    """
    base = os.path.splitext(path)[0]
    name = os.path.basename(base)
    lines = ["# MakeHuman clothes file", "name " + name, "obj_file " + name + ".obj"]
    if uuid:
        # What a preset keys an asset's colour adjustment and alternative
        # material by, so a fixture that is saved and loaded again needs one.
        lines.append("uuid " + uuid)
    if material:
        lines.append("material " + name + ".mhmat")
        write_mhmat(os.path.join(os.path.dirname(path), name + ".mhmat"), lines=mhmat_lines)
    lines.extend(_MHCLO_SCALE_LINES)
    lines.append("verts 0")
    # Each line matches one asset vertex to three basemesh vertices with
    # weights. The indices are low ones every hm08 basemesh has.
    lines.extend([
        "0 1 2 0.3 0.3 0.4 0 0 0",
        "3 4 5 0.3 0.3 0.4 0 0 0",
        "6 7 8 0.3 0.3 0.4 0 0 0",
    ])
    write(os.path.join(os.path.dirname(path), name + ".obj"),
          "v 0.0 0.0 0.0\nv 1.0 0.0 0.0\nv 0.0 1.0 0.0\nf 1 2 3\n")
    return write(path, "\n".join(lines) + "\n")


# One bone of MPFB's sub-rig format, shaped as ``hair/ponytail01/ponytail01.mpfbskel``
# ships it: a ``root`` placed on the garment's own vertices (strategy MEAN),
# bound by a CHILD_OF to the parent rig's ``head``, found through the
# basemesh's ``joint-head`` joints. Vertex indices 0-2 are the three every
# loadable fixture garment has.
_SUBRIG_ROOT_BONE = {
    "constraints": [{
        "name": "Child Of",
        "owner_space": "POSE",
        "set_inverse_pending": False,
        "subtarget": "head",
        "target": {"joint_head": "joint-head", "joint_tail": "joint-head-2",
                   "strategy": "JOINTS"},
        "type": "CHILD_OF",
        "use_location_x": True, "use_location_y": True, "use_location_z": True,
        "use_rotation_x": True, "use_rotation_y": True, "use_rotation_z": True,
        "use_scale_x": True, "use_scale_y": True, "use_scale_z": True,
    }],
    "head": {"default_position": [0.0, 0.5, 0.0], "strategy": "MEAN", "vertex_indices": [0, 1]},
    "tail": {"default_position": [0.5, 0.5, 0.0], "strategy": "MEAN", "vertex_indices": [1, 2]},
    "inherit_scale": "FULL",
    "layers": [True] + [False] * 31,
    "parent": "",
    "rigify": {},
    "roll": 0.0,
    "use_connect": False,
    "use_inherit_rotation": True,
    "use_local_location": True,
}


def write_subrigged_mhclo(path, uuid=None):
    """A loadable MHCLO with a **sub-rig** beside it, as ``ponytail01`` ships one.

    :func:`write_loadable_mhclo`, plus ``<basename>.mpfbskel``, which is the
    file ``ClothesService.set_up_rigging()`` looks for (not a ``.rig.json``,
    which the line-up session first took it for): MPFB then builds a ``Subrig``
    armature, parents the garment to it and the sub-rig to the character's rig.
    The data is MPFB's own format, with the one bone and the one constraint
    that make ``ponytail01`` break away from the origin - not a stand-in shaped
    to pass ([FR 045](../../../feature-requests/done/045-placing-a-character/README.md)).
    Equip it on a character that has a rig, from a redirected data root.
    """
    written = write_loadable_mhclo(path, uuid=uuid)
    write(os.path.splitext(path)[0] + ".mpfbskel", json.dumps({
        "bones": {"root": _SUBRIG_ROOT_BONE},
        "is_subrig": True,
        "rigify_ui": None,
        "version": 100,
    }, indent=1))
    return written


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


def write_pack(user_root, pack_name, entries):
    """One installed pack's metadata, ``<user data>/packs/<pack_name>.json``.

    ``entries`` maps an asset name to ``(license, author, source)``, and each is
    written with every key a real pack entry carries, since the reading is
    MPFB's and a fixture reproduces the install rather than a convenient subset.
    """
    document = dict()
    for asset_name, (license_name, author, source) in entries.items():
        document[asset_name] = {
            "author": author, "category": "", "changed": "2020-01-01",
            "created": "2020-01-01", "description": "Bridge test asset",
            "license": license_name, "original_author": "", "original_source": "",
            "source": source, "thumbnail": asset_name + ".png", "type": "clothes"}
    return write(os.path.join(user_root, "packs", pack_name + ".json"), json.dumps(document))


def build_attributed_library(root):
    """:func:`build_asset_library`, plus pack metadata in the shapes a real install has.

    Every shape is one FR 046's attribution has to get right, and each was
    measured on the maintainer's community install first:

    - ``fedora`` is claimed by **two packs that agree** (``hats01`` and
      ``hats01_cc0``, as ``hats01``/``hats01_cc0`` do there), and the materials
      beside it in its own directory take its attribution;
    - ``fedora/fedora_green/fedora_green.mhmat`` is a material in **a directory
      of its own**, claimed by a pack of its own under another license, as the
      ``system_hair_materials`` packs ship theirs;
    - ``eyes/materials/brown.mhmat`` is claimed only **by its file stem**, as
      ``makehuman_system_assets`` claims the eye materials;
    - ``skins/default.mhmat`` lies **directly in an asset root**, and a pack
      claims an asset called ``skins``, which is exactly what the root rule
      must not attribute it to;
    - ``ponytail`` is claimed by **two packs that disagree** on its license,
      which no install has yet and the rule must still handle;
    - ``plain`` and ``lowpoly`` are claimed by nothing;
    - ``capes01_cc0`` is **registered with nothing on disk**, as
      ``accessories01_cc0``'s capes are there.

    Returns ``(system_root, user_root)``; the metadata is under the user root,
    the only place MPFB reads it from.
    """
    system_root, user_root = build_asset_library(root)
    write_mhmat(os.path.join(system_root, "clothes", "fedora", "fedora_green",
                             "fedora_green.mhmat"))
    write_mhmat(os.path.join(system_root, "eyes", "materials", "brown.mhmat"))
    write_mhmat(os.path.join(user_root, "skins", "default.mhmat"))

    hats = ("CC0", "hatmaker", "http://www.makehumancommunity.org/node/1")
    write_pack(user_root, "hats01", {"fedora": hats})
    write_pack(user_root, "hats01_cc0", {"fedora": hats})
    write_pack(user_root, "fedora_materials01", {
        "fedora_green": ("CC-BY", "painter", "http://www.makehumancommunity.org/node/2")})
    write_pack(user_root, "makehuman_system_assets", {
        "brown": ("CC0", "makehuman_system", "http://www.makehumancommunity.org"),
        "young": ("CC0", "makehuman_system", "http://www.makehumancommunity.org")})
    write_pack(user_root, "odd01", {
        "skins": ("CC-BY", "someone", "http://www.makehumancommunity.org/node/3")})
    write_pack(user_root, "hair01", {
        "ponytail": ("CC0", "barber", "http://www.makehumancommunity.org/node/4")})
    write_pack(user_root, "hair01_ccby", {
        "ponytail": ("CC-BY", "barber", "http://www.makehumancommunity.org/node/4")})
    write_pack(user_root, "capes01_cc0", {
        "cape_long": ("CC0", "tailor", "http://www.makehumancommunity.org/node/5")})
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
    - **real, parseable target data**, gzipped where the name says so, because
      a mutating command loads one rather than merely listing it (see
      :data:`TARGET_CONTENT`);
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
        write_target(os.path.join(system_targets, "arms", name + ".target.gz"))
    # The one bundled target that is *not* gzipped, which is the case
    # _set_opposed_modifier_value() would hand a non-existent path.
    write_target(os.path.join(system_targets, "arms", "upperarm-fat-incr.target"))
    for name in ("nose-scale-depth-decr", "nose-scale-depth-incr"):
        write_target(os.path.join(system_targets, "nose", name + ".target.gz"))
    write_target(os.path.join(system_targets, "chin", "chin-triangle.target.gz"))
    # Left only: the right-hand files of this category are deliberately absent.
    for name in ("l-ear-lobe-decr", "l-ear-lobe-incr"):
        write_target(os.path.join(system_targets, "ears", name + ".target.gz"))
    # A bundled directory target.json never mentions, and one holding nothing.
    write_target(os.path.join(system_targets, "asym", "asym-brow-1-l.target.gz"))
    os.makedirs(os.path.join(system_targets, "_images"), exist_ok=True)

    user_data = os.path.join(root, "user", "data")
    user_targets = os.path.join(user_data, "targets")
    user_custom = os.path.join(user_data, "custom")

    # A user directory sharing its name with a bundled section: MPFB appends
    # these into that section rather than making a second one.
    write_target(os.path.join(user_targets, "arms", "elvs_arm_bulk.target"))
    # A section that exists only as a user directory.
    write_target(os.path.join(user_targets, "animal", "cat_ears.target"))
    write_target(os.path.join(user_targets, "animal", LONG_USER_TARGET + ".target"))
    # A gzipped target in a user targets directory: on disk, loadable, and
    # invisible to MPFB's own scan, which matches only "*.target".
    write_target(os.path.join(user_targets, "animal", "winged.target.gz"))
    # Contains "basis", so MPFB's own get_target_stack() cannot see the shape
    # key this produces - and neither can any MPFB read or write.
    write_target(os.path.join(user_targets, "animal", "basis-nose-widen.target"))
    # The custom section proper. The gzipped one is where MPFB's category name
    # ("vwide.gz") and the catalogue's shapekey_name ("vwide") diverge.
    write_target(os.path.join(user_custom, "closed_eyes.target"))
    write_target(os.path.join(user_custom, "vwide.target.gz"))

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


# The face units the expression fixtures below use, plus "cheekPuff", which is
# the one target FaceService.is_faceunits01_installed() probes for. Written as
# real target files, so that the fixture is a small but genuine faceunits01
# install rather than a probe that happens to pass: a mutating command loads
# every one of these.
FIXTURE_FACE_UNITS = ("cheekPuff", "jawOpen", "mouthSmileLeft", "mouthSmileRight",
                      "browInnerUp", "eyeBlinkLeft")


def write_expression(services, path, face_units, name=None, **metadata):
    """One expression file, written by ``FaceService.save_expression()`` itself.

    Never hand-written JSON: a fixture reproduces the install rather than a
    convenient version of it (specifications/testing.md), and MPFB's own writer
    is what decides the rounding, the zero-dropping and the field defaults.
    ``name`` defaults to the file's basename; pass ``""`` for the file with no
    name, which is the label-fallback case.
    """
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    meta = dict(metadata)
    meta["name"] = os.path.splitext(os.path.basename(path))[0] if name is None else name
    return services["FaceService"].save_expression(path, dict(face_units), meta)


@contextlib.contextmanager
def expression_library(services, root):
    """A redirected data tree holding a small faceunits01 pack and expressions.

    Two data roots, in MPFB's priority order:

    - ``mpfb_data`` holds ``expressions/shadowing.json``, so that a file of the
      same name in user data is **shadowed** - the case ``save_expression``
      refuses and ``list_expressions`` reports;
    - ``user_data`` holds the targets under ``targets/faceunits/`` and the
      expressions ``smile.json``, ``jaw.json`` and ``shadowing.json``.

    ``smile`` and ``jaw`` both open the jaw, at 0.6 and 0.7, so stacking them at
    full weight sums to 1.3 and **clamps** - which is what
    ``clamped_face_units`` exists to report.

    **Build the character first, outside this block.** ``create_human()``
    loads the base mesh out of ``mpfb_data``, which this redirects to the
    fixture tree - so a character created inside it fails with a missing
    ``3dobjs/base.obj``.

    The pack probe's cache is seeded inside the redirect and restored on the
    way out, exactly as ``ddd_mutating/set_face_units_test.py`` does, so that a
    module running afterwards is not left looking at the fixture's answer.

    Yields a dict of the paths a test asserts against.
    """
    face_service = services["FaceService"]
    system = os.path.join(str(root), "system")
    user = os.path.join(str(root), "user")
    for unit in FIXTURE_FACE_UNITS:
        write_target(os.path.join(user, "targets", "faceunits", unit + ".target"))

    paths = dict(
        system=system,
        user=user,
        user_expressions=os.path.join(user, "expressions"),
        system_expressions=os.path.join(system, "expressions"),
    )
    paths["smile"] = write_expression(
        services, os.path.join(paths["user_expressions"], "smile.json"),
        {"mouthSmileLeft": 0.8, "mouthSmileRight": 0.8, "jawOpen": 0.6},
        description="A broad smile.", tags=["happy"], license="CC0")
    paths["jaw"] = write_expression(
        services, os.path.join(paths["user_expressions"], "jaw.json"), {"jawOpen": 0.7})
    paths["shadowed"] = write_expression(
        services, os.path.join(paths["user_expressions"], "shadowing.json"),
        {"browInnerUp": 0.5})
    paths["shadowing"] = write_expression(
        services, os.path.join(paths["system_expressions"], "shadowing.json"),
        {"eyeBlinkLeft": 0.5})

    with only_these_data_roots(services, user_data=user, mpfb_data=system):
        face_service.is_faceunits01_installed(force_recheck=True)
        try:
            yield paths
        finally:
            face_service.is_faceunits01_installed(force_recheck=True)


# The uuids the material fixture's assets carry. A preset keys a colour
# adjustment by uuid, so the round trip needs them to be stable and distinct.
MATERIAL_FIXTURE_UUIDS = {
    "eyes": "b1d9e0a0-0000-4000-8000-00000000e7e5",
    "hair": "b1d9e0a0-0000-4000-8000-0000000a1a12",
    "garment": "b1d9e0a0-0000-4000-8000-0000005a1d17",
    "aoshirt": "b1d9e0a0-0000-4000-8000-00000000a0a0",
}


def material_character(services, character, root):
    """Procedural eyes, a LAYERED skin, and three MakeSkin assets on ``character``.

    The fixture FR 040's three sections need, built the way a user builds it
    and not by writing node values: each asset is equipped through
    ``add_asset``'s own command, and the skin through
    ``HumanService.set_character_skin()``. The hair's and the garment's MHMATs
    name a diffuse texture, as every real one does: without one MPFB builds no
    ``diffuseIntensity`` node, and identifies the material as ``gameengine``.
    ``aoshirt``'s names an AO map as well, so the node on its Base Color is
    ``aoMix``.

    **Call it inside ``material_data_roots(services, root)``, and keep that open
    for as long as anything re-reads an asset** - a refit or a preset load
    searches the data roots rather than remembering where a file came from.
    Returns ``{role: object name}``.
    """
    root = str(root)
    texture = write_png(os.path.join(root, "textures", "fixture_diffuse.png"),
                        (0.6, 0.3, 0.2, 1.0))
    ao_map = write_png(os.path.join(root, "textures", "fixture_ao.png"), (0.9, 0.9, 0.9, 1.0))
    specs = (
        ("eyes", "Eyes", "eyes", "PROCEDURAL_EYES", ()),
        ("hair", "Hair", "hair", "MAKESKIN", ("diffuseTexture " + texture,)),
        ("garment", "Clothes", "clothes", "MAKESKIN", ("diffuseTexture " + texture,)),
        ("aoshirt", "Clothes", "clothes", "MAKESKIN",
         ("diffuseTexture " + texture, "aomapTexture " + ao_map, "aomapIntensity 1.0")),
    )
    names = {}
    for role, object_type, subdir, material_type, mhmat_lines in specs:
        stem = "fixture_" + role
        write_loadable_mhclo(os.path.join(root, subdir, stem, stem + ".mhclo"),
                             uuid=MATERIAL_FIXTURE_UUIDS[role], mhmat_lines=mhmat_lines)
        envelope = dispatch("add_asset", {
            "name": character.basemesh.name,
            "fragment": "{:s}/{:s}.mhclo".format(stem, stem),
            "object_type": object_type,
            "material_type": material_type,
        })
        assert envelope["status"] == "ok", "equipping {:s} failed: {!r}".format(role, envelope)
        assert envelope["result"]["added"] is True, envelope["result"]["message"]
        names[role] = envelope["result"]["asset_object_name"]

    services["HumanService"].set_character_skin(
        None, character.basemesh, skin_type="LAYERED", material_instances=False)
    names["body"] = character.basemesh.name
    return names


def material_data_roots(services, root):
    """:func:`only_these_data_roots` with ``root`` as user data, and MPFB's own data kept.

    Procedural eyes and MakeSkin materials are built from node trees MPFB ships
    in its data directory (``node_trees/procedural_eyes.json``), so pointing that
    root away as well - which is what a deterministic *asset* library wants -
    leaves MPFB unable to build either. MPFB's shipped data is the same on every
    install of one version, so keeping it costs the fixture no determinism.
    """
    return only_these_data_roots(
        services, user_data=str(root),
        mpfb_data=getattr(services["LocationService"], _REDIRECTABLE["mpfb_data"]))


# --------------------------------------------------------------------------
# Posing: a character of each rig family, MPFB's IK helpers, and a snapshot of
# everything a read-only posing command promises not to change. FR 041's two
# command modules and its two shared-module tests all build these.
# --------------------------------------------------------------------------


def mpfb_root():
    """MPFB's root package name here, which is where its UI modules hang."""
    resolution = dynamic_import("mpfb_resolution", "resolve")()
    if not resolution.is_ok:
        pytest.skip("MPFB is {:s} in this Blender: {:s}".format(
            resolution.state, resolution.message))
    return resolution.module.__name__


def mpfb_ui_module(relative):
    """An MPFB UI module MPFB itself has already imported, or a skip naming it.

    Read from ``sys.modules`` the way the bridge reads one, never imported: a
    test that imported it could pass where the add-on would find nothing.
    """
    name = mpfb_root() + "." + relative
    module = sys.modules.get(name)
    if module is None:
        pytest.skip("{:s} is not loaded in this Blender".format(name))
    return module


def _rigify_or_skip(services):
    if not services["SystemService"].check_for_rigify():
        pytest.skip("Rigify is not enabled in this Blender, so no Rigify rig can be generated")


def _activate_only(blender_object):
    for other in bpy.context.view_layer.objects:
        other.select_set(False)
    bpy.context.view_layer.objects.active = blender_object
    blender_object.select_set(True)


def rigged_character(services, character, rig):
    """Rig ``character`` and return the armature that moves it.

    ``rig`` is an identifier ``mpfb_add_rig`` would take, plus three that only a
    generation produces: ``"generated:human_toes"`` and ``"generated:human"``
    add MPFB's meta-rig of that name and generate it with
    ``RigService.generate_rigify_rig()``, and
    ``"generated:game_engine"`` adds the standard ``game_engine`` rig and runs
    MPFB's legacy convert-to-Rigify operator on it, which is the only way MPFB
    makes a ``rigify_generated.game_engine`` rig. Both skip without Rigify.
    """
    human_service = services["HumanService"]
    if rig in ("generated:human_toes", "generated:human"):
        _rigify_or_skip(services)
        meta_name = rig.split(":", 1)[1]
        meta_rig = human_service.add_builtin_rig(
            character.basemesh, "rigify." + meta_name, import_weights=True)
        assert meta_rig is not None, "the meta-rig should have been added"
        generated = services["RigService"].generate_rigify_rig(meta_rig, meta_rig_action="hide")
        assert generated is not None, "Rigify should have generated the {:s} meta-rig".format(
            meta_name)
        return generated
    if rig == "generated:game_engine":
        _rigify_or_skip(services)
        standard = human_service.add_builtin_rig(
            character.basemesh, "game_engine", import_weights=True)
        before = set(blender_object.name for blender_object in bpy.data.objects)
        _activate_only(standard)
        result = bpy.ops.mpfb.convert_to_rigify()
        assert result == {"FINISHED"}, result
        created = [blender_object for blender_object in bpy.data.objects
                   if blender_object.name not in before and blender_object.type == "ARMATURE"]
        assert len(created) == 1, "convert-to-Rigify should have generated one armature"
        return created[0]
    added = human_service.add_builtin_rig(character.basemesh, rig, import_weights=True)
    assert added is not None, "the {:s} rig should have been added".format(rig)
    return added


def with_helpers(rig_object, arm="NONE", leg="NONE", finger="NONE", eye=False):
    """Install MPFB's IK helpers on a default rig, the way its panel's button does.

    Sets the panel's own scene settings and runs ``mpfb.add_helpers``, so what
    is on the rig afterwards - bones, constraints, the recorded modes - is
    exactly what a user clicking the button would get.
    """
    panel = mpfb_ui_module("ui.rigging.standardrig.standardrigpanel")
    settings = panel.SETUP_HELPERS_PROPERTIES
    scene = bpy.context.scene
    settings.set_value("arm_helpers_type", arm, entity_reference=scene)
    settings.set_value("leg_helpers_type", leg, entity_reference=scene)
    settings.set_value("finger_helpers_type", finger, entity_reference=scene)
    settings.set_value("eye_ik", eye, entity_reference=scene)
    _activate_only(rig_object)
    assert bpy.ops.mpfb.add_helpers() == {"FINISHED"}
    return rig_object


def posing_state(rig_object):
    """Everything a read-only posing command must leave as it found it.

    The mode, the active object, the selection, and every pose bone's local
    transform and every custom property on it - which covers the switches.
    """
    bones = {}
    for pose_bone in rig_object.pose.bones:
        properties = {key: pose_bone[key] for key in pose_bone.keys()
                      if isinstance(pose_bone[key], (bool, int, float))}
        bones[pose_bone.name] = (tuple(round(value, 6) for value in pose_bone.location),
                                 tuple(round(value, 6) for value in pose_bone.rotation_quaternion),
                                 tuple(round(value, 6) for value in pose_bone.rotation_euler),
                                 tuple(round(value, 6) for value in pose_bone.scale),
                                 properties)
    active = bpy.context.view_layer.objects.active
    return {
        "mode": bpy.context.mode,
        "rig_mode": rig_object.mode,
        "active": None if active is None else active.name,
        "selected": sorted(blender_object.name for blender_object in bpy.context.selected_objects),
        "bones": bones,
    }


def rest_pose(rig_object):
    """Every pose bone at rest and every switch at its default, for a rig shared by a module.

    The posing fixtures build one rig per module, because generating Rigify
    takes most of a second; each test then puts it back with this, through
    plain ``bpy``, so that what puts a rig back is never the command under test.
    """
    for pose_bone in rig_object.pose.bones:
        pose_bone.location = (0.0, 0.0, 0.0)
        pose_bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pose_bone.rotation_euler = (0.0, 0.0, 0.0)
        pose_bone.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)
        pose_bone.scale = (1.0, 1.0, 1.0)
        for key in pose_bone.keys():
            if not isinstance(pose_bone[key], (bool, int, float)):
                continue
            try:
                default = pose_bone.id_properties_ui(key).as_dict().get("default")
            except (TypeError, KeyError):
                continue
            if default is not None:
                pose_bone[key] = type(pose_bone[key])(default)
    rig_object.data.pose_position = "POSE"
    bpy.context.view_layer.update()
