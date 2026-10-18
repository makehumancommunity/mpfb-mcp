# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 039's own live check: export copies and exports, made with mpfb-mcp tools, in a windowed Blender.

Run once during the effort. Not part of any repeated harness - see
feature-requests/CLAUDE.md's "Tests" guidance. It drives the **real mpfb-mcp
tools over the real socket**, against a Blender already running with the MPFB
Bridge's server started (``MPFB_BRIDGE_PORT``, default 9877), on the
developer's real install: real asset packs, real garments, a real proxy.

**Every copy and every export goes through mpfb-mcp.** The community
blender-mcp add-on's socket (``BLENDER_MCP_PORT``, default 9876) is used for
what no tool does and a check needs: pointing the bridge's export directory
preference at a scratch directory (and back), reading Blender's own state to
compare an original before and after, posing an original rig, and importing an
exported file to count what came back.

    PYTHONPATH=. .venv/bin/python feature-requests/done/039-exporting-characters/live_check.py

It adds characters to the open scene and leaves them there, and writes its
exports into a temporary directory it prints.

1. **A dressed character** - default rig, hair with a sub-rig, eyebrows, a
   garment, a body proxy, a MakeSkin skin, an expression and a composed unit.
2. **The original is unchanged** by a copy with every option on, and the
   caller's selection is put back; the baked face is reported.
3. **The worst case**: no shape key bake, masks baked under every loaded set
   and the modeling keys, timed against a third of the socket timeout. (With
   ``interpolate`` and a proxy, subdivision cannot be baked as well: MPFB's
   sequence fails on it, and the tool refuses - item 2 checks the refusal.)
4. **Formats x presets**: every pair, each file re-imported and counted.
5. **Masks beside shape keys, per exporter**: what FBX, glTF and USD do.
6. **A generated Rigify character**: posing the original does not move the copy.
7. **The REMOVE loop**: whether removing modifiers while iterating skips one.

Prints PASS/FAIL per check and exits non-zero on any failure.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, REPO_ROOT)

BLENDER_MCP_PORT = int(os.environ.get("BLENDER_MCP_PORT", "9876"))
BRIDGE = "bl_ext.user_default.mpfb_bridge"
SOCKET_TIMEOUT_S = 300.0

ASSETS = (
    ("ponytail01/ponytail01.mhclo", "Hair"),
    ("eyebrow001/eyebrow001.mhclo", "Eyebrows"),
    ("punkduck_female_short_jeans/punkduck_female_short_jeans.mhclo", "Clothes"),
    ("callharvey3d_harvey_proxy1/callharvey3d_harvey_proxy1.proxy", "Proxymeshes"),
)
SKIN = "bobby_03_young_female_hairless/bobby_03_young_female_hairless.mhmat"

FAILURES = []
FINDINGS = {}


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print("[{:s}] {:s}{:s}".format(status, label, "" if not detail else " - " + str(detail)),
          flush=True)
    if not condition:
        FAILURES.append(label)


def ok(envelope, what):
    if envelope.get("status") != "ok":
        raise SystemExit("{:s} failed: {!r}".format(what, envelope))
    return envelope["result"]


def in_blender(code):
    """Run ``code`` in the running Blender through the community add-on; returns its stdout."""
    with socket.create_connection(("127.0.0.1", BLENDER_MCP_PORT), timeout=300) as connection:
        connection.sendall(json.dumps({"type": "execute_code",
                                       "params": {"code": code}}).encode("utf-8"))
        buffer = b""
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            buffer += chunk
            try:
                answer = json.loads(buffer.decode("utf-8"))
                break
            except ValueError:
                continue
    if answer.get("status") != "success":
        raise SystemExit("Blender-side code failed: {!r}".format(answer))
    return answer["result"]["result"]


def blender_json(code):
    """``code``'s last ``print(json.dumps(...))``, ignoring whatever an importer printed first."""
    output = in_blender("import bpy, json\n" + code)
    return json.loads([line for line in output.splitlines() if line.strip()][-1])


