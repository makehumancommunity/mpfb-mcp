# SPDX-License-Identifier: GPL-3.0-or-later

"""
Stand-ins for Blender and MPFB, for executing generated payloads locally.

The payloads for ``mpfb_list_objects``, ``mpfb_get_object_info``,
``mpfb_list_rigs``, ``mpfb_list_assets``, ``mpfb_list_targets``,
``mpfb_get_macro_details``, ``mpfb_set_macro_details`` and ``mpfb_refit_human``
carry real branching - type filtering, relationship walking, three asset_info
shapes, a weights fallback walk, filtering and paging over an asset library, a
two-source target scan, preconditions, a write-then-recalculate sequence - so
they are worth running,
and they can only be run against stubs: MPFB is reachable only from inside
Blender (see specifications/architecture.md). This module is shared by those
tools' test modules because they need the same stub scene and services; it holds
no tests of its own.

The stubs reimplement the MPFB behavior the payloads actually depend on rather
than returning convenient values, since several of those behaviors are the
reason the payload is written the way it is:

- ``get_object_type()`` answers ``""``, never None, for an untyped object.
- ``object_is()`` matches by lowercased substring, not equality.
- ``object_is_any_makehuman_object()`` returns a *string*, not a bool.
- ``find_related_objects()`` yields the object it was asked about, first.
- ``get_list_of_children()`` walks the whole file, not the current scene.
- ``get_mpfb_root()`` hands back a ``pathlib.Path`` when given no sub-path, and
  a ``str`` when given one.
- ``get_second_root()`` really can be None.
- ``get_rig_weight_fallbacks()`` carries MPFB's real table, so the two rigs that
  own no weights file of their own resolve to another rig's rather than to none.
- ``get_asset_list()`` builds its items the way ``update_asset_list()`` does and
  keys them by *label*, so two assets whose filenames differ only in case or
  underscores really do collapse into one entry, and each item's ``thumb`` holds
  something JSON cannot encode.
- ``get_asset_roots()`` reports fewer roots than ``get_available_data_roots()``,
  which is the difference the asset tool exists to report.
- ``find_asset_files_matching_pattern()`` really walks the disk and hands back
  ``pathlib.Path`` objects, which is what the target payload's ``str()``
  coercion exists for.
- ``filename_to_shapekey_name()`` strips the extensions *and* encodes a name
  over 60 characters, so ``shapekey_name`` provably differs from the filename
  for a long target. Reproducing only the stripping would make the test pass
  while hiding the bug it exists to catch.
- ``HumanObjectProperties.set_value()`` stores what it is given **unclamped**,
  matching a real property whose definition carries a default but no min/max -
  which is the reason ``mpfb_set_macro_details`` validates its range locally,
  and a stub that clamped would hide it.
- ``get_macro_info_dict_from_basemesh()`` reads back through that same property
  store, so the write-then-read round trip is genuinely under test.
- ``reapply_macro_details()`` follows MPFB's own sequence and really adds and
  removes stub shape keys, including the sub-0.0001 prune, so the reported
  before/after lists are asserted against something that changed.
- ``create_shape_key()`` opens with MPFB's bare ``assert`` on OBJECT mode, which
  is what the mutating payloads check the mode themselves to avoid.
- ``refit()`` raises when handed an object with no basemesh, and otherwise says
  nothing at all about the generated-Rigify-without-metarig case - the failure
  the real one reports only through an ``operator``.
- ``find_rigify_metarig_by_rig()`` is guarded as MPFB's is and follows the
  metarig's own back-pointer rather than a shared id.

The one place these deliberately depart from MPFB is
``calculate_target_stack_from_macro_info_dict()``, which uses a stand-in table
rather than MPFB's corner cases: no payload depends on which targets come out,
only on the shape of the answer, and copying a data file in would prove nothing.

What they cannot do is tell us anything about the values real MPFB returns;
that remains a manual check against a running Blender.
"""

__all__ = (
    "ASSET_LIBRARY_SECTIONS",
    "MACRO_PROPERTY_DEFAULTS",
    "GeneratedCodeTestCase",
    "StubAssetService",
    "StubHumanService",
    "StubLocationService",
    "StubMaterial",
    "StubObject",
    "StubObjectService",
    "StubSystemService",
    "StubTargetService",
)

import json
import os
import pathlib
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

from mpfbmcp import codegen

# Neither may end in "mpfb", or the bootstrap's candidate scan would pick it up
# as an MPFB install of its own.
_OBJECTSERVICE_MODULE = "mpfb_stub_services_objectservice"
_HUMANSERVICE_MODULE = "mpfb_stub_services_humanservice"
_ASSETSERVICE_MODULE = "mpfb_stub_services_assetservice"
_PACKAGE = "bl_ext.test_repo.mpfb"

_ALL_TYPES = ("Skeleton", "Subrig", "Basemesh", "Proxymeshes", "Clothes",
              "Eyes", "Eyelashes", "Eyebrows", "Tongue", "Teeth", "Hair")
_MESH_ASSET_TYPES = ("Proxymeshes", "Clothes", "Eyes", "Eyelashes", "Eyebrows",
                     "Tongue", "Teeth", "Hair")
_SKELETON_TYPES = ("Skeleton", "Subrig")

# The eleven macro properties and the defaults their JSON definitions declare.
# Note what those definitions do *not* declare: a min or a max. The values are
# stored unclamped, here as in MPFB.
MACRO_PROPERTY_DEFAULTS = {
    "gender": 0.5,
    "age": 0.5,
    "muscle": 0.5,
    "weight": 0.5,
    "proportions": 0.5,
    "height": 0.5,
    "cupsize": 0.5,
    "firmness": 0.5,
    "asian": 0.33,
    "caucasian": 0.33,
    "african": 0.33,
}

# MPFB's ASSET_LIBRARY_SECTIONS, trimmed to the rows the tests need but with its
# real shape - a list of dicts carrying more keys than any payload reads, and
# including the three rows whose object_type is not a type an object in a scene
# can carry: skins are "Material", poses are "Pose", ink layers are "Other".
ASSET_LIBRARY_SECTIONS = [
    {
        "bl_label": "Topologies library",
        "asset_subdir": "proxymeshes",
        "asset_type": "proxy",
        "object_type": "Proxymeshes",
        "eye_overrides": False,
        "skin_overrides": True,
    },
    {
        "bl_label": "Skins library",
        "asset_subdir": "skins",
        "asset_type": "mhmat",
        "object_type": "Material",
        "eye_overrides": False,
        "skin_overrides": True,
    },
    {
        "bl_label": "Hair library",
        "asset_subdir": "hair",
        "asset_type": "mhclo",
        "object_type": "Hair",
        "eye_overrides": False,
        "skin_overrides": False,
    },
    {
        "bl_label": "Clothes library",
        "asset_subdir": "clothes",
        "asset_type": "mhclo",
        "object_type": "Clothes",
        "eye_overrides": False,
        "skin_overrides": False,
    },
    {
        "bl_label": "Poses library",
        "asset_subdir": "poses",
        "asset_type": "bvh",
        "object_type": "Pose",
        "eye_overrides": False,
        "skin_overrides": False,
    },
]


