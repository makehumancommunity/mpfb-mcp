"""
``write_mesh_asset``: one checked mesh becomes a complete asset, and says what it wrote.

**MakeClothes' ``ClothesCommon`` is an operator mixin with no service behind it, so it
is reimplemented from services**, as ``set_asset_material`` and the export copy were:
``mesh_is_valid_as_clothes()``, ``create_mhclo_from_clothes_matching()``,
``get_reference_scale()`` and ``Mhclo.write_mhclo()``. It never calls
``bpy.ops.mpfb.write_makeclothes_*``, which can say ``{'ERROR'}`` and still return
``{'FINISHED'}``, reports only through ``self.report`` and takes both meshes from the
selection, the second as "the other selected thing". Here both are named.

**It departs from the panel in eight ways, and an asset still loads as the panel's does.**
``eee_composite/write_mesh_asset_compare_test.py`` holds the two MHCLOs to these differences
and no others:

- **A source texture is never rewritten.** ``shared/texture_writing.py`` copies it byte
  for byte or saves a copy, where ``check_that_all_textures_are_saved()`` re-encodes it.
- **The OBJ matches the MHCLO** (below).
- **Nothing is overwritten by default, and a refusal leaves no directory.** "Store in
  library" overwrites without asking, and makes the directory before its checks.
- **``asset_source`` is updated by a library write**, so the mesh knows what it became
  ([the decision](../../../feature-requests/done/050-writing-mesh-assets/README.md#decisions-taken-while-scoping)).
- **An untextured MakeSkin material is written**, which the operator misses because
  MPFB identifies it as ``gameengine`` (``makeskin.recognized()``).
- **A texture that cannot be written is left out and reported**, where the operator stops
  half way. MPFB's validator is the only check that blocks (below).
- **A missing xref cache is built**, where the panel asks for it to be, and a missing
  ``uuid`` generated, which the panel leaves to a separate button.
- **A posed or turned body is refused** (below), which the panel writes without comment.

**The OBJ.** ``save_wavefront_file()`` exports with ``wm.obj_export``'s default
``apply_modifiers=True``, while the matching strips subdivision, so a garment with its
Subdivision at viewport level 1 got an OBJ of 10,649 vertices beside an MHCLO of 2,674.
The OBJ cannot be left to a separate export, since ``write_mhclo(also_export_obj=False)``
drops the MHCLO's ``obj_file`` line too. So MPFB's call stays, with the garment's modifiers
off in the viewport around it and put back in a ``finally``, and the two counts are compared
before anything moves into place. A modifier that adds vertices fails MPFB's validator.

**A posed body is baked into the file.** ``MeshCrossRef(after_modifiers=True)`` strips only
``MASK`` and ``SUBSURF``, so the armature stays: posing one thigh changed 793 of 2,674 lines,
one offset by 3.7 units, and the reference scale. A **turned** body is the same defect by
another road, which the request did not foresee: offsets are taken in world axes, so a body
at 90 degrees changed 2,670 of the 2,674 lines, each offset rotated, and such an asset would
sit wrongly on every other body. A moved one is fine, and changed 19 by under 0.03, where a
triangle tied with its neighbour. These are not measured defects of the mesh but states in
which the write itself would be wrong, so they refuse where a bad fit does not:
``rig_not_at_rest`` and ``character_turned``, each naming the tool that fixes it.

**Only MPFB's validator blocks**, because it is what MPFB's write would refuse too, and no
threshold on a count would be objective: the finished gi has 613 unmasked pairs and is fine.
Everything measured is in ``check``, a summary of ``check_mesh_asset``'s one reading.

**A name is the whole address, and the directory is never a caller's.** ``destination`` is
``library``, ``<user data>/<subdir>/<asset_name>/`` as the panel's "Store in library", or
``export_directory``, ``<export directory>/<asset_name>/`` with the directory the human
chose, as ``export_character`` has it. ``asset_name`` is narrower than an export's, since
the panel would rewrite anything else (``artifact_names.asset_name_rejection``).

**What a write owes, it owes in this order.** Every refusal is settled first; matching runs
next and nothing exists if it raises; then the files are made in a staging directory beside
the destination, holding their final names, because ``write_mhclo()`` derives the ``obj_file``
and ``material`` lines from the name it is given; and only then do they move, one by one.
Overwriting replaces this asset's own files, and an alternate, a weights file or a thumbnail
beside them is not touched. Properties go on the object last, so a call that failed or was a
``dry_run`` has changed nothing, and ``properties_set`` says which went on.

**``disable_exact_strategy`` is read live, not assumed.** The request says it defaults to true
in the panel. Its JSON has said ``false`` since the option was added, and a live read agrees,
so ``allow_exact_matching`` left out follows the scene's setting and the answer reports what
was used. On a mesh extracted from a helper group the difference is 2,674 exact lines or 624.

**There is no ``homepage``, tag or ``z_depth`` argument, because they would not reach the
file.** ``Mhclo`` has no ``homepage``, ``write_mhclo()`` writes no tags, and ``z_depth`` is
always 50, since the operator passes neither the property nor the attribute's real name,
``zdepth``. Offering them would be a lie.

**A license nobody chose is still written, and said to be.** MPFB's default is CC0, so a mesh
nobody labelled is published as CC0, which FR 046's catalogues will then show. It is the
caller's to decide, so it is a warning and ``license_resolved_by``. The MHMAT takes the MHCLO's
license and author unless MakeSkin's were set on the object, and a difference is a warning.

**``dry_run`` does everything but write**, the matching included, so it is an honest answer and
the smoke item costs no fourth file. It builds no cache, and what the matching does without one
it cleans up after.
"""

