"""
A rig's weighting, read one way: what counts as a bone weight, what the readings say, the clean, and
the helper rules.

**One implementation, imported by every command that needs it.** See [`__init__.py`](__init__.py)
for why this directory exists beside ``commands/``. Three commands use it
([FR 061](../../../feature-requests/done/061-rig-weights-that-hold-up/README.md)): ``weight_rig``
writes a weighting and reports its counts, ``check_rig_weights`` reads one, and ``store_rig``
names the deforming bones with no weights. A character weighted and then checked gets the same
counts twice because both are this module's.

**What counts as a bone weight is decided once, by :func:`read_weights`.** A group counts when it
is named after a **deforming** bone of the rig and the weight is above :data:`NO_WEIGHT`, MPFB's
own ``exclude_weights_below``. Every other group on a body - ``mhmask-*``, ``helper-*``,
``joint-*``, ``body``, a garment's delete group, the groups of a rig no longer on it - is never
counted, trimmed or normalised. That matters most for the masks: the modifiers MPFB builds from
``mhmask-*`` read their exact values, and a normalised mask is a broken one.

**The group vocabulary is MPFB's.** Which groups are the skin, which a helper and which a joint
cube comes from ``ObjectService.get_base_mesh_vertex_group_definition()``, which reads
``basemesh_vertex_groups.json``; the members are read off the live mesh, so a body built with
fewer helpers is read as it is. Nothing here lists a helper by hand except :data:`HELPER_RULES`,
which says what to do with the ones it names, and a helper it does not name falls to
``nearest`` and is reported.

**The helper rules.** Heat weighting leaves the interior shells unweighted and a transfer can
too, and a nearest-skin fill puts an eye on its eyelid: on ``default`` the eyeball is 100%
``eye.L`` while the nearest skin is ``orbicularis03.L``. So each helper takes one of three
rules:

- ``rigid``, the eyes and both sets of teeth: the whole helper to one deforming bone at 1.0.
  The candidates are the deforming bones whose **head is on the helper's anchor joint**, read
  off the bone's stored ``CUBE`` strategy rather than measured, because ``eye.L``,
  ``orbicularis03.L`` and ``orbicularis04.L`` all have their head on ``joint-l-eye`` and no
  distance separates them. One candidate is taken (``only_candidate``); among several, the one
  whose name carries the anchor's word (``anchor_name``); otherwise, and for the upper teeth,
  which have no anchor, the bone carrying the most weight over the helper's nearest skin
  (``nearest_dominant``). ``helper_bones`` overrides any of it (``helper_bones``).
- ``interior_chain``, the tongue: each vertex blends the two nearest deforming bones lying
  wholly inside the helper's bounds, by inverse distance; with none, the tongue follows the
  lower teeth's bone (``follows``).
- ``nearest``, everything else, the joint cubes included: an inverse-distance blend of the
  :data:`NEAREST_K` nearest weighted skin vertices' weights.

A rule fills only the vertices that have no deform weight, so a transfer's own helper weights
stay as the source rig's author made them.

**The clean** (:func:`clean`) drops a weight below ``min_weight``, keeps a vertex's
``max_influences`` largest, and normalises what is left to 1.0, per vertex and over the deform
groups only. Blender normalises at deform time (``armature_deform.cc``), so none of this shows
in Blender; it shows in an engine that takes weights as given, and three of MPFB's own shipped
files are unnormalised.

**The mirror** is MPFB's ``hm08.mirror``, read off the data file through ``LocationService``
rather than through ``TargetService._load_mirror_table()``, which is private; the format is
``<from> <to> <l|r|m>``. The symmetry reading compares each pair both ways round, so it needs to
know which side a line's ``from`` is on no more than a mirrored weighting does.

Plain Blender apart from :func:`layout` and :func:`mirror_pairs`, which ask MPFB for its group
vocabulary and its data directory, and take ``services`` for it.
"""

