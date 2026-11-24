"""
A rig as a bone table, in both directions, and the fit that turns one into positions.

**One implementation, imported by every command that needs it.** See
[`__init__.py`](__init__.py) for why this directory exists beside ``commands/``.
Three commands use it ([FR 060](../../../feature-requests/done/060-authoring-rigs/README.md)):
``get_rig_definition`` reads a rig as a table, ``create_rig`` builds one from a table,
and ``weight_rig`` fits a catalogue rig in memory to transfer its weights. A
disagreement between the reader and the builder would break the claim the reader is
for, that **a read-back is a write**, so the translation between the table and MPFB's
rig format is here once.

**The table.** A bone is ``name``, ``parent`` (``""`` for none), ``head``, ``tail``,
``roll``, ``deform``, ``connect`` and ``collections``; on the way in the last three default to
true, false and ``["Bones"]``, and a compact read leaves out a key at its default. An end is
exactly one kind:

- ``{"joint": "joint-l-elbow"}``, MPFB's ``CUBE`` strategy, the centre of a joint cube;
- ``{"vertex": 1234}``, ``VERTEX``;
- ``{"mean": [1, 2]}``, ``MEAN``, two or more vertices averaged;
- ``{"position": {"forward", "left", "up"}}``, in the character frame. The builder
  **snaps** it by default, the way MPFB's own save matches a bone end (below), and with
  ``"snap": false`` keeps it as MPFB's ``DEFAULT`` strategy, a fixed position that a
  refit does not move.

Any end may carry an ``offset`` in the frame. The reader adds the resolved ``position``
to every end; the builder takes ``position`` as the kind only when no other kind is
given, so the reader's ``position`` beside a ``joint`` is ignored on the way back in.
That is the one place the read shape is wider than the write shape, and it is what lets
a read-back be sent unchanged. ``roll`` is ``"align_z_world_z"``, ``"align_x_world_x"``
(MPFB's two roll strategies, recomputed on every fit) or ``{"degrees": d}``.

**A departure from the request, and why: MPFB's ``DEFAULT`` strategy *is* expressible.**
FR 060 said ``DEFAULT`` and ``XYZ`` have no builder form. ``DEFAULT`` is a fixed position,
which is exactly ``position`` with ``snap: false``, so it reads back as one; only ``XYZ``
(the Rigify heel marker, one vertex per axis) and the ``ALIGN_Z_REFERENCE_Z`` roll are
reported as they are with ``expressible: false``.

**Snapping is MPFB's own matching, not a rule of this module's.** FR 060 said: the nearest
joint within MPFB's ``_MAX_ALLOWED_DIST``, else the nearest vertex. MPFB's save path,
``Rig._match_position_to_strategy()``, does that and one thing more: before settling for a
vertex that is not exact it looks for the pair of vertices whose mean is nearer, which is
how a bone inside the body - a spine, a hip - gets an anchor that moves with the body on
both sides. ``mpfb_store_rig`` runs that matcher on every end anyway, through
``Rig.from_given_armature_context()``, so a builder that snapped differently would build a
rig the store then changes. This snaps through the same public finders
(``find_closest_cube``, ``find_closest_vertex``, ``find_closest_vertex_mean``) in the same
order, and the residual is not kept as an offset, as MPFB keeps none.

**Positions come from MPFB's position info, never from ``mesh.vertices[].co``.**
``Rig.build_basemesh_position_info()`` evaluates the shape keys, so a joint or a vertex is
where it is on the modelled body. A command reading ``co`` would be centimetres off on any
character whose phenotype is not the default, which is the trap the NEXT_STEPS entry this
request came from warned about. The fit is built from a dictionary with no temporary file:
``Rig(basemesh)``, ``rig_header`` and ``rig_definition`` assigned, then the position info.
``Rig.from_json_file_and_basemesh()`` is used only for a catalogue rig, which is a file.

**Coordinates.** MPFB works in the basemesh's local space, which is also the armature's
space once a rig takes the basemesh's place. :class:`Space` is the one conversion between
that and the character frame (``shared/character_frame.py``), whichever object the frame
is taken from.
"""

# MPFB's own capitalisation for the class it hands back, as rig_lookup.py does.
# pylint: disable=invalid-name

