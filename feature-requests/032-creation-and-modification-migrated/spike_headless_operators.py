# SPDX-License-Identifier: GPL-3.0-or-later

"""
The spike FR 032's Architecture section asks for, run before anything migrated.

**The question.** Three of the fourteen commands this effort migrates drive
``bpy.ops`` somewhere below them - ``generate_rigify_rig`` unmistakably, and
``add_rig`` and ``add_asset`` by way of MPFB - and operators in
``blender --background`` fail for context reasons that have nothing to do with
this project's code. Requirement 6 asks for fourteen bridge test modules in a
headless Blender; whether three of them can exist at all is what this script
answers, and it is a day's work to find out at the start and a disaster to find
out at the end.

**How to run it**::

    /path/to/blender -b -noaudio -P spike_headless_operators.py

It needs MPFB installed **and enabled** in that Blender. Nothing else: it builds
its own character, adds its own rig, writes its own asset tree, and deletes
every object it created on the way out. It changes nothing on disk outside a
temporary directory it removes.

**What it prints** is one line per question, each ``PASS``/``FAIL``/``SKIP``
with the exception text where there is one, and a summary block the feature
request can quote. It is a probe, not a test: it asserts nothing and returns 0
whatever it finds, because a ``FAIL`` here is an answer rather than an error.
"""

import os
import sys
import tempfile
import traceback

import bpy

FINDINGS = []


def report(question, outcome, detail=""):
    FINDINGS.append((question, outcome, detail))
    print("[{:4s}] {:s}{:s}".format(
        outcome, question, "" if not detail else "\n         " + detail.replace("\n", "\n         ")))


def probe(question):
    """Decorator running one probe and recording whatever it did."""
    def wrap(function):
        try:
            outcome, detail = function()
        except Exception:  # pylint: disable=broad-except
            report(question, "FAIL", traceback.format_exc(limit=6).strip())
            return None
        report(question, outcome, detail)
        return None
    return wrap


def mpfb_services():
    """MPFB's SERVICES dict, the way the bridge finds it."""
    candidates = sorted(name for name in list(sys.modules) if name.endswith("mpfb"))
    if not candidates:
        return None
    contextual = getattr(sys.modules[candidates[0]], "MPFB_CONTEXTUAL_INFORMATION", None)
    if not isinstance(contextual, dict):
        return None
    services = contextual.get("SERVICES")
    return services if isinstance(services, dict) else None


def write(path, content=""):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


print("=" * 78)
print("FR 032 spike: what MPFB can do in a Blender with no window")
print("Blender {:s}, background={!r}".format(bpy.app.version_string, bpy.app.background))
print("=" * 78)

SERVICES = mpfb_services()
if SERVICES is None:
    report("MPFB is loaded and initialized", "FAIL",
           "No module ending in 'mpfb' published a SERVICES dict. Enable MPFB and re-run.")
    print("\nNothing else can be probed without MPFB.")
    sys.exit(0)

report("MPFB is loaded and initialized", "PASS",
       "services: " + ", ".join(sorted(SERVICES)[:6]) + ", ...")

HumanService = SERVICES["HumanService"]
ObjectService = SERVICES["ObjectService"]
RigService = SERVICES["RigService"]
SystemService = SERVICES["SystemService"]

BEFORE = set(blender_object.name for blender_object in bpy.data.objects)


@probe("Q0: bpy.context.mode is readable and is OBJECT in background mode")
def _q0():
    return ("PASS", "bpy.context.mode = {!r}".format(bpy.context.mode))


@probe("Q1: HumanService.create_human() builds a basemesh headless")
def _q1():
    basemesh = HumanService.create_human()
    globals()["BASEMESH"] = basemesh
    return ("PASS", "{:s}, {:d} vertices".format(basemesh.name, len(basemesh.data.vertices)))


@probe("Q2: SystemService.check_for_rigify() - is Rigify enabled here?")
def _q2():
    available = SystemService.check_for_rigify()
    return ("PASS" if available else "SKIP",
            "check_for_rigify() = {!r}".format(available))