class StubMaterial:
    """A material slot's content, plus what identify_material() makes of it."""

    def __init__(self, identified="makeskin"):
        self.identified = identified


class StubShapeKey:
    """One entry in key_blocks: a name and the weight the payloads read.

    The weight is **clamped to 0.0-1.0 on assignment**, as Blender clamps a real
    shape key: MPFB never touches slider_min/slider_max, so the default range
    applies and assigning -0.4 stores 0.0. That clamp is the whole reason the
    modifier level exists - a negative modifier value has no shape key
    representation at all and must be expressed as the opposing target at a
    positive weight - so a payload that tried to store one directly has to fail
    here rather than in Blender.
    """

    def __init__(self, name, value=0.0):
        self.name = name
        self.value = value

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = min(1.0, max(0.0, float(new_value)))


class _StubKeyBlocks:
    """key_blocks: iterable, and indexable by *name* as well as by position.

    reapply_macro_details() zeroes a target with `key_blocks[encoded_name]`, so
    a plain list here would fail on exactly the line that matters.
    """

    def __init__(self, blocks=()):
        self._blocks = list(blocks)

    def __iter__(self):
        return iter(self._blocks)

    def __len__(self):
        return len(self._blocks)

    def __contains__(self, key):
        return any(block.name == key for block in self._blocks)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._blocks[key]
        for block in self._blocks:
            if block.name == key:
                return block
        raise KeyError(key)

    def append(self, block):
        self._blocks.append(block)

    def remove(self, block):
        self._blocks.remove(block)


class StubShapeKeys:
    def __init__(self, blocks=()):
        self.key_blocks = _StubKeyBlocks(blocks)


class StubMesh:
    """A mesh datablock. `shape_keys` is None until the first one is added."""

    def __init__(self, shapekeys=None):
        self.shape_keys = None
        if shapekeys:
            self.shape_keys = StubShapeKeys(
                StubShapeKey(name, value) for name, value in shapekeys)


class StubObject:
    """One Blender object: its name, type, parent and MPFB custom properties."""

    def __init__(self, name, blender_type="MESH", parent=None, object_type="",
                 asset_source="", alternative_material="", material_source="",
                 material=None, rig_id=None, metarig=False, rig_type="unknown",
                 macro_details=None, is_human_project=False, shapekeys=None,
                 mode="OBJECT", selected=False, rigify_target_rig=None):
        self.name = name
        self.type = blender_type
        self.parent = parent
        self.material = material
        # Rigify's link from a metarig to the rig it generated, which is how
        # MPFB finds one from the other - not a shared id.
        self.rigify_target_rig = rigify_target_rig
        # Settable, because the edit-mode precondition is a branch the mutating
        # payloads exist to get right rather than a state to assume away.
        self.mode = mode
        self.data = StubMesh(shapekeys)
        self._selected = selected
        # Rigify's own markers, which MPFB reads off the armature data rather
        # than through any property of its own.
        self.rig_id = rig_id
        self.metarig = metarig
        # What identify_rig() would deduce from this armature's bones.
        self.rig_type = rig_type
        human_properties = {
            "material_source": material_source,
            "is_human_project": is_human_project,
        }
        # MPFB registers the macro properties on bpy.types.Object, so *every*
        # object reads them back - at their defaults when nothing set them. A
        # stub where only "macro objects" carry them would make the imported-
        # mesh case look like a missing-property case, which it is not.
        human_properties.update(MACRO_PROPERTY_DEFAULTS)
        human_properties.update(macro_details or dict())
        self.properties = {
            "GEN": {
                "object_type": object_type,
                "asset_source": asset_source,
                "alternative_material": alternative_material,
            },
            "HUM": human_properties,
        }

    def select_get(self):
        return self._selected

    def select_set(self, state):
        self._selected = bool(state)

    def shape_key_add(self, name="Key", from_mix=False):
        if self.data.shape_keys is None:
            self.data.shape_keys = StubShapeKeys()
        block = StubShapeKey(name)
        self.data.shape_keys.key_blocks.append(block)
        return block

    def shape_key_remove(self, block):
        self.data.shape_keys.key_blocks.remove(block)
        if not len(self.data.shape_keys.key_blocks):
            # Blender drops the datablock with the last key, which is what makes
            # `if basemesh.data.shape_keys` a real branch rather than always-true.
            self.data.shape_keys = None


class _StubConfigSet:
    """A BlenderConfigSet: unset string properties read back as "", not None."""

    def __init__(self, bucket):
        self._bucket = bucket

    def get_value(self, name, default_value=None, entity_reference=None):
        if entity_reference is None:
            # check_and_transform_entity_reference() raises here, despite the
            # =None default in the real signature.
            raise ValueError("Must provide a valid entity reference")
        return entity_reference.properties[self._bucket].get(name, default_value or "")

    def set_value(self, name, value, entity_reference=None):
        if entity_reference is None:
            raise ValueError("Must provide a valid entity reference")
        # Deliberately unclamped, matching the real property: the definitions
        # under entities/objectproperties/humanproperties carry a default but no
        # min/max. A stub that clamped here would hide the reason
        # mpfb_set_macro_details validates its range locally.
        entity_reference.properties[self._bucket][name] = value


GeneralObjectProperties = _StubConfigSet("GEN")
HumanObjectProperties = _StubConfigSet("HUM")


