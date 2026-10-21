"""
``add_asset``: equip one MHCLO asset, and report what it cost.

**The work itself is MPFB's.** ``HumanService.add_mhclo_asset()`` imports the
mesh, records ``asset_source`` and ``object_type``, builds the material, fits the
mesh, builds the delete group and masks the body under it, rigs the result if a
rig is there, and adds a subdivision modifier. None of that is reimplemented
here. What *is* here is everything around it: the vocabulary checks MPFB does
not make, the observations that have to happen **before** the call to be true,
and the reading-back afterwards of things the function reports to nobody.

The section table comes from
[`shared/asset_sections.py`](../shared/asset_sections.py), shared with
``list_assets`` on purpose: this command is handed the ``object_type`` and
``fragment`` that catalogue reported, and the only thing that turns the first
back into the asset subdir needed to resolve the second is MPFB's section table.

Three things are worth naming.

**``object_type`` is normalised, and the normalisation hides a mismatch.** It is
``add_mhclo_asset()``'s ``asset_type``, which that function stores as
``str(asset_type).lower().capitalize()``, so
``eyes``, ``Eyes`` and ``EYES`` all become ``Eyes`` - and the asset *subdir*
name happens to work as well as the object type for every current section. The
value is validated against MPFB's own table anyway and the recorded form is
echoed back, because relying on that coincidence would break the day a two-word
type appears. Note also that the ``clothes`` branch inside the function - the
one that interpolates the delete group onto a body proxy - is keyed on the
**raw** argument rather than the normalised one, so a garment labelled ``Hair``
does not get it. That is correct behaviour, and it is exactly why the argument
must be right.

**Proxies: MPFB has three code paths and they disagree.**
``add_mhclo_asset()`` alone imports and fits the proxy but does not hide the
basemesh, copy the scale factor, create the proxy's extra vertex groups or run
the corrective pass. ``HumanService._check_add_proxy()`` calls it with
``material_type="NONE"`` and then does all four. The asset library's proxy
operator does not call ``add_mhclo_asset()`` at all and carries a third variant.
This follows ``_check_add_proxy()``: it is the service layer's own answer, it is
what ``deserialize_from_mhm()`` uses, and it is the one a caller comparing
against a loaded ``.mhm`` would expect. The divergence is reported in
``proxy_extras`` rather than normalised away. Reaching ``_proxy_corrective()``
is reaching a private name, which is the one place this command bends the rule
about module-level names - it is a member of a service already resolved from
``SERVICES``, so it costs nothing at import time, and it is read with
``getattr`` and degraded from.

**A delete group is not guaranteed.** ``update_delete_group()`` returns early
when the MHCLO defines no delete vertices, creating neither the vertex group nor
the mask modifier, so the fields describing it are observed from the objects
rather than derived from the filename.

**A failed import is not a no-op**, which is why ``partial_objects_created`` is
on the refusal: ``add_mhclo_asset()`` raises ``IOError`` when the mesh import
produced nothing, and the import may have left an object behind first.

The behaviours above are **MPFB's, reproduced rather than tidied up**. Each
arrived here from the generated program this command replaced, where it had
been established against a real install; a reimplementation that fixed one
would be changing what the tool answers under cover of a migration.

**A sub-rig equipped on a placed character is bound wrong from the start**,
and the answer says so (``subrigs_broken``,
[FR 045](../../../feature-requests/done/045-placing-a-character/README.md)):
MPFB's ``CHILD_OF`` inverse on the sub-rig's root is resolved before the
sub-rig is parented to the rig, which is right only while the rig is at the
origin facing 0. FR 045's live check saw it drag ``ponytail01`` 5.7 m, and stay
that far off after the character was moved back to the origin;
``mpfb_refit_human`` re-binds it. It is the same measured list
``place_character`` reports, read by [`shared/placement.py`](../shared/placement.py),
so it names every badly bound sub-rig on the character, not only a new one.
"""

# The local bindings below are spelled with MPFB's own capitalisation, which is
# what the program this replaced used, which is in turn what MPFB's own
# source uses.
# pylint: disable=invalid-name