__all__ = (
    "DESTINATIONS",
    "PARAMS",
    "SUMMARY",
    "write_mesh_asset",
)

import math
import os
import uuid

import bpy

from .. import export_directory
from ..log import get_logger
from ..shared import asset_sections
from ..shared import makeskin
from ..shared import mesh_asset_report
from ..shared import mesh_overlap
from ..shared import mpfb_surface
from ..shared import pose_reading
from ..shared import selection
from ..shared import subject_resolution
from ..shared import texture_writing
from ..shared.artifact_names import asset_name_rejection
from ..shared.artifact_names import file_facts
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.writemeshasset")

DESTINATIONS = ("library", "export_directory")

PARAMS = (
    Param("asset_name", TYPE_STRING, required=True,
          description="The asset's name, never a path: letters, digits and single '_'. It becomes "
                      "<destination>/<asset_name>/<asset_name>.mhclo."),
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="The mesh. Omit or pass null to use whatever object is currently active."),
    Param("basemesh", TYPE_STRING, default=None, nullable=True,
          description="The body it is matched to. Omit to find it among the mesh's relatives, "
                      "then the selection, then the file."),
    Param("object_type", TYPE_STRING, default=None, nullable=True,
          description="MPFB's object type, as mpfb_add_asset takes it. Required when the mesh has "
                      "none, and stored on it."),
    Param("destination", TYPE_STRING, default="library", choices=DESTINATIONS,
          description="'library' for MPFB's user data, or 'export_directory' for the directory "
                      "the bridge's user chose."),
    Param("overwrite", TYPE_BOOLEAN, default=False,
          description="Replace this asset's own files. False by default: there is no undo for a "
                      "file across this socket."),
    Param("dry_run", TYPE_BOOLEAN, default=False,
          description="Settle and match everything and report it, and write nothing."),
    Param("license", TYPE_STRING, default=None, nullable=True,
          description="The asset's license, from MPFB's own list. Omit to take the object's."),
    Param("author", TYPE_STRING, default=None, nullable=True,
          description="The asset's author. Omit to take the object's."),
    Param("description", TYPE_STRING, default=None, nullable=True,
          description="The asset's description. Omit to take the object's."),
    Param("delete_group", TYPE_STRING, default=None, nullable=True,
          description="The basemesh's vertex group to hide under the asset. Omit to take the "
                      "object's; one named here must exist."),
    Param("allow_exact_matching", TYPE_BOOLEAN, default=None, nullable=True,
          description="Whether a vertex may match a body vertex exactly. Omit to follow the "
                      "MakeClothes panel's setting on the scene."),
    Param("write_material", TYPE_BOOLEAN, default=True,
          description="Write a MakeSkin material's MHMAT and textures with the asset."),
)

SUMMARY = "Write a mesh as a complete asset: MHCLO, OBJ, MHMAT and textures, in the library or " \
          "the export directory."

# MPFB's own test of a panel-marked body proxy, which spells the type "Proxymesh".
_PANEL_PROXY_SPELLING = "proxymesh"

# How far a body may be turned and still be upright. About a twentieth of a degree.
_TURNED_TOLERANCE_RADIANS = 0.001

_MAX_NAMED_BONES = 10


class _ObjDoesNotMatch(Exception):
    """The OBJ MPFB wrote has a different vertex count from the MHCLO it wrote."""


class _Request:
    """One call's resolved state, so the refusals can be read in one place."""

    __slots__ = ("subject", "resolved_by", "body", "body_resolved_by", "object_type",
                 "object_type_before", "object_type_resolved_by", "asset_subdir", "extension",
                 "root", "path_resolved_by", "directory", "file_path", "fragment", "uuid",
                 "uuid_resolved_by", "metadata", "clothes_properties", "general_properties",
                 "delete_group", "delete_group_resolved_by", "allow_exact", "words", "tree",
                 "material_reason", "plans", "skipped_textures", "mhmat_license", "mhmat_author")

    def __init__(self):
        for slot in self.__slots__:
            setattr(self, slot, None)
        self.plans = []
        self.skipped_textures = []
        self.metadata = dict()