class StubObjectService:
    """The subset of ObjectService the payloads use, with MPFB's semantics."""

    # Stands in for bpy.data.objects, which get_list_of_children() walks.
    all_objects = ()
    # The stub bpy module of the run in progress, set by the test harness, so
    # that activate_blender_object() can change the active object the way the
    # real one does rather than only pretending to.
    bpy = None
    # Every object activate_blender_object() was called on, by name.
    activations = []

    @staticmethod
    def get_object_type(blender_object):
        if not blender_object:
            return ""
        value = GeneralObjectProperties.get_value(
            "object_type", entity_reference=blender_object)
        return str(value or "").strip()

    @staticmethod
    def object_is(blender_object, mpfb_type_name):
        if not mpfb_type_name:
            return False
        actual = StubObjectService.get_object_type(blender_object)
        if not actual:
            return False
        actual = actual.lower()
        names = [mpfb_type_name] if isinstance(mpfb_type_name, str) else mpfb_type_name
        for item in names:
            stripped = str(item).lower().strip()
            if stripped and stripped in actual:
                return True
        return False

    @staticmethod
    def object_is_any_makehuman_object(blender_object):
        # Deliberately not a bool: the real one returns the type string.
        return blender_object and StubObjectService.get_object_type(blender_object)

    @staticmethod
    def get_list_of_children(parent_object):
        return [candidate for candidate in StubObjectService.all_objects
                if candidate.parent is parent_object]

    @staticmethod
    def find_all_objects_of_type_amongst_nearest_relatives(
            blender_object, mpfb_type_name="Basemesh", *,
            only_parents=False, strict_parent=False, only_children=False):
        # The walk every MPFB panel uses to get from whatever the user has
        # selected to the object that owns what it wants: down through children
        # (descending through armatures even when they do not match), then up
        # through parents, taking each parent's other branches on the way.
        if not blender_object or not mpfb_type_name:
            return

        def rec_children(rec_parent, exclude=None):
            if only_parents:
                return
            for parents_child in StubObjectService.get_list_of_children(rec_parent):
                if parents_child is exclude:
                    continue
                if StubObjectService.object_is(parents_child, mpfb_type_name):
                    yield parents_child
                elif parents_child.type == "ARMATURE":
                    yield from rec_children(parents_child)

        # Yields the object it was asked about, first, when it matches - which
        # is why callers dedupe.
        if StubObjectService.object_is(blender_object, mpfb_type_name):
            yield blender_object
        yield from rec_children(blender_object)

        if only_children:
            return

        came_from = blender_object
        parent = blender_object.parent
        while parent is not None:
            if StubObjectService.object_is(parent, mpfb_type_name):
                yield parent
            yield from rec_children(parent, came_from)
            came_from = parent
            parent = parent.parent

    @staticmethod
    def find_object_of_type_amongst_nearest_relatives(blender_object, mpfb_type_name="Basemesh",
                                                      **kwargs):
        # Really None when nothing matches, which is the branch that turns "this
        # object is not part of a character" into an answer.
        return next(
            StubObjectService.find_all_objects_of_type_amongst_nearest_relatives(
                blender_object, mpfb_type_name, **kwargs),
            None)

    @staticmethod
    def find_related_mesh_assets(blender_object, **kwargs):
        yield from StubObjectService.find_all_objects_of_type_amongst_nearest_relatives(
            blender_object, _MESH_ASSET_TYPES, **kwargs)

    @staticmethod
    def find_related_objects(blender_object, **kwargs):
        # A thin wrapper over the general walk, exactly as MPFB's is.
        yield from StubObjectService.find_all_objects_of_type_amongst_nearest_relatives(
            blender_object, _ALL_TYPES, **kwargs)

    @staticmethod
    def find_rigify_metarig_by_rig(blender_object):
        # Guarded exactly as MPFB's is: asked about a rig that is not a
        # generated Rigify rig, it answers None rather than searching. The link
        # itself is the metarig's own "rigify_target_rig" pointing back at the
        # rig, not a shared id.
        if not StubObjectService.object_is_generated_rigify_rig(blender_object):
            return None
        for candidate in StubObjectService.all_objects:
            if candidate.type == "ARMATURE" and candidate.rigify_target_rig is blender_object:
                return candidate
        return None

    @staticmethod
    def activate_blender_object(object_to_make_active, context=None, deselect_all=False):
        # Selects *and* activates. The payloads restore both afterwards, so the
        # stub has to actually do both or there would be nothing to restore.
        StubObjectService.activations.append(object_to_make_active.name)
        object_to_make_active.select_set(True)
        StubObjectService.bpy.context.view_layer.objects.active = object_to_make_active

    @staticmethod
    def object_is_generated_rigify_rig(blender_object):
        # Also not a bool: the real one returns Rigify's rig_id string.
        return blender_object.type == "ARMATURE" and blender_object.rig_id

    @staticmethod
    def object_is_rigify_metarig(blender_object, check_bones=False):
        return bool(blender_object.type == "ARMATURE" and blender_object.metarig)


class StubAssetService:
    """Records what it was asked to resolve, so the asset subdir is assertable."""

    calls = []
    resolutions = {}

    @staticmethod
    def find_asset_absolute_path(asset_path_fragment, asset_subdir="clothes"):
        StubAssetService.calls.append((asset_path_fragment, asset_subdir))
        return StubAssetService.resolutions.get(asset_path_fragment)

    # What get_custom_rigs() should answer, and how it was asked. Set by a test
    # that wants a particular set of custom rigs on disk.
    custom_rigs = ()
    custom_rig_calls = []
    invalidations = 0
    # Set by a test exercising the payload's fallback for an MPFB whose
    # get_custom_rigs() predates the use_cache keyword.
    reject_use_cache = False

    @staticmethod
    def get_custom_rigs(use_cache=True):
        if StubAssetService.reject_use_cache and not use_cache:
            raise TypeError("get_custom_rigs() got an unexpected keyword argument 'use_cache'")
        StubAssetService.custom_rig_calls.append(use_cache)
        return [dict(record) for record in StubAssetService.custom_rigs]

    @staticmethod
    def invalidate_custom_rig_cache():
        StubAssetService.invalidations += 1

    # What mpfb_list_assets sees "on disk": asset subdir -> absolute paths, and
    # asset subdir -> the roots that actually contain it. The two are kept
    # separate on purpose, since get_asset_roots() returning fewer roots than
    # get_available_data_roots() is the diagnostic the payload reports.
    asset_files = dict()
    asset_roots = dict()
    # Paths whose .thumb companion exists, keyed by the .thumb path itself.
    thumbs = ()
    asset_list_calls = []
    update_all_calls = 0
    # Pack name -> the asset names its metadata lists. Those are directory
    # names, which is the whole basis of the tool's pack attribution.
    packs = dict()

    @staticmethod
    def get_available_data_roots():
        # Deliberately wider than get_asset_roots(): a data root that holds no
        # such subdir is a configured root that is nonetheless not searched.
        roots = []
        for subdir_roots in StubAssetService.asset_roots.values():
            for root in subdir_roots:
                parent = os.path.dirname(root)
                if parent not in roots:
                    roots.append(parent)
        return roots

    @staticmethod
    def get_asset_roots(asset_subdir="clothes"):
        return list(StubAssetService.asset_roots.get(asset_subdir, []))

    @staticmethod
    def get_asset_list(asset_subdir="clothes", asset_type="mhclo"):
        # A reimplementation of update_asset_list()'s item building, quirks
        # included, rather than a convenient dict: the item keys are exactly
        # MPFB's, `thumb` holds something that is not JSON-safe (a Blender
        # preview object in the real thing), and the list is keyed by *label*,
        # so two files whose names differ only in case or underscores collapse
        # into one entry. That collision is a limitation the tool documents, and
        # it can only be pinned by a stub that actually reproduces it.
        StubAssetService.asset_list_calls.append((asset_subdir, asset_type))
        asset_list = dict()
        for path in StubAssetService.asset_files.get(asset_subdir, []):
            item = dict()
            item["full_path"] = path
            item["basename"] = os.path.basename(path)
            item["dirname"] = os.path.dirname(path)
            item["fragment"] = os.path.basename(item["dirname"]) + "/" + item["basename"]
            item["name_without_ext"] = str(item["basename"]).replace("." + asset_type, "")
            item["thumb"] = None
            item["thumb_path"] = None
            label = str(item["name_without_ext"]).lower().replace("_", " ")
            item["label"] = label.capitalize()
            thumb = os.path.join(item["dirname"], item["name_without_ext"] + ".thumb")
            if thumb in StubAssetService.thumbs:
                item["thumb_path"] = thumb
                # Stands in for the bpy preview object, which json cannot encode.
                item["thumb"] = object()
            asset_list[item["label"]] = item
        return asset_list

    @staticmethod
    def find_asset_files_matching_pattern(asset_roots, pattern="*.mhclo"):
        # A real rglob over real directories, and a list of pathlib.Path - both
        # as MPFB does it. The Path return type is the point: the target payload
        # handles these directly rather than through the cached asset items, so
        # a forgotten str() fails strict_json for real only if the stub keeps
        # the type.
        found = []
        for root in asset_roots:
            if str(root) == "/":
                raise IOError("Refusing to scan entire HD for assets")
            for path in pathlib.Path(str(root)).rglob(pattern):
                if os.path.isfile(path):
                    found.append(path)
        return found

    @staticmethod
    def update_all_asset_lists():
        StubAssetService.update_all_calls += 1

    @staticmethod
    def get_pack_names():
        # Sorted, as MPFB sorts it.
        return sorted(StubAssetService.packs)

    @staticmethod
    def get_asset_names_in_pack(pack_name):
        return sorted(StubAssetService.packs.get(pack_name, []))