__all__ = (
    "PARAMS",
    "SUMMARY",
    "add_asset",
)

import os

import bpy

from ..log import get_logger
from ..shared import asset_sections
from ..shared import blender_data
from ..shared import mpfb_surface
from ..shared import placement
from ..shared import selection
from ..shared import subject_resolution
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_INTEGER
from ..validation import TYPE_STRING

_LOG = get_logger("commands.addasset")

# MPFB's four material models, and the one that is only meaningful for eyes.
# PROCEDURAL_EYES builds an eye node tree from MPFB's own data; on anything else
# it would produce a garment with eye shading and no complaint anywhere.
MATERIAL_TYPES = ("MAKESKIN", "GAMEENGINE", "PROCEDURAL_EYES", "NONE")
EYES_ONLY_MATERIAL_TYPES = ("PROCEDURAL_EYES",)

# The per-type defaults, taken from MPFB's own settings panel and from
# _check_add_proxy() rather than from the function signature, whose single
# default of MAKESKIN is right for exactly one of the eight.
DEFAULT_MATERIAL_TYPES = (
    ("Proxymeshes", "NONE"),
)
FALLBACK_MATERIAL_TYPE = "MAKESKIN"

PARAMS = (
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="Any object in the character's family. Omit or pass null to use whatever "
                      "object is currently active."),
    Param("path", TYPE_STRING, default=None, nullable=True,
          description="Absolute path to the MHCLO, as list_assets reports it. Pass this or "
                      "'fragment', never both."),
    Param("fragment", TYPE_STRING, default=None, nullable=True,
          description="The portable '<pack>/<file>.mhclo' fragment list_assets reports. Resolved "
                      "against this Blender's asset roots for the subdir 'object_type' implies."),
    Param("object_type", TYPE_STRING, required=True,
          description="MPFB's object type for this asset - 'Clothes', 'Eyes', 'Hair', "
                      "'Proxymeshes'... Required: MPFB's own 'Clothes' default is wrong for six "
                      "of the eight types and mislabels a body part silently."),
    Param("material_type", TYPE_STRING, default=None, nullable=True,
          description="MAKESKIN, GAMEENGINE, PROCEDURAL_EYES or NONE. Omit for MPFB's own "
                      "default for this asset type."),
    Param("subdiv_levels", TYPE_INTEGER, default=1, minimum=0,
          description="Subdivision levels on the equipped asset. 0 adds no modifier at all."),
    Param("set_up_rigging", TYPE_BOOLEAN, default=True,
          description="Rig the asset to the character's rig, if there is one when it is "
                      "attached. Nothing rigs it afterwards."),
    Param("interpolate_weights", TYPE_BOOLEAN, default=True,
          description="Interpolate vertex weights from the basemesh."),
    Param("import_subrig", TYPE_BOOLEAN, default=True,
          description="Import the asset's own sub-rig where it ships one."),
    Param("import_weights", TYPE_BOOLEAN, default=True,
          description="Load the asset's own .mhw weights file where it ships one."),
)

SUMMARY = "Equip one MHCLO asset - clothes, hair, eyes, a proxy - on a character."


def _default_material_type(object_type):
    for candidate, material_type in DEFAULT_MATERIAL_TYPES:
        if candidate == object_type:
            return material_type
    return FALLBACK_MATERIAL_TYPE


def _material_types_for(object_type):
    """Which material models are meaningful for this asset type."""
    allowed = []
    for material_type in MATERIAL_TYPES:
        if material_type in EYES_ONLY_MATERIAL_TYPES and object_type != "Eyes":
            continue
        allowed.append(material_type)
    return allowed