def _answer(params, request, **fields):
    answer = dict(
        found=request.subject is not None, ready=False, written=False, blocked_by=None,
        dry_run=params["dry_run"], asset_name=params["asset_name"],
        destination=params["destination"],
        subject_name=None if request.subject is None else request.subject.name,
        subject_resolved_by=request.resolved_by,
        basemesh_name=None if request.body is None else request.body.name,
        basemesh_resolved_by=request.body_resolved_by,
        object_type=request.object_type, object_type_resolved_by=request.object_type_resolved_by,
        path=request.file_path, path_resolved_by=request.path_resolved_by,
        fragment=request.fragment, overwrote=False, file_before=None, files=[],
        warnings=[], message=None)
    answer.update(fields)
    return answer


def _lookup_object_type(services, params, request):
    """Settle ``object_type``, or return ``(blocked_by, sentence, extra)``.

    MakeClothes' panel marks a body proxy ``Proxymesh`` and the section table has
    ``Proxymeshes``, and MPFB treats both as one, so a mesh carrying the first is written
    as the second and stored so. An argument is what ``mpfb_add_asset`` would take.
    """
    sections, _from_mpfb = asset_sections.read_sections(services)
    known = asset_sections.mesh_asset_types(services, sections)
    request.object_type_before = services["ObjectService"].get_object_type(request.subject) or None
    wanted = params["object_type"]
    request.object_type_resolved_by = "argument" if wanted is not None else "object"
    if wanted is None:
        wanted = request.object_type_before
        if wanted is None:
            return ("object_type_required",
                    "'{:s}' has no object type and none was given, so nothing says which section "
                    "of the library it belongs to. Pass 'object_type' naming one of "
                    "known_object_types.".format(request.subject.name),
                    dict(known_object_types=known))
        if str(wanted).lower() == _PANEL_PROXY_SPELLING:
            wanted = "Proxymeshes"
    for candidate in known:
        if candidate.lower() == str(wanted).strip().lower():
            request.object_type = candidate
            request.asset_subdir = asset_sections.subdir_for_object_type(sections, candidate)
            asset_type = next(row[1] for row in sections if row[2] == candidate)
            request.extension = "." + asset_type
            return None
    return ("unknown_object_type",
            "'{!s}' is not a mesh asset type MPFB knows, so nothing was written. The basemesh is "
            "what an asset fits rather than an asset. known_object_types lists the rest.".format(
                wanted),
            dict(known_object_types=known))


def _locate(services, params, request):
    """Settle where it goes, or return ``(blocked_by, sentence, extra)``."""
    if params["destination"] == "library":
        request.path_resolved_by = "library"
        request.root = str(services["LocationService"].get_user_data(request.asset_subdir))
    else:
        directory, resolved_by, exists = export_directory.resolve(
            services["LocationService"].get_user_data("exports"))
        request.path_resolved_by = resolved_by
        request.root = directory
        if not exists and resolved_by != export_directory.RESOLVED_BY_DEFAULT:
            return ("export_directory_missing",
                    "The export directory '{:s}', set {:s}, does not exist, and a directory "
                    "somebody named is not created on their behalf, so nothing was written. Ask "
                    "the person running Blender to create it or correct the MPFB Bridge's export "
                    "directory preference, or pass destination='library'.".format(
                        directory,
                        "with --export-dir"
                        if resolved_by == export_directory.RESOLVED_BY_COMMAND_LINE
                        else "in the MPFB Bridge's preferences"),
                    dict())
    name = params["asset_name"]
    request.directory = os.path.normpath(os.path.join(request.root, name))
    request.file_path = os.path.join(request.directory, name + request.extension)
    request.fragment = "{0:s}/{0:s}{1:s}".format(name, request.extension)
    return None


def _resolved_metadata(request, params, key):
    """``(value, resolved_by)``: the argument, else the object's, else MPFB's default."""
    if params[key] is not None:
        return (params[key], "argument")
    properties = request.clothes_properties
    value = properties.get_value(key, entity_reference=request.subject)
    full_name = properties.get_fullname_key_from_shortname_key(key)
    if request.subject.is_property_set(full_name) and value:
        return (str(value), "object")
    return (None if not value else str(value), "mpfb_default")


def _metadata_refusal(request, params):
    """Settle license, author and description, or return ``(blocked_by, sentence, extra)``."""
    properties = request.clothes_properties
    for key in ("license", "author", "description"):
        value, resolved_by = _resolved_metadata(request, params, key)
        request.metadata[key] = value
        request.metadata[key + "_resolved_by"] = resolved_by
        if value is not None and ("\n" in value or "\r" in value):
            # Defence in depth: an MHCLO is one key per line, and mpfb-mcp refuses this first.
            return ("invalid_" + key, "'{:s}' must be one line of text, so nothing was "
                                      "written.".format(key), dict())
    full_name = properties.get_fullname_key_from_shortname_key("license")
    known = [item.identifier
             for item in bpy.types.Object.bl_rna.properties[full_name].enum_items]
    if request.metadata["license"] not in known:
        return ("invalid_license",
                "'{!s}' is not a license MPFB's panel offers, so nothing was written. It offers: "
                "{:s}.".format(request.metadata["license"], ", ".join(known)),
                dict(known_values=known))
    return None