class StubClothesService:
    @staticmethod
    def find_clothes_absolute_path(clothes_object):
        asset_source = GeneralObjectProperties.get_value(
            "asset_source", entity_reference=clothes_object)
        object_type = StubObjectService.get_object_type(clothes_object).lower()
        if asset_source and object_type:
            return StubAssetService.find_asset_absolute_path(asset_source, object_type)
        return None


class StubMaterialService:
    @staticmethod
    def get_material(blender_object, slot=0):
        return blender_object.material

    @staticmethod
    def identify_material(material):
        if not material:
            return "empty"
        return material.identified


class StubRigService:
    # MPFB's real fallback table, verbatim. The payload mirrors add_builtin_rig()
    # by walking this list, so a stub that returned only the rig itself would
    # make the two entries that actually need a fallback look unweighted.
    WEIGHT_FALLBACKS = {
        "default_no_toes": ["default"],
        "rigify.human": ["rigify.human_toes"],
        "rigify.human_toes": ["rigify.human"],
    }

    @staticmethod
    def identify_rig(armature_object):
        # Never None: "unknown" is the miss.
        return armature_object.rig_type

    @staticmethod
    def get_rig_weight_fallbacks(rig_type):
        return [rig_type, *StubRigService.WEIGHT_FALLBACKS.get(rig_type, [])]


class StubLocationService:
    # Set by a test that wants rig_definition_path to resolve to a real file.
    mpfb_data = "/nonexistent-mpfb-data"
    # MPFB keeps this one as a pathlib.Path despite the str annotation, so the
    # stub does too - a payload that forgets to coerce fails strict_json for
    # real, and only this type reproduces that here.
    mpfb_root = pathlib.Path("/nonexistent-mpfb-root")
    user_data = "/nonexistent-user-data"
    second_root = None

    @staticmethod
    def get_mpfb_data(sub_path=None):
        import os
        if sub_path is None:
            return StubLocationService.mpfb_data
        return os.path.join(StubLocationService.mpfb_data, sub_path)

    @staticmethod
    def get_mpfb_root(sub_path=None):
        import os
        if sub_path is None:
            # A Path, exactly as MPFB returns it.
            return StubLocationService.mpfb_root
        # ...but os.path.join() turns it back into a str, which is why the
        # coercion only bites on the no-sub-path form.
        return os.path.join(StubLocationService.mpfb_root, sub_path)

    @staticmethod
    def get_user_data(sub_path=None):
        import os
        if sub_path is None:
            return StubLocationService.user_data
        return os.path.join(StubLocationService.user_data, sub_path)

    @staticmethod
    def get_second_root(sub_path=None):
        import os
        # Really can be None, and get_custom_rigs() guards for exactly that.
        if StubLocationService.second_root is None:
            return None
        if sub_path is None:
            return StubLocationService.second_root
        return os.path.join(StubLocationService.second_root, sub_path)


class StubSystemService:
    # Never a truthy non-bool, unlike several ObjectService helpers: the real
    # check_for_rigify() does return a real bool.
    rigify_available = True

    @staticmethod
    def check_for_rigify():
        return StubSystemService.rigify_available


# MPFB's real _OPPOSITES table, from targetservice.py: the eight opposing
# suffix pairs shapekey_is_target() recognises a modeling target by.
_OPPOSITES = [
    "decr-incr", "down-up", "in-out", "backward-forward",
    "concave-convex", "compress-uncompress", "square-round", "pointed-triangle",
]

# MPFB's real _SHAPEKEY_ENCODING table, from targetservice.py. Only these
# sixteen words are ever substituted, so a long name containing none of them
# encodes to itself - which is why the test fixture's long target is named with
# words that appear here.
_SHAPEKEY_ENCODING = [
    ["macrodetail", "$md"],
    ["female", "$fe"],
    ["male", "$ma"],
    ["caucasian", "$ca"],
    ["asian", "$as"],
    ["african", "$af"],
    ["average", "$av"],
    ["weight", "$wg"],
    ["height", "$hg"],
    ["muscle", "$mu"],
    ["proportions", "$pr"],
    ["firmness", "$fi"],
    ["ideal", "$id"],
    ["uncommon", "$un"],
    ["young", "$yn"],
    ["child", "$ch"],
]