def _mhclo_material(mhclo_path):
    """Whether the MHCLO names a material, and which file it names.

    Reproduces one line of ``Mhclo.load()``: a line whose first word is
    ``material`` names an MHMAT relative to the MHCLO's own directory. It is
    reproduced rather than imported, because ``entities/clothes/mhclo.py`` is an
    MPFB submodule and importing one of those is what the ``sys.modules`` scan
    exists to avoid.

    It is read for one reason: ``add_mhclo_asset()`` guards its whole material
    block with ``if mhclo.material is not None``, so an MHCLO with no material
    line produces an object with no material and no complaint. Without this the
    warning could not tell that case apart from a material that failed to build.
    Returns ``(None, None)`` when the file cannot be read at all, which is
    reported as "not known" rather than as "no material".
    """
    try:
        with open(mhclo_path, "r", encoding="utf8", errors="surrogateescape") as mhclo_file:
            for line in mhclo_file:
                words = line.split()
                if len(words) > 1 and words[0] == "material":
                    return (True, os.path.join(os.path.dirname(mhclo_path), words[1]))
                if len(words) > 0 and words[0] == "verts":
                    # The vertex block is the bulk of the file and no material
                    # line follows it. Stop rather than read a megabyte.
                    break
    except Exception:  # pylint: disable=broad-except
        return (None, None)
    return (False, None)


def _weights_files_beside(mhclo_path):
    """The ``.mhw`` files ``load_custom_weights()`` could find for this asset.

    ``Mhclo.get_weights_filename()`` builds ``<mhclo path without extension>``
    plus an optional rig-type suffix plus ``.mhw``, and every one of those reads
    is guarded by ``os.path.isfile()`` - so an asset with none is loaded without
    weights and without a word being said. This is that silence, made visible.
    """
    base = os.path.splitext(mhclo_path)[0]
    directory = os.path.dirname(base)
    prefix = os.path.basename(base) + "."
    found = []
    try:
        entries = sorted(os.listdir(directory))
    except OSError:
        return found
    for entry in entries:
        if entry.startswith(prefix) and entry.endswith(".mhw"):
            found.append(entry)
    return found


def _modifier_records(blender_object):
    """(name, type, vertex_group) per modifier, so a diff can name what appeared."""
    records = []
    if blender_object is None:
        return records
    for modifier in getattr(blender_object, "modifiers", None) or []:
        records.append((
            str(getattr(modifier, "name", "")),
            str(getattr(modifier, "type", "")),
            str(getattr(modifier, "vertex_group", "") or ""),
        ))
    return records


def _added_modifiers(before, after):
    remaining = list(before)
    appeared = []
    for record in after:
        if record in remaining:
            remaining.remove(record)
        else:
            appeared.append(record)
    return appeared


def _has_mask_for(blender_object, group_name):
    for name, modifier_type, vertex_group in _modifier_records(blender_object):
        if modifier_type == "MASK" and (vertex_group == group_name or name == group_name):
            return True
    return False


def _hides_the_base_mesh(blender_object):
    """Whether a *body-proxy* hide modifier is already on this basemesh.

    Not ``_has_mask_for(basemesh, "body")``, which is always true: every
    basemesh MPFB creates already carries a ``Hide helpers`` MASK modifier on
    the vertex group ``body``. The two modifiers differ only in
    ``invert_vertex_group`` - ``Hide helpers`` shows the body and hides the
    helper geometry, while the one a body proxy needs inverts that and hides the
    body itself - so the inversion is what has to be tested. Asking the looser
    question would mean the modifier was never added and the basemesh stayed
    visible under its own proxy.
    """
    for modifier in (getattr(blender_object, "modifiers", None) or []):
        if str(getattr(modifier, "type", "")) != "MASK":
            continue
        if str(getattr(modifier, "vertex_group", "")) != "body":
            continue
        if bool(getattr(modifier, "invert_vertex_group", False)):
            return True
    return False


class _Request:
    """One call's resolved arguments, so the refusals can be read in one place."""

    __slots__ = ("sections", "sections_from_mpfb", "known_asset_types", "normalized_asset_type",
                 "asset_type_recognized", "asset_subdir", "material_type",
                 "material_type_defaulted", "allowed_material_types", "resolved_path",
                 "resolved_by")