@probe("Q3: Rigify can be enabled from this script if it was not")
def _q3():
    if SystemService.check_for_rigify():
        return ("SKIP", "already enabled, nothing to prove")
    try:
        bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.rigify")
    except Exception:  # pylint: disable=broad-except
        bpy.ops.preferences.addon_enable(module="rigify")
    return ("PASS" if SystemService.check_for_rigify() else "FAIL",
            "check_for_rigify() after enabling = {!r}".format(SystemService.check_for_rigify()))


@probe("Q4: add_rig - RigService adds a standard rig headless (drives bpy.ops)")
def _q4():
    basemesh = globals().get("BASEMESH")
    if basemesh is None:
        return ("SKIP", "no basemesh")
    ObjectService.activate_blender_object(basemesh)
    armature = HumanService.add_builtin_rig(basemesh, "default", import_weights=True)
    globals()["STANDARD_RIG"] = armature
    return ("PASS", "{!r}, bones={:d}".format(
        getattr(armature, "name", armature), len(armature.data.bones)))


@probe("Q5: add_rig - the rigify meta rig path headless")
def _q5():
    if not SystemService.check_for_rigify():
        return ("SKIP", "Rigify is not enabled")
    standard = globals().get("STANDARD_RIG")
    if standard is not None:
        # One rig at a time: the second would be added beside the first.
        bpy.data.objects.remove(standard, do_unlink=True)
        globals()["STANDARD_RIG"] = None
    basemesh = globals().get("BASEMESH")
    if basemesh is None:
        return ("SKIP", "no basemesh")
    ObjectService.activate_blender_object(basemesh)
    meta = HumanService.add_builtin_rig(basemesh, "rigify.human", import_weights=True)
    globals()["META_RIG"] = meta
    return ("PASS", "{!r}, identify_rig={!r}".format(
        getattr(meta, "name", meta), RigService.identify_rig(meta)))


@probe("Q6: generate_rigify_rig - RigService.generate_rigify_rig() headless")
def _q6():
    meta = globals().get("META_RIG")
    if meta is None:
        return ("SKIP", "no meta rig to generate from")
    generated = RigService.generate_rigify_rig(meta, name="", meta_rig_action="hide")
    globals()["GENERATED_RIG"] = generated
    if generated is None:
        return ("FAIL", "generate_rigify_rig() returned None - Rigify rejected the meta rig")
    return ("PASS", "{:s}, identify_rig={!r}, active after = {!r}".format(
        generated.name, RigService.identify_rig(generated),
        getattr(bpy.context.view_layer.objects.active, "name", None)))


@probe("Q7: add_asset - HumanService.add_mhclo_asset() headless (import + fit)")
def _q7():
    basemesh = globals().get("BASEMESH")
    if basemesh is None:
        return ("SKIP", "no basemesh")

    # A real MHCLO, small but structurally valid: three vertices fitted to
    # basemesh vertices, which is what MPFB's importer and fitter read.
    directory = tempfile.mkdtemp(prefix="mpfb-spike-")
    globals()["ASSET_DIR"] = directory
    mhclo = os.path.join(directory, "spike.mhclo")
    write(mhclo, "\n".join([
        "# MakeHuman clothes file",
        "name spike",
        "obj_file spike.obj",
        "x_scale 5399 11998 1.0000",
        "y_scale 5399 11998 1.0000",
        "z_scale 5399 11998 1.0000",
        "verts 0",
        "0 1 2 0.3 0.3 0.4 0 0 0",
        "3 4 5 0.3 0.3 0.4 0 0 0",
        "6 7 8 0.3 0.3 0.4 0 0 0",
        "",
    ]))
    write(os.path.join(directory, "spike.obj"), "\n".join([
        "v 0.0 0.0 0.0",
        "v 1.0 0.0 0.0",
        "v 0.0 1.0 0.0",
        "f 1 2 3",
        "",
    ]))

    ObjectService.activate_blender_object(basemesh)
    asset_object = HumanService.add_mhclo_asset(mhclo, basemesh, asset_type="Clothes")
    if asset_object is None:
        return ("FAIL", "add_mhclo_asset() returned None")
    globals()["ASSET_OBJECT"] = asset_object
    return ("PASS", "equipped {:s}, {:d} vertices after fitting".format(
        asset_object.name, len(asset_object.data.vertices)))