class StubTargetService:
    """The name-encoding half of the real one, and the macro half.

    The macro half stores nothing of its own: it reads through the same property
    set the payloads write to, and it adds and removes real stub shape keys, so
    the before/after lists the mutating tool reports are asserted against
    something that actually changed.
    """

    calls = []
    reapply_calls = []
    load_calls = []
    set_calls = []
    # MPFB's module-level _ODD_TARGET_NAMES, which load_target() appends to and
    # shapekey_is_target() falls back on. Reset between tests, as the real one
    # is not - which is itself why the fallback is a "last resort".
    odd_target_names = []

    @staticmethod
    def encode_shapekey_name(original_name):
        name = str(original_name)
        for code in _SHAPEKEY_ENCODING:
            name = name.replace(code[0], code[1])
        return name

    @staticmethod
    def filename_to_shapekey_name(filename, *, macrodetail=False, encode_name=None):
        # Keyword-only, exactly as MPFB declares it: a payload passing
        # macrodetail positionally would fail here rather than in Blender.
        StubTargetService.calls.append((str(filename), macrodetail, encode_name))
        name = os.path.basename(str(filename))
        name = re.sub(r"\.gz$", "", name, flags=re.IGNORECASE)
        name = re.sub(r"\.p?target$", "", name, flags=re.IGNORECASE)
        if macrodetail:
            name = "macrodetail-" + name
            if encode_name is None:
                encode_name = True
        if encode_name is None and len(name) > 60:
            encode_name = True
        if encode_name:
            name = StubTargetService.encode_shapekey_name(name)
        return name

    @staticmethod
    def decode_shapekey_name(encoded_name):
        name = str(encoded_name)
        for code in _SHAPEKEY_ENCODING:
            name = name.replace(code[1], code[0])
        return name

    @staticmethod
    def macrodetail_filename_to_shapekey_name(filename, encode_name=False):
        # Note the signature: encode_name is positional-or-keyword here, while
        # on filename_to_shapekey_name it is keyword-only. Reproducing that is
        # what would catch a payload calling the wrong one of the two.
        return StubTargetService.filename_to_shapekey_name(
            filename, macrodetail=True, encode_name=encode_name)

    @staticmethod
    def has_any_shapekey(blender_object):
        if not blender_object or blender_object.type != "MESH":
            return False
        if not blender_object.data.shape_keys:
            return False
        return len(blender_object.data.shape_keys.key_blocks) > 0

    @staticmethod
    def get_default_macro_info_dict():
        # MPFB's own values, race weights summing to 0.99 and not to 1.0.
        return {
            "gender": 0.5,
            "age": 0.5,
            "muscle": 0.5,
            "weight": 0.5,
            "proportions": 0.5,
            "height": 0.5,
            "cupsize": 0.5,
            "firmness": 0.5,
            "race": {
                "asian": 0.33,
                "caucasian": 0.33,
                "african": 0.33,
            },
        }

    @staticmethod
    def get_macro_info_dict_from_basemesh(basemesh):
        # Reads through the same property set set_value() writes to, so the
        # write-then-read round trip in mpfb_set_macro_details is genuinely
        # under test rather than asserted against a value the stub kept aside.
        def value(name):
            return HumanObjectProperties.get_value(name, entity_reference=basemesh)

        return {
            "gender": value("gender"),
            "age": value("age"),
            "muscle": value("muscle"),
            "weight": value("weight"),
            "proportions": value("proportions"),
            "height": value("height"),
            "cupsize": value("cupsize"),
            "firmness": value("firmness"),
            "race": {
                "asian": value("asian"),
                "caucasian": value("caucasian"),
                "african": value("african"),
            },
        }

    @staticmethod
    def _interpolate(value, low_name, high_name):
        return [(low_name, round(1.0 - value, 4)), (high_name, round(value, 4))]

    @staticmethod
    def calculate_target_stack_from_macro_info_dict(macro_info, cutoff=0.01):
        """A *stand-in* interpolation. Deliberately not MPFB's real table.

        Reproducing MPFB's corner cases would mean copying a data file into the
        test suite and would prove nothing extra: no payload depends on which
        targets come out, only on the shape of what comes back - pairs of a file
        fragment and a weight, several per macro property, some falling below
        the cutoff and disappearing. That is what is reproduced here, including
        the multiplication of race weight by the rest, which is why an
        unnormalized race sum scales the whole stack.
        """
        if macro_info is None:
            macro_info = StubTargetService.get_default_macro_info_dict()

        stack = []
        genders = StubTargetService._interpolate(macro_info["gender"], "female", "male")
        ages = StubTargetService._interpolate(macro_info["age"], "young", "old")
        for race_name in ("asian", "caucasian", "african"):
            race_weight = macro_info["race"][race_name]
            for gender_name, gender_weight in genders:
                for age_name, age_weight in ages:
                    weight = race_weight * gender_weight * age_weight
                    if weight > cutoff:
                        stack.append([
                            "macrodetails/" + race_name + "-" + gender_name + "-" + age_name,
                            round(weight, 4),
                        ])
        for name, weight in StubTargetService._interpolate(macro_info["weight"], "minweight",
                                                           "maxweight"):
            if weight > cutoff:
                stack.append(["macrodetails-universal/" + name, round(weight, 4)])
        return stack

    @staticmethod
    def get_current_macro_targets(basemesh, decode_names=True):
        # Filters on the *raw* name starting with "$md" while returning the
        # decoded one, exactly as MPFB does - the two are different strings and
        # a stub that filtered on the decoded name would never match anything.
        targets = []
        if basemesh and basemesh.data.shape_keys and len(basemesh.data.shape_keys.key_blocks):
            for shape_key in basemesh.data.shape_keys.key_blocks:
                name = shape_key.name
                if decode_names:
                    name = StubTargetService.decode_shapekey_name(name)
                if str(shape_key.name).startswith("$md"):
                    targets.append(name)
        return targets

    # ---- The write half, and the reads the writes depend on. -------------
    #
    # Each of these reproduces a quirk of the real one that a payload exists to
    # work around; a helpful stub would make the workaround look unnecessary.

    @staticmethod
    def get_target_stack(blender_object, exclude_starts_with=None, exclude_ends_with=None):
        # Note the exclusion: any name *containing* "basis", not equal to it.
        # A user target called "basis-nose-widen" is therefore invisible to
        # has_target(), get_target_value() and every write MPFB can perform.
        if blender_object is None or blender_object.type != "MESH":
            raise ValueError("Must provide a valid mesh object")
        keys = blender_object.data.shape_keys
        if keys is None or keys.key_blocks is None or len(keys.key_blocks) < 1:
            return []

        if exclude_starts_with is None:
            starts_with_prefixes = ()
        elif isinstance(exclude_starts_with, str):
            starts_with_prefixes = (exclude_starts_with.lower(),)
        else:
            starts_with_prefixes = tuple(str(p).lower() for p in exclude_starts_with)

        if exclude_ends_with is None:
            ends_with_suffixes = ()
        elif isinstance(exclude_ends_with, str):
            ends_with_suffixes = (exclude_ends_with.lower(),)
        else:
            ends_with_suffixes = tuple(str(s).lower() for s in exclude_ends_with)

        stack = []
        for shape_key in keys.key_blocks:
            sk_name = str(shape_key.name).lower()
            exclude = "basis" in sk_name
            if starts_with_prefixes and any(sk_name.startswith(p) for p in starts_with_prefixes):
                exclude = True
            if ends_with_suffixes and any(sk_name.endswith(s) for s in ends_with_suffixes):
                exclude = True
            if not exclude:
                stack.append({"target": shape_key.name, "value": shape_key.value})
        return stack

    @staticmethod
    def has_target(blender_object, target_name, also_check_for_encoded=True):
        # Checks the encoded name as well as the given one - which
        # set_target_value() and get_target_value() below do *not*.
        if blender_object is None or target_name is None or not target_name:
            return False
        encoded_name = StubTargetService.encode_shapekey_name(target_name)
        for target in StubTargetService.get_target_stack(blender_object):
            if target["target"] == target_name:
                return True
            if also_check_for_encoded and target["target"] == encoded_name:
                return True
        return False

    @staticmethod
    def get_target_value(blender_object, target_name):
        # 0.0 for a name that does not exist, indistinguishable from a target
        # that exists at zero. That ambiguity is why the payloads report
        # existence separately from value.
        if blender_object is None or target_name is None or not target_name:
            return 0.0
        for target in StubTargetService.get_target_stack(blender_object):
            if target["target"] == target_name:
                return target["value"]
        return 0.0

    @staticmethod
    def set_target_value(blender_object, target_name, value, delete_target_on_zero=False):
        # A **silent no-op** for a name that is not among the key blocks: it
        # neither loads the target nor raises. A stub that raised instead would
        # make the has_target()-then-load_target() logic look unnecessary and
        # let the bug it prevents through. It does raise when the mesh has no
        # shape keys at all, which is a different situation.
        if blender_object is None or target_name is None or not target_name:
            raise ValueError("Empty object or target")
        keys = blender_object.data.shape_keys
        if keys is None or keys.key_blocks is None or len(keys.key_blocks) < 1:
            raise ValueError("Empty object or target")
        StubTargetService.set_calls.append((blender_object.name, str(target_name), value,
                                            delete_target_on_zero))
        for shape_key in list(keys.key_blocks):
            if shape_key.name == target_name:
                shape_key.value = value
                if value < 0.0001 and delete_target_on_zero:
                    blender_object.shape_key_remove(shape_key)

    @staticmethod
    def load_target(blender_object, full_path, *, weight=0.0, name=None):
        # IOError for a path that is not there, which is what makes the
        # .target.gz/.target fallback and the resolve-before-write ordering
        # genuinely exercised rather than merely described.
        if blender_object is None:
            raise ValueError("Can only load targets onto specified mesh objects")
        if full_path is None or not full_path:
            raise ValueError("Must specify a valid path - null or none was given")
        if not os.path.exists(str(full_path)):
            raise IOError(str(full_path) + " does not exist")
        if name is None:
            name = StubTargetService.filename_to_shapekey_name(full_path)
        StubTargetService.load_calls.append((blender_object.name, str(full_path), weight,
                                             str(name)))
        # Through create_shape_key(), as the real one does via
        # target_string_to_shape_key() - which is where the OBJECT-mode assert
        # is reached.
        shape_key = StubTargetService.create_shape_key(blender_object, str(name))
        shape_key.value = weight
        if not StubTargetService.shapekey_is_target(shape_key.name):
            if shape_key.name not in StubTargetService.odd_target_names:
                StubTargetService.odd_target_names.append(shape_key.name)
        return shape_key

    @staticmethod
    def shapekey_is_target(shapekey_name):
        if not shapekey_name:
            return False
        if shapekey_name.lower() == "basis":
            return False
        if shapekey_name.startswith("$md"):
            return True
        for opposite in _OPPOSITES:
            if opposite in shapekey_name:
                return True
            low, high = opposite.split("-")
            if "-" + low in shapekey_name or "-" + high in shapekey_name:
                return True
        # Populated by load_target() at run time, exactly as MPFB's own
        # module-level list is - so it is empty for a target that was never
        # loaded in this session.
        return shapekey_name in StubTargetService.odd_target_names

    @staticmethod
    def prune_shapekeys(blender_object, cutoff=0.0001):
        keys = blender_object.data.shape_keys
        if keys is None or keys.key_blocks is None or len(keys.key_blocks) < 1:
            return
        skip = True  # The first shape key is assumed to be Basis, by position.
        for shape_key in list(keys.key_blocks):
            if not skip and shape_key.value < cutoff:
                if StubTargetService.shapekey_is_target(shape_key.name):
                    blender_object.shape_key_remove(shape_key)
            skip = False

    @staticmethod
    def target_full_path(target_name):
        """MPFB's tiered search, exact stem preferred and prefix as a fallback.

        The prefix fallback is reproduced because it is the reason the payloads
        build paths from the category data instead, and report the path when
        they do fall back here: "nose-scale-depth" resolving to
        "nose-scale-depth-decr" is a wrong answer that looks like a right one.
        """
        lowered = str(target_name).lower()

        def match_in(paths):
            prefix_match = None
            for path in paths:
                basename = str(os.path.basename(str(path))).lower()
                if basename.endswith(".target.gz"):
                    stem = basename[:-len(".target.gz")]
                else:
                    stem = basename[:-len(".target")]
                if stem == lowered:
                    return str(path)
                if prefix_match is None and basename.startswith(lowered):
                    prefix_match = str(path)
            return prefix_match

        targets_dir = StubLocationService.get_mpfb_data("targets")
        found = match_in(pathlib.Path(str(targets_dir)).rglob("*.target.gz"))
        if found:
            return found

        custom_roots = StubAssetService.get_asset_roots("custom")
        custom_roots.extend(StubAssetService.get_asset_roots("targets/custom"))
        custom = StubAssetService.find_asset_files_matching_pattern(custom_roots, "*.target")
        custom.extend(
            StubAssetService.find_asset_files_matching_pattern(custom_roots, "*.target.gz"))
        found = match_in(custom)
        if found:
            return found

        target_roots = StubAssetService.get_asset_roots("targets")
        targets = StubAssetService.find_asset_files_matching_pattern(target_roots, "*.target")
        targets.extend(
            StubAssetService.find_asset_files_matching_pattern(target_roots, "*.target.gz"))
        return match_in(targets)

    @staticmethod
    def create_shape_key(blender_object, shape_key_name, also_create_basis=True,
                         create_from_mix=False):
        # The bare assert MPFB opens with, and the whole reason the mutating
        # payloads check the mode themselves: without a message, this comes back
        # as a traceback that names nothing.
        assert blender_object.mode == "OBJECT"
        if also_create_basis and not StubTargetService.has_any_shapekey(blender_object):
            blender_object.shape_key_add(name="Basis", from_mix=False)
        return blender_object.shape_key_add(name=shape_key_name, from_mix=create_from_mix)

    @staticmethod
    def reapply_macro_details(basemesh, remove_zero_weight_targets=True):
        """MPFB's own sequence: zero, load what is missing, set, then prune."""
        StubTargetService.reapply_calls.append(
            (basemesh.name, remove_zero_weight_targets))

        macro_info = StubTargetService.get_macro_info_dict_from_basemesh(basemesh)
        for target in StubTargetService.get_current_macro_targets(basemesh, decode_names=False):
            basemesh.data.shape_keys.key_blocks[target].value = 0.0

        current = StubTargetService.get_current_macro_targets(basemesh, decode_names=True)
        required = StubTargetService.calculate_target_stack_from_macro_info_dict(macro_info)

        for target in required:
            requested = str(StubTargetService.macrodetail_filename_to_shapekey_name(
                target[0], encode_name=False)).strip()
            if requested not in current:
                # The real one loads the target from disk here, which is where
                # the OBJECT-mode assert is reached.
                name = StubTargetService.macrodetail_filename_to_shapekey_name(
                    target[0], encode_name=True)
                StubTargetService.create_shape_key(basemesh, name)

        for target in required:
            requested = str(StubTargetService.macrodetail_filename_to_shapekey_name(
                target[0], encode_name=True)).strip()
            basemesh.data.shape_keys.key_blocks[requested].value = target[1]

        if remove_zero_weight_targets and basemesh.data.shape_keys:
            for shape_key in list(basemesh.data.shape_keys.key_blocks):
                if str(shape_key.name).startswith("$md") and shape_key.value < 0.0001:
                    basemesh.shape_key_remove(shape_key)