__all__ = (
    "FAR_MIN_METRES",
    "FAR_RATIO",
    "HELPER_RULES",
    "Layout",
    "NEAREST_K",
    "NORMALISED_TOLERANCE",
    "NO_WEIGHT",
    "REACH_WEIGHT",
    "RIGID_SHARE",
    "RULES",
    "SIDES",
    "bone_rows",
    "by_group",
    "by_vertex",
    "clean",
    "coverage",
    "deforming_bones",
    "distance_to_segment",
    "fill",
    "helper_rows",
    "histogram",
    "influences",
    "layout",
    "mirror_pairs",
    "partner",
    "reach_limit",
    "read_weights",
    "symmetry",
    "unweighted_bones",
    "unweighted_counts",
    "write_groups",
)

import os

from mathutils import Vector  # pylint: disable=import-error
from mathutils.kdtree import KDTree  # pylint: disable=import-error

from . import mpfb_surface

# A weight at or below this is no weight, as MPFB's get_weights() drops below 0.0001.
NO_WEIGHT = 0.0001

# A vertex whose deform weights add up to further than this from 1.0 is unnormalised.
NORMALISED_TOLERANCE = 0.01

# A helper whose dominant bone carries this share of its weight is rigid.
RIGID_SHARE = 0.99

# A vertex counts towards a bone's reach when its weight is above this; a smoothed tail far
# away is not what the reach is about.
REACH_WEIGHT = 0.1

# A vertex is far from a bone beyond FAR_RATIO times the bone's length, and never nearer than
# FAR_MIN_METRES, so a finger's bone is not held to a centimetre.
FAR_RATIO = 1.0
FAR_MIN_METRES = 0.05

# How many weighted skin vertices the nearest fill blends. Settled by FR 061's live check on
# the skirt with the hips abducted, which hangs between the legs.
NEAREST_K = 4

# A weight the clean changed by less than this is unchanged: vertex groups hold float32, and a
# total of several is never exactly 1.0.
_UNCHANGED = 1e-4

# How many rows a reading keeps of a list it ranks, worst first.
MAX_WORST = 10

# The side suffixes a mirror pairs bones by, left first.
SIDES = ((".L", ".R"), ("_l", "_r"))

RULES = ("rigid", "interior_chain", "nearest")

_HELPER_PREFIX = "helper-"
_JOINT_PREFIX = "joint-"
_BODY_GROUP = "body"

# MPFB's helper groups and what to do with each. ``anchor`` is the joint a rigid helper's bone
# has its head on, ``word`` what that bone's name carries, ``follows`` the helper whose bone an
# interior chain with no bone of its own goes with. A helper not named here is ``nearest``.
HELPER_RULES = {
    "helper-l-eye": {"rule": "rigid", "anchor": "joint-l-eye", "word": "eye"},
    "helper-r-eye": {"rule": "rigid", "anchor": "joint-r-eye", "word": "eye"},
    "helper-lower-teeth": {"rule": "rigid", "anchor": "joint-mouth", "word": "jaw"},
    "helper-upper-teeth": {"rule": "rigid", "anchor": None, "word": None},
    "helper-tongue": {"rule": "interior_chain", "follows": "helper-lower-teeth"},
    "helper-l-eyelashes-1": {"rule": "nearest"},
    "helper-l-eyelashes-2": {"rule": "nearest"},
    "helper-r-eyelashes-1": {"rule": "nearest"},
    "helper-r-eyelashes-2": {"rule": "nearest"},
    "helper-hair": {"rule": "nearest"},
    "helper-genital": {"rule": "nearest"},
    "helper-skirt": {"rule": "nearest"},
    "helper-tights": {"rule": "nearest"},
}

# Digits a weight and a distance are reported to.
_WEIGHT_DIGITS = 4
_METRE_DIGITS = 4


# ----------------------------------------------------------------------
# The body's layout, in MPFB's vocabulary


class Layout:
    """Which vertex is skin, which a helper and which a joint cube, by MPFB's groups.

    ``classes`` per vertex is ``"body"``, ``"helper"`` or ``"joint_cube"``; ``helpers`` maps each
    helper group on the mesh to its vertices, and ``helper_of`` a vertex to its helper. A vertex in
    no group of the vocabulary is skin, as FR 060's fill took it.
    """

    __slots__ = ("classes", "helpers", "helper_of", "vocabulary")

    def __init__(self, classes, helpers, helper_of, vocabulary):
        self.classes = classes
        self.helpers = helpers
        self.helper_of = helper_of
        self.vocabulary = vocabulary

    def skin(self):
        """The skin's vertex indices."""
        return [index for index, kind in enumerate(self.classes) if kind == "body"]