def _resolve_arguments(services, params):
    """The type against MPFB's table, then the file. Nothing is touched yet.

    Both are mistakes a caller can fix without looking at the scene, so both are
    worth reporting even when the scene would also have refused.
    """
    request = _Request()
    request.resolved_by = "path" if params["path"] is not None else "fragment"

    request.sections, request.sections_from_mpfb = asset_sections.read_sections(services)
    request.known_asset_types = asset_sections.mesh_asset_types(services, request.sections)
    request.normalized_asset_type = asset_sections.normalize_asset_type(params["object_type"])

    request.asset_type_recognized = False
    for candidate in request.known_asset_types:
        if candidate.lower() == str(params["object_type"]).strip().lower():
            request.normalized_asset_type = candidate
            request.asset_type_recognized = True

    request.asset_subdir = asset_sections.subdir_for_object_type(
        request.sections, request.normalized_asset_type)

    material_type = params["material_type"]
    request.material_type_defaulted = material_type is None
    if request.material_type_defaulted:
        material_type = _default_material_type(request.normalized_asset_type)
    else:
        material_type = str(material_type).strip().upper()
    request.material_type = material_type
    request.allowed_material_types = _material_types_for(request.normalized_asset_type)

    request.resolved_path = None
    if params["path"] is not None:
        request.resolved_path = mpfb_surface.as_path(params["path"])
    elif request.asset_subdir is not None:
        # find_asset_absolute_path() matches on *basename*, prefers a candidate
        # whose parent directory also matches, and otherwise returns the first
        # hit - so two packs shipping hat.mhclo resolve to a coin toss. Whatever
        # it chooses is reported, which is the acting-command counterpart of
        # list_assets' pack_ambiguous.
        try:
            request.resolved_path = mpfb_surface.as_path(
                services["AssetService"].find_asset_absolute_path(
                    params["fragment"], request.asset_subdir))
        except Exception:  # pylint: disable=broad-except
            request.resolved_path = None
    return request


def _blocked(subject, basemesh, subject_resolved_by, params, request, reason, message, **extra):
    """One shape for every refusal, so a caller can branch on ``blocked_by``."""
    answer = dict(
        found=basemesh is not None,
        ready=False,
        added=False,
        blocked_by=reason,
        subject_name=None if subject is None else subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=None if basemesh is None else basemesh.name,
        asset_object_name=None,
        requested_object_type=params["object_type"],
        path_resolved_by=request.resolved_by,
        resolved_path=None,
        message=message,
    )
    answer.update(extra)
    return with_performed(answer, False)


