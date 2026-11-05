"""
``store_makeskin_material``: keep a MakeSkin material where MPFB's catalogues will find it.

MakeSkin's panel stores a material as an alternate beside an asset or as a body skin,
and no tool could do either. **The two operators are reimplemented from services, as
``set_asset_material`` reimplements its panel, and depart from them in three ways, each
because the operator breaks a rule here:**

- ``write_alternate`` and ``write_makeskin_to_library`` create the directory first and
  overwrite without asking. This settles every refusal first, and refuses an existing
  file unless ``overwrite`` says otherwise
  ([the obligation](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)).
- Both call ``check_that_all_textures_are_saved()``, which re-encodes every source in
  place. [`shared/texture_writing.py`](../shared/texture_writing.py) does not.
- Both read the name off the object's ``MS_name``. Here it is an argument, a name and
  never a path, and ``store_as`` says which of the two panels is meant.

**The MHMAT is still MPFB's**: ``populate_from_object()`` reads the object and
``export_to_disk()`` writes the file. What is put into its ``_settings`` in between is
the textures' staged paths, this call's name, license and author, and the numbers
:func:`shared.makeskin.file_settings` read, without which the displacement strength and
the diffuse mix factor never reach a file.

**MPFB's loader does not read most of what this writes, and the answer says so.**
``apply_node_tree()`` fills the template from the textures and ``diffuseColor`` alone.
``roughness``, ``metallic``, ``ior`` and every intensity are parsed and dropped, and
come back as the template's constants, through MPFB's panel, ``set_asset_material`` and
``set_skin`` alike. Those two follow the panel on purpose (see ``set_asset_material``'s
docstring), so ``values_not_restored`` names each value of this material that an apply
will lose, with what it will be instead. The file still holds it, and the day MPFB reads
it the list empties, since it is measured against the template rather than kept here.

**Refuse to write where the result cannot be found.** MPFB finds a material by basename
and then by the parent directory's name, in root order, so another
``<name>/<name>.mhmat`` in an earlier root *or in this one* could answer for it:
``name_shadowed``. Two assets' alternates of one name in one root are the likely case.

**An alternate lands in a directory a pack may own.** Nothing stops that, MPFB's panel
included, and a reinstall could remove it. ``asset_packs`` names the packs claiming the
asset, with a warning. A refusal would make alternates impossible for every asset a pack
shipped, which is most of them, so a warning is the decision. The new file is not
attributed to the pack: FR 046's rule looks at a file's own directory, and an alternate
has a directory of its own.

**``dry_run`` does everything but write**, so a smoke run leaves nothing behind.
"""

__all__ = (
    "PARAMS",
    "STORE_AS",
    "SUMMARY",
    "store_makeskin_material",
)

import os

import bpy

from ..log import get_logger
from ..shared import asset_sections
from ..shared import makeskin
from ..shared import mpfb_surface
from ..shared import pack_attribution
from ..shared import subject_resolution
from ..shared import texture_writing
from ..shared.artifact_names import file_facts
from ..shared.artifact_names import material_name_rejection
from ..shared.performed import with_performed
from ..validation import Param
from ..validation import TYPE_BOOLEAN
from ..validation import TYPE_STRING

_LOG = get_logger("commands.storemakeskinmaterial")

STORE_AS = ("alternate", "skin")

PARAMS = (
    Param("store_as", TYPE_STRING, required=True, choices=STORE_AS,
          description="'alternate' beside the mesh's asset, or 'skin' among MPFB's user skins."),
    Param("material_name", TYPE_STRING, required=True,
          description="The stored name, never a path: lower case letters, digits and '_'."),
    Param("name", TYPE_STRING, default=None, nullable=True,
          description="The mesh. Omit or pass null to use whatever object is currently active."),
    Param("overwrite", TYPE_BOOLEAN, default=False,
          description="Replace an existing material of this name. False by default: there is no "
                      "undo for a file across this socket."),
    Param("dry_run", TYPE_BOOLEAN, default=False,
          description="Settle everything and report it, and write nothing."),
    Param("license", TYPE_STRING, default=None, nullable=True,
          description="The file's license. Omit to take the object's."),
    Param("author", TYPE_STRING, default=None, nullable=True,
          description="The file's author. Omit to take the object's."),
)

SUMMARY = "Store a MakeSkin material as an alternate of its asset, or as a body skin."

_SKIN_SUBDIR = "skins"