@probe("Q8: set_skin - MakeSkin material creation headless")
def _q8():
    basemesh = globals().get("BASEMESH")
    if basemesh is None:
        return ("SKIP", "no basemesh")
    material_service = SERVICES["MaterialService"]
    material = material_service.create_empty_material("spike-skin", basemesh)
    return ("PASS", "created {!r}, slots={:d}".format(
        getattr(material, "name", material), len(basemesh.material_slots)))


@probe("Q9: HumanService.refit() headless, on a character with no assets")
def _q9():
    spare = HumanService.create_human()
    globals().setdefault("EXTRA_OBJECTS", []).append(spare)
    HumanService.refit(spare)
    return ("PASS", "refit() returned without raising")


@probe("Q9b: refit() with a garment whose MHCLO is outside every data root")
def _q9b():
    basemesh = globals().get("BASEMESH")
    if basemesh is None or globals().get("ASSET_OBJECT") is None:
        return ("SKIP", "no equipped asset to refit")
    try:
        HumanService.refit(basemesh)
    except IOError as error:
        # Not a headless finding and not a defect: ClothesService.fit_clothes_to_human()
        # re-reads the garment's MHCLO through AssetService, which searches the
        # data roots - so a garment equipped from a path outside them cannot be
        # refitted. A fixture asset tree must therefore be a *redirected data
        # root*, not merely a temporary directory.
        return ("SKIP", "IOError, and it is the fixture's doing rather than headless mode: "
                        + str(error))
    return ("PASS", "refit() returned without raising")


@probe("Q10: HumanService.serialize_to_json_file() writes a preset headless")
def _q10():
    basemesh = globals().get("BASEMESH")
    if basemesh is None:
        return ("SKIP", "no basemesh")
    directory = tempfile.mkdtemp(prefix="mpfb-spike-presets-")
    globals()["PRESET_DIR"] = directory
    path = os.path.join(directory, "human.spike.json")
    HumanService.serialize_to_json_file(basemesh, path, save_clothes=True)
    return ("PASS" if os.path.exists(path) else "FAIL",
            "{:s}, {:d} bytes".format(path, os.path.getsize(path) if os.path.exists(path) else 0))


@probe("Q11: HumanService.deserialize_from_json_file() rebuilds one headless")
def _q11():
    directory = globals().get("PRESET_DIR")
    if directory is None:
        return ("SKIP", "no preset was written")
    path = os.path.join(directory, "human.spike.json")
    settings = HumanService.get_default_deserialization_settings()
    rebuilt = HumanService.deserialize_from_json_file(path, settings)
    if rebuilt is not None:
        globals().setdefault("EXTRA_OBJECTS", []).append(rebuilt)
    return ("PASS" if rebuilt is not None else "FAIL",
            "rebuilt {!r}".format(getattr(rebuilt, "name", rebuilt)))


print()
print("=" * 78)
print("SUMMARY")
for question, outcome, _detail in FINDINGS:
    print("  {:4s}  {:s}".format(outcome, question))
print("=" * 78)

# Leave the .blend as it was found. This is a background run that exits without
# saving, so it costs nothing - but a probe that tidies up is one that can be
# re-run against a real file if somebody ever wants to.
for blender_object in list(bpy.data.objects):
    if blender_object.name not in BEFORE:
        bpy.data.objects.remove(blender_object, do_unlink=True)
for key in ("ASSET_DIR", "PRESET_DIR"):
    directory = globals().get(key)
    if directory and os.path.isdir(directory):
        for root, _dirs, files in os.walk(directory, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
        os.rmdir(directory)

sys.exit(0)
