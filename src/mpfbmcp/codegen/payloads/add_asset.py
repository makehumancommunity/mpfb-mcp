"""
Payload for ``mpfb_add_asset``: equip one MHCLO asset, and report what it cost.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the raising bootstrap (see
``mpfbmcp.codegen.assemble``). A linter will flag three names as undefined
because the assembler binds them ahead of this file:

- ``PARAMS`` - the tool's arguments as plain JSON data: ``name``, ``path``,
  ``fragment``, ``asset_type``, ``material_type``, ``subdiv_levels`` and the
  four pass-through flags.
- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap, and used here to reach names
  MPFB keeps at module level rather than on a service.

...and a further set because they come from the shared fragment
``asset_sections.py``, concatenated ahead of this file: ``AssetService``,
``as_path()``, ``read_sections()``, ``mesh_asset_types()``,
``subdir_for_object_type()`` and ``normalize_asset_type()``. That fragment is
shared with ``list_assets.py`` on purpose: this tool is handed the
``object_type`` and ``fragment`` that payload reported, and the only thing that
turns the first back into the asset subdir needed to resolve the second is
MPFB's section table.

**The work itself is MPFB's.** ``HumanService.add_mhclo_asset()`` imports the
mesh, records ``asset_source`` and ``object_type``, builds the material, fits
the mesh, builds the delete group and masks the body under it, rigs the result
if a rig is there, and adds a subdivision modifier. None of that is
reimplemented here. What is here is everything around it: the vocabulary checks
MPFB does not make, the observations that have to happen *before* the call to be
true, and the reading-back afterwards of things the function reports to nobody.

Three of those are worth naming.

**``asset_type`` is normalised, and the normalisation hides a mismatch.**
``add_mhclo_asset()`` stores ``str(asset_type).lower().capitalize()``, so
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
This payload follows ``_check_add_proxy()``: it is the service layer's own
answer, it is what ``deserialize_from_mhm()`` uses, and it is the one a caller
comparing against a loaded ``.mhm`` would expect. The divergence is reported in
``proxy_extras`` and stated in the tool docstring rather than normalised away.
Reaching ``_proxy_corrective()`` is reaching a private name, which is the one
place this tool bends the rule about module-level names - it is a member of a
service already resolved from ``SERVICES``, so it costs nothing at import time,
and it is read with ``getattr`` and degraded from.

**A delete group is not guaranteed.** ``update_delete_group()`` returns early
when the MHCLO defines no delete vertices, creating neither the vertex group nor
the mask modifier, so the fields describing it are observed from the objects
rather than derived from the filename.
"""

import os

import bpy

ObjectService = _MPFB_SERVICES["ObjectService"]
HumanService = _MPFB_SERVICES["HumanService"]
MaterialService = _MPFB_SERVICES["MaterialService"]

# GeneralObjectProperties is a BlenderConfigSet on ObjectService's module, and
# ALL_EXTRA_GROUPS is the proxy vertex-group table, imported into
# humanservice.py from entities/socketobject. Both are module-level names MPFB
# does not publish, so both are read through the module of a service that
# already resolved, with a fallback - never by importing an MPFB submodule.
OBJECTSERVICE_MODULE = sys.modules[ObjectService.__module__]
HUMANSERVICE_MODULE = sys.modules[HumanService.__module__]

GeneralObjectProperties = getattr(OBJECTSERVICE_MODULE, "GeneralObjectProperties", None)
ALL_EXTRA_GROUPS = getattr(HUMANSERVICE_MODULE, "ALL_EXTRA_GROUPS", None)

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


def property_value(config_set, property_name, blender_object):
    """One custom property, or None when it was never set.

    An unset string property reads back as "" rather than None, and "" means
    "nothing was recorded" - it must not be reported as a fragment.
    """
    if config_set is None or blender_object is None:
        return None
    try:
        value = config_set.get_value(property_name, entity_reference=blender_object)
    except Exception:  # pylint: disable=broad-except
        return None
    if not value:
        return None
    return str(value)


def default_material_type(object_type):
    for candidate, material_type in DEFAULT_MATERIAL_TYPES:
        if candidate == object_type:
            return material_type
    return FALLBACK_MATERIAL_TYPE