STATE_CODE = '''
def family(root):
    out = [root]
    i = 0
    while i < len(out):
        out.extend(o for o in bpy.data.objects if o.parent == out[i])
        i += 1
    return out
def state(o):
    keys = o.data.shape_keys if o.type == "MESH" else None
    return dict(parent=o.parent and o.parent.name,
                modifiers=[(m.name, m.type, getattr(getattr(m, "object", None), "name", None)) for m in o.modifiers],
                keys=None if keys is None else [(k.name, round(k.value, 5)) for k in keys.key_blocks],
                materials=[(m.name, len(m.node_tree.nodes) if m and m.node_tree else 0) for m in getattr(o.data, "materials", []) if m],
                vertices=len(o.data.vertices) if o.type == "MESH" else None,
                groups=len(getattr(o, "vertex_groups", [])), custom=sorted(o.keys()))
b = bpy.data.objects[{name!r}]
root = b.parent or b
active = bpy.context.view_layer.objects.active
print(json.dumps(dict(objects={{o.name: state(o) for o in family(root)}},
                      selected=sorted(o.name for o in bpy.context.view_layer.objects if o.select_get()),
                      active=active and active.name)))
'''


def original_state(name):
    return blender_json(STATE_CODE.format(name=name))


def reimport(path, chosen_format):
    """What Blender's own importer rebuilds from ``path``: meshes, vertices, keys, bones."""
    importer = {"fbx": "bpy.ops.import_scene.fbx", "gltf": "bpy.ops.import_scene.gltf",
                "usd": "bpy.ops.wm.usd_import"}[chosen_format]
    return blender_json('''
before = set(bpy.data.objects)
{importer}(filepath={path!r})
new = [o for o in bpy.data.objects if o not in before]
out = dict(meshes={{}}, bones=[])
for o in new:
    if o.type == "MESH" and not o.name.startswith("Icosphere"):
        k = o.data.shape_keys
        out["meshes"][o.name] = [len(o.data.vertices), 0 if k is None else len(k.key_blocks) - 1]
    elif o.type == "ARMATURE":
        out["bones"].append(len(o.data.bones))
for o in new:
    bpy.data.objects.remove(o, do_unlink=True)
print(json.dumps(out))
'''.format(importer=importer, path=path))


def build_character(tools):
    name = ok(tools["mpfb_create_human"](), "create_human")["basemesh_name"]
    ok(tools["mpfb_add_rig"](name=name, identifier="default"), "add_rig")
    for fragment, object_type in ASSETS:
        added = ok(tools["mpfb_add_asset"](name=name, fragment=fragment, object_type=object_type),
                   "add_asset " + fragment)
        check("equipped " + fragment, added["added"], added["message"][:120])
    ok(tools["mpfb_set_skin"](name=name, fragment=SKIN), "set_skin")
    expressions = ok(tools["mpfb_list_expressions"](), "list_expressions")
    fragment = expressions["expressions"][0]["fragment"] if expressions.get("expressions") else None
    if fragment:
        ok(tools["mpfb_apply_expressions"](name=name, expressions=[
            {"fragment": fragment, "weight": 0.6}]), "apply_expressions")
    ok(tools["mpfb_set_face_units"](name=name, face_units=[
        {"face_unit": "eyeBlinkLeft", "value": 0.7}]), "set_face_units")
    return name, fragment


