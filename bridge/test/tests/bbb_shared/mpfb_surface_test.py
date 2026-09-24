"""
``shared/mpfb_surface.py``, called directly.

Every read of a name MPFB keeps on a service's module goes through this module,
so its three rules are checked here once, against the real install, rather than
through whichever command happens to read a given name:

- a name that is there is read off the module of the service named;
- a name that is not there takes the fallback, and does not raise;
- **the service matters**: ``HumanObjectProperties`` is on ``HumanService``'s
  module and not on ``ObjectService``'s. That is the claim the whole third rule
  rests on, and the one a wrong read would never report, so it is asserted
  against MPFB rather than assumed.

The required form is checked on ``FaceService``'s vocabulary, the one surface
FR 036 decided has no fallback, and on a name that is not there. The two
coercions need no MPFB at all.
"""

import pathlib

import pytest

from .. import bridge_module
from .._fixtures import Character
from .._fixtures import services_or_skip


def _module():
    return bridge_module("shared.mpfb_surface")


def test_a_name_on_the_services_module_is_read():
    services = services_or_skip()
    value = _module().module_level(services, "ObjectService", "GeneralObjectProperties",
                                   fallback="unused")
    assert value is not None and value != "unused"


def test_a_missing_name_takes_the_fallback():
    services = services_or_skip()
    sentinel = object()
    assert _module().module_level(services, "ObjectService", "BridgeTestNoSuchName",
                                  fallback=sentinel) is sentinel


def test_human_object_properties_is_on_humanservices_module_and_not_objectservices():
    """The read that takes the fallback silently when made from the wrong module."""
    services = services_or_skip()
    assert _module().human_object_properties(services) is not None
    assert _module().module_level(services, "ObjectService", "HumanObjectProperties",
                                  fallback=None) is None, \
        "if ObjectService's module now carries it too, the accessor's docstring is stale"
    assert _module().general_object_properties(services) is not None


def test_the_required_form_reads_the_face_vocabulary():
    services = services_or_skip()
    arkit = _module().required_module_level(services, "FaceService", "ARKIT_FACEUNITS")
    assert len(arkit) == 52


def test_the_required_form_names_what_is_missing():
    services = services_or_skip()
    missing = _module().MissingFromMpfb
    with pytest.raises(missing) as raised:
        _module().required_module_level(services, "FaceService", "BridgeTestNoSuchName")
    assert "FaceService" in str(raised.value)
    assert "BridgeTestNoSuchName" in str(raised.value)


def test_an_unset_string_property_reads_as_none():
    services = services_or_skip()
    properties = _module().general_object_properties(services)
    with Character() as character:
        assert _module().property_value(properties, "asset_source", character.basemesh) is None
        assert _module().property_value(properties, "object_type",
                                        character.basemesh) == "Basemesh"


def test_property_value_tolerates_a_missing_config_set_or_object():
    assert _module().property_value(None, "object_type", object()) is None
    assert _module().property_value(object(), "object_type", None) is None


def test_as_path_coerces_a_path_and_drops_an_empty_one():
    assert _module().as_path(pathlib.Path("/tmp/x")) == "/tmp/x"
    assert _module().as_path("/tmp/x") == "/tmp/x"
    assert _module().as_path("") is None
    assert _module().as_path(None) is None


def test_dotted_joins_a_tuple_and_refuses_anything_else():
    assert _module().dotted((2, 0, 14)) == "2.0.14"
    assert _module().dotted([4, 2]) == "4.2"
    assert _module().dotted(None) is None
    assert _module().dotted("2.0") is None, "a string would be joined character by character"