def _delete_group_refusal(request, params):
    """Settle the delete group, or return ``(blocked_by, sentence, extra)``."""
    named = params["delete_group"]
    if named is not None:
        request.delete_group_resolved_by = "argument"
        request.delete_group = named
        if named not in request.body.vertex_groups:
            return ("delete_group_not_found",
                    "'{:s}' has no vertex group '{:s}', so nothing was written. Omit delete_group "
                    "to write the asset hiding nothing under it.".format(
                        request.body.name, named),
                    dict())
        return None
    properties = request.clothes_properties
    request.delete_group = mpfb_surface.property_value(
        properties, "delete_group", request.subject)
    full_name = properties.get_fullname_key_from_shortname_key("delete_group")
    request.delete_group_resolved_by = (
        "object" if request.subject.is_property_set(full_name) else "mpfb_default")
    return None


def _rigs_of(*meshes):
    """Each armature a modifier that is on makes one of these meshes follow."""
    rigs = []
    for mesh in meshes:
        for modifier in mesh.modifiers:
            if (modifier.type == "ARMATURE" and modifier.show_viewport
                    and modifier.object is not None and modifier.object not in rigs):
                rigs.append(modifier.object)
    return rigs


def _state_refusal(request):
    """A state in which the write itself would be wrong. See this module's docstring."""
    if bpy.context.mode != "OBJECT":
        return ("not_in_object_mode",
                "Blender is in {:s} mode, and MPFB's exporter works on the selection in object "
                "mode, so nothing was written. Switch to object mode and call again.".format(
                    str(bpy.context.mode)), dict())
    if not request.subject.visible_get():
        return ("mesh_not_visible",
                "'{:s}' is hidden or outside this view layer, and MPFB's exporter writes what it "
                "can select, so nothing was written. Show it and call again.".format(
                    request.subject.name), dict())
    pose_reading.evaluated()
    for rig in _rigs_of(request.subject, request.body):
        posed = pose_reading.deforming_bones_off_rest(rig)
        if posed:
            return ("rig_not_at_rest",
                    "'{:s}' has {:d} deforming bone(s) off rest, and MPFB's matching would bake "
                    "that pose into every asset's offsets, so nothing was written. "
                    "mpfb_reset_pose puts it back, and its restore_with returns the pose "
                    "afterwards.".format(rig.name, len(posed)),
                    dict(rig_name=rig.name, posed_bone_count=len(posed),
                         posed_bones=posed[:_MAX_NAMED_BONES]))
    rotation = request.body.matrix_world.to_quaternion()
    if abs(rotation.angle) > _TURNED_TOLERANCE_RADIANS:
        return ("character_turned",
                "'{:s}' is turned {:.1f} degrees, and MPFB's matching takes offsets in world axes, "
                "so the turn would be baked into every one of them and nothing was written. "
                "mpfb_place_character with facing 0 turns it back, and its restore_with returns "
                "it afterwards.".format(request.body.name, math.degrees(rotation.angle)),
                dict(rotation_degrees=round(math.degrees(rotation.angle), 3)))
    return None


def _plan_material(services, root_name, params, request):
    """Decide what the material contributes, into ``request``. Writes nothing."""
    is_proxy = request.object_type == "Proxymeshes"
    if is_proxy:
        request.material_reason = "A body proxy has no material of its own, as in MPFB's panel."
        return
    if not params["write_material"]:
        request.material_reason = "write_material was false."
        return
    material = services["MaterialService"].get_material(request.subject)
    if material is None:
        request.material_reason = "The mesh has no material in its first slot."
        return
    words = makeskin.vocabulary(services, root_name)
    is_makeskin, identified_as, _recognized_by = makeskin.recognized(services, words, material)
    if not is_makeskin:
        request.material_reason = (
            "MPFB identifies its material '{:s}' as {:s}, and only a MakeSkin material can be "
            "written as an MHMAT.".format(str(material.name), identified_as))
        return
    request.words = words
    request.tree = material.node_tree
    for slot in words.slots:
        node = makeskin.texture_node(request.tree, slot)
        if node is None:
            continue
        planned = texture_writing.plan(slot, node.image, request.directory, params["asset_name"])
        if planned.refusal is None:
            request.plans.append(planned)
        elif node.image is None:
            request.skipped_textures.append(dict(slot=slot, image_name=None, blank=True,
                                                 message=planned.refusal))
        else:
            request.skipped_textures.append(dict(slot=slot, image_name=planned.image_name,
                                                 blank=False, message=planned.refusal))
    for key, target in (("license", "mhmat_license"), ("author", "mhmat_author")):
        value = request.metadata[key]
        if params[key] is None and request.subject.is_property_set(words.metadata[key]):
            value = words.properties.get_value(key, entity_reference=request.subject)
        setattr(request, target, None if not value else str(value))


