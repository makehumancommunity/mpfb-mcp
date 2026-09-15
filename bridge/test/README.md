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
the ones before it work.

| Module | What it covers |
|--------|----------------|
| `aaa_bridge_test.py` | The harness itself, the shape of the command table, and the start/stop lifecycle. Also the background-mode refusal, which is **the one test that could only be written because the suite runs headless**: `bpy.app.background` is `True` here, so the refusal is directly assertable |
| `bbb_validation_test.py` | The parameter contract, as one table of cases read by one loop. Every case is a failure that would otherwise be silent — `limit=True` paging one entry at a time, `refresh="false"` rescanning the disk, a misspelled key producing a call that succeeds and does nothing |
| `ccc_dispatch_test.py` | What a request becomes before a handler sees it: the order of the checks, the `mpfb_unavailable` precondition with both non-`ok` states supplied rather than waited for, the handshake, and that a handler which raises does not take the server down |
| `ddd_roundtrip_test.py` | **A real request over a real socket.** Client on a thread, dispatch on the main one, which is the add-on's production shape. This is what the headless drive mechanism bought: before it, the transport was the one part of the add-on its own tests could not reach |
| `eee_metadata_test.py` | The two claims kept in step by hand — the reported version against the manifest, and `list_commands` against the table the dispatcher actually uses |

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
   it once. You need write permission to Blender's python directory.

## Why there is a `pytest.ini` here

To pin pytest's rootdir to this directory. Without it pytest adopts the repository's
`pyproject.toml` as its config file, so `[tool.pytest.ini_options]` added there later for an
unrelated reason would silently apply to this run. The two harnesses share nothing on purpose.

## No coverage, for now

MPFB's harness produces a coverage report; this one does not. MPFB activates coverage
through an `a1_coverage.pth` in Blender's `site-packages` that starts `coverage` *before*
the add-on is imported — and no script in the mpfb2 repository creates that file, so
adopting it means writing that step rather than copying it. It is worth having and is
recorded as such in
[../../specifications/testing.md](../../specifications/testing.md); it is deferred to the
effort that first migrates a real command, where there will be something worth measuring.
