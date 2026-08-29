# SPDX-License-Identifier: GPL-3.0-or-later

"""
Stand-ins for Blender and MPFB, for executing generated payloads locally.

The payloads for ``mpfb_list_objects``, ``mpfb_get_object_info``,
``mpfb_list_rigs`` and ``mpfb_list_assets`` carry real branching - type
filtering, relationship walking, three asset_info shapes, a weights fallback
walk, filtering and paging over an asset library - so they are worth running,
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

What they cannot do is tell us anything about the values real MPFB returns;
that remains a manual check against a running Blender.
"""

__all__ = (
    "ASSET_LIBRARY_SECTIONS",
    "GeneratedCodeTestCase",
    "StubAssetService",
    "StubLocationService",
    "StubMaterial",
    "StubObject",
    "StubSystemService",
)

import os
import pathlib
import sys
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


class StubObject:
    """One Blender object: its name, type, parent and MPFB custom properties."""

    def __init__(self, name, blender_type="MESH", parent=None, object_type="",
                 asset_source="", alternative_material="", material_source="",
                 material=None, rig_id=None, metarig=False, rig_type="unknown"):
        self.name = name
        self.type = blender_type
        self.parent = parent
        self.material = material
        # Rigify's own markers, which MPFB reads off the armature data rather
        # than through any property of its own.
        self.rig_id = rig_id
        self.metarig = metarig
        # What identify_rig() would deduce from this armature's bones.
        self.rig_type = rig_type
        self.properties = {
            "GEN": {
                "object_type": object_type,
                "asset_source": asset_source,
                "alternative_material": alternative_material,
            },
            "HUM": {"material_source": material_source},
        }


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


GeneralObjectProperties = _StubConfigSet("GEN")
HumanObjectProperties = _StubConfigSet("HUM")


class StubObjectService:
    """The subset of ObjectService the payloads use, with MPFB's semantics."""

    # Stands in for bpy.data.objects, which get_list_of_children() walks.
    all_objects = ()

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
    def find_related_objects(blender_object, **kwargs):
        def rec_children(rec_parent, exclude=None):
            for child in StubObjectService.get_list_of_children(rec_parent):
                if child is exclude:
                    continue
                if StubObjectService.object_is(child, _ALL_TYPES):
                    yield child
                elif child.type == "ARMATURE":
                    yield from rec_children(child)

        if StubObjectService.object_is(blender_object, _ALL_TYPES):
            yield blender_object
        yield from rec_children(blender_object)

        came_from = blender_object
        parent = blender_object.parent
        while parent is not None:
            if StubObjectService.object_is(parent, _ALL_TYPES):
                yield parent
            yield from rec_children(parent, came_from)
            came_from = parent
            parent = parent.parent

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


class StubHumanService:
    """Present only so HumanObjectProperties can be reached off its module."""


_SERVICES = {
    "ObjectService": StubObjectService,
    "AssetService": StubAssetService,
    "ClothesService": StubClothesService,
    "MaterialService": StubMaterialService,
    "RigService": StubRigService,
    "LocationService": StubLocationService,
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

    def run_payload(self, payload, params, scene_objects=(), all_objects=None, active=None):
        """Assemble and execute one payload, returning the ``result`` it bound."""
        if all_objects is None:
            all_objects = scene_objects
        StubObjectService.all_objects = tuple(all_objects)
        code = codegen.assemble(payload, bootstrap="raising", params=params)
        namespace = {}
        bpy = _make_bpy(scene_objects, all_objects, active)
        with mock.patch.dict(sys.modules, {"bpy": bpy}):
            exec(code, namespace)  # noqa: S102
        return namespace["result"]