def layout(services, basemesh):
    """The basemesh's :class:`Layout`, its group names from MPFB's file and members off the mesh."""
    definition = services["ObjectService"].get_base_mesh_vertex_group_definition()
    vocabulary = set(str(name) for name in definition)
    joint = {}
    helper = {}
    for group in basemesh.vertex_groups:
        if group.name not in vocabulary:
            continue
        if group.name.startswith(_JOINT_PREFIX):
            joint[group.index] = group.name
        elif group.name.startswith(_HELPER_PREFIX):
            helper[group.index] = group.name
    classes = []
    helpers = {name: [] for name in sorted(helper.values())}
    helper_of = {}
    for vertex in basemesh.data.vertices:
        indices = [element.group for element in vertex.groups]
        if any(index in joint for index in indices):
            classes.append("joint_cube")
            continue
        names = sorted(helper[index] for index in indices if index in helper)
        if names:
            classes.append("helper")
            helpers[names[0]].append(vertex.index)
            helper_of[vertex.index] = names[0]
        else:
            classes.append("body")
    return Layout(classes, helpers, helper_of, vocabulary)


# ----------------------------------------------------------------------
# The one reading of a weighting


def deforming_bones(armature):
    """The rig's deforming bones, in its own order."""
    return [bone.name for bone in armature.data.bones if bone.use_deform]


def read_weights(mesh_object, names, floor=NO_WEIGHT):
    """``{group: {vertex: weight}}`` for the groups in ``names`` that exist, above ``floor``.

    The one place that decides what counts as a bone weight: pass the deforming bones' names.
    ``clean`` reads with ``floor`` 0.0, so that a ``min_weight`` below :data:`NO_WEIGHT` means
    what it says.
    """
    by_index = {group.index: group.name for group in mesh_object.vertex_groups
                if group.name in names}
    weights = {name: {} for name in by_index.values()}
    for vertex in mesh_object.data.vertices:
        for element in vertex.groups:
            name = by_index.get(element.group)
            if name is not None and element.weight > floor:
                weights[name][vertex.index] = float(element.weight)
    return weights


def write_groups(mesh_object, weights):
    """Replace each named group's content with ``weights[name]``, creating it if need be."""
    every = list(range(len(mesh_object.data.vertices)))
    for name, entries in weights.items():
        group = mesh_object.vertex_groups.get(name)
        if group is None:
            group = mesh_object.vertex_groups.new(name=name)
        group.remove(every)
        for index, weight in entries.items():
            group.add([index], min(1.0, weight), "REPLACE")


def by_vertex(weights):
    """``{vertex: {group: weight}}`` out of ``{group: {vertex: weight}}``."""
    rows = {}
    for name, entries in weights.items():
        for index, weight in entries.items():
            rows.setdefault(index, {})[name] = weight
    return rows


def by_group(rows, names):
    """The inverse of :func:`by_vertex`, with every name in ``names`` present."""
    weights = {name: {} for name in names}
    for index, entries in rows.items():
        for name, weight in entries.items():
            weights.setdefault(name, {})[index] = weight
    return weights


def unweighted_counts(the_layout, rows):
    """How many vertices have no deform weight, as ``body``, ``helper`` and ``joint_cube``."""
    counts = {"body": 0, "helper": 0, "joint_cube": 0}
    for index, kind in enumerate(the_layout.classes):
        if not rows.get(index):
            counts[kind] += 1
    return counts


def unweighted_bones(weights, deforming):
    """The deforming bones with no group, or an empty one."""
    return sorted(name for name in deforming if not weights.get(name))


def histogram(rows, vertex_count):
    """``{"0": n, "1": n, ...}``: how many vertices have each number of deform influences."""
    counts = {}
    for index in range(vertex_count):
        count = len(rows.get(index, ()))
        counts[count] = counts.get(count, 0) + 1
    return {str(count): counts[count] for count in sorted(counts)}


