"""
``export_character``: write one character to one file another application can open.

MPFB writes no file when it exports; its documentation
([Exporting MPFB characters](https://github.com/makehumancommunity/makehuman-static-website/blob/master/content/MPFB/Docs/exporting/_index.md))
ends with the user selecting the character and running Blender's FBX exporter
by hand, with three settings. This is that step, for FBX, glTF and USD, and it
works on any character - an export copy from ``create_export_copy`` or not, so a
character that needs no processing costs one call.

**One self-contained file per export.** ``.fbx`` with its textures embedded
(``path_mode="COPY"``, ``embed_textures=True``, the two settings MPFB's
documentation names besides the selection), ``.glb``, and ``.usdz``. One file
is one artifact to name, report, and refuse to overwrite; textures written
beside it would be several.

**It writes outside the ``.blend``, so it owes what the two saving commands owe**
([mutating-tools.md](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)):
the name is a name and never a path (``shared/artifact_names.py``, the third
noun beside presets and saved expressions), an existing file is refused unless
``overwrite``, every precondition is settled before the exporter runs, and the
absolute ``path`` is in every answer, refusals included. **The directory is the
human's**, read by [`export_directory.py`](../export_directory.py) from the
add-on's preferences or ``--export-dir``, else ``<MPFB user data>/exports``;
``path_resolved_by`` says which. A directory the human named that does not exist
is refused (``export_directory_missing``), never created.

**Only the character is written.** Blender's exporters write the selection, so
the command selects the family - the root, which is the rig or else the body,
and every descendant, walked recursively because a garment with a sub-rig is a
grandchild - exports, and puts every object's selection back
(``selection.restored_all``). Another character, the original of an export copy,
lights and cameras are not selected. A family member that is not visible cannot
be selected, so it is not written either, and ``objects_left_out`` says so.

**The subject may have no basemesh.** A character whose basemesh was removed
behind a body proxy - ``create_export_copy`` with ``remove_basemesh`` - is found
through the proxy instead.

**Readiness facts, never refusals.** What tends to go wrong in another
application is reported per mesh, so the caller decides: the material MPFB
identifies (anything but ``gameengine`` is procedural, and MPFB's documentation
calls only GameEngine likely to translate), helper geometry still on the
basemesh, mask and subdivision modifiers, shape keys by kind, and a
topology-changing modifier beside shape keys. That last one is the case
``ExportService._apply_modifiers_keep_shapekeys()`` exists for. What each
exporter does with it was measured by FR 039 on a copy carrying MPFB's two masks
and 24 shape keys, re-imported into Blender: **FBX applies the masks and drops
every shape key** (13,070 vertices, no keys), while **glTF and USD keep the
shape keys and ignore the masks**, so the helper geometry and the body under the
garments come along (19,158 vertices, 24 keys; glTF splits vertices at UV seams
and reads back more). No exporter keeps both. The fix is ``create_export_copy``
with ``mask_modifiers: "BAKE"``.

**Engine presets** (``target_engine``) are fixed tables of exporter options, per
format, each value cited below. ``generic`` is Blender's defaults plus the
self-contained-file settings. A preset with no table for a format is refused,
naming the formats it has. The answer reports ``exporter_options``, exactly what
was passed, so a caller can reproduce the export in Blender's dialog. What this
cannot establish is that Unity, Unreal or Godot accept the file: the bridge
tests re-import each format into Blender, which proves a file reads back and
nothing about another application.

Sources for the preset values:

- ``unity`` / FBX: ``apply_scale_options="FBX_SCALE_ALL"`` so Unity does not
  import the character at 100x
  ([Katsbits, *Unity & Blender FBX Scale*](https://www.katsbits.com/codex/unity-blender-fbx-scale));
  ``axis_forward="-Z"``, ``axis_up="Y"``, ``use_space_transform=True``,
  ``bake_space_transform=False`` ("known to be broken with armatures"),
  ``mesh_smooth_type="FACE"``, ``add_leaf_bones=False`` and
  ``use_armature_deform_only=True`` "for control rigs (Rigify)"
  ([Cinevva, *Blender to Unity export checklist*](https://app.cinevva.com/guides/blender-to-unity-export-checklist)).
- ``unreal`` / FBX: every value is the default of the FBX settings in
  *Send to Unreal*, the add-on Epic Games released for this pipeline
  (``send2ue/resources/settings.json`` in
  [poly-hammer/BlenderTools](https://github.com/poly-hammer/BlenderTools), read
  2026-10-18): ``axis_forward="Y"``, ``axis_up="Z"``, ``global_scale=1.0``,
  ``apply_unit_scale=True``, ``apply_scale_options="FBX_SCALE_NONE"``,
  ``bake_space_transform=False``, ``mesh_smooth_type="FACE"``,
  ``use_tspace=False``, ``primary_bone_axis="Y"``, ``secondary_bone_axis="X"``,
  ``armature_nodetype="NULL"``, ``use_armature_deform_only=False``,
  ``add_leaf_bones=False``.
- ``godot`` / glTF: Godot's documentation recommends glTF 2.0, and the binary
  ``.glb`` export from Blender
  ([Godot, *Available 3D formats*](https://docs.godotengine.org/en/4.2/tutorials/assets_pipeline/importing_3d_scenes/available_formats.html));
  ``export_yup=True`` is glTF's own up axis and Blender's default, stated so the
  table says it. Godot is glTF only here, so ``godot`` with FBX or USD is
  refused.
- Every FBX: ``path_mode="COPY"``, ``embed_textures=True`` and
  ``use_selection=True``, MPFB's documentation's three settings. Every glTF:
  ``export_format="GLB"``, ``use_selection=True``. Every USD:
  ``selected_objects_only=True``, ``export_armatures=True``,
  ``export_shapekeys=True``, because a rig and shape keys are what an MPFB
  character is.
"""

