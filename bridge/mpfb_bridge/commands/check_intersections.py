"""
``check_intersections``: how much meshes intersect, and how close they come.

Nothing in the other tools could see two meshes pass through each other. Each of
them describes one character, so two can occupy the same cubic centimetres while
every tool reports success. The measurement is in
[`shared/mesh_overlap.py`](../shared/mesh_overlap.py), whose docstring says what is
counted and why a body is counted twice; this is which pairs, and the answer.

**A subject is a character, or a mesh that belongs to none**, so a held prop can be
measured. Without ``other``, every pair inside the subject's family; with it, every
pair across the two, counting an object that is in both once and never against
itself, which is what ``include_self`` is for.

**No verdict.** A finished garment has 613 pairs against the unmasked body and
renders cleanly, so no threshold would be objective, and the answer has none.

**``pairs_clear`` and ``closest_pair`` cover every pair, including those cut from
the rows.** The rows are sorted by the larger of a row's two counts, since sorting
on the masked one alone would bury the very pair a mask is hiding.
``closest_pair`` is by the distance as things stand, with the largest count winning
a tie, so that of several intersecting pairs it names the worst.

``region`` counts a face only if its centre is inside the box, and measures distance
only from vertices inside it. An axis may be left open, which is how a z band is
asked for. The bound is on faces rather than on where they cross, so a large face
reaching into the box from outside is not counted, which at this density is a matter
of a centimetre or so.

Changes nothing that can be observed afterwards: the masks are put back exactly,
and no selection, mode or active object is borrowed.
"""

__all__ = (
    "MAX_ROWS",
    "PARAMS",
    "SUMMARY",
    "check_intersections",
)

from ..log import get_logger
from ..shared import mesh_overlap
from ..shared import subject_resolution
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_OBJECT
from ..validation import TYPE_STRING

_LOG = get_logger("commands.checkintersections")

# Rows in one answer, largest first. A character with eight assets has 36 pairs and
# a row is about 300 B, so this keeps the worst case under 8 KB, the summary's line.
MAX_ROWS = 25

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in a character's family, or a mesh belonging to no character. "
                      "Omit or pass null to use whatever object is currently active."),
    Param("other", TYPE_STRING, default=None, nullable=True,
          description="A second subject, resolved the same way. Omit to measure every pair "
                      "inside the first."),
    Param("include_self", TYPE_BOOLEAN, default=False,
          description="Also measure each mesh against itself, leaving out faces that share a "
                      "vertex."),
    Param("region", TYPE_OBJECT, default=None, nullable=True,
          description="A world-space box, {'min': {x, y, z}, 'max': {x, y, z}}, any axis left "
                      "open. Only faces whose centre is inside it count."),
)

SUMMARY = "Measure how much meshes intersect and how close they come, with masks on and off."


def _largest_count(row):
    return max(row["face_pairs"], row.get("face_pairs_unmasked", 0))


def _pairs_among(first, second, include_self):
    """Each unordered pair once: inside ``first`` without ``second``, else across the two."""
    pairs = []
    seen = set()

    def add(one, other):
        key = frozenset((one.name, other.name))
        if key not in seen:
            seen.add(key)
            pairs.append((one, other))

    if second is None:
        for index, one in enumerate(first):
            for other in first[index + 1:]:
                add(one, other)
    else:
        for one in first:
            for other in second:
                if one.name != other.name:
                    add(one, other)
    if include_self:
        for one in first + (second or []):
            add(one, one)
    return pairs


def _is_clear(row):
    return _largest_count(row) == 0


def _closest_pair(rows):
    """The pair with the smallest distance as things stand, or ``None``. Never a self row."""
    candidates = [row for row in rows if row["min_distance"] is not None]
    if not candidates:
        return None
    closest = min(candidates, key=lambda row: (row["min_distance"], -row["face_pairs"],
                                               row["object_name"], row["other_object_name"]))
    return dict(object_name=closest["object_name"],
                other_object_name=closest["other_object_name"],
                min_distance=closest["min_distance"],
                face_pairs=closest["face_pairs"])


def _refused(found, reason, message, subject, resolved_by):
    return dict(found=found, ready=False, blocked_by=reason,
                subject_name=None if subject is None else subject.name,
                subject_resolved_by=resolved_by, other_name=None, pairs=[], pairs_measured=0,
                pairs_clear=0, pairs_truncated=False, closest_pair=None, not_measured=[],
                message=message)


def _message_for(rows, clear, truncated, unmeasured):
    parts = ["Measured {:d} pair(s): {:d} clear.".format(len(rows), clear)]
    if rows and not _is_clear(rows[0]):
        worst = rows[0]
        parts.append(" Most is '{:s}' with '{:s}': {:d} face pair(s).".format(
            worst["object_name"], worst["other_object_name"], _largest_count(worst)))
    if truncated:
        parts.append(" Only the {:d} largest are listed.".format(MAX_ROWS))
    if unmeasured:
        parts.append(" {:d} mesh(es) could not be measured; see 'not_measured'.".format(
            len(unmeasured)))
    return "".join(parts)


def check_intersections(params, resolution):
    """Which pairs, each measured once, the answer capped and the totals not."""
    services = resolution.services
    subject, resolved_by, message = subject_resolution.resolve_subject(
        params["name"], select="a mesh")
    if subject is None:
        return _refused(False, "subject_not_found", message, None, resolved_by)
    first = mesh_overlap.family_of(services, subject)
    if not first:
        return _refused(
            True, "no_meshes",
            "'{:s}' is not a mesh and belongs to no character, so there is nothing to "
            "measure.".format(subject.name), subject, resolved_by)

    second = None
    other_subject = None
    if params["other"] is not None:
        other_subject, _other_resolved_by, message = subject_resolution.resolve_subject(
            params["other"])
        if other_subject is None:
            return _refused(True, "other_not_found", message, subject, resolved_by)
        second = mesh_overlap.family_of(services, other_subject)
        if not second:
            return _refused(
                True, "no_meshes",
                "'{:s}' is not a mesh and belongs to no character, so there is nothing to "
                "measure it against.".format(other_subject.name), subject, resolved_by)

    everything = {blender_object.name: blender_object for blender_object in first + (second or [])}
    readings, unmeasured = mesh_overlap.read_all(
        list(everything.values()), mesh_overlap.bodies_among(services, everything.values()))

    rows = []
    for one, other in _pairs_among(first, second, params["include_self"]):
        if one.name in readings and other.name in readings:
            # The same Reading twice is how pair_row knows it is a self row.
            rows.append(mesh_overlap.pair_row(
                readings[one.name], readings[other.name], box=params["region"]))
    rows.sort(key=lambda row: (-_largest_count(row), row["object_name"],
                               row["other_object_name"]))
    clear = sum(1 for row in rows if _is_clear(row))
    truncated = len(rows) > MAX_ROWS
    _LOG.debug("check_intersections: %d pairs", len(rows))
    return dict(
        found=True,
        ready=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=resolved_by,
        other_name=None if other_subject is None else other_subject.name,
        include_self=params["include_self"],
        counted_in=params["region"],
        pairs=rows[:MAX_ROWS],
        pairs_measured=len(rows),
        pairs_clear=clear,
        pairs_truncated=truncated,
        closest_pair=_closest_pair(rows),
        not_measured=[dict(object_name=entry.object_name, reason=entry.reason)
                      for entry in unmeasured],
        message=_message_for(rows, clear, truncated, unmeasured),
    )
