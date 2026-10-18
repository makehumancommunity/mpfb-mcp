# Bridge unit tests

These tests run **inside a headless Blender**, with pytest called from Blender's own
embedded interpreter, because the add-on under test is a Blender extension and every
assertion needs a real `bpy`.

That is MPFB's arrangement, adopted here on purpose — see
[../../specifications/testing.md](../../specifications/testing.md) for why this repository
now has two test harnesses and where the line between them is. The short version: the tests
under [`../../tests/`](../../tests/) test a package that never imports `bpy` and must keep
running on a machine with no Blender installed, so a test that imports `bpy` cannot live
there. It lives here.

## Running

```bash
BLENDER_EXE=$(which blender) ./execute_tests_headless.bash
```

Set `TEST_MODULE` to narrow the run, relative to this directory. It takes a whole layer or one
module:

```bash
TEST_MODULE=tests/ddd_mutating BLENDER_EXE=$(which blender) ./execute_tests_headless.bash
TEST_MODULE=tests/ccc_reading/list_rigs_test.py BLENDER_EXE=$(which blender) ./execute_tests_headless.bash
```

A narrowed run skips the layers before it, so a failure it reports may be a symptom of one of them.

## What is in here

**Only directories carry a prefix, and each directory is a layer** that assumes every earlier one
passed. The harness runs pytest with `-x`, so the first failure stops the run: a fault in the
add-on's own machinery is reported once, in `aaa_addon/`, rather than as thirty symptoms in thirty
command modules that depend on it. That is MPFB's arrangement (`bbb_services/`, `ccc_data/`), and
the rule is in [testing.md](../../specifications/testing.md#two-harnesses-split-at-the-directory-boundary).
Modules inside a layer are unprefixed, named after their subject — for a command module, the
command name exactly — and their order carries no meaning. A new module goes into the layer that
matches what it tests, never under a new letter.

| Layer | What it holds |
|-------|---------------|
| `aaa_addon/` | The add-on itself, with no MPFB subject |
| `bbb_shared/` | Direct tests of `mpfb_bridge/shared/`, called without going through dispatch. Created by FR 036 for the modules it added, joined by FR 041's frame and classification and FR 042's pose writing; the others are still tested only through the commands that use them |
| `ccc_reading/` | One module per read-only command |
| [`ddd_mutating/`](tests/ddd_mutating/__init__.py) | One module per command that changes a `.blend`, and the cleanup rules that go with that |
| `eee_composite/` | Tests whose claim is about several commands at once |

| Module | What it covers |
|--------|----------------|
| `aaa_addon/bridge_test.py` | The harness itself, the shape of the command table, and the start/stop lifecycle. Also the background-mode refusal, which is **the one test that could only be written because the suite runs headless**: `bpy.app.background` is `True` here, so the refusal is directly assertable |
| `aaa_addon/validation_test.py` | The parameter contract, as one table of cases read by one loop. Every case is a failure that would otherwise be silent — `limit=True` paging one entry at a time, `refresh="false"` rescanning the disk, a misspelled key producing a call that succeeds and does nothing |
| `aaa_addon/dispatch_test.py` | What a request becomes before a handler sees it: the order of the checks, the `mpfb_unavailable` precondition with both non-`ok` states supplied rather than waited for, the handshake, and that a handler which raises does not take the server down |
| `aaa_addon/roundtrip_test.py` | **A real request over a real socket.** Client on a thread, dispatch on the main one, which is the add-on's production shape. This is what the headless drive mechanism bought: before it, the transport was the one part of the add-on its own tests could not reach |
| `aaa_addon/metadata_test.py` | The two claims kept in step by hand — the reported version against the manifest, and `list_commands` against the table the dispatcher actually uses |
| `ccc_reading/list_objects_test.py` | **The first module whose subject is MPFB rather than the transport.** `list_objects` against a real install: the substring type match, an unrecognised type, `""` coerced to `null`, the `_ALL_TYPES` fallback, an object outside the current scene, and the `mpfb_unavailable` refusal. It also sets the three conventions every other command module inherits — build a character with `HumanService.create_human()` and a snapshot-and-delete cleanup, skip with a reason when the install lacks a prerequisite, and supply a broken MPFB rather than waiting for one |
| `ccc_reading/` (the rest) | One module per read-only command, each following `list_objects_test.py`'s conventions |
| `ccc_reading/list_urls_test.py` | `list_urls` against a real MPFB. Here rather than in `aaa_addon/`, although it is the third command declaring `requires_mpfb=False` — since "where do I download MPFB" is asked most often by somebody whose MPFB is not working — because its subject is still what MPFB answers |
| `ccc_reading/get_face_units_test.py` | `get_face_units` against a real MPFB: the zero-for-missing convention (a fresh character and one whose expression targets are simply absent read identically), `known_face_units` covering `ARKIT_FACEUNITS` exactly once, and `shapekey_present` against a shape key added with Blender's own API |
| `ccc_reading/list_expressions_test.py` | `list_expressions` over a redirected expressions tree: the same path in two roots (first root wins, the other reported as `shadowed`), a malformed file (skipped by MPFB, counted here), a file with no name, an empty tree, and the pack probe's cache |
| `ccc_reading/get_expression_test.py` | `get_expression`'s divergence check in its four cases — agreeing, a composed unit, a row whose file is gone, a clamped sum — each set up with MPFB's own functions rather than with `apply_expressions`, and that the 52 live values are not restated |
| `ccc_reading/get_material_settings_test.py` | `get_material_settings` on `_fixtures.material_character()` - procedural eyes, a LAYERED skin, textured MakeSkin hair and garment, a garment with an AO map, each equipped the way a user would - and **agreement with MPFB's serializer, exactly, key for key**. Also every "does not apply" reason, the linked flags on the layered region colours and on `Color2`, `aoMix` for the AO garment, MPFB's own range contradiction, and the trap that an untextured MakeSkin material is identified as `gameengine`. The fixture needs `material_data_roots`, which keeps MPFB's shipped data: its node trees are what procedural eyes are built from |
| `ccc_reading/get_pose_controls_test.py` | `get_pose_controls` on one character per rig family, each built once per module - a generated `human_toes`, a generated `game_engine` (through MPFB's legacy convert-to-Rigify operator, the only way MPFB makes one), a default rig with MPFB's helpers - plus `mixamo` unclassified, the meta-rig and no-rig refusals. The karate session's bones carry the roles it used them for, `hidden_by_default` equals what Rigify hid, and **every parent switch's `parent_names` equals the list in the generated `rig_ui.py`**, which the test searches as data. Reading changes nothing |
| `ccc_reading/get_pose_test.py` | `get_pose` with poses made by the test in plain `bpy`: an IK hand past reach with `IK_Stretch` on (stretched, reaching) and off (`target_unreachable`), a finger master scaled on Y that `get_pose_as_dict()` is asserted to miss, a rig moved and turned 135 degrees, landmarks unmoved by an IK control while the arm is in FK, a posed face behind the default filter, a default rig's helper past reach, `mixamo` unclassified. Reading changes nothing |
| `ddd_mutating/` | **The twenty commands that change a `.blend`**, one module each. Its [`__init__.py`](tests/ddd_mutating/__init__.py) carries the two rules that go with mutating: what a test made the fixture removes however the test ends, and a test that writes outside the `.blend` writes somewhere redirected. `set_face_units_test.py` shows the asset-pack technique: the pack-absent refusal and the `could_not_load` partial-install case redirect MPFB's data roots (`only_these_data_roots`) and force `FaceService`'s installed-probe cache to re-read them, restoring the real answer again before the `with` block exits. FR 027's `apply_expressions_test.py` and `save_expression_test.py` use `_fixtures.expression_library`, which does the same with a small but real `faceunits01` pack and expression files written by MPFB's own `save_expression()` — build the character **before** entering it, since it redirects `mpfb_data` too |
| `ddd_mutating/set_pose_bones_test.py`, `set_pose_switches_test.py`, `reset_pose_test.py` | FR 042's writers on a generated `human_toes` rig moved and turned away from the origin, posed and put back by the test in plain `bpy` (`_fixtures.rest_pose`). Every change kind read back through `get_pose`, and a read-back written back; parent first; symmetry as mirror-equality; every refusal and the exact rollback of a batch that fails after writing; `achieved: false` against a Limit Distance the test adds (Rigify's controls carry no constraints); an animated channel flagged with auto-keying on and no key inserted. **The snap chains against the generated `rig_ui.py`** of `human_toes` and `game_engine`, searched as data, and every snap in both directions under 1 mm on a limb within reach; `raw: true` moving the limb. A reset with switches whose `restore_with`, fed to the other two, puts every channel back within 1e-5 |
| `eee_composite/get_character_summary_test.py` | **The summary dispatched beside each command it summarizes**, on one character rigged, dressed, skinned, morphed and wearing an expression with a unit composed on top, and every shared field asserted equal — twice, inside and outside the expression fixture, since no one moment makes every section interesting. Also the rollup cap (lowered on the module rather than built up to), a generated Rigify rig, the miss, and that reading changes nothing. `ccc_reading/get_macro_details_test.py` gained `macro_drift` in both directions alongside it |
| `bbb_shared/subject_resolution_test.py` | The subject resolver called directly: the three sentences and where each command's phrases go in them, the view layer's active object, a name looked up in the file rather than the scene, and the family walk to a basemesh |
| `bbb_shared/blender_data_test.py` | The three plain Blender reads - every object name in the file, one object's vertex groups, its material slots - on an object the test makes, on `None`, and on an object with none of them |
| `bbb_shared/mpfb_surface_test.py` | How a name MPFB keeps on a service's module is read: off the module of the service named, with the fallback when it is absent, and **not** off the wrong one - `HumanObjectProperties` is asserted to be on `HumanService`'s module and not `ObjectService`'s, the read that would otherwise fail silently. Also the required form over `FaceService`'s vocabulary, and the three coercions |
| `bbb_shared/selection_test.py` | What ten mutating commands put back: the active object and the borrowed object's own selection, after a block that raises as well as one that finishes, and a borrowed object the caller had selected left selected. Also the recorded gap - another object the block selected stays selected |
| `bbb_shared/character_frame_test.py` | The frame on a rig object at the origin and on one moved and turned, round trips between world and frame, rotation as axis and degrees the short way, and **MPFB's convention itself** - forward is local -Y and the `.L` side local +X - asserted on a default rig and a Rigify meta-rig as `add_rig` builds them |
| `bbb_shared/pose_writing_test.py` | The pose writers' shared module on armatures the test builds: snapshot and restore exact to the bit, the parent-first order, locks read the way Rigify reads them (a connected head, 4D locks, a whole-or-nothing quaternion), drivers and keyframes found by data path with a quoted bone name, a restore entry recreating a bone's own channels after its parent moved, and the frame's inverse conversions on a moved, turned, scaled rig |
| `bbb_shared/pose_controls_test.py` | **The drift test for the default-rig table**: its chains and limb segments against `DefaultArmHelpers`, `DefaultLegHelpers` and `DefaultFingerHelpers`, read out of `sys.modules`, and the recorded helper modes against the enums MPFB's panel offers. Every bone of a default rig classified; each arm helper mode with the master grip recognised, with `driven_by` read off the constraints; a recorded helper whose bone is gone reported in `helpers_missing`; helper modes `null` rather than guessed without MPFB's UI module |
| `eee_composite/subject_resolution_test.py` | **All twenty commands that take a subject**, in the three miss states - nothing active, a name that does not exist, a plain object with no basemesh - required to agree on `found`, the subject, how it was resolved and the start of the sentence. Also that the twenty are exactly the commands declaring an optional `name` or a `subject`. The two save commands run with MPFB's user directories redirected, so a regression cannot write |
| `eee_composite/material_settings_roundtrip_test.py` | FR 040's primary goal across four commands: settings written, saved as a preset, loaded as a new character with clothes, and read back **exactly** equal. Also the ordering the request asked for both ways - an alternative material then a tint keeps both, a tint then an alternative material loses the tint |
| `eee_composite/expression_divergence_test.py` | The three expression-aware commands asked about one character and required to agree, then the compose-save-apply round trip across them |

**What this suite cannot establish** is that the *timer-driven* path answers the same as the
blocking one, because there is no event loop here to drive a timer. That comparison belongs
to a feature request's own live check.

## Prerequisites

Two:

1. The MPFB Bridge add-on must be **installed** in one of that Blender's extension
   repositories, with `realpath()` of its directory pointing at `bridge/mpfb_bridge` in a
   source clone. A symlink is the usual way:

   ```bash
   ln -s "$PWD/bridge/mpfb_bridge" ~/.config/blender/<version>/extensions/user_default/mpfb_bridge
   ```

   It does **not** need to be enabled. MPFB's harness requires that, which is fair for MPFB —
   a developer's daily driver, enabled once, deliberately. Requiring it here would mean leaving
   a listening-socket add-on permanently enabled in your preferences as a side effect of running
   tests, so [`test_headless.py`](test_headless.py) enables it for that process only and saves
   nothing.

2. pytest must be installed into Blender's bundled Python. Open
   [`run_to_install_pytest.py`](run_to_install_pytest.py) in Blender's script editor and run
   it once. You need write permission to Blender's python directory. It installs `coverage`
   too, and the `.pth` that starts it — see [Coverage](#coverage); neither is needed to run
   the tests.

## Why there is a `pytest.ini` here

To pin pytest's rootdir to this directory. Without it pytest adopts the repository's
`pyproject.toml` as its config file, so `[tool.pytest.ini_options]` added there later for an
unrelated reason would silently apply to this run. The two harnesses share nothing on purpose.

## Coverage

`execute_tests_headless.bash` writes an HTML and a JSON report into `coverage/` when Blender's own
Python can produce one. The mechanism is MPFB's: `COVERAGE_PROCESS_START` names
[`.coveragerc`](.coveragerc), and an `a1_coverage.pth` in Blender's `site-packages` starts coverage
*before* the add-on is imported — without which every `class` and `def` line in it counts as
missed, since the module was executed before measurement began. No script in the mpfb2 repository
creates that `.pth`, so [`run_to_install_pytest.py`](run_to_install_pytest.py) writes it, and three
things about that are deliberate:

- **It is inert unless the environment asks for coverage**, and it survives a Blender whose Python
  has no `coverage` installed. A bare `import coverage` in a `.pth` would break every start of that
  Blender the day somebody uninstalls it.
- **An existing `a1_coverage.pth` is left alone.** MPFB's own harness installs one, and
  overwriting somebody's working arrangement to install an equivalent would be rude and invisible.
- **A missing coverage tool cannot fail a passing suite.** The report is produced after Blender
  exits, and the script's exit code is the tests'.

Nothing is excluded by pattern, so the uncovered lines in `timer.py` and `ui.py` show up as what
they are: the parts a headless suite cannot reach. FR 030 measured 77% overall with them in.