class StubHumanService:
    """refit(), plus the module HumanObjectProperties is reached off."""

    refit_calls = []
    # Set by a test that wants refit() itself to blow up, to check that the
    # payload still restores the active object and the selection.
    refit_raises = None

    @staticmethod
    def refit(blender_object, *, operator=None):
        basemesh = StubObjectService.find_object_of_type_amongst_nearest_relatives(
            blender_object, "Basemesh")
        if basemesh is None:
            # The real one raises rather than answering, which is why the
            # payload resolves the basemesh itself first.
            raise ValueError("Could not find basemesh as relative of given object")
        StubHumanService.refit_calls.append(basemesh.name)
        if StubHumanService.refit_raises is not None:
            raise StubHumanService.refit_raises
        # The real one refits the mesh assets *before* it reaches the rig, and
        # returns silently when a generated Rigify rig has no meta rig - having
        # refitted the assets and not the rig. Nothing is reported to a caller
        # that is not an operator, and there is no operator here.


_SERVICES = {
    "ObjectService": StubObjectService,
    "AssetService": StubAssetService,
    "ClothesService": StubClothesService,
    "MaterialService": StubMaterialService,
    "RigService": StubRigService,
    "LocationService": StubLocationService,
    "TargetService": StubTargetService,
    "HumanService": StubHumanService,
    "SystemService": StubSystemService,
}