__all__ = (
    "BONE_KEYS",
    "DEFAULT_COLLECTION",
    "END_KINDS",
    "END_KEYS",
    "EXACT_METRES",
    "READ_ONLY_BONE_KEYS",
    "ROLL_ALIGNMENTS",
    "Space",
    "armature_definition",
    "authored_marker",
    "catalogue_files",
    "current_version",
    "end_signature",
    "features_from_armature",
    "features_from_definition",
    "fit_definition",
    "fit_file",
    "head_joints",
    "header_for",
    "is_authored",
    "joint_names",
    "joints",
    "mark_authored",
    "max_snap_metres",
    "read_bones",
    "resolve_table",
    "rig_class",
    "rig_file_definition",
    "table_shape_errors",
)

import contextlib
import json
import math
import os
import sys

import bpy
from mathutils import Vector  # pylint: disable=import-error

from . import mpfb_surface
from . import rig_lookup
from .rig_table import BONE_KEYS  # pylint: disable=unused-import
from .rig_table import DEFAULT_COLLECTION
from .rig_table import END_KEYS  # pylint: disable=unused-import
from .rig_table import END_KINDS  # pylint: disable=unused-import
from .rig_table import READ_ONLY_BONE_KEYS  # pylint: disable=unused-import
from .rig_table import ROLL_ALIGNMENTS
from .rig_table import end_kind
from .rig_table import table_shape_errors  # pylint: disable=unused-import
from .character_frame import Frame
from .character_frame import rounded_degrees

# MPFB's own "exact" (``_MAX_DIST_TO_CONSIDER_EXACT``), and the bound FR 060's transfer uses for
# two bone ends being the same place, as MakeRig's auto transfer does.
EXACT_METRES = 0.001

# MPFB's ``_MAX_ALLOWED_DIST``, the radius of every finder, used only if MPFB stops defining it.
_FALLBACK_SNAP_METRES = 0.01

# The object property this add-on stamps on an armature its builder made. It is what lets
# ``create_rig``'s ``replace`` and ``weight_rig`` tell an authored rig from a shipped one
# after a store has made it identifiable as ``custom.*``.
_AUTHORED_PROPERTY = "mpfb_bridge_authored_rig"

# A position, a direction and a degree are rounded where the reader reports them, by the frame.
_ROLL_DIGITS = 4


def rig_class(services):
    """MPFB's ``Rig`` entity, which ``humanservice.py`` imports, or ``MissingFromMpfb``."""
    return mpfb_surface.required_module_level(services, "HumanService", "Rig")


def max_snap_metres(services):
    """The radius MPFB's finders search, read off its own module so the two cannot disagree."""
    module = sys.modules.get(rig_class(services).__module__)
    value = getattr(module, "_MAX_ALLOWED_DIST", None)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0.0:
        return float(value)
    return _FALLBACK_SNAP_METRES


def current_version(services):
    """The rig format version MPFB writes, ``CUR_VERSION`` on the entity's module, or None."""
    value = getattr(sys.modules.get(rig_class(services).__module__), "CUR_VERSION", None)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def authored_marker():
    """The property name, for a test that has to build an authored rig by other means."""
    return _AUTHORED_PROPERTY


def mark_authored(armature_object):
    """Stamp an armature as built by ``create_rig``."""
    armature_object[_AUTHORED_PROPERTY] = 1


def is_authored(armature_object):
    """Whether ``create_rig`` built this armature."""
    return bool(armature_object.get(_AUTHORED_PROPERTY, 0))


# ----------------------------------------------------------------------
# The fit


def _scale_factor(services, basemesh):
    properties = mpfb_surface.general_object_properties(services)
    if properties is None:
        return None
    try:
        value = properties.get_value("scale_factor", entity_reference=basemesh)
    except (KeyError, AttributeError, TypeError):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0.0:
        return float(value)
    return None


