"""
``get_makeskin_material``: which maps a MakeSkin material has wired, and which numbers count.

``get_material_settings`` reports only ``diffuseIntensity`` for a garment, because
that is all a preset saves. Which maps are wired, at what strength, in which colour
space and from which file was unknown without a script. The reading itself is
[`shared/makeskin.py`](../shared/makeskin.py), which ``set_makeskin_material`` answers
through too.

**What it reports, the writer accepts** ([FR 047](../../../feature-requests/done/047-rigify-hand-shapes/README.md)'s
rule): ``textures``, ``values`` and ``metadata`` can be sent to
``mpfb_set_makeskin_material`` unchanged. A value is only in ``values`` if the tree
has a socket for it, since the writer refuses one it has nowhere to put, and the rest
are in ``values_absent`` with the slot each would need.

**The first slot only**, as ``populate_from_object()`` reads, and so as anything
stored from this object would be. ``material_slots`` says when there are others.

Any mesh is accepted, as MakeSkin's panel accepts any mesh. Reads and changes nothing.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_makeskin_material",
)

from ..log import get_logger
from ..shared import blender_data
from ..shared import makeskin
from ..shared import material_settings
from ..shared import subject_resolution
from ..validation import Param
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getmakeskinmaterial")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="The mesh. Omit or pass null to use whatever object is currently active."),
)

SUMMARY = "Read a mesh's MakeSkin material: wired maps, strengths, colour spaces, values in effect."


def _refused(words, found, reason, message, subject, resolved_by, **extra):
    answer = dict(found=found, ready=False, blocked_by=reason,
                  subject_name=None if subject is None else subject.name,
                  subject_resolved_by=resolved_by, material_name=None,
                  material_identified_as=None, recognized_by=None, material_slots=None,
                  material_shared_with=[], textures=dict(), empty_slots=[], values=dict(),
                  values_absent=dict(), metadata=dict(), metadata_unset=[],
                  known_slots=list(words.slots), message=message)
    answer.update(extra)
    return answer


def _message_for(subject, material, textures, values):
    wired = sorted(slot for slot, entry in textures.items() if entry["wired"])
    parts = ["'{:s}' has the MakeSkin material '{:s}', with {:s}.".format(
        subject.name, str(material.name),
        "maps wired for {:s}".format(", ".join(wired)) if wired else "no maps")]
    idle = sorted(key for key, entry in values.items() if not entry["in_effect"])
    if idle:
        parts.append(" Not in effect: {:s}.".format(", ".join(idle)))
    return "".join(parts)


def get_makeskin_material(params, resolution):
    """One mesh's first material, read the way a store would read it."""
    services = resolution.services
    words = makeskin.vocabulary(services, resolution.module.__name__)

    subject, resolved_by, message = subject_resolution.resolve_subject(
        params["name"], select="a mesh")
    if subject is None:
        return _refused(words, False, "subject_not_found", message, None, resolved_by)
    if subject.type != "MESH":
        return _refused(
            words, True, "not_a_mesh",
            "'{:s}' is a {:s}, not a mesh, so it has no material to read.".format(
                subject.name, str(subject.type)), subject, resolved_by)
    material = services["MaterialService"].get_material(subject)
    if material is None:
        return _refused(
            words, True, "no_material",
            "'{:s}' has no material in its first slot. mpfb_set_makeskin_material gives it "
            "one.".format(subject.name), subject, resolved_by)
    is_makeskin, identified_as, recognized_by = makeskin.recognized(services, words, material)
    if not is_makeskin:
        return _refused(
            words, True, "not_makeskin",
            "'{:s}' has the material '{:s}', which MPFB identifies as {:s} and which holds nodes "
            "MakeSkin's template does not. mpfb_get_material_settings reads procedural eyes and "
            "the layered skin.".format(subject.name, str(material.name), identified_as),
            subject, resolved_by, material_name=str(material.name),
            material_identified_as=identified_as)

    tree = material.node_tree
    textures = makeskin.read_textures(words, tree)
    values, values_absent = makeskin.read_values(words, tree)
    metadata, metadata_unset = makeskin.read_metadata(words, subject)
    _LOG.debug("get_makeskin_material: %r on %r", material.name, subject.name)
    return dict(
        found=True,
        ready=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=resolved_by,
        material_name=str(material.name),
        material_identified_as=identified_as,
        recognized_by=recognized_by,
        material_slots=len(blender_data.material_names(subject)),
        material_shared_with=material_settings.material_shared_with(material, [subject]),
        textures=textures,
        empty_slots=makeskin.empty_slots(words, tree),
        values=values,
        values_absent=values_absent,
        metadata=metadata,
        metadata_unset=metadata_unset,
        known_slots=list(words.slots),
        message=_message_for(subject, material, textures, values),
    )