class _Request:
    """One call's resolved state, so the refusals can be read in one place."""

    __slots__ = ("subject", "resolved_by", "directory", "file_path", "fragment", "asset_subdir",
                 "asset_path", "object_type", "plans")

    def __init__(self):
        self.subject = None
        self.resolved_by = None
        self.directory = None
        self.file_path = None
        self.fragment = None
        self.asset_subdir = None
        self.asset_path = None
        self.object_type = None
        self.plans = []


def _answer(words, params, request, **fields):
    answer = dict(
        found=request.subject is not None, ready=False, saved=False, blocked_by=None,
        dry_run=params["dry_run"], store_as=params["store_as"],
        material_name=params["material_name"],
        subject_name=None if request.subject is None else request.subject.name,
        subject_resolved_by=request.resolved_by,
        object_type=request.object_type,
        path=request.file_path, fragment=request.fragment,
        overwrote=False, file_before=None,
        textures_written=[], texture_errors=[],
        license=None, license_resolved_by=None, author=None, author_resolved_by=None,
        values_not_restored=dict(), asset_packs=[], attribution=None,
        apply_with=None, cache_invalidated=False, warnings=[],
        known_slots=list(words.slots), message=None)
    answer.update(fields)
    return answer


def _resolve_alternate(services, request):
    """``(reason, sentence, extra)`` when this mesh cannot have an alternate stored."""
    object_service = services["ObjectService"]
    subject = request.subject
    if object_service.object_is_basemesh_or_body_proxy(subject):
        return ("type_not_supported",
                "'{:s}' is a body or a body proxy, which takes a skin rather than an alternate. "
                "Pass store_as='skin'.".format(subject.name), dict())
    if not request.object_type or not object_service.object_is_any_makehuman_mesh(subject):
        return ("not_an_mpfb_object",
                "'{:s}' is not a MakeHuman mesh asset, so it has no asset for an alternate to sit "
                "beside. mpfb_get_object_info says what it is.".format(subject.name), dict())
    source = mpfb_surface.property_value(
        mpfb_surface.general_object_properties(services), "asset_source", subject)
    if not source:
        return ("asset_source_missing",
                "'{:s}' records no asset_source, so nothing says where its asset is, and an "
                "alternate sits beside its asset.".format(subject.name), dict())
    request.asset_subdir = str(request.object_type).lower()
    try:
        request.asset_path = mpfb_surface.as_path(services["AssetService"].find_asset_absolute_path(
            source, request.asset_subdir))
    except Exception:  # pylint: disable=broad-except
        request.asset_path = None
    if not request.asset_path:
        return ("asset_not_in_library",
                "'{:s}' came from '{:s}', which is under none of this Blender's '{:s}' asset roots, "
                "and an alternate anywhere else is somewhere MPFB would not look.".format(
                    subject.name, source, request.asset_subdir), dict(asset_source=source))
    request.directory = os.path.join(os.path.dirname(request.asset_path), "{name}")
    return None


def _resolve_skin(services, request):
    subject = request.subject
    if not services["ObjectService"].object_is_basemesh_or_body_proxy(subject):
        return ("type_not_supported",
                "'{:s}' is neither a body nor a body proxy, and only those take a skin. Pass "
                "store_as='alternate' for a mesh asset.".format(subject.name), dict())
    request.asset_subdir = _SKIN_SUBDIR
    request.directory = os.path.join(
        str(services["LocationService"].get_user_data(_SKIN_SUBDIR)), "{name}")
    return None


def _shadowing_file(services, request, name):
    """Another ``<name>/<name>.mhmat`` that could answer for this one, or ``None``.

    Walked as ``find_asset_absolute_path()`` walks: by basename, in root order, taking
    the first whose parent directory matches too. One in an earlier root wins for
    certain, and one in the same root wins or not by the order of ``os.walk``.
    """
    roots = [os.path.abspath(str(root))
             for root in services["AssetService"].get_asset_roots(request.asset_subdir)]
    target = os.path.abspath(request.file_path)
    filename = name + ".mhmat"
    own_root = next((index for index, root in enumerate(roots)
                     if target.startswith(root + os.sep)), len(roots))
    for index, root in enumerate(roots[:own_root + 1]):
        for dirpath, _dirs, files in os.walk(root):
            if filename not in files or os.path.basename(dirpath) != name:
                continue
            found = os.path.abspath(os.path.join(dirpath, filename))
            if found != target:
                return dict(path=found, same_root=index == own_root)
    return None