class _StubCollection:
    """A bpy_prop_collection: iterable, and `in` tests the *name*, not the object."""

    def __init__(self, objects):
        self._objects = list(objects)

    def __iter__(self):
        return iter(self._objects)

    def __contains__(self, key):
        return any(candidate.name == key for candidate in self._objects)

    def get(self, key, default=None):
        for candidate in self._objects:
            if candidate.name == key:
                return candidate
        return default


def _make_bpy(scene_objects, all_objects, active):
    bpy = types.ModuleType("bpy")
    bpy.data = types.SimpleNamespace(objects=_StubCollection(all_objects))
    bpy.context = types.SimpleNamespace(
        scene=types.SimpleNamespace(objects=_StubCollection(scene_objects)),
        view_layer=types.SimpleNamespace(
            objects=types.SimpleNamespace(active=active)),
    )
    return bpy


class GeneratedCodeTestCase(unittest.TestCase):
    """Executes an assembled payload against the stubs above."""

    def setUp(self):
        stray = [name for name in list(sys.modules) if name.endswith("mpfb")]
        self.assertEqual(stray, [], "a real module ending in 'mpfb' would skew these tests")

        StubAssetService.calls = []
        StubAssetService.resolutions = {}
        StubAssetService.custom_rigs = (
            {"name": "my_rig", "path": "/home/user/data/rigs/my_rig.json",
             "identifying_bones": ["root"]},
        )
        StubAssetService.custom_rig_calls = []
        StubAssetService.invalidations = 0
        StubAssetService.reject_use_cache = False
        StubAssetService.asset_files = dict()
        StubAssetService.asset_roots = dict()
        StubAssetService.thumbs = ()
        StubAssetService.asset_list_calls = []
        StubAssetService.update_all_calls = 0
        StubAssetService.packs = dict()
        StubTargetService.calls = []
        StubTargetService.reapply_calls = []
        StubTargetService.load_calls = []
        StubTargetService.set_calls = []
        StubTargetService.odd_target_names = []
        StubObjectService.activations = []
        StubHumanService.refit_calls = []
        StubHumanService.refit_raises = None
        StubLocationService.mpfb_data = "/nonexistent-mpfb-data"
        StubLocationService.mpfb_root = pathlib.Path("/nonexistent-mpfb-root")
        StubLocationService.user_data = "/nonexistent-user-data"
        StubLocationService.second_root = None
        StubSystemService.rigify_available = True

        # The payloads reach the type vocabulary and the two property sets off
        # the module of a service that imported them, so the stub classes'
        # __module__ has to point at a module carrying those names.
        objectservice_module = types.ModuleType(_OBJECTSERVICE_MODULE)
        objectservice_module._ALL_TYPES = _ALL_TYPES
        objectservice_module._MESH_ASSET_TYPES = _MESH_ASSET_TYPES
        objectservice_module._SKELETON_TYPES = _SKELETON_TYPES
        objectservice_module.GeneralObjectProperties = GeneralObjectProperties
        StubObjectService.__module__ = _OBJECTSERVICE_MODULE

        humanservice_module = types.ModuleType(_HUMANSERVICE_MODULE)
        humanservice_module.HumanObjectProperties = HumanObjectProperties
        StubHumanService.__module__ = _HUMANSERVICE_MODULE

        # ASSET_LIBRARY_SECTIONS is module-level in assetservice.py rather than
        # a member of AssetService, so the payload reaches it the same way the
        # others reach the type vocabulary - which means this stub class needs a
        # module of its own too.
        assetservice_module = types.ModuleType(_ASSETSERVICE_MODULE)
        assetservice_module.ASSET_LIBRARY_SECTIONS = ASSET_LIBRARY_SECTIONS
        StubAssetService.__module__ = _ASSETSERVICE_MODULE

        # Unlike the status payload, these run on the raising bootstrap, so an
        # initialized MPFB has to be there or the exec raises before the payload.
        mpfb_module = types.ModuleType(_PACKAGE)
        mpfb_module.MPFB_CONTEXTUAL_INFORMATION = {"SERVICES": _SERVICES}

        self._injected = {
            _OBJECTSERVICE_MODULE: objectservice_module,
            _HUMANSERVICE_MODULE: humanservice_module,
            _ASSETSERVICE_MODULE: assetservice_module,
            _PACKAGE: mpfb_module,
        }
        sys.modules.update(self._injected)

    def tearDown(self):
        for name in self._injected:
            sys.modules.pop(name, None)

    def run_payload(self, payload, params, scene_objects=(), all_objects=None, active=None,
                    shared=None):
        """Assemble and execute one payload, returning the ``result`` it bound.

        ``shared`` names the fragments the payload's own tool module passes, so
        what is executed here is the same program the tool would send.
        """
        if all_objects is None:
            all_objects = scene_objects
        StubObjectService.all_objects = tuple(all_objects)
        code = codegen.assemble(
            payload, bootstrap="raising", params=params, shared=shared)
        namespace = {}
        bpy = _make_bpy(scene_objects, all_objects, active)
        # activate_blender_object() changes the active object for real, so the
        # stub service needs the same bpy the payload is about to run against -
        # and a test needs it afterwards, to see what the payload left behind.
        StubObjectService.bpy = bpy
        self.last_bpy = bpy
        with mock.patch.dict(sys.modules, {"bpy": bpy}):
            exec(code, namespace)  # noqa: S102
        return namespace["result"]