def everything_on(tools, name, fragment):
    in_blender('''
import bpy
for o in bpy.context.view_layer.objects:
    o.select_set(False)
b = bpy.data.objects[{name!r}]
b.select_set(True)
bpy.context.view_layer.objects.active = b
'''.format(name=name))
    before = original_state(name)
    refused = ok(tools["mpfb_create_export_copy"](
        name=name, subdiv_modifiers="BAKE", load_meta_visemes=True, interpolate=True,
        suffix="_refused"), "create_export_copy refused")
    check("baking the proxy's subdivision after interpolating is refused before copying",
          refused["blocked_by"] == "proxy_cannot_be_baked"
          and original_state(name) == before, refused.get("proxy_modifiers_blocking"))
    started = time.perf_counter()
    copy = ok(tools["mpfb_create_export_copy"](
        name=name, mask_modifiers="BAKE", subdiv_modifiers="KEEP", load_microsoft_visemes=True,
        load_meta_visemes=True, load_arkit_face_units=True, interpolate=True,
        material_type="GAMEENGINE", suffix="_live"), "create_export_copy")
    elapsed = time.perf_counter() - started
    after = original_state(name)
    check("a copy with everything on is created", copy["created"], copy["message"][:300])
    check("the original family is unchanged", before["objects"] == after["objects"],
          [key for key in before["objects"] if before["objects"][key] != after["objects"].get(key)])
    check("the caller's selection and active object are put back",
          (before["selected"], before["active"]) == (after["selected"], after["active"]),
          (after["selected"], after["active"]))
    units = {u["face_unit"] for u in copy["face_baked_into_mesh"]}
    check("the composed unit is named as baked", "eyeBlinkLeft" in units, sorted(units))
    if fragment:
        check("the expression row is named as baked",
              [row["fragment"] for row in copy["expressions_baked_into_mesh"]] == [fragment])
    check("the sub-rig's hair is repaired into the copy",
          any("ponytail01" in entry["source_name"] for entry in copy["copy_repairs"]["objects_copied"]),
          copy["copy_repairs"]["objects_copied"])
    check("every mesh got a GameEngine material", not copy["materials_not_swapped"],
          copy["materials_not_swapped"])
    check("every set loaded in full", all(not s["could_not_load"] for s in copy["shape_keys_loaded"].values()),
          copy["shape_keys_loaded"])
    print("    everything on: {:.2f} s, interpolated onto {!r}".format(elapsed, copy["interpolated_onto"]))
    FINDINGS["everything_on_seconds"] = round(elapsed, 2)
    return copy


def worst_case(tools, name):
    started = time.perf_counter()
    copy = ok(tools["mpfb_create_export_copy"](
        name=name, bake_shapekeys=False, mask_modifiers="BAKE", subdiv_modifiers="KEEP",
        load_microsoft_visemes=True, load_meta_visemes=True, load_arkit_face_units=True,
        interpolate=True, suffix="_worst"), "create_export_copy worst case")
    elapsed = time.perf_counter() - started
    check("the worst case completes", copy["created"], copy["message"][:200])
    print("    worst case: {:.2f} s, {:d} shape keys loaded under the masks".format(
        elapsed, sum(s["loaded_count"] for s in copy["shape_keys_loaded"].values())))
    FINDINGS["worst_case_seconds"] = round(elapsed, 2)
    check("the worst case is under a third of the socket timeout", elapsed < SOCKET_TIMEOUT_S / 3,
          "{:.1f} s".format(elapsed))
    return copy


def formats_and_presets(tools, copy, directory):
    root = copy["copy_root_name"]
    for chosen, engine in (("fbx", "generic"), ("gltf", "generic"), ("usd", "generic"),
                           ("fbx", "unity"), ("fbx", "unreal"), ("gltf", "godot")):
        envelope = tools["mpfb_export_character"](
            name=root, export_name="live_{:s}_{:s}".format(chosen, engine), format=chosen,
            target_engine=engine, overwrite=True)
        result = ok(envelope, "export " + chosen + " " + engine)
        check("{:s}/{:s} written into the preference's directory".format(chosen, engine),
              result["exported"] and result["path_resolved_by"] == "preferences"
              and os.path.dirname(result["path"]) == directory, result.get("message", "")[:200])
        read = reimport(result["path"], chosen)
        FINDINGS["read_back_{:s}_{:s}".format(chosen, engine)] = dict(
            size_bytes=result["size_bytes"], export_ms=result["export_ms"], read=read)
        check("{:s}/{:s} reads back with every mesh and a rig".format(chosen, engine),
              len(read["meshes"]) == sum(1 for o in result["objects_exported"] if o["type"] == "MESH")
              and len(read["bones"]) >= 1, read)
    refused = ok(tools["mpfb_export_character"](name=root, export_name="live_fbx_godot",
                                                format="fbx", target_engine="godot"), "godot fbx")
    check("godot with fbx is refused, naming gltf",
          refused["blocked_by"] == "format_not_supported_by_engine"
          and refused["known_formats_for_target_engine"] == ["gltf"])