def _resolved_metadata(words, subject, argument, key):
    """``(value, resolved_by)``: the argument, else the object's, else MPFB's default."""
    if argument is not None:
        return (argument, "argument")
    value = words.properties.get_value(key, entity_reference=subject)
    if subject.is_property_set(words.metadata[key]) and value:
        return (str(value), "object")
    return (None if not value else str(value), "mpfb_default")


def _values_not_restored(services, words, tree):
    """Each value here that MPFB's template will not give back when the file is applied.

    Measured against the template rather than kept in a list: a scratch material built
    with this one's slots, the way ``apply_node_tree()`` will, compared socket by socket.
    Only ``diffuseColor`` is ever filled in, so it is the one key skipped, and a value not
    in effect here loses nothing by going back to the template's.
    """
    MakeSkinMaterial = mpfb_surface.module_level(  # pylint: disable=invalid-name
        services, "HumanService", "MakeSkinMaterial", fallback=None)
    template_values = dict()
    for slot in words.slots:
        has_slot = makeskin.texture_node(tree, slot) is not None
        template_values["has_" + slot] = "true" if has_slot else "false"
        template_values[slot + "_filename"] = '""'
    scratch = services["MaterialService"].create_empty_material("mpfb_bridge_scratch", None)
    try:
        MakeSkinMaterial().apply_node_tree(scratch, template_values)
        ours = makeskin.file_settings(words, tree)
        built = makeskin.file_settings(words, scratch.node_tree)
    finally:
        bpy.data.materials.remove(scratch)
    in_effect, _absent = makeskin.read_values(words, tree)
    lost = dict()
    for key, value in ours.items():
        if key == "diffuseColor" or value is None or built.get(key) is None:
            continue
        if not in_effect[key]["in_effect"]:
            continue
        if abs(float(value) - float(built[key])) > 1e-4:
            lost[key] = dict(stored=round(float(value), 6),
                             after_apply=round(float(built[key]), 6))
    return lost


def _settings_for_file(words, settings, staged_directory, plans, name, license_value, author):
    """Everything put into ``_settings`` between MPFB's read and MPFB's write."""
    for slot in words.slots:
        settings[slot + "Texture"] = None
    for planned in plans:
        # export_to_disk() computes the same path and so copies nothing.
        settings[planned.slot + "Texture"] = os.path.join(staged_directory, planned.filename)
    settings["name"] = name
    settings["license"] = license_value
    settings["author"] = author
    for key in words.metadata:
        if settings.get(key) == "":
            # A line holding a key and no value parses back as nothing at all.
            settings[key] = None


def _reload_stale_images(plans):
    """MPFB reuses a loaded image by basename, so a replaced file must reach the loaded one."""
    warnings = []
    for planned in plans:
        image = bpy.data.images.get(planned.filename)
        if image is None or image == planned.image:
            continue
        if texture_writing.image_file_path(image) == planned.destination and not image.is_dirty:
            image.reload()
        else:
            warnings.append(
                "An image named '{:s}' is already loaded from elsewhere, and MPFB reuses a loaded "
                "image by name, so applying this material in this session shows that image's "
                "pixels.".format(planned.filename))
    return warnings


def _write(services, words, request, params, tree, license_value, author):
    """Stage everything beside the destination, then move it in. Returns the rows written."""
    MakeSkinMaterial = mpfb_surface.module_level(  # pylint: disable=invalid-name
        services, "HumanService", "MakeSkinMaterial", fallback=None)
    name = params["material_name"]
    parent = os.path.dirname(request.directory)
    made = texture_writing.made_directories(parent)
    try:
        with texture_writing.staging(parent) as staged_directory:
            staged = [texture_writing.write_staged(planned, staged_directory)
                      for planned in request.plans]
            mhmat = MakeSkinMaterial()
            mhmat.populate_from_object(request.subject)
            # pylint: disable=protected-access
            mhmat._settings.update(makeskin.file_settings(words, tree))
            _settings_for_file(words, mhmat._settings, staged_directory, request.plans, name,
                               license_value, author)
            staged_mhmat = os.path.join(staged_directory, name + ".mhmat")
            mhmat.export_to_disk(staged_mhmat)
            made.extend(texture_writing.made_directories(request.directory))
            for staged_file in staged:
                if staged_file is not None:
                    texture_writing.move_into_place(staged_file, request.directory)
            texture_writing.move_into_place(staged_mhmat, request.directory)
    except Exception:
        texture_writing.remove_directories(made)
        raise