# pylint: disable=invalid-name

__all__ = (
    "ENGINE_PRESETS",
    "FORMATS",
    "PARAMS",
    "SUMMARY",
    "export_character",
)

import os
import time

import bpy

from .. import export_directory
from ..log import get_logger
from ..shared import blender_data
from ..shared import mpfb_surface
from ..shared import selection
from ..shared import subject_resolution
from ..shared.artifact_names import file_facts
from ..shared.artifact_names import name_rejection
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.exportcharacter")

# Per format: the file extension and the settings that make one self-contained
# file of the selection, whatever the preset.
FORMATS = {
    "fbx": dict(extension=".fbx",
                common=dict(use_selection=True, path_mode="COPY", embed_textures=True)),
    "gltf": dict(extension=".glb",
                 common=dict(use_selection=True, export_format="GLB")),
    "usd": dict(extension=".usdz",
                common=dict(selected_objects_only=True, export_armatures=True,
                            export_shapekeys=True)),
}

# Per preset, the format it uses when none is named, and its exporter options
# per format. A format missing from a preset is refused. Sources: the module
# docstring, one per value.
ENGINE_PRESETS = {
    "generic": dict(default_format="fbx", formats=dict(fbx={}, gltf={}, usd={})),
    "unity": dict(default_format="fbx", formats=dict(fbx=dict(
        apply_scale_options="FBX_SCALE_ALL",
        axis_forward="-Z",
        axis_up="Y",
        use_space_transform=True,
        bake_space_transform=False,
        mesh_smooth_type="FACE",
        add_leaf_bones=False,
        use_armature_deform_only=True,
    ))),
    "unreal": dict(default_format="fbx", formats=dict(fbx=dict(
        axis_forward="Y",
        axis_up="Z",
        global_scale=1.0,
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_NONE",
        bake_space_transform=False,
        mesh_smooth_type="FACE",
        use_tspace=False,
        primary_bone_axis="Y",
        secondary_bone_axis="X",
        armature_nodetype="NULL",
        use_armature_deform_only=False,
        add_leaf_bones=False,
    ))),
    "godot": dict(default_format="gltf", formats=dict(gltf=dict(export_yup=True))),
}

