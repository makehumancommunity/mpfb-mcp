# SPDX-License-Identifier: GPL-3.0-or-later

"""
Stand-ins for Blender and MPFB, for executing generated payloads locally.

The payloads for ``mpfb_list_objects`` and ``mpfb_get_object_info`` carry real
branching - type filtering, relationship walking, three asset_info shapes - so
they are worth running, and they can only be run against stubs: MPFB is
reachable only from inside Blender (see specifications/architecture.md). This
module is shared by both tools' test modules because they need the same stub
scene; it holds no tests of its own.

The stubs reimplement the MPFB behavior the payloads actually depend on rather
than returning convenient values, since several of those behaviors are the
reason the payload is written the way it is:

- ``get_object_type()`` answers ``""``, never None, for an untyped object.
- ``object_is()`` matches by lowercased substring, not equality.
- ``object_is_any_makehuman_object()`` returns a *string*, not a bool.
- ``find_related_objects()`` yields the object it was asked about, first.
- ``get_list_of_children()`` walks the whole file, not the current scene.

What they cannot do is tell us anything about the values real MPFB returns;
that remains a manual check against a running Blender.
"""

__all__ = (
    "GeneratedCodeTestCase",
    "StubMaterial",
    "StubObject",
)

import sys
import types
import unittest
from unittest import mock

from mpfbmcp import codegen

# Neither may end in "mpfb", or the bootstrap's candidate scan would pick it up
# as an MPFB install of its own.
_OBJECTSERVICE_MODULE = "mpfb_stub_services_objectservice"
_HUMANSERVICE_MODULE = "mpfb_stub_services_humanservice"
_PACKAGE = "bl_ext.test_repo.mpfb"

_ALL_TYPES = ("Skeleton", "Subrig", "Basemesh", "Proxymeshes", "Clothes",
              "Eyes", "Eyelashes", "Eyebrows", "Tongue", "Teeth", "Hair")
_MESH_ASSET_TYPES = ("Proxymeshes", "Clothes", "Eyes", "Eyelashes", "Eyebrows",
                     "Tongue", "Teeth", "Hair")
_SKELETON_TYPES = ("Skeleton", "Subrig")


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

    @staticmethod
    def get_custom_rigs(use_cache=True):
        return [{"name": "my_rig", "path": "/home/user/data/rigs/my_rig.json",
                 "identifying_bones": ["root"]}]


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
    @staticmethod
    def identify_rig(armature_object):
        # Never None: "unknown" is the miss.
        return armature_object.rig_type


class StubLocationService:
    # Set by a test that wants rig_definition_path to resolve to a real file.
    mpfb_data = "/nonexistent-mpfb-data"

    @staticmethod
    def get_mpfb_data(sub_path=None):
        import os
        if sub_path is None:
            return StubLocationService.mpfb_data
        return os.path.join(StubLocationService.mpfb_data, sub_path)


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
        StubLocationService.mpfb_data = "/nonexistent-mpfb-data"

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

        # Unlike the status payload, these run on the raising bootstrap, so an
        # initialized MPFB has to be there or the exec raises before the payload.
        mpfb_module = types.ModuleType(_PACKAGE)
        mpfb_module.MPFB_CONTEXTUAL_INFORMATION = {"SERVICES": _SERVICES}

        self._injected = {
            _OBJECTSERVICE_MODULE: objectservice_module,
            _HUMANSERVICE_MODULE: humanservice_module,
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