def _texture_rows(plans, written):
    rows = []
    for planned in plans:
        facts = file_facts(planned.destination) if written else file_facts(planned.source_path)
        rows.append(dict(
            slot=planned.slot, source_path=planned.source_path, source_image=planned.image_name,
            how=planned.how, path=planned.destination,
            size_bytes=facts["size_bytes"]))
    return rows


def _invalidate(services, store_as):
    """That entry's catalogue, so that what was stored is listed at once."""
    asset_service = services["AssetService"]
    if store_as == "alternate":
        asset_service.invalidate_alternative_materials_cache()
    else:
        sections, _from_mpfb = asset_sections.read_sections(services)
        for asset_subdir, asset_type, _object_type in sections:
            if asset_subdir == _SKIN_SUBDIR:
                asset_service.update_asset_list(asset_subdir, asset_type)
    return True


def _apply_with(params, request):
    if params["store_as"] == "alternate":
        return dict(mpfb_set_asset_material=dict(name=request.subject.name,
                                                 path=request.file_path))
    return dict(mpfb_set_skin=dict(name=request.subject.name, skin_type="MAKESKIN",
                                   path=request.file_path))


def _asset_packs(services, request):
    """Who claims the asset an alternate sits beside, and whom the new file is attributed to."""
    if request.asset_path is None:
        return ([], None)
    roots = services["AssetService"].get_asset_roots(request.asset_subdir)
    index = pack_attribution.read_index(services)
    packs = pack_attribution.attribute(index, request.asset_path, roots)["packs"]
    attribution = pack_attribution.attribute(index, request.file_path, roots)
    return (packs, {key: attribution[key] for key in pack_attribution.FIELDS})


def _message_for(params, request, overwrote, lost, warnings):
    parts = []
    if params["dry_run"]:
        parts.append("Would store '{:s}' as '{:s}'; nothing was written.".format(
            params["material_name"], request.file_path))
    else:
        parts.append("Stored '{:s}' as '{:s}'.".format(params["material_name"],
                                                        request.file_path))
    if overwrote:
        parts.append(" It replaced an existing file; file_before says what that was.")
    if lost:
        parts.append(
            " MPFB's loader builds its template without reading {:s}, so applying this file "
            "leaves each as values_not_restored says. The file holds them; send them to "
            "mpfb_set_makeskin_material after applying to have them on a mesh.".format(
                ", ".join(sorted(lost))))
    if warnings:
        parts.append(" {:d} warning(s); see 'warnings'.".format(len(warnings)))
    return "".join(parts)


