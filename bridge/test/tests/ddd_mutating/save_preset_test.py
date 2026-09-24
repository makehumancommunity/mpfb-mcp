"""
``save_preset`` against a real MPFB: the first command here that writes a file.

**Every test in this module redirects MPFB's user config directory**, and that
is not a convenience. A bridge test that wrote into the developer's real config
directory would leave presets in their MPFB panel as a side effect of running a
suite, and a *failing* test is the one most likely to leave one. ``user_config``
is the field, ``redirected_locations()`` is the mechanism, and it is undone in a
``finally``.

What lives here and could live nowhere else:

- **The four properties of a tool that writes outside the ``.blend``.** A name
  and never a path; the name rule shared with ``list_presets``; ``overwrite``
  defaulting to false; and the absolute path in every answer, refusal included.
- **A character MPFB refuses to serialize is a refusal here first.**
  ``serialize_to_json_string()`` raises for a mesh that is not marked as a human
  project, and checking ``is_human_project`` beforehand is what turns that into
  an answer.
- **What was written is read back from the file.** ``contents`` is parsed from
  the JSON that is now on disk rather than assembled from the scene, which is
  the only version of the claim that can be wrong in the same way the file is.
"""

import json
import os

import bpy

from .._fixtures import Character as _Character
from .._fixtures import dispatch
from .._fixtures import linked_plain_object
from .._fixtures import redirected_locations
from .._fixtures import result as _fixture_result
from .._fixtures import services_or_skip as _services_or_skip
from .._fixtures import supplied_resolution


def _result(params=None):
    return _fixture_result("save_preset", params)


def _config(root):
    """A config directory of this test's own, created."""
    confdir = os.path.join(str(root), "config")
    os.makedirs(confdir, exist_ok=True)
    return confdir


def test_a_character_is_written_and_the_answer_names_the_file():
    """commands.save_preset on a character create_human() made"""
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "save-preset-simple"))
    with _Character() as character:
        with redirected_locations(services, user_config=confdir):
            result = _result({"preset_name": "alice", "name": character.basemesh.name})

        assert result["performed"] is True, result["message"]
        assert result["saved"] is True
        assert result["path"] == os.path.join(confdir, "human.alice.json"), \
            "a preset is always human.<name>.json in the config directory, got {!r}".format(
                result["path"])
        assert os.path.isfile(result["path"]), "the file must really be there"
        assert result["size_bytes"] > 0
        assert result["overwrote"] is False
        assert result["file_before"] is None


def test_the_reported_contents_are_read_back_from_the_file():
    """commands.save_preset reports what is on disk, not what was in the scene"""
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "save-preset-contents"))
    with _Character() as character:
        with redirected_locations(services, user_config=confdir):
            result = _result({"preset_name": "bob", "name": character.basemesh.name})

        with open(result["path"], "r", encoding="utf-8") as handle:
            on_disk = json.load(handle)

        assert result["contents"] is not None
        assert result["contents"]["rig"] == (on_disk.get("rig") or None)
        assert result["contents"]["clothes"] == list(on_disk.get("clothes") or [])
        assert result["contents"]["target_count"] == len(on_disk.get("targets") or [])


def test_an_existing_preset_is_not_replaced_unless_asked():
    """commands.save_preset twice, without overwrite

    There is no undo for a file across this socket, which is why the default
    refuses.
    """
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "save-preset-overwrite"))
    with _Character() as character:
        with redirected_locations(services, user_config=confdir):
            first = _result({"preset_name": "carol", "name": character.basemesh.name})
            refused = _result({"preset_name": "carol", "name": character.basemesh.name})

            assert refused["saved"] is False
            assert refused["blocked_by"] == "preset_exists"
            assert refused["performed"] is False
            assert refused["path"] == first["path"], \
                "the path is on every refusal too - the caller cannot see the directory"
            assert refused["file_before"]["size_bytes"] == first["size_bytes"]

            allowed = _result({"preset_name": "carol", "name": character.basemesh.name,
                               "overwrite": True})

        assert allowed["saved"] is True
        assert allowed["overwrote"] is True
        assert allowed["file_before"] is not None


def test_a_mesh_that_is_not_a_human_project_is_refused_rather_than_raising():
    """commands.save_preset on a mesh tagged as a basemesh but not built by MPFB

    ``serialize_to_json_string()`` raises for exactly this, and an imported or
    hand-built mesh tagged as a basemesh looks like it.
    """
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "save-preset-notahuman"))
    plain = bpy.data.objects.new("NotAHuman", bpy.data.meshes.new("NotAHumanMesh"))
    bpy.context.scene.collection.objects.link(plain)
    try:
        import sys  # pylint: disable=import-outside-toplevel
        objectservice_module = sys.modules[services["ObjectService"].__module__]
        objectservice_module.GeneralObjectProperties.set_value(
            "object_type", "Basemesh", entity_reference=plain)

        with redirected_locations(services, user_config=confdir):
            envelope = dispatch("save_preset", {"preset_name": "nothuman", "name": "NotAHuman"})

        assert envelope["status"] == "ok", \
            "MPFB would have raised; this must answer instead: {!r}".format(envelope)
        result = envelope["result"]
        assert result["saved"] is False
        assert result["blocked_by"] == "not_a_human_project"
        assert not os.path.exists(os.path.join(confdir, "human.nothuman.json")), \
            "nothing may have been written"
    finally:
        bpy.data.objects.remove(plain, do_unlink=True)