def fit_definition(services, basemesh, header, shape_keys=True):
    """A ``Rig`` holding ``header``, its position info built from ``basemesh``. No file, no object.

    ``relative_scale`` is set as ``from_json_file_and_basemesh()`` sets it, so an offset in
    a header that carries a ``scale_factor`` is scaled the same way on either road.
    ``shape_keys`` false fits to the neutral body, the Basis, which is what ``weight_rig``'s
    heat pass weights ([FR 061](../../../feature-requests/done/061-rig-weights-that-hold-up/README.md))
    and the only fit in this add-on that is not to the modelled body.
    """
    Rig = rig_class(services)
    rig = Rig(basemesh)
    rig.rig_header = header
    rig.rig_definition = header["bones"]
    if header.get("scale_factor"):
        scale_factor = _scale_factor(services, basemesh)
        if scale_factor:
            rig.relative_scale = scale_factor / float(header["scale_factor"])
    with _active_shape_key_kept(basemesh):
        rig.build_basemesh_position_info(take_shape_keys_into_account=shape_keys)
    return rig


def fit_file(services, basemesh, path):
    """A catalogue rig fitted to ``basemesh`` in memory, through MPFB's own loader."""
    with _active_shape_key_kept(basemesh):
        return rig_class(services).from_json_file_and_basemesh(path, basemesh)


@contextlib.contextmanager
def _active_shape_key_kept(basemesh):
    """Put back the active shape key, which MPFB's temporary fitting key takes over.

    ``build_basemesh_position_info()`` adds a shape key from the mix and removes it again,
    so the mesh is unchanged, but the panel's selected key is left on whatever index the
    removal lands on. A reading tool should leave the panel as it found it.
    """
    index = basemesh.active_shape_key_index
    try:
        yield
    finally:
        keys = basemesh.data.shape_keys
        if keys is not None and 0 <= index < len(keys.key_blocks):
            basemesh.active_shape_key_index = index


def catalogue_files(services, identifier):
    """``(rig_path, weights_path, weights_from)`` for a catalogue identifier, or Nones.

    Through ``shared/rig_lookup.py``, so a rig read or transferred from here is the file
    ``mpfb_add_rig`` would load, with the weights it would load: ``default_no_toes`` reads
    ``default``'s through MPFB's fallback table, and a ``custom.*`` rig only its own.
    """
    family = rig_lookup.family_of(identifier)
    if family == "custom":
        short_name = rig_lookup.custom_short_name(identifier)
        record = rig_lookup.custom_rig_record(
            rig_lookup.custom_rig_records(services, False), short_name)
        if record is None:
            return (None, None, None)
        path = mpfb_surface.as_path(record.get("path"))
        _has, weights_path, weights_from = rig_lookup.custom_weights(path, short_name)
        return (path, weights_path, weights_from)
    rigs_dir = rig_lookup.rigs_directory(services)
    path = rig_lookup.builtin_rig_file(rigs_dir, identifier)
    if path is None or not os.path.isfile(path):
        return (None, None, None)
    _has, weights_path, weights_from = rig_lookup.builtin_weights(
        services, identifier, os.path.dirname(path))
    return (path, weights_path, weights_from)


def rig_file_definition(path):
    """``(header, definition)`` out of a rig file, without fitting it: what the store compares."""
    with open(path, "r", encoding="utf-8") as json_file:
        data = json.load(json_file)
    if "bones" in data:
        return (data, data["bones"])
    return ({"version": 100, "bones": data}, data)


def head_joints(services, armature_object, fit, space):
    """``({bone: joint cube its head is on, or None}, anchors_from)`` for every bone of a rig.

    The joint is read, not measured, wherever it can be: off the strategy saved on the bone
    (``"armature"``, every rig ``create_rig`` built), else off the catalogue file
    ``identify_rig()`` names (``"catalogue"``, a shipped rig, which carries none). Only a rig
    with neither, a generated Rigify rig or one made by hand, is matched by position, a head
    within :data:`EXACT_METRES` of a cube's centre on this body (``"positions"``). Several bones
    can have their head on one joint - ``eye.L`` and two eyelid bones on ``joint-l-eye`` - and
    no distance would separate them, which is why the reading comes first.
    """
    definition, saved = armature_definition(services, armature_object)
    if saved:
        return ({name: _cube_of(info["head"]) for name, info in definition.items()}, "armature")
    identified = services["RigService"].identify_rig(armature_object)
    if identified and not identified.startswith("rigify_generated") \
            and not identified.endswith("unknown"):
        path = catalogue_files(services, identified)[0]
        if path is not None:
            _header, file_definition = rig_file_definition(path)
            return ({bone.name: _cube_of(file_definition.get(bone.name, {}).get("head") or {})
                     for bone in armature_object.data.bones}, "catalogue")
    cubes = {name: Vector(position) for name, position in fit.position_info.get("cubes", {}).items()}
    found = {}
    for bone in armature_object.data.bones:
        head = space.armature_to_local(armature_object, bone.head_local)
        ranked = sorted(((cubes[name] - head).length, name) for name in cubes)
        found[bone.name] = ranked[0][1] if ranked and ranked[0][0] < EXACT_METRES else None
    return (found, "positions")