# ----------------------------------------------------------------------
# The readings


def coverage(the_layout, weights, deforming, mesh_object, rig_bones):
    """Unweighted vertices by class and helper, bones with no group, and groups that are no bone's.

    ``helpers`` names only the helper groups with an unweighted vertex, so a weighted body's
    answer is short.

    ``orphan_groups`` are named after a bone of the rig that does not deform, which is a weighting
    left behind; ``other_groups`` after nothing in MPFB's vocabulary, no mask and no bone of the
    rig, such as a garment's delete group or a rig no longer on the body.
    """
    weighted = set()
    for entries in weights.values():
        weighted.update(entries)
    counts = {"body": 0, "joint_cube": 0}
    helpers = {name: 0 for name in the_layout.helpers}
    for index, kind in enumerate(the_layout.classes):
        if index in weighted:
            continue
        if kind == "helper":
            helpers[the_layout.helper_of[index]] += 1
        else:
            counts[kind] += 1
    bones = set(deforming)
    rig_bones = set(rig_bones)
    orphans = []
    others = []
    for group in mesh_object.vertex_groups:
        name = group.name
        if name in bones or name in the_layout.vocabulary or name.startswith("mhmask-"):
            continue
        if name in rig_bones:
            orphans.append(name)
        else:
            others.append(name)
    return {
        "unweighted": dict(counts,
                           helpers={name: count for name, count in helpers.items() if count},
                           total=counts["body"] + counts["joint_cube"] + sum(helpers.values())),
        "unweighted_bones": unweighted_bones(weights, deforming),
        "orphan_groups": sorted(orphans),
        "other_groups": sorted(others),
    }


def influences(rows, vertex_count):
    """The influence histogram, the most any vertex has, and the vertices that do not add up to 1."""
    unnormalised = []
    for index, entries in rows.items():
        total = sum(entries.values())
        if abs(total - 1.0) > NORMALISED_TOLERANCE:
            unnormalised.append((abs(total - 1.0), index, total))
    unnormalised.sort(reverse=True)
    return {
        "histogram": histogram(rows, vertex_count),
        "max_influences": max((len(entries) for entries in rows.values()), default=0),
        "unnormalised": len(unnormalised),
        "worst_unnormalised": [{"vertex": index, "total": round(total, _WEIGHT_DIGITS)}
                               for _gap, index, total in unnormalised[:MAX_WORST]],
    }


def distance_to_segment(point, head, tail):
    """How far ``point`` is from the segment ``head``-``tail``; all three ``Vector``."""
    line = tail - head
    length_squared = line.length_squared
    if length_squared == 0.0:
        return (point - head).length
    factor = max(0.0, min(1.0, (point - head).dot(line) / length_squared))
    return (point - (head + line * factor)).length


def reach_limit(head, tail):
    """How far from a bone a weighted vertex may sit before it is far: see :data:`FAR_RATIO`."""
    return max(FAR_RATIO * (tail - head).length, FAR_MIN_METRES)


def bone_rows(weights, deforming, segments, positions, cap):
    """Per deforming bone, ``vertex_count``, ``weight_sum``, ``reach`` and ``far_vertices``.

    ``segments`` maps a bone to ``(head, tail)`` and ``positions`` a vertex to where it is, in one
    space. Rows are ranked by ``far_vertices``, then ``weight_sum``, and cut at ``cap``; the totals
    cover every bone.
    """
    rows = []
    for name in deforming:
        entries = weights.get(name, {})
        head, tail = segments[name]
        limit = reach_limit(head, tail)
        reach = 0.0
        far = 0
        for index, weight in entries.items():
            if weight <= REACH_WEIGHT:
                continue
            distance = distance_to_segment(Vector(positions[index]), head, tail)
            reach = max(reach, distance)
            if distance > limit:
                far += 1
        rows.append({"name": name, "vertex_count": len(entries),
                     "weight_sum": round(sum(entries.values()), 2),
                     "reach": round(reach, _METRE_DIGITS),
                     "reach_limit": round(limit, _METRE_DIGITS),
                     "far_vertices": far})
    rows.sort(key=lambda row: (-row["far_vertices"], -row["weight_sum"], row["name"]))
    return {
        "bone_count": len(rows),
        "bones_truncated": len(rows) > cap,
        "bones_with_far_vertices": sum(1 for row in rows if row["far_vertices"]),
        "far_vertices_total": sum(row["far_vertices"] for row in rows),
        "bones_without_weights": sum(1 for row in rows if not row["vertex_count"]),
        "rows": rows[:cap],
    }


