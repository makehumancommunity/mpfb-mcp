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
[../../specifications/testing.md](../../specifications/testing.md); it is not worth having
to measure the five tests that currently exist.