def _cube_of(end_info):
    return end_info.get("cube_name") if end_info.get("strategy") == "CUBE" else None


def joint_names(fit):
    """The joint cubes this body has, which is the vocabulary a ``joint`` end takes."""
    return sorted(fit.position_info.get("cubes", {}))


class Space:
    """Basemesh-local space and the character frame, one conversion each way.

    The frame is the rig's when there is one and the basemesh's otherwise; ``create_rig``
    gives the rig the basemesh's place and turn, so a position given before the rig exists
    is the same position after.
    """

    def __init__(self, basemesh, frame_object):
        self.basemesh = basemesh
        self.frame = Frame(frame_object)
        self._local_to_world = basemesh.matrix_world.copy()
        self._world_to_local = self._local_to_world.inverted()

    def point(self, local_point):
        """A basemesh-local position, in the frame, rounded."""
        return self.frame.point(self._local_to_world @ Vector(local_point))

    def offset(self, local_vector):
        """A basemesh-local displacement, in the frame, rounded."""
        return self.frame.offset(self._local_to_world.to_3x3() @ Vector(local_vector))

    def to_local(self, frame_point):
        """``{forward, left, up}`` as a basemesh-local ``Vector``."""
        return self._world_to_local @ self.frame.world_point(frame_point)

    def to_local_offset(self, frame_vector):
        """``{forward, left, up}`` as a basemesh-local displacement."""
        return self._world_to_local.to_3x3() @ self.frame.world_vector(frame_vector)

    def armature_to_local(self, armature_object, armature_point):
        """A position in an armature's own space, as basemesh-local."""
        return self._world_to_local @ armature_object.matrix_world @ Vector(armature_point)


def joints(fit, space):
    """Every joint cube's centre in the frame, as MPFB evaluated it for the fit."""
    cubes = fit.position_info.get("cubes", {})
    return {name: space.point(cubes[name]) for name in sorted(cubes)}


# ----------------------------------------------------------------------
# Reading: MPFB's format to the table


def end_signature(end_info):
    """What makes two ends the same anchor: strategy, anchor and offset to the micrometre.

    ``create_rig`` keeps a bone's weights across a rebuild only when both its ends have the
    same signature, and ``store_rig`` names an end whose strategy MPFB's save changed.
    """
    strategy = end_info.get("strategy")
    if strategy == "CUBE":
        anchor = end_info.get("cube_name")
    elif strategy == "VERTEX":
        anchor = end_info.get("vertex_index")
    elif strategy in ("MEAN", "XYZ"):
        anchor = tuple(end_info.get("vertex_indices") or ())
    else:
        anchor = tuple(round(float(value), 6) for value in end_info.get("default_position") or ())
    offset = tuple(round(float(value), 6) for value in end_info.get("offset") or (0.0, 0.0, 0.0))
    if all(value == 0.0 for value in offset):
        offset = None
    return (strategy, anchor, offset)


def _read_end(end_info, space, located):
    """One end of MPFB's format, as the table reports it."""
    strategy = end_info.get("strategy")
    if strategy == "CUBE":
        row = {"joint": end_info.get("cube_name")}
    elif strategy == "VERTEX":
        row = {"vertex": int(end_info.get("vertex_index"))}
    elif strategy == "MEAN":
        row = {"mean": [int(index) for index in end_info.get("vertex_indices") or ()]}
    elif strategy in (None, "DEFAULT"):
        row = {"snap": False}
    else:
        row = {"strategy": strategy, "expressible": False}
        if "vertex_indices" in end_info:
            row["vertex_indices"] = [int(index) for index in end_info["vertex_indices"]]
    offset = end_info.get("offset")
    if offset and any(float(value) != 0.0 for value in offset):
        row["offset"] = space.offset(offset)
    row["position"] = None if located is None else space.point(located)
    return row