def _refusal(subject, basemesh, subject_resolved_by, params, request, message):
    """The first refusal that applies, or ``None``."""
    def blocked(reason, text, **extra):
        return _blocked(subject, basemesh, subject_resolved_by, params, request,
                        reason, text, **extra)

    if basemesh is None:
        return blocked("subject_not_found", message,
                       known_object_types=request.known_asset_types)
    if not request.asset_type_recognized:
        return blocked(
            "unknown_object_type",
            "'{!s}' is not an MHCLO asset type MPFB knows, so nothing was equipped. "
            "known_object_types lists what this Blender accepts; each is the 'object_type' "
            "mpfb_list_assets reports for an entry. Skins, poses and ink layers are in that "
            "catalogue but are not mesh assets and cannot be added with this tool.".format(
                params["object_type"]),
            known_object_types=request.known_asset_types,
            section_table_from_mpfb=request.sections_from_mpfb)
    if request.material_type not in request.allowed_material_types:
        return blocked(
            "invalid_material_type",
            "'{!s}' is not a material type for a {:s} asset, so nothing was equipped. "
            "PROCEDURAL_EYES builds MPFB's eye node tree and is meaningful only for Eyes; the "
            "others apply to every type. Omit material_type to take MPFB's own default for this "
            "asset type.".format(params["material_type"], request.normalized_asset_type),
            object_type=request.normalized_asset_type,
            allowed_material_types=request.allowed_material_types)
    if request.asset_subdir is None:
        # Only reachable through the fallback table, or through an MPFB whose
        # section table has a mesh type with no subdir. Reported rather than
        # turned into a confusing "asset not found".
        return blocked(
            "no_asset_subdir",
            "MPFB's asset library table names no asset subdir for the type '{:s}', so a fragment "
            "cannot be resolved to a file. Pass the absolute 'path' mpfb_list_assets reports "
            "instead.".format(request.normalized_asset_type),
            object_type=request.normalized_asset_type,
            section_table_from_mpfb=request.sections_from_mpfb)
    if request.resolved_path is None or not os.path.isfile(request.resolved_path):
        if params["path"] is not None:
            not_found_message = (
                "No file exists at '{!s}', so nothing was equipped. Pass the 'path' "
                "mpfb_list_assets reports for an installed asset, or its 'fragment' to have this "
                "Blender's asset roots searched.".format(params["path"]))
        else:
            not_found_message = (
                "The fragment '{!s}' resolved to no file under this Blender's '{!s}' asset roots, "
                "so nothing was equipped. The asset may not be installed here, or the fragment "
                "may belong to a different asset type - fragments are resolved per subdir, and "
                "the subdir comes from object_type.".format(
                    params["fragment"], request.asset_subdir))
        return blocked("asset_not_found", not_found_message,
                       asset_subdir=request.asset_subdir,
                       resolved_path=request.resolved_path)
    if basemesh.mode != "OBJECT" or bpy.context.mode != "OBJECT":
        # Two checks rather than one, and both are needed. add_mhclo_asset()
        # calls bpy.ops.object.shade_smooth() and the fitting code activates
        # objects, and bpy.ops polls on the *context* mode - so an unrelated
        # object left in edit mode fails the operator even though the basemesh
        # itself looks fine.
        return blocked(
            "not_object_mode",
            "Blender is in {:s} mode and the basemesh '{:s}' is in {:s} mode. Importing and "
            "fitting an asset runs operators that require OBJECT mode, so nothing was equipped. "
            "Leave edit mode and call again.".format(
                str(bpy.context.mode), basemesh.name, str(basemesh.mode)))
    return None


def _proxy_extras(services, basemesh, asset_object, general_properties, warnings):
    """``HumanService._check_add_proxy()``'s four extra steps, and what they did.

    See this module's docstring for why this path and not ``add_mhclo_asset()``
    alone or the asset library operator's.
    """
    hide_modifier_added = False
    if not _hides_the_base_mesh(basemesh):
        modifier = basemesh.modifiers.new("Hide base mesh", "MASK")
        modifier.vertex_group = "body"
        modifier.invert_vertex_group = True
        hide_modifier_added = True

    scale_factor_copied = False
    if general_properties is not None:
        try:
            scale_factor = general_properties.get_value(
                "scale_factor", entity_reference=basemesh)
            general_properties.set_value(
                "scale_factor", scale_factor, entity_reference=asset_object)
            scale_factor_copied = True
        except Exception:  # pylint: disable=broad-except
            scale_factor_copied = False

    all_extra_groups = mpfb_surface.module_level(
        services, "HumanService", "ALL_EXTRA_GROUPS", fallback=None)
    extra_groups_created = []
    proxy_uuid = mpfb_surface.property_value(general_properties, "uuid", asset_object)
    if proxy_uuid and all_extra_groups and proxy_uuid in all_extra_groups:
        for vgroup_name in all_extra_groups[proxy_uuid].keys():
            vgroup = asset_object.vertex_groups.new(name=vgroup_name)
            vgroup.add(all_extra_groups[proxy_uuid][vgroup_name], 1.0, "ADD")
            extra_groups_created.append(str(vgroup_name))

    corrective = getattr(services["HumanService"], "_proxy_corrective", None)
    corrective_applied = False
    if corrective is not None:
        try:
            corrective(asset_object)
            corrective_applied = True
        except Exception:  # pylint: disable=broad-except
            corrective_applied = False
            warnings.append(
                "MPFB's proxy corrective pass raised while fixing the proxy's left/right vertex "
                "weights. The proxy is attached, but bones may deform the wrong side of it.")
    else:
        warnings.append(
            "HumanService._proxy_corrective() was not found in this MPFB, so the proxy's "
            "left/right weight correction was skipped. The proxy is attached and fitted; this "
            "affects only mirrored vertex weights.")

    return dict(
        basemesh_hidden=hide_modifier_added,
        basemesh_hide_modifier_present=_hides_the_base_mesh(basemesh),
        scale_factor_copied=scale_factor_copied,
        extra_vertex_groups_created=extra_groups_created,
        corrective_applied=corrective_applied,
        uuid=proxy_uuid,
    )