def material_types_for(object_type):
    """Which material models are meaningful for this asset type."""
    allowed = []
    for material_type in MATERIAL_TYPES:
        if material_type in EYES_ONLY_MATERIAL_TYPES and object_type != "Eyes":
            continue
        allowed.append(material_type)
    return allowed


def mhclo_material(mhclo_path):
    """Whether the MHCLO names a material, and which file it names.

    Reproduces one line of ``Mhclo.load()``: a line whose first word is
    ``material`` names an MHMAT relative to the MHCLO's own directory. It is
    reproduced rather than imported, because ``entities/clothes/mhclo.py`` is an
    MPFB submodule and importing one of those is what the bootstrap exists to
    avoid.

    It is read for one reason: ``add_mhclo_asset()`` guards its whole material
    block with ``if mhclo.material is not None``, so an MHCLO with no material
    line produces an object with no material and no complaint. Without this the
    warning could not tell that case apart from a material that failed to build.
    Returns (None, None) when the file cannot be read at all, which is reported
    as "not known" rather than as "no material".
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


def weights_files_beside(mhclo_path):
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


def modifier_records(blender_object):
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


def added_modifiers(before, after):
    remaining = list(before)
    appeared = []
    for record in after:
        if record in remaining:
            remaining.remove(record)
        else:
            appeared.append(record)
    return appeared


def vertex_group_names(blender_object):
    if blender_object is None:
        return []
    return [str(group.name) for group in (getattr(blender_object, "vertex_groups", None) or [])]


def object_names():
    return set(blender_object.name for blender_object in bpy.data.objects)


def has_mask_for(blender_object, group_name):
    for name, modifier_type, vertex_group in modifier_records(blender_object):
        if modifier_type == "MASK" and (vertex_group == group_name or name == group_name):
            return True
    return False


def hides_the_base_mesh(blender_object):
    """Whether a *body-proxy* hide modifier is already on this basemesh.

    Not ``has_mask_for(basemesh, "body")``, which is what this used to ask and
    which is always true: every basemesh MPFB creates already carries a
    ``Hide helpers`` MASK modifier on the vertex group ``body``. The two
    modifiers differ only in ``invert_vertex_group`` - ``Hide helpers`` shows
    the body and hides the helper geometry, while the one a body proxy needs
    inverts that and hides the body itself - so the inversion is what has to be
    tested. Asking the looser question meant the modifier was never added and
    the basemesh stayed visible under its own proxy.
    """
    for modifier in (getattr(blender_object, "modifiers", None) or []):
        if str(getattr(modifier, "type", "")) != "MASK":
            continue
        if str(getattr(modifier, "vertex_group", "")) != "body":
            continue
        if bool(getattr(modifier, "invert_vertex_group", False)):
            return True
    return False


def blocked(subject, basemesh, reason, message, **extra):
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
        requested_asset_type=requested_asset_type,
        resolved_by=resolved_by,
        resolved_path=None,
        message=message,
    )
    answer.update(extra)
    return answer


requested_name = PARAMS["name"]
requested_path = PARAMS["path"]
requested_fragment = PARAMS["fragment"]
requested_asset_type = PARAMS["asset_type"]
requested_material_type = PARAMS["material_type"]
subdiv_levels = PARAMS["subdiv_levels"]
set_up_rigging = PARAMS["set_up_rigging"]
interpolate_weights = PARAMS["interpolate_weights"]
import_subrig = PARAMS["import_subrig"]
import_weights = PARAMS["import_weights"]

resolved_by = "path" if requested_path is not None else "fragment"
subject_resolved_by = "active" if requested_name is None else "name"
subject = None
message = None

if requested_name is None:
    # The view layer rather than bpy.context.active_object: this code runs in
    # the add-on's execution context, not from a viewport operator.
    subject = bpy.context.view_layer.objects.active
    if subject is None:
        message = ("No object name was given and no object is active in this Blender session, so "
                   "nothing was equipped. Select a MakeHuman object, or call mpfb_list_objects "
                   "and pass one of its names.")
else:
    subject = bpy.data.objects.get(requested_name)
    if subject is None:
        message = ("No object named '" + str(requested_name) + "' exists in this .blend file, so "
                   "nothing was equipped. Call mpfb_list_objects to see what the current scene "
                   "holds.")

basemesh = None
if subject is not None:
    # The same call MPFB's own asset panels make: the caller may name a garment
    # or the character's rig - the names mpfb_list_objects hands out - and the
    # object actually dressed is reported back rather than the argument echoed.
    basemesh = ObjectService.find_object_of_type_amongst_nearest_relatives(subject, "Basemesh")
    if basemesh is None:
        message = ("'" + subject.name + "' has no MakeHuman basemesh among its nearest relatives, "
                   "so there is nothing to equip. Mesh assets attach to a basemesh; call "
                   "mpfb_get_object_info to see what this object is related to.")

# The argument's own resolution, done before anything is touched: the type
# against MPFB's table, then the file. Both are mistakes a caller can fix
# without looking at the scene, so both are worth reporting even when the scene
# would also have refused.
sections, sections_from_mpfb = read_sections()
known_asset_types = mesh_asset_types(sections)
normalized_asset_type = normalize_asset_type(requested_asset_type)

asset_type_recognized = False
for candidate in known_asset_types:
    if candidate.lower() == str(requested_asset_type).strip().lower():
        normalized_asset_type = candidate
        asset_type_recognized = True

asset_subdir = subdir_for_object_type(sections, normalized_asset_type)

material_type = requested_material_type
material_type_defaulted = material_type is None
if material_type_defaulted:
    material_type = default_material_type(normalized_asset_type)
else:
    material_type = str(material_type).strip().upper()
allowed_material_types = material_types_for(normalized_asset_type)

resolved_path = None
if requested_path is not None:
    resolved_path = as_path(requested_path)
elif asset_subdir is not None:
    # find_asset_absolute_path() matches on *basename*, prefers a candidate
    # whose parent directory also matches, and otherwise returns the first hit -
    # so two packs shipping hat.mhclo resolve to a coin toss. Whatever it
    # chooses is reported, which is the acting-tool counterpart of
    # mpfb_list_assets' pack_ambiguous.
    try:
        resolved_path = as_path(
            AssetService.find_asset_absolute_path(requested_fragment, asset_subdir))
    except Exception:  # pylint: disable=broad-except
        resolved_path = None

if basemesh is None:
    result = blocked(subject, None, "subject_not_found", message,
                     known_asset_types=known_asset_types)
elif not asset_type_recognized:
    result = blocked(
        subject, basemesh, "unknown_asset_type",
        ("'" + str(requested_asset_type) + "' is not an MHCLO asset type MPFB knows, so nothing "
         "was equipped. known_asset_types lists what this Blender accepts; each is the "
         "'object_type' mpfb_list_assets reports for an entry. Skins, poses and ink layers are "
         "in that catalogue but are not mesh assets and cannot be added with this tool."),
        known_asset_types=known_asset_types,
        section_table_from_mpfb=sections_from_mpfb)
elif material_type not in allowed_material_types:
    result = blocked(
        subject, basemesh, "invalid_material_type",
        ("'" + str(requested_material_type) + "' is not a material type for a "
         + normalized_asset_type + " asset, so nothing was equipped. PROCEDURAL_EYES builds "
         "MPFB's eye node tree and is meaningful only for Eyes; the others apply to every type. "
         "Omit material_type to take MPFB's own default for this asset type."),
        asset_type=normalized_asset_type,
        allowed_material_types=allowed_material_types)
elif asset_subdir is None:
    # Only reachable through the fallback table, or through an MPFB whose
    # section table has a mesh type with no subdir. Reported rather than turned
    # into a confusing "asset not found".
    result = blocked(
        subject, basemesh, "no_asset_subdir",
        ("MPFB's asset library table names no asset subdir for the type '"
         + normalized_asset_type + "', so a fragment cannot be resolved to a file. Pass the "
         "absolute 'path' mpfb_list_assets reports instead."),
        asset_type=normalized_asset_type,
        section_table_from_mpfb=sections_from_mpfb)
elif resolved_path is None or not os.path.isfile(resolved_path):
    if requested_path is not None:
        not_found_message = (
            "No file exists at '" + str(requested_path) + "', so nothing was equipped. Pass the "
            "'path' mpfb_list_assets reports for an installed asset, or its 'fragment' to have "
            "this Blender's asset roots searched.")
    else:
        not_found_message = (
            "The fragment '" + str(requested_fragment) + "' resolved to no file under this "
            "Blender's '" + str(asset_subdir) + "' asset roots, so nothing was equipped. The "
            "asset may not be installed here, or the fragment may belong to a different asset "
            "type - fragments are resolved per subdir, and the subdir comes from asset_type.")
    result = blocked(subject, basemesh, "asset_not_found", not_found_message,
                     asset_subdir=asset_subdir,
                     resolved_path=resolved_path)
elif basemesh.mode != "OBJECT" or bpy.context.mode != "OBJECT":
    # Two checks rather than one, and both are needed. add_mhclo_asset() calls
    # bpy.ops.object.shade_smooth() and the fitting code activates objects, and
    # bpy.ops polls on the *context* mode - so an unrelated object left in edit
    # mode fails the operator even though the basemesh itself looks fine.
    result = blocked(
        subject, basemesh, "not_object_mode",
        ("Blender is in " + str(bpy.context.mode) + " mode and the basemesh '" + basemesh.name
         + "' is in " + str(basemesh.mode) + " mode. Importing and fitting an asset runs "
           "operators that require OBJECT mode, so nothing was equipped. Leave edit mode and "
           "call again."))
else:
    # Everything below this line is observed *before* the asset exists, which is
    # what makes the claims about it precise afterwards: whether there was a rig
    # at the moment of attachment, and which modifiers and groups are new.
    existing_rig = ObjectService.find_object_of_type_amongst_nearest_relatives(
        basemesh, "Skeleton")
    rig_is_generated_rigify = bool(
        existing_rig is not None
        and ObjectService.object_is_generated_rigify_rig(existing_rig))
    body_proxy = ObjectService.find_object_of_type_amongst_nearest_relatives(
        basemesh, "Proxymeshes")

    basemesh_modifiers_before = modifier_records(basemesh)
    basemesh_groups_before = vertex_group_names(basemesh)
    proxy_modifiers_before = modifier_records(body_proxy)
    names_before = object_names()

    names_material, mhmat_path = mhclo_material(resolved_path)
    weights_beside = weights_files_beside(resolved_path)

    previous_active = bpy.context.view_layer.objects.active
    basemesh_was_selected = bool(basemesh.select_get())

    asset_object = None
    failure_message = None
    try:
        # MPFB's own operators run with the basemesh active, and the import and
        # the fitting both go through bpy.ops, which reads the context.
        ObjectService.activate_blender_object(basemesh)
        asset_object = HumanService.add_mhclo_asset(
            resolved_path,
            basemesh,
            asset_type=normalized_asset_type,
            subdiv_levels=subdiv_levels,
            material_type=material_type,
            set_up_rigging=set_up_rigging,
            interpolate_weights=interpolate_weights,
            import_subrig=import_subrig,
            import_weights=import_weights)
    except IOError as error:
        # add_mhclo_asset() raises this when the mesh import produced nothing.
        # It has already created no object at that point, but the import may
        # have left one, which is why the stray check below runs either way.
        failure_message = (
            "MPFB could not import the mesh for '" + os.path.basename(resolved_path)
            + "': " + str(error))
    finally:
        if not basemesh_was_selected:
            basemesh.select_set(False)
        # Put back what was borrowed: the user is looking at this scene.
        bpy.context.view_layer.objects.active = previous_active

    if failure_message is not None:
        stray = sorted(object_names() - names_before)
        result = blocked(
            subject, basemesh, "import_failed",
            failure_message + (
                (" Objects left behind by the failed import: " + ", ".join(stray)
                 + ". Delete them before trying again.") if stray else ""),
            partial_objects_created=stray,
            resolved_path=resolved_path)
    else:
        warnings = []

        # The delete group and its masks, observed rather than derived: an MHCLO
        # that defines no delete vertices gets neither, because
        # update_delete_group() returns before creating either one.
        basemesh_masks_added = [
            record for record in added_modifiers(basemesh_modifiers_before,
                                                 modifier_records(basemesh))
            if record[1] == "MASK"]
        proxy_masks_added = [
            record for record in added_modifiers(proxy_modifiers_before,
                                                 modifier_records(body_proxy))
            if record[1] == "MASK"]
        groups_added = [name for name in vertex_group_names(basemesh)
                        if name not in basemesh_groups_before]

        delete_group_name = None
        for name, modifier_type, vertex_group in basemesh_masks_added:
            if str(vertex_group).startswith("Delete.") or str(name).startswith("Delete."):
                delete_group_name = vertex_group or name
        if delete_group_name is None:
            for name in groups_added:
                if name.startswith("Delete."):
                    delete_group_name = name

        delete_group_applied_to = []
        if delete_group_name is not None:
            if has_mask_for(basemesh, delete_group_name):
                delete_group_applied_to.append(basemesh.name)
            if body_proxy is not None and has_mask_for(body_proxy, delete_group_name):
                delete_group_applied_to.append(body_proxy.name)

        subrig = None
        if asset_object is not None:
            # The same lookup unload_mhclo_asset() makes, so what is reported
            # here is what removal would take away.
            subrig = ObjectService.find_object_of_type_amongst_nearest_relatives(
                asset_object, "Subrig", only_parents=True)

        # Read off the asset rather than assumed from the arguments: the
        # subdivision modifier is skipped for subdiv_levels 0, and an armature
        # modifier appears only when there was a rig to set up against.
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
            asset_object is not None and MaterialService.has_materials(asset_object))
        material_name = None
        if material_created:
            material = MaterialService.get_material(asset_object, 0)
            material_name = None if material is None else str(material.name)

        # Proxy extras, reproducing HumanService._check_add_proxy() rather than
        # add_mhclo_asset() alone. See this module's docstring for why this path
        # and not the asset library operator's.
        proxy_extras = None
        if normalized_asset_type == "Proxymeshes" and asset_object is not None:
            hide_modifier_added = False
            if not hides_the_base_mesh(basemesh):
                modifier = basemesh.modifiers.new("Hide base mesh", "MASK")
                modifier.vertex_group = "body"
                modifier.invert_vertex_group = True
                hide_modifier_added = True

            scale_factor_copied = False
            if GeneralObjectProperties is not None:
                try:
                    scale_factor = GeneralObjectProperties.get_value(
                        "scale_factor", entity_reference=basemesh)
                    GeneralObjectProperties.set_value(
                        "scale_factor", scale_factor, entity_reference=asset_object)
                    scale_factor_copied = True
                except Exception:  # pylint: disable=broad-except
                    scale_factor_copied = False

            extra_groups_created = []
            proxy_uuid = property_value(GeneralObjectProperties, "uuid", asset_object)
            if proxy_uuid and ALL_EXTRA_GROUPS and proxy_uuid in ALL_EXTRA_GROUPS:
                for vgroup_name in ALL_EXTRA_GROUPS[proxy_uuid].keys():
                    vgroup = asset_object.vertex_groups.new(name=vgroup_name)
                    vgroup.add(ALL_EXTRA_GROUPS[proxy_uuid][vgroup_name], 1.0, "ADD")
                    extra_groups_created.append(str(vgroup_name))

            corrective = getattr(HumanService, "_proxy_corrective", None)
            corrective_applied = False
            if corrective is not None:
                try:
                    corrective(asset_object)
                    corrective_applied = True
                except Exception:  # pylint: disable=broad-except
                    corrective_applied = False
                    warnings.append(
                        "MPFB's proxy corrective pass raised while fixing the proxy's left/right "
                        "vertex weights. The proxy is attached, but bones may deform the wrong "
                        "side of it.")
            else:
                warnings.append(
                    "HumanService._proxy_corrective() was not found in this MPFB, so the proxy's "
                    "left/right weight correction was skipped. The proxy is attached and fitted; "
                    "this affects only mirrored vertex weights.")

            proxy_extras = dict(
                basemesh_hidden=hide_modifier_added,
                basemesh_hide_modifier_present=hides_the_base_mesh(basemesh),
                scale_factor_copied=scale_factor_copied,
                extra_vertex_groups_created=extra_groups_created,
                corrective_applied=corrective_applied,
                uuid=proxy_uuid,
            )

        if names_material is False:
            warnings.append(
                "The MHCLO names no material, so the asset has whatever material the imported "
                "mesh came with - usually none. MPFB only logs this.")
        elif names_material is True and material_type == "NONE":
            warnings.append(
                "material_type was NONE while the MHCLO names a material, so MPFB deleted the "
                "imported mesh's materials and created nothing. That is the proxy path, and it "
                "is not obvious from the argument name.")
        elif names_material is None:
            warnings.append(
                "The MHCLO could not be read to see whether it names a material, so nothing is "
                "claimed about the asset's material either way.")

        if set_up_rigging and existing_rig is None:
            warnings.append(
                "set_up_rigging was requested but this character has no rig, so the asset is "
                "parented to the basemesh and will not deform. MPFB rigs a garment only if a rig "
                "exists at the moment it is attached and nothing rigs it afterwards - not "
                "mpfb_refit_human either. Add the rig with mpfb_add_rig first, then re-add this "
                "asset.")
        if import_weights and not weights_beside:
            warnings.append(
                "import_weights was requested but no .mhw weights file ships beside this asset, "
                "so its weights are whatever interpolation produced. MPFB checks for the file and "
                "says nothing when it is absent.")
        if rig_is_generated_rigify:
            warnings.append(
                "This character's rig is a *generated* Rigify rig. The asset was rigged against "
                "it, but RigifyHelpers.adjust_children_for_rigify() handles only what is on the "
                "character when generation runs and will not run again - so this asset did not "
                "get that handling. Add assets to the meta rig and generate afterwards.")

        message_parts = [
            "Equipped '" + os.path.basename(resolved_path) + "' on '" + basemesh.name + "' as '"
            + (asset_object.name if asset_object is not None else "?") + "', of type "
            + normalized_asset_type + "."]
        if material_type_defaulted:
            message_parts.append(
                " material_type was not given and defaulted to " + material_type
                + " for this asset type.")
        if existing_rig is not None and set_up_rigging:
            message_parts.append(" It was rigged to '" + existing_rig.name + "'.")
        else:
            message_parts.append(
                " It is parented to the basemesh and follows no armature.")
        if delete_group_name is None:
            message_parts.append(
                " The MHCLO defines no delete group, so no part of the body is masked under it.")
        if warnings:
            message_parts.append(" " + str(len(warnings)) + " warning(s); see 'warnings'.")

        result = dict(
            found=True,
            ready=True,
            added=True,
            blocked_by=None,
            subject_name=subject.name,
            subject_resolved_by=subject_resolved_by,
            basemesh_name=basemesh.name,
            asset_object_name=None if asset_object is None else asset_object.name,
            requested_asset_type=requested_asset_type,
            object_type_recorded=property_value(
                GeneralObjectProperties, "object_type", asset_object),
            resolved_by=resolved_by,
            resolved_path=resolved_path,
            asset_subdir=asset_subdir,
            asset_source=property_value(GeneralObjectProperties, "asset_source", asset_object),
            material_type_used=material_type,
            material_type_defaulted=material_type_defaulted,
            material_created=material_created,
            material_name=material_name,
            mhclo_names_material=names_material,
            mhmat_path=as_path(mhmat_path),
            rigged_to=(
                existing_rig.name if (existing_rig is not None and set_up_rigging) else None),
            parented_to=(
                None if asset_object is None or asset_object.parent is None
                else asset_object.parent.name),
            armature_modifier_targets=armature_modifier_targets,
            subrig_object_name=None if subrig is None else subrig.name,
            delete_group_name=delete_group_name,
            delete_group_applied_to=delete_group_applied_to,
            vertex_groups_created_on_basemesh=groups_added,
            subdiv_levels=subdiv_levels,
            subdiv_modifier_added=subdiv_modifier_added,
            weights_files_beside_asset=weights_beside,
            proxy_extras=proxy_extras,
            objects_created=sorted(object_names() - names_before),
            warnings=warnings,
            message="".join(message_parts),
        )