def _read_roll(bone_info):
    strategy = bone_info.get("roll_strategy")
    for spelled, mpfb_name in ROLL_ALIGNMENTS.items():
        if strategy == mpfb_name:
            return spelled
    if strategy:
        row = {"strategy": strategy, "expressible": False}
        if bone_info.get("roll_reference_z") is not None:
            row["reference_z"] = [round(float(value), _ROLL_DIGITS)
                                  for value in bone_info["roll_reference_z"]]
        return row
    return {"degrees": rounded_degrees(float(bone_info.get("roll", 0.0)))}


def features_from_definition(bone_info):
    """What the builder would drop from one bone of a rig file, by name."""
    features = []
    for constraint in bone_info.get("constraints", ()) or ():
        features.append("constraint:{!s}".format(constraint.get("type") or constraint.get("name")))
    if bone_info.get("bendy_bone"):
        features.append("bendy_bone")
    rigify = bone_info.get("rigify") or {}
    if rigify.get("rigify_type"):
        features.append("rigify_type")
    if rigify.get("rigify_parameters"):
        features.append("rigify_parameters")
    if bone_info.get("use_local_location") is False or bone_info.get(
            "use_inherit_rotation") is False or bone_info.get("inherit_scale", "FULL") != "FULL":
        features.append("inheritance")
    return features


def features_from_armature(armature_object, bone_name):
    """What the builder would drop from one bone of a built armature, by name.

    Custom properties are named except MPFB's own (``mpfb_*``), which hold the strategies
    the builder writes itself.
    """
    features = []
    pose_bone = armature_object.pose.bones.get(bone_name)
    bone = armature_object.data.bones.get(bone_name)
    if pose_bone is not None:
        for constraint in pose_bone.constraints:
            features.append("constraint:{!s}".format(constraint.type))
        if getattr(pose_bone, "rigify_type", ""):
            features.append("rigify_type")
        custom = sorted(key for key in pose_bone.keys()
                        if not str(key).startswith("mpfb_") and key not in ("rigify_parameters",))
        features.extend("custom_property:{!s}".format(key) for key in custom)
    if bone is not None:
        if int(getattr(bone, "bbone_segments", 1)) > 1:
            features.append("bendy_bone")
        if (not bone.use_local_location or not bone.use_inherit_rotation
                or bone.inherit_scale != "FULL"):
            features.append("inheritance")
        custom = sorted(key for key in bone.keys() if not str(key).startswith("mpfb_"))
        features.extend("custom_property:{!s}".format(key) for key in custom)
    return features


def armature_definition(services, armature_object):
    """A built armature as MPFB's bone format, with ``use_deform`` beside it.

    The ends are the strategies saved on the bones (``save_strategies()``, which the builder
    asks for), read through ``Rig.get_bone_end_strategy()``; an end with none is ``DEFAULT``
    at the bone's position. Roll is read off the bone's rest matrix, which is what the edit
    bone's roll is, and the roll strategy off the property ``restore_saved_strategies()``
    reads. Returns ``(definition, saved_ends)``, the second counting the ends that had one.
    """
    Rig = rig_class(services)
    definition = {}
    saved_ends = 0
    for bone in armature_object.data.bones:
        info = {
            "parent": bone.parent.name if bone.parent else "",
            "use_connect": bool(bone.use_connect),
            "use_deform": bool(bone.use_deform),
            "collections": sorted(collection.name for collection in bone.collections),
            "roll": float(bpy.types.Bone.AxisRollFromMatrix(bone.matrix_local.to_3x3())[1]),
        }
        # A registered property on Bone, not an ID property: MPFB's own
        # restore_saved_strategies() reads it with bone.get() and so never finds it, and gets
        # the roll strategy from the edit bone instead. Read the way it is stored.
        roll_strategy = getattr(bone, "mpfb_roll_strategy", "") or bone.get("mpfb_roll_strategy")
        if roll_strategy:
            info["roll_strategy"] = str(roll_strategy)
        for key, is_tail, local in (("head", False, bone.head_local),
                                    ("tail", True, bone.tail_local)):
            end, _force = Rig.get_bone_end_strategy(bone, is_tail)
            if end is None:
                end = {"strategy": "DEFAULT"}
            else:
                saved_ends += 1
            end["default_position"] = [float(value) for value in local]
            info[key] = end
        definition[bone.name] = info
    return (definition, saved_ends)