def store_makeskin_material(params, resolution):  # pylint: disable=too-many-return-statements,too-many-locals,too-many-branches
    """Settle every refusal, then stage, then move, then invalidate."""
    services = resolution.services
    words = makeskin.vocabulary(services, resolution.module.__name__)
    request = _Request()

    def blocked(reason, message, **extra):
        return with_performed(_answer(words, params, request, blocked_by=reason, message=message,
                                      **extra), False)

    request.subject, request.resolved_by, message = subject_resolution.resolve_subject(
        params["name"], not_done="nothing was stored", select="a mesh")
    if request.subject is None:
        return blocked("subject_not_found", message)
    subject = request.subject
    if subject.type != "MESH":
        return blocked("not_a_mesh", "'{:s}' is a {:s}, not a mesh, so it has no material to "
                                     "store.".format(subject.name, str(subject.type)))

    name = params["material_name"]
    rejection = material_name_rejection(name)
    if rejection is not None:
        # Defence in depth, as in save_expression: mpfb-mcp refuses this before sending.
        return blocked("invalid_name", rejection + " Nothing was stored.")

    material = services["MaterialService"].get_material(subject)
    if material is None:
        return blocked("no_material", "'{:s}' has no material in its first slot, so there is "
                                      "nothing to store.".format(subject.name))
    is_makeskin, identified_as, _recognized_by = makeskin.recognized(services, words, material)
    if not is_makeskin:
        return blocked(
            "not_makeskin",
            "'{:s}' has the material '{:s}', which MPFB identifies as {:s}. Only a MakeSkin "
            "material can be written as an MHMAT.".format(
                subject.name, str(material.name), identified_as),
            material_identified_as=identified_as)

    request.object_type = services["ObjectService"].get_object_type(subject) or None
    refusal = (_resolve_alternate(services, request) if params["store_as"] == "alternate"
               else _resolve_skin(services, request))
    if refusal is not None:
        return blocked(refusal[0], refusal[1], **refusal[2])

    request.directory = request.directory.format(name=name)
    request.file_path = os.path.normpath(os.path.join(request.directory, name + ".mhmat"))
    request.fragment = "{0:s}/{0:s}.mhmat".format(name)

    license_value, license_resolved_by = _resolved_metadata(
        words, subject, params["license"], "license")
    author, author_resolved_by = _resolved_metadata(words, subject, params["author"], "author")
    resolved = dict(license=license_value, license_resolved_by=license_resolved_by,
                    author=author, author_resolved_by=author_resolved_by)
    for key, argument in (("license", params["license"]), ("author", params["author"])):
        if argument is not None:
            issue = makeskin.metadata_issue(words, key, argument)
            if issue is not None:
                return blocked("invalid_" + key, issue[1] + " Nothing was stored.",
                               known_values=issue[2], **resolved)

    tree = material.node_tree
    request.plans = [texture_writing.plan(slot, makeskin.texture_node(tree, slot).image,
                                          request.directory, name)
                     for slot in words.slots if makeskin.texture_node(tree, slot) is not None]
    texture_errors = [dict(slot=planned.slot, image_name=planned.image_name,
                           message=planned.refusal)
                      for planned in request.plans if planned.refusal is not None]
    if texture_errors:
        return blocked(
            "texture_unavailable",
            "{:d} of this material's textures cannot be stored, so nothing was. See "
            "'texture_errors'.".format(len(texture_errors)),
            texture_errors=texture_errors, **resolved)

    previous = file_facts(request.file_path)
    file_before = previous if previous["exists"] else None
    existing_textures = [planned.destination for planned in request.plans
                         if planned.how != texture_writing.ALREADY_IN_PLACE
                         and os.path.exists(planned.destination)]
    if (file_before is not None or existing_textures) and not params["overwrite"]:
        return blocked(
            "material_exists",
            "'{:s}' already exists{:s}, and overwrite is false, so nothing was written. Pass "
            "overwrite=true to replace it, or choose another name: there is no undo for a file "
            "across this socket.".format(
                request.file_path if file_before is not None else existing_textures[0],
                "" if file_before is None else ", written {!s}".format(file_before["modified"])),
            file_before=file_before, existing_textures=existing_textures, **resolved)

    shadowing = _shadowing_file(services, request, name)
    if shadowing is not None:
        return blocked(
            "name_shadowed",
            "Another '{0:s}/{0:s}.mhmat' exists at '{1:s}', and MPFB finds a material by those two "
            "names and takes the first, so one stored here might never be the one it finds. "
            "Nothing was written. Choose another name.".format(name, shadowing["path"]),
            shadowed_by=shadowing, **resolved)

    lost = _values_not_restored(services, words, tree)
    asset_packs, attribution = _asset_packs(services, request)
    warnings = []
    if asset_packs:
        warnings.append(
            "This asset's directory belongs to {:s}. A material stored there is not part of the "
            "pack, and reinstalling or removing the pack may take it away.".format(
                ", ".join(asset_packs)))
    if license_resolved_by == "mpfb_default":
        warnings.append("license is MPFB's default, {!s}, rather than anything somebody "
                        "chose.".format(license_value))

    cache_invalidated = False
    if not params["dry_run"]:
        try:
            _write(services, words, request, params, tree, license_value, author)
        except Exception as error:  # pylint: disable=broad-except
            now = file_facts(request.file_path)
            return blocked(
                "write_failed",
                "Writing '{:s}' failed, and no part of it was moved into place: {:s}".format(
                    request.file_path, str(error)),
                file_before=file_before, file_after=now if now["exists"] else None, **resolved)
        warnings.extend(_reload_stale_images(request.plans))
        cache_invalidated = _invalidate(services, params["store_as"])

    _LOG.debug("store_makeskin_material: %r dry_run=%r", request.file_path, params["dry_run"])
    written = not params["dry_run"]
    answer = _answer(
        words, params, request,
        ready=True,
        saved=written,
        overwrote=written and file_before is not None,
        file_before=file_before,
        size_bytes=file_facts(request.file_path)["size_bytes"] if written else None,
        textures_written=_texture_rows(request.plans, written),
        values_not_restored=lost,
        asset_packs=asset_packs,
        attribution=attribution,
        apply_with=_apply_with(params, request),
        cache_invalidated=cache_invalidated,
        warnings=warnings,
        message=_message_for(params, request, written and file_before is not None, lost, warnings),
        **resolved)
    return with_performed(answer, written)