def helper_rows(the_layout, rows):
    """Per helper group, its dominant bone and share, and whether it is ``rigid``."""
    answer = []
    for name in sorted(the_layout.helpers):
        members = the_layout.helpers[name]
        totals = {}
        unweighted = 0
        for index in members:
            entries = rows.get(index)
            if not entries:
                unweighted += 1
                continue
            for bone, weight in entries.items():
                totals[bone] = totals.get(bone, 0.0) + weight
        overall = sum(totals.values())
        dominant = max(sorted(totals), key=totals.get) if totals else None
        share = (totals[dominant] / overall) if dominant is not None and overall > 0.0 else 0.0
        answer.append({
            "group": name,
            "rule": HELPER_RULES.get(name, {"rule": "nearest"})["rule"],
            "vertex_count": len(members),
            "unweighted": unweighted,
            "dominant_bone": dominant,
            "dominant_share": round(share, 3),
            "bone_count": len(totals),
            "rigid": dominant is not None and unweighted == 0 and share >= RIGID_SHARE,
        })
    return answer


def partner(name):
    """``(other side's name, True)`` for a sided bone, ``(name, False)`` for a centre one."""
    for left, right in SIDES:
        for own, other in ((left, right), (right, left)):
            if name.endswith(own):
                return (name[:-len(own)] + other, True)
    return (name, False)


def mirror_pairs(services, side="l"):
    """``(from, to)`` vertex pairs out of MPFB's ``hm08.mirror``, the lines marked ``side``."""
    directory = mpfb_surface.as_path(services["LocationService"].get_mpfb_data("mesh_metadata"))
    pairs = []
    with open(os.path.join(directory, "hm08.mirror"), "r", encoding="utf-8") as mirror_file:
        for line in mirror_file:
            parts = line.split()
            if len(parts) >= 3 and parts[2] == side:
                pairs.append((int(parts[0]), int(parts[1])))
    return pairs


def symmetry(weights, deforming, pairs):
    """Per ``.L``/``.R`` pair and centre bone, how far a weighting is from its mirror image.

    For mirrored vertices ``a`` and ``b`` and bones ``P`` and ``Q``, a symmetric weighting has
    ``P(a) == Q(b)`` and ``P(b) == Q(a)``; both are compared, so no line's side is assumed.
    Only vertices where either side carries weight are counted in the mean.
    """
    rows = []
    without = []
    seen = set()
    for name in deforming:
        if name in seen:
            continue
        other, sided = partner(name)
        if sided and other not in deforming:
            without.append(name)
            continue
        seen.update((name, other))
        own = weights.get(name, {})
        theirs = weights.get(other, {})
        largest = 0.0
        total = 0.0
        counted = 0
        for first, second in pairs:
            for one, two in ((first, second), (second, first)):
                a = own.get(one, 0.0)
                b = theirs.get(two, 0.0)
                if a == 0.0 and b == 0.0:
                    continue
                difference = abs(a - b)
                largest = max(largest, difference)
                total += difference
                counted += 1
        rows.append({"bones": [name, other] if sided else [name],
                     "max_difference": round(largest, _WEIGHT_DIGITS),
                     "mean_difference": round(total / counted, _WEIGHT_DIGITS) if counted else 0.0,
                     "vertices_compared": counted})
    rows.sort(key=lambda row: (-row["max_difference"], -row["mean_difference"], row["bones"]))
    return {
        "pairs_compared": len(rows),
        "max_difference": rows[0]["max_difference"] if rows else 0.0,
        "pairs_over_0_1": sum(1 for row in rows if row["max_difference"] > 0.1),
        "worst": rows[:MAX_WORST],
        "bones_without_partner": sorted(without),
    }


# ----------------------------------------------------------------------
# The clean