def read_bones(definition, space, locate, names=None, compact=False, features=None):
    """The table for a definition in MPFB's format: ``(bones, features_not_carried)``.

    ``locate(bone_name, "head"|"tail", end_info)`` is where the end actually is, basemesh
    local, or ``None``. ``features(bone_name, bone_info)`` names what would be dropped;
    only bones that have any are listed, keyed by name, so the common case costs nothing.
    ``compact`` drops the read-only ``position`` of every end that is not a position, and any
    key at the builder's default, so a compact read-back is still a write.
    """
    rows = []
    dropped = {}
    for bone_name, info in definition.items():
        if names is not None and bone_name not in names:
            continue
        row = {"name": bone_name, "parent": info.get("parent") or ""}
        for key in ("head", "tail"):
            end = _read_end(info[key], space, locate(bone_name, key, info[key]))
            if compact and not ("snap" in end and end["snap"] is False):
                end.pop("position", None)
            row[key] = end
        row["roll"] = _read_roll(info)
        deform = info.get("use_deform", True) is not False
        connect = bool(info.get("use_connect"))
        collections = list(info.get("collections") or ()) or [DEFAULT_COLLECTION]
        # Every key is on a full row. A compact row, which the caller chose, leaves out a key
        # at the builder's default, which the builder then supplies: the one place the
        # responses specification lets a key be absent rather than null.
        if not compact or not deform:
            row["deform"] = deform
        if not compact or connect:
            row["connect"] = connect
        if not compact or collections != [DEFAULT_COLLECTION]:
            row["collections"] = collections
        rows.append(row)
        if features is not None and not compact:
            named = features(bone_name, info)
            if named:
                dropped[bone_name] = named
    return (rows, dropped)


# ----------------------------------------------------------------------
# Writing: the table to MPFB's format


def _snapped(fit, local, max_snap):
    """Where MPFB's own matcher would anchor a position, as ``(end_info, snapped_to)``.

    The order of ``Rig._match_position_to_strategy()``: a joint within the radius, unless a
    vertex is exact and the joint is not; otherwise a vertex mean, if one is nearer than the
    vertex; otherwise the vertex, and failing everything the nearest vertex at any distance.
    """
    position = list(local)
    cube_name, cube_distance = fit.find_closest_cube(position, max_snap)
    vertex_index, vertex_distance = fit.find_closest_vertex(position, max_snap)
    if cube_name is not None and not (
            vertex_index is not None and vertex_distance < EXACT_METRES < cube_distance):
        return ({"strategy": "CUBE", "cube_name": cube_name},
                {"joint": cube_name, "distance": round(float(cube_distance), 4)})
    best = vertex_distance if vertex_index is not None else None
    if best is None or best > EXACT_METRES:
        search = (2.0 * max_snap) if vertex_index is not None else None
        indices, mean_distance = fit.find_closest_vertex_mean(position, search_radius=search)
        if indices is not None and (best is None or mean_distance < best):
            indices = [int(index) for index in indices]
            return ({"strategy": "MEAN", "vertex_indices": indices},
                    {"mean": indices, "distance": round(float(mean_distance), 4)})
    if vertex_index is None:
        vertex_index, vertex_distance = fit.find_closest_vertex(position, None)
    return ({"strategy": "VERTEX", "vertex_index": int(vertex_index)},
            {"vertex": int(vertex_index), "distance": round(float(vertex_distance), 4)})