def _own_file_paths(request):
    """Every file of this asset's own, by the name this write would give it."""
    stem = os.path.splitext(request.file_path)[0]
    paths = [request.file_path, stem + ".obj"]
    if request.tree is not None:
        paths.append(stem + ".mhmat")
    paths.extend(planned.destination for planned in request.plans
                 if planned.how != texture_writing.ALREADY_IN_PLACE)
    return paths


def _kept_or_new_uuid(request):
    """The uuid to write, and where it came from: alternates are keyed by it, so it is kept."""
    existing = mpfb_surface.property_value(request.general_properties, "uuid", request.subject)
    if existing:
        return (existing, "object")
    try:
        with open(request.file_path, "r", encoding="utf8", errors="surrogateescape") as handle:
            for line in handle:
                words = line.split()
                if len(words) > 1 and words[0] == "uuid":
                    return (words[1], "existing_file")
                if words and words[0] == "verts":
                    break
    except OSError:
        pass
    return (str(uuid.uuid4()), "generated")


def _allow_exact(root_name, params):
    """``(allow_exact, resolved_by)``, the panel's setting unless one was named."""
    if params["allow_exact_matching"] is not None:
        return (params["allow_exact_matching"], "argument")
    settings = mpfb_surface.make_clothes_scene_properties(root_name)
    if settings is None:
        raise mpfb_surface.MissingFromMpfb(
            "MPFB's MakeClothes panel settings are not where this add-on reads them, so it cannot "
            "follow the panel's matching. Pass allow_exact_matching, and check mpfb_get_status.")
    disabled = settings.get_value("disable_exact_strategy", entity_reference=bpy.context.scene)
    return (not disabled, "panel")


def _matched(services, request, params):
    """MPFB's matching and reference scale, leaving nothing in the file. Writes no file."""
    clothes_service = services["ClothesService"]
    metadata = request.metadata
    properties = dict(author=metadata["author"] or "", description=metadata["description"] or "",
                      license=metadata["license"], name=params["asset_name"], uuid=request.uuid)
    with selection.restored_all(), mesh_asset_report.debris_removed(services):
        mhclo = clothes_service.create_mhclo_from_clothes_matching(
            request.body, request.subject, properties_dict=properties,
            delete_group=request.delete_group, allow_exact=request.allow_exact)
        reference_scale = clothes_service.get_reference_scale(request.body)
    return (mhclo, reference_scale)


def _counts(mhclo):
    """How many lines of each kind ``write_mhclo()`` will write, by its own test."""
    exact = 0
    for line in mhclo.verts.values():
        weights = line["weights"]
        if weights[0] == 1 and weights[1] == 0 and weights[2] == 0:
            exact += 1
    return dict(exact=exact, offset=len(mhclo.verts) - exact)


def _check(request, warnings):
    """``check_mesh_asset``'s reading, summarised, or ``None`` with a warning. Never refuses."""
    subject = request.subject
    body = request.body
    try:
        readings, unmeasured = mesh_overlap.read_all(
            [subject, body], {body.name}, with_groups=True)
        if subject.name not in readings or body.name not in readings:
            return dict(applies=False,
                        reason="Blender has no evaluated geometry for: {:s}.".format(
                            ", ".join(entry.object_name for entry in unmeasured)))
        return mesh_asset_report.check_summary(mesh_asset_report.component_report(
            readings[subject.name], readings[body.name],
            [str(group.name) for group in subject.vertex_groups]))
    except Exception as error:  # pylint: disable=broad-except
        warnings.append("Measuring it raised {:s}: {!s}. mpfb_check_mesh_asset asks the same "
                        "question.".format(type(error).__name__, error))
        return None


def _vertex_lines(obj_path):
    with open(obj_path, "r", encoding="utf8", errors="surrogateescape") as handle:
        return sum(1 for line in handle if line.startswith("v "))


def _write_mhclo_and_obj(mhclo, staged_path, reference_scale, with_material, subject):
    """MPFB's writer, with the garment's modifiers off and the selection put back.

    **In a window's context**, since ``save_wavefront_file()`` reads ``bpy.context.object``
    and ``wm.obj_export`` polls for a window. ``cli.py`` gives its loop one, for the case
    this was found in, and a timer's callback is not promised one either.
    """
    states = [(modifier, modifier.show_viewport) for modifier in subject.modifiers]
    windows = bpy.context.window_manager.windows
    window = bpy.context.window or (windows[0] if len(windows) > 0 else None)
    try:
        for modifier, _state in states:
            modifier.show_viewport = False
        with selection.restored_all(), bpy.context.temp_override(window=window):
            mhclo.write_mhclo(staged_path, reference_scale=reference_scale,
                              also_export_mhmat=with_material)
    finally:
        for modifier, state in states:
            modifier.show_viewport = state
    staged_obj = os.path.splitext(staged_path)[0] + ".obj"
    lines = _vertex_lines(staged_obj)
    if lines != len(mhclo.verts):
        raise _ObjDoesNotMatch("The OBJ has {:d} vertices and the MHCLO {:d} lines.".format(
            lines, len(mhclo.verts)))
    return staged_obj