PARAMS = (
    Param("export_name", TYPE_STRING, required=True,
          description="The file's name, never a path. Letters, digits, underscore, hyphen and "
                      "dot only; it becomes <export directory>/<export_name>.<extension>."),
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("format", TYPE_STRING, default=None, nullable=True, choices=tuple(sorted(FORMATS)),
          description="fbx, gltf (.glb) or usd (.usdz). Null takes the preset's format."),
    Param("target_engine", TYPE_STRING, default="generic", choices=tuple(ENGINE_PRESETS),
          description="Which preset of exporter options to use."),
    Param("overwrite", TYPE_BOOLEAN, default=False,
          description="Replace an existing file of this name. False by default: there is no "
                      "undo for a file across this socket."),
)

SUMMARY = ("Export a character - its rig, body and mesh assets - to one FBX, glTF or USD file "
           "in the export directory the bridge's user chose.")

# Modifiers that change how many vertices a mesh has, and so cannot be applied
# under shape keys by an exporter: MPFB's own two first, then Blender's other
# generators.
_TOPOLOGY_CHANGING = ("MASK", "SUBSURF", "MULTIRES", "DECIMATE", "REMESH", "BOOLEAN", "WELD",
                      "SOLIDIFY", "MIRROR", "ARRAY", "BEVEL", "SCREW", "SKIN", "TRIANGULATE",
                      "WIREFRAME", "BUILD", "EDGE_SPLIT", "NODES")

_HELPER_GROUPS = ("HelperGeometry", "JointCubes")

# The one material MPFB's documentation calls likely to translate; "empty" is a
# mesh with no material, which is not procedural either.
_NOT_PROCEDURAL = ("gameengine", "empty")


# ----------------------------------------------------------------------------
# The character
# ----------------------------------------------------------------------------


def _resolve(services, params):
    """``(subject, resolved_by, basemesh, bodyproxy, root, message)``."""
    ObjectService = services["ObjectService"]
    subject, resolved_by, message = subject_resolution.resolve_subject(
        params["name"], not_done="nothing was exported")
    if subject is None:
        return (None, resolved_by, None, None, None, message)
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    bodyproxy = ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Proxymeshes")
    body = basemesh if basemesh is not None else bodyproxy
    if body is None:
        # The shared sentence's shape (subject_resolution.resolve_basemesh), with
        # the proxy this command also accepts said in the middle of it.
        return (subject, resolved_by, None, None, None,
                "'{:s}' has no MakeHuman basemesh among its nearest relatives, so - with no body "
                "proxy either - there is no character to export, and nothing was exported. Call "
                "mpfb_get_object_info to see what it is related to.".format(subject.name))
    root = body.parent if body.parent is not None else body
    return (subject, resolved_by, basemesh, bodyproxy, root, None)


def _shape_key_kinds(services, blender_object):
    """Shape keys on one mesh, counted as ``modeling``, ``visemes``, ``face_units``, ``expression``, ``other``.

    ``face_units`` are the plain ARKit names ``create_export_copy`` loads, which
    is what a face-tracking pipeline looks for; ``expression`` are MPFB's
    composer keys, ``!ex-<unit>``, which it does not.
    """
    counts = dict(modeling=0, visemes=0, face_units=0, expression=0, other=0)
    keys = getattr(blender_object.data, "shape_keys", None)
    if keys is None:
        return counts
    visemes = set(mpfb_surface.required_module_level(services, "FaceService", "MICROSOFT_VISEMES"))
    visemes.update(mpfb_surface.required_module_level(services, "FaceService", "META_VISEMES"))
    face_units = set(mpfb_surface.required_module_level(services, "FaceService", "ARKIT_FACEUNITS"))
    target_service = services["TargetService"]
    for block in keys.key_blocks:
        name = str(block.name)
        if block == keys.reference_key:
            continue
        if name in visemes:
            counts["visemes"] += 1
        elif name in face_units:
            counts["face_units"] += 1
        elif name.startswith("!ex-"):
            counts["expression"] += 1
        elif name.startswith("$md"):
            counts["modeling"] += 1
        else:
            try:
                is_target = bool(target_service.shapekey_is_target(name))
            except Exception:  # pylint: disable=broad-except
                is_target = False
            counts["modeling" if is_target else "other"] += 1
    return counts


