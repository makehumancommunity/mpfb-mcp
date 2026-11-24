"""
``get_rig_definition``: a rig, read as the bone table ``create_rig`` takes.

**A read-back is a write** ([FR 060](../../../feature-requests/done/060-authoring-rigs/README.md)).
Every bone comes back in the table's shape, through
[`shared/rig_definition.py`](../shared/rig_definition.py), so a shipped rig can be the
starting point for an authored one and a rig built by ``create_rig`` reads back as the
table it was built from. Each end also carries where it is, ``position`` in the character
frame, which the builder ignores beside another kind.

**Which definition is read, and from where.** With ``rig``, a catalogue identifier, that
rig's file is fitted **in memory** to this character's body through MPFB's own loader and
nothing is created; it need not be the rig the character has, or have one at all. Without
it, the rig that moves the character is read, and there are three cases, which
``definition_from`` names:

- ``"armature"``: the bones carry the strategies MPFB saves for a developer, which is what
  ``create_rig`` asks for and MakeRig's "Load rig" leaves. They are read off the bones, and
  each end's ``position`` is where the bone actually is.
- ``"catalogue"``: a rig added from the catalogue carries no strategies, so the file
  ``identify_rig()`` points at is fitted to this body as above. A rig loaded from a file
  is, at rest, where that file puts it.
- ``"armature_positions"``: neither, which is a generated Rigify rig or one made by hand.
  Every end is reported as a fixed position (``snap: false``), which is true and is what the
  builder would make of it.

**What the table cannot carry is named, not dropped.** ``features_not_carried`` lists, per
bone and only for bones that have any, constraints, bendy bones, Rigify types and
parameters, non-default inheritance and custom properties; ``rig_features_not_carried``
the rig-level ones (a Rigify UI, extra bones). A rig derived from a read one loses them
knowingly.

**Size.** The default rig is 163 bones. A key at the builder's default is left out of each
row, ``bone_names`` narrows to named bones and ``compact`` drops the read-only
``position`` and ``features_not_carried``. ``include_joints`` adds the 125 joint cubes, which
is the vocabulary a ``joint`` end takes, each evaluated as MPFB evaluates it when fitting.

Reading changes nothing. MPFB's fitting adds a shape key from the mix and removes it again,
and the active shape key is put back after it.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "get_rig_definition",
)

from ..log import get_logger
from ..shared import mpfb_surface
from ..shared import rig_definition
from ..shared import subject_resolution
from ..validation import Param
from ..validation import TYPE_ARRAY
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.getrigdefinition")

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("rig", TYPE_STRING, default=None, nullable=True,
          description="A catalogue identifier from list_rigs, fitted to this body in memory and "
                      "read. Omit to read the rig that moves the character."),
    Param("bone_names", TYPE_ARRAY, default=None, nullable=True,
          description="Only these bones, by name. Omit for every bone."),
    Param("include_joints", TYPE_BOOLEAN, default=False,
          description="Also list every joint cube with its centre in the character frame: the "
                      "names a 'joint' end takes."),
    Param("compact", TYPE_BOOLEAN, default=False,
          description="Leave out each end's resolved position and features_not_carried."),
)

SUMMARY = ("Read a rig as the bone table create_rig takes: per bone its parent and ends against "
           "the body's joints, with each end's position in the character frame.")


def _answer(subject, resolved_by, basemesh, params, **fields):
    answer = dict(
        found=basemesh is not None,
        ready=False,
        blocked_by=None,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        rig=params["rig"],
    )
    answer.update(fields)
    return answer


def _names_error(value):
    if value is None:
        return None
    if (not isinstance(value, list) or not value
            or not all(isinstance(item, str) and item for item in value)
            or len(set(value)) != len(value)):
        return "bone_names must be a non-empty list of distinct bone names, or omitted."
    return None


def _catalogue_source(services, basemesh, identifier):
    """The fit and path for a catalogue rig, or ``(None, None, refusal)``."""
    path, _weights, _from = rig_definition.catalogue_files(services, identifier)
    if path is None:
        return (None, None, (
            "unknown_identifier",
            "No rig in the catalogue is identified by '{!s}', so nothing was read. Call "
            "mpfb_list_rigs and pass an entry's 'identifier'.".format(identifier)))
    return (rig_definition.fit_file(services, basemesh, path), path, None)


def get_rig_definition(params, resolution):  # pylint: disable=too-many-locals
    """Read one rig, as a catalogue fit or off the armature that moves the character."""
    services = resolution.services
    object_service = services["ObjectService"]

    basemesh, subject, resolved_by, message = subject_resolution.resolve_basemesh(
        services, params["name"], not_done="nothing was read",
        not_a_character="there is no body to read a rig against")

    def blocked(reason, text, **extra):
        return _answer(subject, resolved_by, basemesh, params, blocked_by=reason,
                       message=text, **extra)

    if basemesh is None:
        return blocked("subject_not_found", message)
    error = _names_error(params["bone_names"])
    if error is not None:
        return blocked("invalid_shape", error)

    rig_object = object_service.find_object_of_type_amongst_nearest_relatives(
        basemesh, "Skeleton")
    space = rig_definition.Space(basemesh, rig_object if rig_object is not None else basemesh)
    rig_service = services["RigService"]
    identified = None if rig_object is None else rig_service.identify_rig(rig_object)

    path = None
    fit = None
    rig_features = []
    if params["rig"] is not None:
        fit, path, refusal = _catalogue_source(services, basemesh, params["rig"])
        if refusal is not None:
            return blocked(refusal[0], refusal[1])
        definition_from = "catalogue"
        identified_as = params["rig"]
    elif rig_object is None:
        return blocked(
            "not_rigged",
            "'{:s}' has no rig, so there is nothing to read. Pass rig, an identifier from "
            "mpfb_list_rigs, to read a catalogue rig fitted to this body, or build one with "
            "mpfb_create_rig.".format(basemesh.name))
    else:
        identified_as = identified
        definition, saved_ends = rig_definition.armature_definition(services, rig_object)
        if saved_ends:
            definition_from = "armature"
        else:
            catalogue_path = None
            if identified and not identified.startswith("rigify_generated") \
                    and not identified.endswith("unknown"):
                catalogue_path = rig_definition.catalogue_files(services, identified)[0]
            if catalogue_path is not None:
                fit = rig_definition.fit_file(services, basemesh, catalogue_path)
                path = catalogue_path
                definition_from = "catalogue"
            else:
                definition_from = "armature_positions"

    if fit is not None:
        definition = fit.rig_definition

        def locate(_bone_name, _key, end_info):
            return fit.get_best_location_from_strategy(end_info)

        def features(_bone_name, info):
            return rig_definition.features_from_definition(info)

        header = fit.rig_header
        rig_features = [key for key in ("rigify_ui", "extra_bones") if header.get(key)]
        version = header.get("version")
    else:
        def locate(bone_name, key, _end_info):
            bone = rig_object.data.bones[bone_name]
            return space.armature_to_local(
                rig_object, bone.head_local if key == "head" else bone.tail_local)

        def features(bone_name, _info):
            return rig_definition.features_from_armature(rig_object, bone_name)

        if rig_service.get_extra_bones(rig_object):
            rig_features.append("extra_bones")
        version = rig_definition.current_version(services)

    names = None
    if params["bone_names"] is not None:
        unknown = [name for name in params["bone_names"] if name not in definition]
        if unknown:
            return blocked(
                "unknown_bone_names",
                "{:d} name(s) in bone_names are not bones of this rig, so nothing was read: "
                "{:s}.".format(len(unknown), ", ".join(unknown[:20])),
                unknown_bone_names=unknown)
        names = set(params["bone_names"])

    bones, dropped = rig_definition.read_bones(
        definition, space, locate, names=names, compact=params["compact"], features=features)

    answer = _answer(
        subject, resolved_by, basemesh, params,
        ready=True,
        rig_object_name=None if rig_object is None else rig_object.name,
        rig_identified_as=identified_as,
        definition_from=definition_from,
        definition_path=mpfb_surface.as_path(path),
        version=version,
        character_frame=space.frame.describe(),
        bone_count=len(definition),
        bones_listed=len(bones),
        bones=bones,
        features_not_carried=None if params["compact"] else dropped,
        rig_features_not_carried=rig_features,
        unexpressible_ends=sum(1 for bone in bones for key in ("head", "tail")
                               if bone[key].get("expressible") is False),
    )
    if params["include_joints"]:
        joint_fit = fit if fit is not None else rig_definition.fit_definition(
            services, basemesh, {"bones": {}, "version": 110})
        answer["joints"] = rig_definition.joints(joint_fit, space)
        answer["joint_count"] = len(answer["joints"])
    answer["message"] = (
        "Read {:d} of {:d} bone(s) of '{!s}' from the {:s}.".format(
            len(bones), len(definition), identified_as,
            {"armature": "strategies saved on the armature",
             "catalogue": "catalogue file, fitted to '{:s}'".format(basemesh.name),
             "armature_positions": "armature's bone positions, since it carries no "
                                   "strategies and no catalogue file is known for it"}[
                                       definition_from])
        + (" {:d} bone(s) carry features the builder would drop; see features_not_carried."
           .format(len(dropped)) if dropped else ""))
    _LOG.debug("get_rig_definition: %r from %s", identified_as, definition_from)
    return answer