# The trimmed target.json the three detail-target payloads run against. Its
# shape is the real one's, and every category in it is there because it is a
# branch: an unsided pair of opposites, a sided pair with all four l-/r- entries,
# a category with no opposites at all, a sided pair whose right-hand files are
# missing from disk, and the real index's genuinely empty "measure" section.
DETAIL_TARGET_JSON = {
    "arms": {
        "include_per_default": True,
        "label": "Arms",
        "unsorted": [],
        "categories": [
            {
                "has_left_and_right": True,
                "label": "lowerarm-scale-depth-decr-incr",
                "name": "lowerarm-scale-depth-decr-incr",
                "opposites": {
                    "negative-left": "l-lowerarm-scale-depth-decr",
                    "negative-right": "r-lowerarm-scale-depth-decr",
                    "negative-unsided": "",
                    "positive-left": "l-lowerarm-scale-depth-incr",
                    "positive-right": "r-lowerarm-scale-depth-incr",
                    "positive-unsided": "",
                },
                "targets": [
                    "l-lowerarm-scale-depth-decr", "r-lowerarm-scale-depth-incr",
                    "r-lowerarm-scale-depth-decr", "l-lowerarm-scale-depth-incr",
                ],
            },
            {
                "has_left_and_right": False,
                "label": "upperarm-fat-decr-incr",
                "name": "upperarm-fat-decr-incr",
                "opposites": {
                    "negative-left": "", "negative-right": "",
                    "negative-unsided": "upperarm-fat-decr",
                    "positive-left": "", "positive-right": "",
                    "positive-unsided": "upperarm-fat-incr",
                },
                "targets": ["upperarm-fat-decr", "upperarm-fat-incr"],
            },
        ],
    },
    "nose": {
        "include_per_default": True,
        "label": "Nose",
        "unsorted": [],
        "categories": [
            {
                "has_left_and_right": False,
                "label": "nose-scale-depth-decr-incr",
                "name": "nose-scale-depth-decr-incr",
                "opposites": {
                    "negative-left": "", "negative-right": "",
                    "negative-unsided": "nose-scale-depth-decr",
                    "positive-left": "", "positive-right": "",
                    "positive-unsided": "nose-scale-depth-incr",
                },
                "targets": ["nose-scale-depth-decr", "nose-scale-depth-incr"],
            },
        ],
    },
    "chin": {
        "include_per_default": True,
        "label": "Chin",
        "unsorted": [],
        "categories": [
            # No "opposites" key at all: a 0.0-1.0 modifier with one target.
            {
                "has_left_and_right": False,
                "label": "chin-triangle",
                "name": "chin-triangle",
                "targets": ["chin-triangle"],
            },
        ],
    },
    "ears": {
        "include_per_default": True,
        "label": "Ears",
        "unsorted": [],
        "categories": [
            # Sided, but only the left-hand files are on disk - so a change to
            # the right side, or a symmetrize onto it, cannot be loaded.
            {
                "has_left_and_right": True,
                "label": "ear-lobe-decr-incr",
                "name": "ear-lobe-decr-incr",
                "opposites": {
                    "negative-left": "l-ear-lobe-decr",
                    "negative-right": "r-ear-lobe-decr",
                    "negative-unsided": "",
                    "positive-left": "l-ear-lobe-incr",
                    "positive-right": "r-ear-lobe-incr",
                    "positive-unsided": "",
                },
                "targets": [
                    "l-ear-lobe-decr", "l-ear-lobe-incr",
                    "r-ear-lobe-decr", "r-ear-lobe-incr",
                ],
            },
        ],
    },
    "measure": {
        "include_per_default": False,
        "label": "measure",
        "unsorted": [],
        "categories": [],
    },
}

# Over 60 characters once the extension is stripped, and built from words in
# MPFB's encoding table, so its shape key name provably differs from its
# filename. FR 006's live pass showed that addressing it by filename fails
# silently, which is why it is in this fixture too.
LONG_USER_TARGET = (
    "young-female-average-caucasian-uncommon-proportions-weight-height-experiment")


def touch(path, content="dummy target data"):
    """Create a real file, and the directories above it."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class DetailTargetTestCase(GeneratedCodeTestCase):
    """A real target tree plus a dressed, rigged character.

    Shared by the three detail-target payloads because they need the same two
    things and for the same reason. The tree is a real ``tempfile`` one rather
    than a mocked filesystem: path resolution and on-demand loading are most of
    what these payloads do, and mocking ``os.path.exists()`` away would leave
    the part that matters untested.
    """

    def setUp(self):
        super().setUp()
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        root = self._temporary.name

        self.mpfb_data = os.path.join(root, "mpfb", "data")
        self.system_targets = os.path.join(self.mpfb_data, "targets")
        self.target_json_path = os.path.join(self.system_targets, "target.json")
        os.makedirs(self.system_targets)
        self.write_target_json(DETAIL_TARGET_JSON)

        # Gzipped, as every bundled target on a real install is.
        for name in ("l-lowerarm-scale-depth-decr", "l-lowerarm-scale-depth-incr",
                     "r-lowerarm-scale-depth-decr", "r-lowerarm-scale-depth-incr",
                     "upperarm-fat-decr"):
            touch(os.path.join(self.system_targets, "arms", name + ".target.gz"))
        # The one bundled target that is *not* gzipped, which is the case
        # _set_opposed_modifier_value() would hand a non-existent path.
        touch(os.path.join(self.system_targets, "arms", "upperarm-fat-incr.target"))
        for name in ("nose-scale-depth-decr", "nose-scale-depth-incr"):
            touch(os.path.join(self.system_targets, "nose", name + ".target.gz"))
        touch(os.path.join(self.system_targets, "chin", "chin-triangle.target.gz"))
        # Left only: the right-hand files of this category are deliberately absent.
        for name in ("l-ear-lobe-decr", "l-ear-lobe-incr"):
            touch(os.path.join(self.system_targets, "ears", name + ".target.gz"))

        self.user_data = os.path.join(root, "user", "data")
        self.user_targets = os.path.join(self.user_data, "targets")
        self.user_custom = os.path.join(self.user_data, "custom")

        # A user directory sharing its name with a bundled section: MPFB appends
        # these into that section rather than making a second one.
        touch(os.path.join(self.user_targets, "arms", "elvs_arm_bulk.target"))
        # A section that exists only as a user directory.
        touch(os.path.join(self.user_targets, "animal", "cat_ears.target"))
        touch(os.path.join(self.user_targets, "animal", LONG_USER_TARGET + ".target"))
        # Contains "basis", so MPFB's own get_target_stack() cannot see the
        # shape key this produces - and neither can any MPFB read or write.
        touch(os.path.join(self.user_targets, "animal", "basis-nose-widen.target"))
        # The custom section proper. The gzipped one is where MPFB's category
        # name ("vwide.gz") and the catalogue's shapekey_name ("vwide") diverge.
        touch(os.path.join(self.user_custom, "closed_eyes.target"))
        touch(os.path.join(self.user_custom, "vwide.target.gz"))

        StubLocationService.mpfb_data = self.mpfb_data
        StubLocationService.user_data = self.user_data
        StubAssetService.asset_roots = {
            "custom": [self.user_custom],
            "targets/custom": [os.path.join(self.user_targets, "custom")],
            "targets": [self.user_targets],
        }

    def write_target_json(self, data):
        with open(self.target_json_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def build_character(self, shapekeys=(("Basis", 0.0),), rig=True, **basemesh_kwargs):
        """A dressed - and by default rigged - character to read or modify.

        Parented the way MPFB parents one: a garment on a rigged character hangs
        off the *rig* rather than off the basemesh, so the mesh assets are found
        by walking up to the rig and back down its other branches.
        """
        self.rig = None
        if rig:
            self.rig = StubObject(
                "Human.rig", blender_type="ARMATURE", object_type="Skeleton")
        self.basemesh = StubObject(
            "Human", parent=self.rig, object_type="Basemesh",
            shapekeys=list(shapekeys) if shapekeys else None, **basemesh_kwargs)
        self.shirt = StubObject(
            "Shirt", parent=self.rig or self.basemesh, object_type="Clothes")
        self.objects = [obj for obj in (self.rig, self.basemesh, self.shirt) if obj]
        return self.objects

    def shapekey_values(self):
        """Every shape key on the basemesh, as a name -> value dict."""
        keys = self.basemesh.data.shape_keys
        if keys is None:
            return dict()
        return dict((str(block.name), block.value) for block in keys.key_blocks)