def _readiness(services, family, basemesh, root):
    """The facts about export readiness, per mesh and rolled up."""
    ObjectService = services["ObjectService"]
    MaterialService = services["MaterialService"]
    meshes = []
    for blender_object in family:
        if blender_object.type != "MESH":
            continue
        shape_keys = _shape_key_kinds(services, blender_object)
        shape_key_count = sum(shape_keys.values())
        topology = [str(modifier.name) for modifier in blender_object.modifiers
                    if modifier.type in _TOPOLOGY_CHANGING]
        meshes.append(dict(
            name=blender_object.name,
            object_type=ObjectService.get_object_type(blender_object) or None,
            material_identified_as=MaterialService.identify_material(
                MaterialService.get_material(blender_object, 0)),
            shape_keys=shape_keys,
            mask_modifiers=[str(modifier.name) for modifier in blender_object.modifiers
                            if modifier.type == "MASK"],
            subdivision_modifiers=[str(modifier.name) for modifier in blender_object.modifiers
                                   if modifier.type == "SUBSURF"],
            topology_changing_modifiers_beside_shape_keys=topology if shape_key_count else [],
        ))
    rig_identified_as = None
    if root.type == "ARMATURE":
        try:
            rig_identified_as = services["RigService"].identify_rig(root)
        except Exception:  # pylint: disable=broad-except
            rig_identified_as = None
    helper = None
    if basemesh is not None and basemesh in family:
        helper = blender_data.vertices_in_groups(basemesh, _HELPER_GROUPS)
    return dict(
        meshes=meshes,
        procedural_material_meshes=[mesh["name"] for mesh in meshes
                                    if mesh["material_identified_as"] not in _NOT_PROCEDURAL],
        meshes_with_modifiers_beside_shape_keys=[
            mesh["name"] for mesh in meshes if mesh["topology_changing_modifiers_beside_shape_keys"]],
        helper_vertices=helper,
        rig_identified_as=rig_identified_as,
    )


# ----------------------------------------------------------------------------
# The answer
# ----------------------------------------------------------------------------


def _blocked(request, reason, message, **extra):
    answer = dict(
        found=request["root"] is not None,
        ready=False,
        exported=False,
        blocked_by=reason,
        subject_name=None if request["subject"] is None else request["subject"].name,
        subject_resolved_by=request["subject_resolved_by"],
        basemesh_name=None if request["basemesh"] is None else request["basemesh"].name,
        root_name=None if request["root"] is None else request["root"].name,
        export_name=request["export_name"],
        requested_format=request["requested_format"],
        format=request["format"],
        target_engine=request["target_engine"],
        known_formats_for_target_engine=request["known_formats"],
        export_directory=request["directory"],
        path_resolved_by=request["resolved_by"],
        # Always present, on a refusal as much as on a success: the caller
        # cannot see the directory, and "which file would this have been" is the
        # first thing they need in order to fix a name or pass overwrite.
        path=request["path"],
        overwrote=False,
        file_before=request["file_before"],
        message=message,
    )
    answer.update(extra)
    return with_performed(answer, False)


def _request(services, params):
    """Everything that has to be true before the exporter runs."""
    preset = ENGINE_PRESETS[params["target_engine"]]
    chosen_format = params["format"] or preset["default_format"]
    directory, resolved_by, exists = export_directory.resolve(
        services["LocationService"].get_user_data("exports"))
    request: dict = dict(
        export_name=params["export_name"],
        requested_format=params["format"],
        format=chosen_format,
        target_engine=params["target_engine"],
        known_formats=sorted(preset["formats"]),
        directory=directory,
        resolved_by=resolved_by,
        directory_exists=exists,
        name_rejection=name_rejection(params["export_name"], "export"),
        path=None,
        file_before=None,
    )
    if request["name_rejection"] is None:
        request["path"] = os.path.join(directory,
                                       params["export_name"] + FORMATS[chosen_format]["extension"])
        facts = file_facts(request["path"])
        request["file_before"] = facts if facts["exists"] else None
    (request["subject"], request["subject_resolved_by"], request["basemesh"],
     request["bodyproxy"], request["root"], request["subject_message"]) = _resolve(services, params)
    return request


