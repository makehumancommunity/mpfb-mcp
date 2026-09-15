import pytest, os, sys, bpy

# Run from inside Blender's own embedded interpreter, never from a system pytest:
# every test below needs a real `bpy`, and the add-on under test is a Blender
# extension that only exists once Blender has loaded it.

_PACKAGE = "mpfb_bridge"


def ensure_addon_enabled():
    """Enable the add-on under test, for this process only.

    MPFB's harness assumes the add-on it tests is already enabled, which is fair
    for MPFB: it is the developer's daily driver and enabling it is something
    they did once, deliberately. The bridge is not that. Requiring a developer to
    enable it in the GUI and save their preferences before a headless run would
    make the prerequisite list longer than the test suite, and would leave a
    listening-socket add-on permanently enabled in their configuration as a side
    effect of running tests.

    So the harness enables it here instead. Nothing is saved: this is a `-b` run
    that exits, the user's preferences on disk are untouched, and the add-on's
    server is not started - enabling only registers classes.
    """
    already = [name for name in sys.modules if name.endswith(_PACKAGE)]
    if already:
        return already[0]

    # The module name depends on which extension repository the add-on was
    # installed into, exactly as it does for MPFB, so ask Blender rather than
    # guessing one. A plain `mpfb_bridge` covers a legacy scripts/addons install.
    candidates = ["bl_ext.{:s}.{:s}".format(repo.module, _PACKAGE)
                  for repo in bpy.context.preferences.extensions.repos]
    candidates.append(_PACKAGE)

    for candidate in candidates:
        try:
            bpy.ops.preferences.addon_enable(module=candidate)
        except Exception:  # pylint: disable=broad-except
            continue
        if candidate in bpy.context.preferences.addons:
            print("Enabled the add-on under test as " + candidate)
            return candidate

    raise SystemExit(
        "Could not enable the MPFB Bridge add-on. It must be installed in one of this Blender's "
        "extension repositories, with realpath() pointing at bridge/mpfb_bridge in a source "
        "clone - a symlink is the usual way. Tried: " + ", ".join(candidates))


ensure_addon_enabled()

tests = os.path.abspath(os.path.join(os.path.dirname(__file__), "tests"))

if "TEST_MODULE" in os.environ:
    tests = os.path.abspath(os.path.join(tests, "..", os.environ["TEST_MODULE"]))
    print("TEST_MODULE is set: " + tests)

# -p no:cacheprovider keeps a .pytest_cache out of whichever directory pytest
# decides is the rootdir, which is the repository root rather than this one.
retcode = pytest.main(["-v", "--capture=tee-sys", "-x", "-p", "no:cacheprovider", tests])
if retcode:
    print("Unit tests have finished with error code " + str(retcode) + ". See console output for results.")
else:
    print("Unit tests have finished without error. See console output for results.")

# Blender's exit code is otherwise 0 whatever pytest thought, which would make a
# failing run look like a passing one to anything scripting this.
sys.exit(1 if retcode else 0)