def _resolved_end(fit, space, end, where, vertex_count, max_snap, errors):
    """One table end as MPFB's ``{strategy, ...}``, with what the answer says about it.

    Returns ``(end_info, snapped_to, follows_body)``, or ``(None, None, None)`` with a row
    added to ``errors``.
    """
    kind = end_kind(end)[0]
    cubes = fit.position_info.get("cubes", {})
    snapped_to = None
    follows = True
    if kind == "joint":
        if end["joint"] not in cubes:
            errors.append({"where": where, "error": "unknown_joint",
                           "message": "{:s}: there is no joint cube {!r} on this body; "
                                      "mpfb_get_rig_definition with include_joints lists "
                                      "them".format(where, end["joint"])})
            return (None, None, None)
        info = {"strategy": "CUBE", "cube_name": end["joint"]}
    elif kind == "vertex":
        if end["vertex"] >= vertex_count:
            errors.append({"where": where, "error": "vertex_out_of_range",
                           "message": "{:s}: vertex {:d} does not exist; the basemesh has "
                                      "{:d}".format(where, end["vertex"], vertex_count)})
            return (None, None, None)
        info = {"strategy": "VERTEX", "vertex_index": end["vertex"]}
    elif kind == "mean":
        outside = [index for index in end["mean"] if index >= vertex_count]
        if outside:
            errors.append({"where": where, "error": "vertex_out_of_range",
                           "message": "{:s}: vertex {:d} does not exist; the basemesh has "
                                      "{:d}".format(where, outside[0], vertex_count)})
            return (None, None, None)
        info = {"strategy": "MEAN", "vertex_indices": list(end["mean"])}
    else:
        local = space.to_local(end["position"])
        if end.get("snap", True):
            info, snapped_to = _snapped(fit, local, max_snap)
        else:
            info = {"strategy": "DEFAULT"}
            follows = False
        info["default_position"] = [float(value) for value in local]
    if "offset" in end:
        offset = space.to_local_offset(end["offset"])
        if offset.length > 0.0:
            info["offset"] = [float(value) for value in offset]
    if "default_position" not in info:
        located = fit.get_best_location_from_strategy(dict(info, default_position=None),
                                                      use_default=False)
        info["default_position"] = [float(value) for value in located]
    return (info, snapped_to, follows)


def resolve_table(fit, space, bones, vertex_count, max_snap):
    """A table, every end resolved against this body, before anything is built.

    Returns ``(definition, notes, errors)``: ``definition`` in MPFB's bone format,
    ``notes`` per bone name (``snapped_to`` per end and whether each end follows the body),
    and ``errors`` as ``{where, error, message}``. Any error means nothing may be built.
    """
    definition = {}
    notes = {}
    errors = []
    for position, bone in enumerate(bones):
        where = "bones[{:d}]".format(position)
        info = {
            "parent": bone.get("parent", "") or "",
            "use_connect": bool(bone.get("connect", False)),
            "use_local_location": True,
            "use_inherit_rotation": True,
            "inherit_scale": "FULL",
            "rigify": {},
            "collections": list(bone.get("collections") or [DEFAULT_COLLECTION]),
            "roll": 0.0,
        }
        roll = bone.get("roll", {"degrees": 0.0})
        if isinstance(roll, str):
            info["roll_strategy"] = ROLL_ALIGNMENTS[roll]
        else:
            info["roll"] = math.radians(float(roll["degrees"]))
        note = {"deform": bool(bone.get("deform", True)), "snapped_to": {}, "fixed_ends": []}
        for key in ("head", "tail"):
            end_info, snapped_to, follows = _resolved_end(
                fit, space, bone[key], "{:s}.{:s}".format(where, key), vertex_count, max_snap,
                errors)
            if end_info is None:
                continue
            info[key] = end_info
            if snapped_to is not None:
                note["snapped_to"][key] = snapped_to
            if not follows:
                note["fixed_ends"].append(key)
        if "head" in info and "tail" in info:
            head = fit.get_best_location_from_strategy(info["head"])
            tail = fit.get_best_location_from_strategy(info["tail"])
            if (Vector(tail) - Vector(head)).length < EXACT_METRES:
                errors.append({"where": where, "error": "zero_length_bone",
                               "message": "{:s}: '{:s}' would have its head and tail within "
                                          "a millimetre of each other on this body, and "
                                          "Blender deletes a bone of zero length".format(
                                              where, bone["name"])})
        definition[bone["name"]] = info
        notes[bone["name"]] = note
    return (definition, notes, errors)


def header_for(services, basemesh, definition):
    """A version-110 rig header around ``definition``, its collections in order of first use."""
    collections = []
    for info in definition.values():
        for name in info.get("collections") or ():
            if name not in collections:
                collections.append(name)
    header = {"bones": definition, "collections": collections, "is_subrig": False,
              "version": 110}
    scale_factor = _scale_factor(services, basemesh)
    if scale_factor:
        header["scale_factor"] = scale_factor
    return header