def _file_row(path, kind, written, **fields):
    facts = file_facts(path)
    row = dict(path=path, kind=kind, size_bytes=facts["size_bytes"] if written else None,
               action=("replaced" if facts["exists"] else "created"))
    row.update(fields)
    return row


def _write(services, request, params, mhclo, reference_scale):
    """Stage everything beside the destination, then move it in. Returns the file rows."""
    name = params["asset_name"]
    with_material = request.tree is not None
    made = texture_writing.made_directories(request.root)
    rows = []
    try:
        with texture_writing.staging(request.root) as staged_directory:
            staged_textures = [texture_writing.write_staged(planned, staged_directory)
                               for planned in request.plans]
            staged = []
            if with_material:
                staged.append((makeskin.export_staged(
                    services, request.words, request.subject, request.tree, staged_directory,
                    request.plans, name, request.mhmat_license, request.mhmat_author), "mhmat"))
            staged_main = os.path.join(staged_directory, name + request.extension)
            staged_obj = _write_mhclo_and_obj(mhclo, staged_main, reference_scale, with_material,
                                              request.subject)
            staged.extend(((staged_obj, "obj"), (staged_main, request.extension[1:])))
            made.extend(texture_writing.made_directories(request.directory))
            for planned, staged_file in zip(request.plans, staged_textures):
                destination = planned.destination
                action = ("kept" if staged_file is None
                          else "replaced" if os.path.exists(destination) else "created")
                if staged_file is not None:
                    texture_writing.move_into_place(staged_file, request.directory)
                rows.append(dict(path=destination, kind="texture",
                                 size_bytes=file_facts(destination)["size_bytes"], action=action,
                                 slot=planned.slot, how=planned.how,
                                 source_path=planned.source_path,
                                 source_image=planned.image_name))
            for staged_file, kind in staged:
                destination = os.path.join(request.directory, os.path.basename(staged_file))
                action = "replaced" if os.path.exists(destination) else "created"
                texture_writing.move_into_place(staged_file, request.directory)
                rows.append(dict(path=destination, kind=kind,
                                 size_bytes=file_facts(destination)["size_bytes"], action=action))
    except Exception:
        texture_writing.remove_directories(made)
        raise
    return rows


def _planned_rows(request):
    """What :func:`_write` would report, for a ``dry_run``."""
    stem = os.path.splitext(request.file_path)[0]
    rows = []
    for planned in request.plans:
        rows.append(_file_row(planned.destination, "texture", False, slot=planned.slot,
                              how=planned.how, source_path=planned.source_path,
                              source_image=planned.image_name))
        if planned.how == texture_writing.ALREADY_IN_PLACE:
            rows[-1]["action"] = "kept"
    if request.tree is not None:
        rows.append(_file_row(stem + ".mhmat", "mhmat", False))
    rows.append(_file_row(stem + ".obj", "obj", False))
    rows.append(_file_row(request.file_path, request.extension[1:], False))
    return rows


def _set_properties(request, params):
    """What a finished write leaves on the object, so that it and MPFB's panel know."""
    general = request.general_properties
    clothes = request.clothes_properties
    subject = request.subject
    changed = []

    def put(config_set, key, value, label, argument=False):
        # An argument is set even when it equals what reads back: a chosen CC0 has to be
        # told from MPFB's default CC0 next time, and being set is the difference.
        if argument or config_set.get_value(key, entity_reference=subject) != value:
            config_set.set_value(key, value, entity_reference=subject)
            changed.append(label)

    put(general, "object_type", request.object_type, "object_type")
    put(general, "uuid", request.uuid, "uuid")
    put(clothes, "name", params["asset_name"], "name")
    for key in ("license", "author", "description", "delete_group"):
        if params[key] is not None:
            put(clothes, key, params[key], key, argument=True)
    if request.words is not None:
        for key in ("license", "author"):
            if params[key] is not None:
                put(request.words.properties, key, params[key], "makeskin_" + key, argument=True)
    if params["destination"] == "library":
        put(general, "asset_source", request.fragment, "asset_source")
    return changed


def _try_with(params, request):
    """The recipe's next calls, keyed by tool, in the order to send them."""
    add_asset = dict(name=None, object_type=request.object_type)
    if params["destination"] == "library":
        add_asset["fragment"] = request.fragment
    else:
        add_asset["path"] = request.file_path
    return dict(mpfb_create_human_from_preset=dict(preset_name=None),
                mpfb_add_asset=add_asset,
                mpfb_check_intersections=dict(name=None))