def _refusal(params, request):
    """The first precondition that fails, as ``(blocked_by, sentence)``, or None. Order is the contract."""
    if request["root"] is None:
        return ("subject_not_found", request["subject_message"])
    if request["name_rejection"] is not None:
        # Defence in depth: mpfb-mcp refuses this before a request is built (see
        # mpfbmcp/artifact_names.py). It is the last statement before a path is
        # assembled.
        return ("invalid_name", request["name_rejection"] + " An export is always "
                "<export_name>.<extension> in the export directory, so a name that could become "
                "a path is refused rather than resolved.")
    if request["format"] not in ENGINE_PRESETS[params["target_engine"]]["formats"]:
        return ("format_not_supported_by_engine",
                "The {:s} preset has no exporter options for {:s}, so nothing was exported. It "
                "has: {:s}; known_formats_for_target_engine lists them.".format(
                    params["target_engine"], request["format"],
                    ", ".join(request["known_formats"])))
    if not request["directory_exists"] and request["resolved_by"] != export_directory.RESOLVED_BY_DEFAULT:
        return ("export_directory_missing",
                "The export directory '{:s}', set {:s}, does not exist, and a directory somebody "
                "named is not created on their behalf, so nothing was exported. Ask the person "
                "running Blender to create it or correct the MPFB Bridge's export directory "
                "preference.".format(
                    request["directory"],
                    "with --export-dir" if request["resolved_by"] == export_directory.RESOLVED_BY_COMMAND_LINE
                    else "in the MPFB Bridge's preferences"))
    previous = request["file_before"]
    if previous is not None and not params["overwrite"]:
        return ("export_exists",
                "A file '{:s}' already exists, written {!s}, and overwrite is false, so nothing "
                "was written. Pass overwrite=true to replace it, or choose another export_name - "
                "there is no undo for a file across this socket.".format(
                    request["path"], previous["modified"]))
    if bpy.context.mode != "OBJECT":
        return ("not_object_mode",
                "Blender is in {:s} mode, and the exporters work on the selection in object mode, "
                "so nothing was exported. Switch to object mode and call again.".format(
                    str(bpy.context.mode)))
    return None


def _exporter(chosen_format) -> tuple:
    """The operator for a format, called with its keyword arguments."""
    if chosen_format == "fbx":
        return ("export_scene.fbx", bpy.ops.export_scene.fbx)
    if chosen_format == "gltf":
        return ("export_scene.gltf", bpy.ops.export_scene.gltf)
    return ("wm.usd_export", bpy.ops.wm.usd_export)


def _message(answer):
    parts = ["Exported '{:s}' ({:d} object(s)) to '{:s}' as {:s} with the {:s} preset, {!s} "
             "bytes.".format(answer["root_name"], len(answer["objects_exported"]), answer["path"],
                             answer["format"], answer["target_engine"], answer["size_bytes"])]
    if answer["overwrote"]:
        parts.append(" It replaced an existing file, which cannot be restored from here.")
    if answer["objects_left_out"]:
        parts.append(" {:d} family member(s) are not visible and were not written; see "
                     "objects_left_out.".format(len(answer["objects_left_out"])))
    readiness = answer["readiness"]
    if readiness["procedural_material_meshes"]:
        parts.append(" {:d} mesh(es) carry a procedural material, which other applications rarely "
                     "read; mpfb_create_export_copy with material_type 'GAMEENGINE' gives a copy "
                     "GameEngine materials.".format(len(readiness["procedural_material_meshes"])))
    if readiness["meshes_with_modifiers_beside_shape_keys"]:
        parts.append(" {:s} carry a topology-changing modifier beside shape keys: FBX applies "
                     "the modifier and drops the keys, glTF and USD keep the keys and ignore the "
                     "modifier. mpfb_create_export_copy's mask_modifiers and subdiv_modifiers "
                     "'BAKE' bake them on the basemesh, and on the body proxy; a mesh asset's "
                     "are left as they are.".format(
                         ", ".join(readiness["meshes_with_modifiers_beside_shape_keys"])))
    if readiness["helper_vertices"]:
        parts.append(" The basemesh still has its helper geometry; mpfb_create_export_copy "
                     "removes it.")
    return "".join(parts)


