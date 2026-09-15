#!/usr/bin/bash

# Run the bridge's tests in a headless Blender. Modelled on
# ../../../mpfb2/test/execute_tests_headless.bash, minus the coverage plumbing:
# MPFB activates coverage through an `a1_coverage.pth` that no script in that
# repository actually creates, and wiring one up here to measure a handful of
# tests would be work without a reader. See ../../specifications/testing.md.
#
# Prerequisites, both inherited from MPFB's harness:
#   - The MPFB Bridge add-on must be installed and enabled in this Blender, and
#     realpath() of its extension directory must point at bridge/mpfb_bridge in a
#     source clone (a symlink is the usual way).
#   - pytest must be installed into Blender's own bundled Python. Run
#     run_to_install_pytest.py from Blender's script editor once to do that.

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

if [ -z "$BLENDER_EXE" ]; then
  echo "Must set the BLENDER_EXE environment variable to point at the blender executable"
  exit 1
fi

# --factory-startup would disable the extension under test, so the user's own
# configuration is what runs. -noaudio keeps a headless box from complaining.
cd "$SCRIPT_DIR" && "$BLENDER_EXE" -b -noaudio -P "$SCRIPT_DIR/test_headless.py"