def masks_beside_shape_keys(tools, name):
    copy = ok(tools["mpfb_create_export_copy"](
        name=name, bake_shapekeys=False, delete_helpers=False, load_meta_visemes=True,
        suffix="_masked"), "create_export_copy masked")
    for chosen in ("fbx", "gltf", "usd"):
        result = ok(tools["mpfb_export_character"](
            name=copy["copy_root_name"], export_name="masked_" + chosen, format=chosen,
            overwrite=True), "export masked " + chosen)
        body = copy["copy_basemesh_name"]
        check("readiness names the masked body ({:s})".format(chosen),
              body in result["readiness"]["meshes_with_modifiers_beside_shape_keys"])
        read = reimport(result["path"], chosen)
        bodies = {k: v for k, v in read["meshes"].items() if v[0] > 10000}
        FINDINGS["masked_" + chosen] = bodies
        print("    masks beside shape keys, {:s}: {!r}".format(chosen, bodies))


def rigify(tools):
    name = ok(tools["mpfb_create_human"](), "create_human")["basemesh_name"]
    ok(tools["mpfb_add_rig"](name=name, identifier="rigify.human_toes"), "add_rig rigify")
    generated = ok(tools["mpfb_generate_rigify_rig"](name=name), "generate")["rig_object_name"]
    copy = ok(tools["mpfb_create_export_copy"](name=name, bake_shapekeys=False, suffix="_rigify"),
              "create_export_copy rigify")
    retargeted = [(r["object_name"], r["name"]) for r in copy["copy_repairs"]["references_retargeted"]]
    check("Armature PV is retargeted on the Rigify copy",
          any(name_ == "Armature PV" for _o, name_ in retargeted), retargeted)
    drivers = [r for r in copy["copy_repairs"]["references_retargeted"] if r["kind"] == "driver"]
    FINDINGS["rigify_data_drivers_retargeted"] = len(drivers)
    check("the copied armature data's drivers are retargeted", len(drivers) > 0, len(drivers))
    moved = blender_json('''
copy = bpy.data.objects[{body!r}]
rig = bpy.data.objects[{rig!r}]
def vertex():
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    mesh = copy.evaluated_get(dg).to_mesh()
    value = tuple(round(c, 5) for c in mesh.vertices[5000].co)
    copy.evaluated_get(dg).to_mesh_clear()
    return value
before = vertex()
rig.pose.bones["torso"].location = (0.0, 0.3, 0.0)
after = vertex()
rig.pose.bones["torso"].location = (0.0, 0.0, 0.0)
bpy.context.view_layer.update()
print(json.dumps(before != after))
'''.format(body=copy["copy_basemesh_name"], rig=generated))
    check("posing the original Rigify rig does not move the copy", moved is False)


def remove_loop():
    skipped = blender_json('''
me = bpy.data.meshes.new("fr039_probe")
ob = bpy.data.objects.new("fr039_probe", me)
bpy.context.scene.collection.objects.link(ob)
for i, kind in enumerate(["MASK", "MASK", "SUBSURF", "MASK", "MASK"]):
    ob.modifiers.new("m%d" % i, kind)
for m in ob.modifiers:
    if m.type == "MASK":
        ob.modifiers.remove(m)
left = [m.type for m in ob.modifiers]
bpy.data.objects.remove(ob)
bpy.data.meshes.remove(me)
print(json.dumps(left))
''')
    FINDINGS["remove_loop_left"] = skipped
    check("the operator's REMOVE loop skips nothing on this Blender (candidate refuted)",
          skipped == ["SUBSURF"], skipped)


def main():
    from verification import harness  # pylint: disable=import-outside-toplevel
    tools = harness.tools()
    directory = tempfile.mkdtemp(prefix="fr039_live_")
    previous = blender_json(
        "print(json.dumps(bpy.context.preferences.addons[{!r}].preferences.export_directory))".format(BRIDGE))
    in_blender("import bpy\nbpy.context.preferences.addons[{!r}].preferences.export_directory = {!r}\n"
               .format(BRIDGE, directory))
    print("exports go to {:s}".format(directory))
    try:
        name, fragment = build_character(tools)
        copy = everything_on(tools, name, fragment)
        worst_case(tools, name)
        formats_and_presets(tools, copy, directory)
        masks_beside_shape_keys(tools, name)
        rigify(tools)
        remove_loop()
    finally:
        in_blender("import bpy\nbpy.context.preferences.addons[{!r}].preferences.export_directory = {!r}\n"
                   .format(BRIDGE, previous))
    print()
    print(json.dumps(FINDINGS, indent=1))
    print("{:d} failure(s)".format(len(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