def export_character(params, resolution):  # pylint: disable=too-many-locals
    """Select one character, export it to one file, and put the selection back."""
    services = resolution.services
    request = _request(services, params)
    refusal = _refusal(params, request)
    if refusal is not None:
        return _blocked(request, *refusal)

    root = request["root"]
    family = blender_data.with_descendants(root)
    visible = [blender_object for blender_object in family if blender_object.visible_get()]
    left_out = [dict(name=blender_object.name, reason="not_visible")
                for blender_object in family if blender_object not in visible]
    readiness = _readiness(services, family, request["basemesh"], root)

    options = dict(FORMATS[request["format"]]["common"])
    options.update(ENGINE_PRESETS[params["target_engine"]]["formats"][request["format"]])
    operator_name, operator = _exporter(request["format"])
    previous = request["file_before"]

    if request["resolved_by"] == export_directory.RESOLVED_BY_DEFAULT:
        os.makedirs(request["directory"], exist_ok=True)
    started = time.perf_counter()
    with selection.restored_all():
        try:
            for blender_object in bpy.context.view_layer.objects:
                blender_object.select_set(False)
            for blender_object in visible:
                blender_object.select_set(True)
            bpy.context.view_layer.objects.active = root if root in visible else visible[0]
            outcome = operator(filepath=request["path"], **options)
        except Exception as error:  # pylint: disable=broad-except
            now = file_facts(request["path"])
            return _blocked(
                request, "export_failed",
                "Blender's {:s} raised while writing '{:s}': {!s}. file_after reports what is at "
                "that path now.".format(operator_name, request["path"], error),
                file_after=now if now["exists"] else None, exporter=operator_name,
                exporter_options=options)
    elapsed = int(round((time.perf_counter() - started) * 1000))
    written = file_facts(request["path"])
    if "FINISHED" not in outcome or not written["exists"]:
        return _blocked(
            request, "export_failed",
            "Blender's {:s} returned {!s} and '{:s}' {:s}.".format(
                operator_name, sorted(outcome), request["path"],
                "exists" if written["exists"] else "was not written"),
            file_after=written if written["exists"] else None, exporter=operator_name,
            exporter_options=options)

    answer = dict(
        found=True,
        ready=True,
        exported=True,
        blocked_by=None,
        subject_name=request["subject"].name,
        subject_resolved_by=request["subject_resolved_by"],
        basemesh_name=None if request["basemesh"] is None else request["basemesh"].name,
        bodyproxy_name=None if request["bodyproxy"] is None else request["bodyproxy"].name,
        root_name=root.name,
        export_name=params["export_name"],
        requested_format=params["format"],
        format=request["format"],
        target_engine=params["target_engine"],
        known_formats_for_target_engine=request["known_formats"],
        export_directory=request["directory"],
        path_resolved_by=request["resolved_by"],
        path=request["path"],
        size_bytes=written["size_bytes"],
        modified=written["modified"],
        overwrote=previous is not None,
        file_before=previous,
        objects_exported=[dict(name=blender_object.name, type=blender_object.type,
                               object_type=services["ObjectService"].get_object_type(blender_object)
                               or None)
                          for blender_object in visible],
        objects_left_out=left_out,
        exporter=operator_name,
        exporter_options=options,
        export_ms=elapsed,
        readiness=readiness,
    )
    answer["message"] = _message(answer)
    _LOG.debug("export_character: wrote %r", request["path"])
    return with_performed(answer, True)