def _warnings_for(request):
    warnings = []
    metadata = request.metadata
    if metadata["license_resolved_by"] == "mpfb_default":
        warnings.append("license is MPFB's default, {!s}, rather than anything somebody chose, "
                        "and the catalogues will show it. Pass 'license' to choose.".format(
                            metadata["license"]))
    if metadata["author_resolved_by"] == "mpfb_default":
        warnings.append("author is {:s} rather than anything somebody chose. Pass "
                        "'author' to choose.".format(
                            "empty, MPFB's default," if metadata["author"] is None
                            else "MPFB's default, {!s},".format(metadata["author"])))
    if metadata["description_resolved_by"] == "mpfb_default":
        warnings.append("description is MPFB's default rather than anything somebody chose.")
    if request.tree is not None:
        for key, value in (("license", request.mhmat_license), ("author", request.mhmat_author)):
            if value != metadata[key]:
                warnings.append("The MHMAT's {0:s} is {1!r} and the MHCLO's is {2!r}, since MakeSkin "
                                "and MakeClothes each hold one. Pass '{0:s}' to write one to "
                                "both.".format(key, value, metadata[key]))
    if request.delete_group is None or request.delete_group not in request.body.vertex_groups:
        warnings.append("'{:s}' has no delete group {!r}, so the asset hides none of the body "
                        "under it, and the body will show through wherever it pokes out.".format(
                            request.body.name, request.delete_group))
    for row in request.skipped_textures:
        if not row["blank"]:
            warnings.append("The {:s} texture was left out of the MHMAT: {:s}".format(
                row["slot"], row["message"]))
    return warnings


def _message_for(params, request, overwrote, counts, warnings):
    if params["dry_run"]:
        parts = ["Would write '{:s}' as '{:s}'; nothing was written.".format(
            request.subject.name, request.file_path)]
    else:
        parts = ["Wrote '{:s}' as '{:s}'.".format(request.subject.name, request.file_path)]
    parts.append(" {:d} exact and {:d} offset vertex matches against '{:s}'.".format(
        counts["exact"], counts["offset"], request.body.name))
    if overwrote:
        parts.append(" It replaced an existing asset's files; file_before says what that was.")
    if request.material_reason is not None:
        parts.append(" No material was written: {:s}".format(request.material_reason))
    if warnings:
        parts.append(" {:d} warning(s); see 'warnings'.".format(len(warnings)))
    parts.append(" try_with is how to see it on another body.")
    return "".join(parts)


def _settled_request(services, root_name, params, request):
    """Every refusal short of the validator, as ``(blocked_by, sentence, extra)``, or ``None``."""
    subject = request.subject
    if subject.type != "MESH":
        return ("not_a_mesh", "'{:s}' is a {:s}, not a mesh, so it cannot be an asset.".format(
            subject.name, str(subject.type)), dict())
    if services["ObjectService"].object_is_basemesh(subject):
        return ("subject_is_basemesh",
                "'{:s}' is the basemesh, which is what an asset fits rather than an asset. Name "
                "the mesh to write.".format(subject.name), dict())
    rejection = asset_name_rejection(params["asset_name"])
    if rejection is not None:
        # Defence in depth: mpfb-mcp refuses this before sending, and it is the last
        # statement before a path is assembled.
        return ("invalid_name", rejection + " Nothing was written.", dict())

    request.body, request.body_resolved_by, refusal = subject_resolution.resolve_asset_body(
        services, params["basemesh"], subject, "to match it to", "nothing was written")
    if refusal is not None:
        return (refusal[0], refusal[1], dict(candidates=refusal[2]))

    request.general_properties = mpfb_surface.general_object_properties(services)
    request.clothes_properties = mpfb_surface.make_clothes_properties(root_name)
    if request.clothes_properties is None or request.general_properties is None:
        raise mpfb_surface.MissingFromMpfb(
            "MPFB's MakeClothes or general object properties are not loaded, and this command "
            "cannot write an asset without them. Check mpfb_get_status.")

    return (_lookup_object_type(services, params, request)
            or _locate(services, params, request)
            or _metadata_refusal(request, params)
            or _delete_group_refusal(request, params)
            or _state_refusal(request))


