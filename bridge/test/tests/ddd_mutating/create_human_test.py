"""
``create_human`` against a real MPFB: the first command here that changes a .blend.

Small, and deliberately so. What this command does is call
``HumanService.create_human()`` and report four facts about what came back, so
what is worth asserting is exactly those four facts plus the two conventions
this module is the first to demonstrate:

- **``performed`` is true and there is no verb beside it.** Creation either
  returns a basemesh or raises, so ``with_performed(result, True)`` is
  unconditional - and a raise becomes a ``command_failed`` envelope rather than
  a ``performed: false`` answer, which is a distinction a caller branches on.
- **The phenotype that was asked for is the phenotype that arrives.** The
  eleven sliders reach this command as MPFB's own nested ``macro_detail_dict``,
  and the answer echoes it, so a caller can compare what it asked for against
  what was applied without a second call.

**There is no test here for an out-of-range slider**, and its absence is the
point rather than an omission: the 0.0-1.0 rule is mpfb-mcp's, enforced in
``tools/create_human.py`` before any transport is chosen, because MPFB's macro
properties carry a default but no min/max and nothing on this side clamps. See
the command module's docstring for why that asymmetry was left alone during a
migration rather than tidied up.

``Character`` is not used here: this module's subject *is* the creation, so it
snapshots and deletes for itself.
"""

import bpy

from .._fixtures import dispatch
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import supplied_resolution


def _result(params=None):
    return _fixture_result("create_human", params)


class _Created:
    """Whatever this block created, deleted again however the test ends."""

    def __init__(self):
        self._before = None

    def __enter__(self):
        self._before = set(blender_object.name for blender_object in bpy.data.objects)
        return self

    def __exit__(self, *args):
        for blender_object in list(bpy.data.objects):
            if blender_object.name not in self._before:
                bpy.data.objects.remove(blender_object, do_unlink=True)


def test_a_default_call_builds_a_basemesh():
    """commands.create_human with no parameters at all"""
    _services_or_skip()
    with _Created():
        result = _result()

        assert result["performed"] is True, \
            "creation either succeeds or raises, so performed is unconditional"
        assert result["basemesh_name"], "the new basemesh must be named"
        assert result["basemesh_name"] in bpy.data.objects, \
            "the reported name must be the name the object really has"
        # MPFB's hm08 basemesh. Asserted as "a lot" rather than as the exact
        # count, which is a property of the base mesh rather than of this
        # command and would make this test fail on an MPFB that improved it.
        assert result["vertex_count"] > 1000, \
            "a MakeHuman basemesh has thousands of vertices, got {!r}".format(
                result["vertex_count"])
        assert len(result["location"]) == 3, "location is an xyz triple"


def test_the_reported_name_is_the_uniquified_one():
    """commands.create_human twice: Blender renames the second"""
    _services_or_skip()
    with _Created():
        first = _result()
        second = _result()

        assert first["basemesh_name"] != second["basemesh_name"], \
            "Blender uniquifies a name already in use, and the answer must carry the real one"
        assert second["basemesh_name"] in bpy.data.objects
        assert result_vertex_counts_agree(first, second)


def result_vertex_counts_agree(first, second):
    """Two default characters have the same mesh; a helper so the assert reads."""
    return first["vertex_count"] == second["vertex_count"]


def test_the_macro_detail_dict_is_applied_and_echoed():
    """commands.create_human with a phenotype, read back through MPFB"""
    services = _services_or_skip()
    target_service = services["TargetService"]
    asked = {
        "gender": 1.0,
        "age": 0.75,
        "muscle": 0.5,
        "weight": 0.5,
        "proportions": 0.5,
        "height": 0.5,
        "cupsize": 0.5,
        "firmness": 0.5,
        "race": {"asian": 0.0, "caucasian": 1.0, "african": 0.0},
    }
    with _Created():
        result = _result({"macro_detail_dict": asked})

        assert result["macro_detail_dict"] == asked, \
            "the answer echoes what was applied, unreshaped"

        # And MPFB agrees, which is the half a stub could never establish.
        basemesh = bpy.data.objects[result["basemesh_name"]]
        stored = target_service.get_macro_info_dict_from_basemesh(basemesh)
        assert abs(stored["gender"] - 1.0) < 0.0001, \
            "MPFB should have stored the gender that was asked for, got {!r}".format(
                stored["gender"])
        assert abs(stored["race"]["caucasian"] - 1.0) < 0.0001


def test_scale_reaches_mpfb():
    """commands.create_human with a non-default scale"""
    _services_or_skip()
    with _Created():
        default = _result()
        scaled = _result({"scale": 1.0})

        default_object = bpy.data.objects[default["basemesh_name"]]
        scaled_object = bpy.data.objects[scaled["basemesh_name"]]
        default_height = max(vertex.co.z for vertex in default_object.data.vertices)
        scaled_height = max(vertex.co.z for vertex in scaled_object.data.vertices)

        assert scaled_height > default_height, \
            "scale=1.0 should produce a taller mesh than MPFB's decimetre default, got " \
            "{!r} against {!r}".format(scaled_height, default_height)


def test_a_non_number_scale_is_refused_by_the_contract():
    """commands.create_human with scale as a string"""
    _services_or_skip()
    envelope = dispatch("create_human", {"scale": "0.1"})

    assert envelope["status"] == "error", "a string is not a number"
    assert envelope["error"] == "invalid_params", \
        "the parameter contract refuses this, not the handler: {!r}".format(envelope)


def test_an_unknown_parameter_is_refused_rather_than_ignored():
    """commands.create_human with a misspelled parameter"""
    _services_or_skip()
    envelope = dispatch("create_human", {"macro_details": {}})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params", \
        "a misspelled key that is quietly dropped is a call that succeeds and does the wrong " \
        "thing: {!r}".format(envelope)


def test_mpfb_being_unavailable_refuses_rather_than_half_building():
    """commands.create_human against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("create_human")

        assert envelope["status"] == "error", \
            "a mutating command with no MPFB must refuse: {!r}".format(envelope)
        assert envelope["error"] == "mpfb_unavailable"
        assert state in str(envelope), "the refusal should say which state it found"