def _warnings_for(params, request, names_material, existing_rig, weights_beside,
                  rig_is_generated_rigify, warnings):
    """Everything MPFB does silently that a caller would want to have been told."""
    if names_material is False:
        warnings.append(
            "The MHCLO names no material, so the asset has whatever material the imported mesh "
            "came with - usually none. MPFB only logs this.")
    elif names_material is True and request.material_type == "NONE":
        warnings.append(
            "material_type was NONE while the MHCLO names a material, so MPFB deleted the "
            "imported mesh's materials and created nothing. That is the proxy path, and it is not "
            "obvious from the argument name.")
    elif names_material is None:
        warnings.append(
            "The MHCLO could not be read to see whether it names a material, so nothing is "
            "claimed about the asset's material either way.")

    if params["set_up_rigging"] and existing_rig is None:
        warnings.append(
            "set_up_rigging was requested but this character has no rig, so the asset is parented "
            "to the basemesh and will not deform. MPFB rigs a garment only if a rig exists at the "
            "moment it is attached and nothing rigs it afterwards - not mpfb_refit_human either. "
            "Add the rig with mpfb_add_rig first, then re-add this asset.")
    if params["import_weights"] and not weights_beside:
        warnings.append(
            "import_weights was requested but no .mhw weights file ships beside this asset, so "
            "its weights are whatever interpolation produced. MPFB checks for the file and says "
            "nothing when it is absent.")
    if rig_is_generated_rigify:
        warnings.append(
            "This character's rig is a *generated* Rigify rig. The asset was rigged against it, "
            "but RigifyHelpers.adjust_children_for_rigify() handles only what is on the character "
            "when generation runs and will not run again - so this asset did not get that "
            "handling. Add assets to the meta rig and generate afterwards.")
    return warnings


def _message_for(request, basemesh, asset_object, existing_rig, set_up_rigging,
                 delete_group_name, subrig, subrigs_broken, warnings):
    """What happened, said once, in the order a reader wants it."""
    parts = ["Equipped '{:s}' on '{:s}' as '{:s}', of type {:s}.".format(
        os.path.basename(request.resolved_path), basemesh.name,
        asset_object.name if asset_object is not None else "?",
        request.normalized_asset_type)]
    if request.material_type_defaulted:
        parts.append(" material_type was not given and defaulted to {:s} for this asset "
                     "type.".format(request.material_type))
    if existing_rig is not None and set_up_rigging:
        parts.append(" It was rigged to '{:s}'.".format(existing_rig.name))
    else:
        parts.append(" It is parented to the basemesh and follows no armature.")
    if delete_group_name is None:
        parts.append(" The MHCLO defines no delete group, so no part of the body is masked "
                     "under it.")
    for record in subrigs_broken:
        if subrig is not None and record["subrig_object_name"] == subrig.name:
            parts.append(" Its sub-rig '{:s}' was bound while the character stood away from the "
                         "origin, which MPFB gets wrong, so in a render the asset's "
                         "sub-rig-weighted vertices are dragged {:.2f} m away (subrigs_broken). "
                         "Call mpfb_refit_human to re-bind it.".format(
                             subrig.name, record["displacement"]))
    if warnings:
        parts.append(" {:d} warning(s); see 'warnings'.".format(len(warnings)))
    return "".join(parts)


