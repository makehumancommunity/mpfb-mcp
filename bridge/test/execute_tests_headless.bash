#!/usr/bin/bash

# Run the bridge's tests in a headless Blender, with coverage when Blender's own
# Python has it. Modelled on MPFB's
# https://github.com/makehumancommunity/mpfb2/blob/master/test/execute_tests_headless.bash.
#
# Prerequisites, both inherited from MPFB's harness:
#   - The MPFB Bridge add-on must be installed in this Blender, and realpath()
#     of its extension directory must point at bridge/mpfb_bridge in a source
#     clone (a symlink is the usual way). It need not be enabled: test_headless.py
#     enables it for this process only.
#   - pytest must be installed into Blender's own bundled Python. Run
#     run_to_install_pytest.py from Blender's script editor once to do that; it
#     also installs coverage and writes the a1_coverage.pth that starts it.
#
# Coverage is optional and its absence is not an error. The .pth does nothing
# unless COVERAGE_PROCESS_START names a configuration file, which is exported
# below; if the .pth was never installed, nothing measures anything and the run
# is otherwise identical.

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

if [ -z "$BLENDER_EXE" ]; then
  echo "Must set the BLENDER_EXE environment variable to point at the blender executable"
  exit 1
fi

# Previous data, base file and every parallel file. Stale .coverage.* files are
# combined into the next report and would silently credit deleted code.
rm -rf "$SCRIPT_DIR/coverage"
rm -f "$SCRIPT_DIR/.coverage"
rm -f "$SCRIPT_DIR"/.coverage.*

# Starts coverage before Blender imports the add-on, through the .pth in
# Blender's site-packages. Without this, every class and def line in the add-on
# is reported as missed, because the module was executed before measurement began.
export COVERAGE_PROCESS_START="$SCRIPT_DIR/.coveragerc"
# Pin where the .coverage.<host>.<pid> files land, so they are beside the config
# rather than in whatever directory Blender thinks it is in.
export COVERAGE_FILE="$SCRIPT_DIR/.coverage"

# --factory-startup would disable the extension under test, so the user's own
# configuration is what runs. -noaudio keeps a headless box from complaining.
cd "$SCRIPT_DIR" && "$BLENDER_EXE" -b -noaudio -P "$SCRIPT_DIR/test_headless.py"
TEST_RESULT=$?

# Blender's Python, which is the only interpreter that has the data: coverage
# ran inside Blender's process and wrote its files at exit.
BLENDER_PYTHON=$(find "$(dirname "$BLENDER_EXE")" -maxdepth 5 -name "python3*" -type f -executable 2>/dev/null | grep -E "bin/python3(\.[0-9]+)?$" | head -1)

if ls "$SCRIPT_DIR"/.coverage.* > /dev/null 2>&1 && [ -n "$BLENDER_PYTHON" ]; then
  cd "$SCRIPT_DIR"
  # Or coverage starts again inside the reporting run and measures itself.
  unset COVERAGE_PROCESS_START
  "$BLENDER_PYTHON" -m coverage combine
  "$BLENDER_PYTHON" -m coverage report
  "$BLENDER_PYTHON" -m coverage html
  "$BLENDER_PYTHON" -m coverage json
  echo "Coverage reports written to bridge/test/coverage/ (HTML and JSON)"
else
  echo "No coverage data was produced. Run run_to_install_pytest.py from Blender's script"
  echo "editor to install coverage and its a1_coverage.pth; the tests themselves do not need it."
fi

# The test result, not the reporting step's: a coverage tool that is not
# installed must not be able to fail a passing suite.
exit $TEST_RESULT