def write_mesh_asset(params, resolution):  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches
    """Settle every refusal, match, stage, move, then mark the object."""
    services = resolution.services
    root_name = resolution.module.__name__
    request = _Request()

    def blocked(reason, message, **extra):
        return with_performed(_answer(params, request, blocked_by=reason, message=message,
                                      **extra), False)

    request.subject, request.resolved_by, message = subject_resolution.resolve_subject(
        params["name"], not_done="nothing was written", select="the mesh to write")
    if request.subject is None:
        return blocked("subject_not_found", message)

    refusal = _settled_request(services, root_name, params, request)
    if refusal is not None:
        return blocked(refusal[0], refusal[1], **refusal[2])

    _plan_material(services, root_name, params, request)

    previous = file_facts(request.file_path)
    file_before = previous if previous["exists"] else None
    existing = [path for path in _own_file_paths(request) if os.path.exists(path)]
    if existing and not params["overwrite"]:
        return blocked(
            "asset_exists",
            "'{:s}' already exists{:s}, and overwrite is false, so nothing was written. Pass "
            "overwrite=true to replace this asset's own files, or choose another name: there is "
            "no undo for a file across this socket.".format(
                existing[0],
                "" if file_before is None else ", written {!s}".format(file_before["modified"])),
            file_before=file_before, existing_files=existing)

    if params["destination"] == "library":
        shadowing = asset_sections.shadowing_file(services, request.asset_subdir,
                                                  request.file_path)
        if shadowing is not None:
            return blocked(
                "name_shadowed",
                "Another '{0:s}' exists at '{1:s}', and MPFB finds an asset by those two names "
                "and takes the first, so one written here might never be the one it finds. "
                "Nothing was written. Choose another name.".format(
                    request.fragment, shadowing["path"]),
                shadowed_by=shadowing)

    # Before the validator, which can create the very directory this reports on.
    state = mesh_asset_report.write_state(services, root_name, request.subject, request.body)
    report, validator_error = mesh_asset_report.validator(services, request.subject, request.body)
    if report is None or not report.get("all_checks_ok"):
        return blocked(
            "not_valid_as_asset",
            "{:s} This is the one check that blocks a write, because it is what MPFB's own write "
            "would refuse. Nothing was written.".format(
                validator_error or "MPFB's validator says this mesh cannot be an asset; see "
                                   "'validator'."),
            validator=report)

    request.allow_exact, exact_resolved_by = _allow_exact(root_name, params)
    request.uuid, request.uuid_resolved_by = _kept_or_new_uuid(request)
    warnings = _warnings_for(request)

    xref_cache_built = False
    if not state["xref_cache_exists"] and not params["dry_run"]:
        mesh_asset_report.build_xref_cache(services, request.body)
        xref_cache_built = True

    try:
        mhclo, reference_scale = _matched(services, request, params)
    except Exception as error:  # pylint: disable=broad-except
        return blocked(
            "match_failed",
            "MPFB's matching raised {:s}: {!s}. It runs before anything is written, so nothing "
            "was.".format(type(error).__name__, error),
            validator=report, xref_cache_built=xref_cache_built)

    counts = _counts(mhclo)
    check = _check(request, warnings)
    lost = (dict() if request.tree is None
            else makeskin.values_not_restored(services, request.words, request.tree))

    properties_set = []
    asset_lists_refreshed = False
    if params["dry_run"]:
        files = _planned_rows(request)
    else:
        try:
            files = _write(services, request, params, mhclo, reference_scale)
        except Exception as error:  # pylint: disable=broad-except
            now = file_facts(request.file_path)
            return blocked(
                "obj_does_not_match" if isinstance(error, _ObjDoesNotMatch) else "write_failed",
                "Writing '{:s}' failed, and no part of it was moved into place unless file_after "
                "says so: {:s}".format(request.file_path, str(error)),
                file_before=file_before, file_after=now if now["exists"] else None,
                xref_cache_built=xref_cache_built)
        warnings.extend(texture_writing.reload_stale_images(request.plans))
        properties_set = _set_properties(request, params)
        if params["destination"] == "library":
            services["AssetService"].update_all_asset_lists()
            asset_lists_refreshed = True

    _LOG.debug("write_mesh_asset: %r dry_run=%r", request.file_path, params["dry_run"])
    written = not params["dry_run"]
    overwrote = written and bool(existing)
    return with_performed(_answer(
        params, request,
        ready=True,
        written=written,
        overwrote=overwrote,
        file_before=file_before,
        files=files,
        object_type_before=request.object_type_before,
        match_counts=counts,
        delete_group=request.delete_group,
        delete_group_resolved_by=request.delete_group_resolved_by,
        delete_vertices=len(mhclo.delverts),
        max_pole=mhclo.max_pole,
        allow_exact_matching=request.allow_exact,
        allow_exact_matching_resolved_by=exact_resolved_by,
        uuid=request.uuid,
        uuid_resolved_by=request.uuid_resolved_by,
        license=request.metadata["license"],
        license_resolved_by=request.metadata["license_resolved_by"],
        author=request.metadata["author"],
        author_resolved_by=request.metadata["author_resolved_by"],
        description=request.metadata["description"],
        material_written=written and request.tree is not None,
        material_not_written_because=request.material_reason,
        textures_left_out=request.skipped_textures,
        values_not_restored=lost,
        xref_cache_built=xref_cache_built,
        xref_cache_missing=not state["xref_cache_exists"] and not xref_cache_built,
        asset_source=mpfb_surface.property_value(
            request.general_properties, "asset_source", request.subject),
        asset_source_updated="asset_source" in properties_set,
        asset_lists_refreshed=asset_lists_refreshed,
        properties_set=properties_set,
        selection_restored=True,
        check=check,
        try_with=_try_with(params, request),
        warnings=warnings,
        message=_message_for(params, request, overwrote, counts, warnings)), written)