def add_asset(params, resolution):  # pylint: disable=too-many-locals,too-many-statements
    """Equip one MHCLO asset, having checked the type and the file first."""
    services = resolution.services
    object_service = services["ObjectService"]
    material_service = services["MaterialService"]
    GeneralObjectProperties = mpfb_surface.general_object_properties(services)

    basemesh, subject, subject_resolved_by, message = subject_resolution.resolve_basemesh(
        services, params["name"],
        not_done="nothing was equipped",
        not_a_character="there is nothing to equip, since mesh assets attach to a basemesh")
    request = _resolve_arguments(services, params)

    refused = _refusal(subject, basemesh, subject_resolved_by, params, request, message)
    if refused is not None:
        _LOG.debug("add_asset: refused %r", refused["blocked_by"])
        return refused

    # Everything below this line is observed *before* the asset exists, which is
    # what makes the claims about it precise afterwards: whether there was a rig
    # at the moment of attachment, and which modifiers and groups are new.
    existing_rig = object_service.find_object_of_type_amongst_nearest_relatives(
        basemesh, "Skeleton")
    rig_is_generated_rigify = bool(
        existing_rig is not None
        and object_service.object_is_generated_rigify_rig(existing_rig))
    body_proxy = object_service.find_object_of_type_amongst_nearest_relatives(
        basemesh, "Proxymeshes")

    basemesh_modifiers_before = _modifier_records(basemesh)
    basemesh_groups_before = blender_data.vertex_group_names(basemesh)
    proxy_modifiers_before = _modifier_records(body_proxy)
    names_before = blender_data.object_names()

    names_material, mhmat_path = _mhclo_material(request.resolved_path)
    weights_beside = _weights_files_beside(request.resolved_path)

    asset_object = None
    failure_message = None
    with selection.restored(basemesh):
        try:
            # MPFB's own operators run with the basemesh active, and the import and
            # the fitting both go through bpy.ops, which reads the context.
            object_service.activate_blender_object(basemesh)
            asset_object = services["HumanService"].add_mhclo_asset(
                request.resolved_path,
                basemesh,
                asset_type=request.normalized_asset_type,
                subdiv_levels=params["subdiv_levels"],
                material_type=request.material_type,
                set_up_rigging=params["set_up_rigging"],
                interpolate_weights=params["interpolate_weights"],
                import_subrig=params["import_subrig"],
                import_weights=params["import_weights"])
        except IOError as error:
            # add_mhclo_asset() raises this when the mesh import produced nothing.
            # It has already created no object at that point, but the import may
            # have left one, which is why the stray check below runs either way.
            failure_message = "MPFB could not import the mesh for '{:s}': {:s}".format(
                os.path.basename(request.resolved_path), str(error))

    if failure_message is not None:
        stray = sorted(blender_data.object_names() - names_before)
        return _blocked(
            subject, basemesh, subject_resolved_by, params, request, "import_failed",
            failure_message + (
                (" Objects left behind by the failed import: " + ", ".join(stray)
                 + ". Delete them before trying again.") if stray else ""),
            partial_objects_created=stray,
            resolved_path=request.resolved_path)

    warnings = []

    # The delete group and its masks, observed rather than derived: an MHCLO
    # that defines no delete vertices gets neither, because
    # update_delete_group() returns before creating either one.
    basemesh_masks_added = [
        record for record in _added_modifiers(basemesh_modifiers_before,
                                              _modifier_records(basemesh))
        if record[1] == "MASK"]
    # Computed and deliberately unused, exactly as MPFB's own loader does: the
    # delete group is looked for among the *basemesh's* new masks only. Kept
    # rather than deleted because FR 032's rule is reproduction over
    # improvement, and a quirk tidied away during a migration is
    # indistinguishable from a defect in the comparison the migration rests on.
    _proxy_masks_added = [  # noqa: F841  pylint: disable=unused-variable
        record for record in _added_modifiers(proxy_modifiers_before,
                                              _modifier_records(body_proxy))
        if record[1] == "MASK"]
    groups_added = [name for name in blender_data.vertex_group_names(basemesh)
                    if name not in basemesh_groups_before]

    delete_group_name = None
    for name, _modifier_type, vertex_group in basemesh_masks_added:
        if str(vertex_group).startswith("Delete.") or str(name).startswith("Delete."):
            delete_group_name = vertex_group or name
    if delete_group_name is None:
        for name in groups_added:
            if name.startswith("Delete."):
                delete_group_name = name

    delete_group_applied_to = []
    if delete_group_name is not None:
        if _has_mask_for(basemesh, delete_group_name):
            delete_group_applied_to.append(basemesh.name)
        if body_proxy is not None and _has_mask_for(body_proxy, delete_group_name):
            delete_group_applied_to.append(body_proxy.name)

    subrig = None
    if asset_object is not None:
        # The same lookup unload_mhclo_asset() makes, so what is reported here
        # is what removal would take away.
        subrig = object_service.find_object_of_type_amongst_nearest_relatives(
            asset_object, "Subrig", only_parents=True)

    # Read off the asset rather than assumed from the arguments: the subdivision
    # modifier is skipped for subdiv_levels 0, and an armature modifier appears
    # only when there was a rig to set up against.
    armature_modifier_targets = []
    subdiv_modifier_added = False
    for modifier in getattr(asset_object, "modifiers", None) or []:
        modifier_type = getattr(modifier, "type", None)
        if modifier_type == "SUBSURF":
            subdiv_modifier_added = True
        if modifier_type == "ARMATURE":
            target = getattr(modifier, "object", None)
            if target is not None:
                armature_modifier_targets.append(target.name)

    material_created = bool(
        asset_object is not None and material_service.has_materials(asset_object))
    material_name = None
    if material_created:
        material = material_service.get_material(asset_object, 0)
        material_name = None if material is None else str(material.name)

    proxy_extras = None
    if request.normalized_asset_type == "Proxymeshes" and asset_object is not None:
        proxy_extras = _proxy_extras(
            services, basemesh, asset_object, GeneralObjectProperties, warnings)

    _warnings_for(params, request, names_material, existing_rig, weights_beside,
                  rig_is_generated_rigify, warnings)

    bpy.context.view_layer.update()
    subrigs_broken = placement.subrigs_broken(services, placement.root_of(basemesh))

    _LOG.debug("add_asset: equipped %r as %r", request.resolved_path,
               None if asset_object is None else asset_object.name)

    result = dict(
        found=True,
        ready=True,
        added=True,
        blocked_by=None,
        subject_name=subject.name,
        subject_resolved_by=subject_resolved_by,
        basemesh_name=basemesh.name,
        asset_object_name=None if asset_object is None else asset_object.name,
        requested_object_type=params["object_type"],
        object_type_recorded=mpfb_surface.property_value(
            GeneralObjectProperties, "object_type", asset_object),
        path_resolved_by=request.resolved_by,
        resolved_path=request.resolved_path,
        asset_subdir=request.asset_subdir,
        asset_source=mpfb_surface.property_value(
            GeneralObjectProperties, "asset_source", asset_object),
        material_type_used=request.material_type,
        material_type_defaulted=request.material_type_defaulted,
        material_created=material_created,
        material_name=material_name,
        mhclo_names_material=names_material,
        mhmat_path=mpfb_surface.as_path(mhmat_path),
        rigged_to=(
            existing_rig.name
            if (existing_rig is not None and params["set_up_rigging"]) else None),
        parented_to=(
            None if asset_object is None or asset_object.parent is None
            else asset_object.parent.name),
        armature_modifier_targets=armature_modifier_targets,
        subrig_object_name=None if subrig is None else subrig.name,
        subrigs_broken=subrigs_broken,
        delete_group_name=delete_group_name,
        delete_group_applied_to=delete_group_applied_to,
        vertex_groups_created_on_basemesh=groups_added,
        subdiv_levels=params["subdiv_levels"],
        subdiv_modifier_added=subdiv_modifier_added,
        weights_files_beside_asset=weights_beside,
        proxy_extras=proxy_extras,
        objects_created=sorted(blender_data.object_names() - names_before),
        warnings=warnings,
        message=_message_for(request, basemesh, asset_object, existing_rig,
                             params["set_up_rigging"], delete_group_name, subrig,
                             subrigs_broken, warnings),
    )

    # The verb is "added". See shared/performed.py.
    return with_performed(result, result["added"])
