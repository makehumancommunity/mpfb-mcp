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

Set `TEST_MODULE` to narrow the run to one file.

## What is in here

Modules are prefixed alphabetically to force order, as MPFB does it, and each one assumes
the ones before it work. **Since [FR 032](../../feature-requests/done/032-creation-and-modification-migrated/README.md)
the prefix also goes on a *directory*** — that effort added fourteen modules against the eleven
letters left before `zzz_`, and prefixing directories is MPFB's own way out (`bbb_services/`,
`ccc_data/`). Inside one, modules need no prefix of their own.

| Module | What it covers |
|--------|----------------|
| `aaa_bridge_test.py` | The harness itself, the shape of the command table, and the start/stop lifecycle. Also the background-mode refusal, which is **the one test that could only be written because the suite runs headless**: `bpy.app.background` is `True` here, so the refusal is directly assertable |
| `bbb_validation_test.py` | The parameter contract, as one table of cases read by one loop. Every case is a failure that would otherwise be silent — `limit=True` paging one entry at a time, `refresh="false"` rescanning the disk, a misspelled key producing a call that succeeds and does nothing |
| `ccc_dispatch_test.py` | What a request becomes before a handler sees it: the order of the checks, the `mpfb_unavailable` precondition with both non-`ok` states supplied rather than waited for, the handshake, and that a handler which raises does not take the server down |
| `ddd_roundtrip_test.py` | **A real request over a real socket.** Client on a thread, dispatch on the main one, which is the add-on's production shape. This is what the headless drive mechanism bought: before it, the transport was the one part of the add-on its own tests could not reach |
| `eee_metadata_test.py` | The two claims kept in step by hand — the reported version against the manifest, and `list_commands` against the table the dispatcher actually uses |
| `fff_list_objects_test.py` | **The first module here whose subject is MPFB rather than the transport.** `list_objects` against a real install: the substring type match, an unrecognised type, `""` coerced to `null`, the `_ALL_TYPES` fallback, an object outside the current scene, and the `mpfb_unavailable` refusal. It also sets the three conventions the remaining twenty-three commands inherit — build a character with `HumanService.create_human()` and a snapshot-and-delete cleanup, skip with a reason when the install lacks a prerequisite, and supply a broken MPFB rather than waiting for one |
| `ggg_`…`ooo_` | One module per command FR 031 migrated, each following `fff_`'s conventions |
| `ppp_mutating/` | **The fourteen commands that change a `.blend`**, one module each, unprefixed among themselves. A directory rather than fourteen more prefixed files, and its [`__init__.py`](tests/ppp_mutating/__init__.py) carries the two rules that go with mutating: what a test made the fixture removes however the test ends, and a test that writes outside the `.blend` writes somewhere redirected. `set_face_units_test.py` is the newest: the vocabulary refusal needs no asset pack, but the pack-absent refusal and the `could_not_load` partial-install case redirect MPFB's data roots (`only_these_data_roots`) and force `FaceService`'s installed-probe cache to re-read them, restoring the real answer again before the `with` block exits |
| `qqq_list_urls_test.py` | `list_urls` against a real MPFB. A flat sibling rather than one of the fourteen, because it is **read-only** — and the third command declaring `requires_mpfb=False`, since "where do I download MPFB" is asked most often by somebody whose MPFB is not working |
| `rrr_get_face_units_test.py` | `get_face_units` against a real MPFB: the zero-for-missing convention (a fresh character and one whose expression targets are simply absent read identically), `known_face_units` covering `ARKIT_FACEUNITS` exactly once, and `shapekey_present` against a shape key added with Blender's own API |

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