def clean(rows, min_weight, max_influences):
    """Trim, cap and normalise each vertex's deform weights. Returns ``(rows, report)``.

    ``rows`` is :func:`by_vertex`'s shape and is not changed; the answer is new. A vertex whose
    weights are all trimmed away keeps its largest, so the clean never unweights a vertex.
    """
    cleaned = {}
    trimmed = 0
    normalised = 0
    largest_removed = 0.0
    changed_groups = set()
    for index, entries in rows.items():
        ranked = sorted(entries.items(), key=lambda item: (-item[1], item[0]))
        kept = [(name, weight) for name, weight in ranked if weight >= min_weight]
        if not kept and ranked:
            kept = ranked[:1]
        if max_influences is not None:
            kept = kept[:max_influences]
        removed = [(name, weight) for name, weight in ranked if (name, weight) not in kept]
        if removed:
            trimmed += 1
            largest_removed = max(largest_removed, max(weight for _name, weight in removed))
            changed_groups.update(name for name, _weight in removed)
        total = sum(weight for _name, weight in kept)
        result = {}
        if total > 0.0:
            if abs(total - 1.0) > _UNCHANGED:
                normalised += 1
            for name, weight in kept:
                value = weight / total
                if abs(value - entries[name]) > _UNCHANGED:
                    changed_groups.add(name)
                result[name] = value
        cleaned[index] = result
    return (cleaned, {
        "vertices_trimmed": trimmed,
        "vertices_normalised": normalised,
        "max_weight_removed": round(largest_removed, _WEIGHT_DIGITS),
        "groups_changed": sorted(changed_groups),
    })


# ----------------------------------------------------------------------
# The fill


def _tree(points):
    tree = KDTree(len(points))
    for slot, point in enumerate(points):
        tree.insert(point, slot)
    tree.balance()
    return tree


def _blend(found, rows):
    """An inverse-distance blend of the weights of ``found``'s ``(slot index, distance)`` vertices."""
    blended = {}
    exact = [index for index, distance in found if distance < 1e-9]
    if exact:
        return dict(rows[exact[0]])
    total = 0.0
    for index, distance in found:
        factor = 1.0 / distance
        total += factor
        for name, weight in rows[index].items():
            blended[name] = blended.get(name, 0.0) + factor * weight
    return {name: weight / total for name, weight in blended.items()} if total else {}


def _nearest_dominant(members, rows, sources, tree, positions, candidates):
    """Of ``candidates`` (every bone when ``None``), the one carrying most weight over the nearest skin."""
    totals = {}
    for index in members:
        _co, slot, _distance = tree.find(positions[index])
        for name, weight in rows[sources[slot]].items():
            if candidates is None or name in candidates:
                totals[name] = totals.get(name, 0.0) + weight
    if not totals:
        return None
    return max(totals, key=lambda name: (totals[name], name))


def _rigid_choice(spec, deforming, anchors, chooser):
    """``(bone, chosen_by, candidates)`` for a rigid helper's rule entry."""
    anchor = spec.get("anchor")
    candidates = sorted(name for name in deforming if anchor and anchors.get(name) == anchor)
    if len(candidates) == 1:
        return (candidates[0], "only_candidate", candidates)
    if len(candidates) > 1:
        named = [name for name in candidates if spec.get("word") and spec["word"] in name.lower()]
        if len(named) == 1:
            return (named[0], "anchor_name", candidates)
        return (chooser(named or candidates), "nearest_dominant", candidates)
    return (chooser(None), "nearest_dominant", candidates)


def _interior_chain(members, positions, segments, deforming):
    """``{vertex: {bone: weight}}`` over the bones wholly inside the members' bounds, or None."""
    low = [min(positions[index][axis] for index in members) for axis in range(3)]
    high = [max(positions[index][axis] for index in members) for axis in range(3)]

    def inside(point):
        return all(low[axis] <= point[axis] <= high[axis] for axis in range(3))

    bones = [name for name in deforming
             if inside(segments[name][0]) and inside(segments[name][1])]
    if not bones:
        return (None, [])
    answer = {}
    for index in members:
        point = Vector(positions[index])
        ranked = sorted((distance_to_segment(point, segments[name][0], segments[name][1]), name)
                        for name in bones)[:2]
        if ranked[0][0] < 1e-9:
            answer[index] = {ranked[0][1]: 1.0}
            continue
        factors = {name: 1.0 / distance for distance, name in ranked}
        total = sum(factors.values())
        answer[index] = {name: factor / total for name, factor in factors.items()}
    return (answer, sorted(bones))