def test_a_name_that_could_become_a_path_is_refused_by_the_last_statement_before_open():
    """commands.save_preset with a name MPFB's own panel would accept

    mpfb-mcp refuses this before a request is built, so reaching the command
    means something else spoke to this socket - which is exactly why the rule is
    here too. A listening socket is reachable by anything on this machine.
    """
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "save-preset-badname"))
    with _Character() as character:
        for name in ("../escape", "a/b", ".hidden"):
            with redirected_locations(services, user_config=confdir):
                envelope = dispatch("save_preset", {"preset_name": name,
                                                    "name": character.basemesh.name})

            assert envelope["status"] == "ok", \
                "a bad name is an answer, not a failure: {!r}".format(envelope)
            assert envelope["result"]["blocked_by"] == "invalid_name", \
                "{!r} should have been refused".format(name)
            assert envelope["result"]["saved"] is False


def test_a_rigged_character_records_the_rig_by_identifier():
    """commands.save_preset on a character carrying MPFB's standard rig"""
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "save-preset-rigged"))
    with _Character() as character:
        services["ObjectService"].activate_blender_object(character.basemesh)
        rig = services["HumanService"].add_builtin_rig(
            character.basemesh, "default", import_weights=True)

        with redirected_locations(services, user_config=confdir):
            result = _result({"preset_name": "rigged", "name": character.basemesh.name})

        assert result["saved"] is True, result["message"]
        assert result["rig_object_name"] == rig.name
        assert result["rig_identified_as"], "identify_rig() should have named it"
        assert result["rig_saved_as"], "and the preset should record an identifier"


def test_the_subject_may_be_any_object_in_the_family():
    """commands.save_preset addressed by the rig rather than the basemesh"""
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "save-preset-family"))
    with _Character() as character:
        services["ObjectService"].activate_blender_object(character.basemesh)
        rig = services["HumanService"].add_builtin_rig(
            character.basemesh, "default", import_weights=True)

        with redirected_locations(services, user_config=confdir):
            result = _result({"preset_name": "byrig", "name": rig.name})

        assert result["saved"] is True
        assert result["subject_name"] == rig.name
        assert result["basemesh_name"] == character.basemesh.name


def test_an_unresolvable_subject_is_an_answer_carrying_the_path_anyway():
    """commands.save_preset naming an object that does not exist"""
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "save-preset-nosubject"))
    with redirected_locations(services, user_config=confdir):
        result = _result({"preset_name": "nowhere", "name": "no-such-object-anywhere"})

    assert result["saved"] is False
    assert result["blocked_by"] == "subject_not_found"
    assert result["path"] == os.path.join(confdir, "human.nowhere.json"), \
        "which file this would have been is the first thing a caller needs"
    assert result["preset_name"] == "nowhere"
    assert "name" not in result, "the preset is preset_name in the answer too"


def test_a_preset_passed_as_name_is_pointed_at_preset_name():
    """commands.save_preset where ``name`` looks like the preset it used to be (FR 037).

    ``name`` changed meaning rather than being retired, so a caller still using
    the old spelling reaches this command. The sentence must say where the preset
    goes - but only when no object has that name at all, since an object that
    exists and belongs to no character is a different mistake.
    """
    services = _services_or_skip()
    confdir = _config(os.path.join(bpy.app.tempdir, "save-preset-oldspelling"))
    with redirected_locations(services, user_config=confdir):
        missing = _result({"preset_name": "alice", "name": "alice"})
        plain = linked_plain_object("PlainNotACharacter")
        try:
            unrelated = _result({"preset_name": "alice", "name": plain.name})
        finally:
            bpy.data.objects.remove(plain, do_unlink=True)

    assert missing["blocked_by"] == "subject_not_found"
    assert "pass it as preset_name" in missing["message"]
    assert unrelated["blocked_by"] == "subject_not_found"
    assert "preset_name" not in unrelated["message"]


def test_the_preset_name_is_required_by_the_contract():
    """commands.save_preset with no preset_name at all"""
    _services_or_skip()
    envelope = dispatch("save_preset", {})

    assert envelope["status"] == "error"
    assert envelope["error"] == "invalid_params"
    assert "preset_name" in envelope["message"]


def test_mpfb_being_unavailable_refuses_rather_than_writing():
    """commands.save_preset against a Blender with no usable MPFB"""
    for state in ("absent", "not_initialized"):
        with supplied_resolution(state):
            envelope = dispatch("save_preset", {"preset_name": "anything"})

        assert envelope["status"] == "error"
        assert envelope["error"] == "mpfb_unavailable"