def fill(the_layout, rows, positions, deforming, anchors, segments, helper_bones=None,
         apply_rules=True, k=None):
    """Give every vertex with no deform weight some, by the helper rules. Returns ``(rows, report)``.

    ``rows`` is :func:`by_vertex`'s shape and is changed in place. ``positions`` per vertex and
    ``segments`` per deforming bone (``(head, tail)`` ``Vector``) are in one space, the body the
    bones are fitted to. ``anchors`` maps a bone to the joint its head is on. With ``apply_rules``
    false every vertex is ``nearest``, which is what a call writing only some bones gets.
    """
    k = NEAREST_K if k is None else k
    helper_bones = helper_bones or {}
    sources = [index for index in the_layout.skin() if rows.get(index)]
    report = {"filled": 0, "helpers": [], "helpers_not_in_table": []}
    if not sources:
        return (rows, report)
    tree = _tree([positions[index] for index in sources])

    def chooser_for(members):
        return lambda candidates: _nearest_dominant(members, rows, sources, tree, positions,
                                                    candidates)

    missing = [index for index in range(len(the_layout.classes)) if not rows.get(index)]
    missing_set = set(missing)
    done = set()
    chosen = {}
    if apply_rules:
        ordered = sorted(the_layout.helpers,
                         key=lambda name: HELPER_RULES.get(name, {}).get("rule") != "rigid")
        for name in ordered:
            members = [index for index in the_layout.helpers[name] if index in missing_set]
            if not members:
                continue
            spec = HELPER_RULES.get(name)
            if spec is None:
                report["helpers_not_in_table"].append(name)
                spec = {"rule": "nearest"}
            row = {"group": name, "vertex_count": len(members)}
            if name in helper_bones:
                bone, chosen_by, candidates = (helper_bones[name], "helper_bones", [])
                spec = dict(spec, rule="rigid")
            elif spec["rule"] == "rigid":
                bone, chosen_by, candidates = _rigid_choice(spec, deforming, anchors,
                                                            chooser_for(members))
            else:
                bone, chosen_by, candidates = (None, None, [])
            if spec["rule"] == "rigid":
                if bone is None:
                    continue
                for index in members:
                    rows[index] = {bone: 1.0}
                chosen[name] = bone
                row.update(rule="rigid", bone=bone, chosen_by=chosen_by,
                           candidates=[other for other in candidates if other != bone])
            elif spec["rule"] == "interior_chain":
                chain, bones = _interior_chain(members, positions, segments, deforming)
                if chain is None:
                    bone = chosen.get(spec["follows"])
                    if bone is None:
                        bone = _rigid_choice(HELPER_RULES[spec["follows"]], deforming, anchors,
                                             chooser_for(members))[0]
                    if bone is None:
                        continue
                    for index in members:
                        rows[index] = {bone: 1.0}
                    row.update(rule="interior_chain", bones=[bone], follows=spec["follows"])
                else:
                    rows.update(chain)
                    row.update(rule="interior_chain", bones=bones)
            else:
                continue
            done.update(members)
            report["helpers"].append(row)
    nearest_by_helper = {}
    for index in missing:
        if index in done:
            continue
        found = [(sources[slot], distance)
                 for _co, slot, distance in tree.find_n(positions[index], k)]
        blended = _blend(found, rows)
        if blended:
            rows[index] = blended
            done.add(index)
            helper = the_layout.helper_of.get(index)
            if helper is not None:
                nearest_by_helper[helper] = nearest_by_helper.get(helper, 0) + 1
    for name in sorted(nearest_by_helper):
        report["helpers"].append({"group": name, "rule": "nearest", "k": k,
                                  "vertex_count": nearest_by_helper[name]})
    report["helpers"].sort(key=lambda row: row["group"])
    report["filled"] = len(done)
    return (rows, report)
