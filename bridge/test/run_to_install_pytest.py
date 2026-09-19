"""Open this in Blender's script editor and run it, once, before running the tests.

Installs pytest and coverage into Blender's *own* bundled Python, which is
where the tests run, and writes the one file that makes coverage work at all in
this arrangement. Copied from mpfb2/test/run_to_install_pytest.py; you must have
write permission to Blender's python directory.

**The `.pth` is the part that is not a copy.** Coverage has to start *before*
Blender imports the add-on, or every `class` and `def` line in it is reported as
missed - the module was executed before the measurement began. The mechanism
is coverage.py's own subprocess support: a `.pth` file in site-packages whose
single line runs `coverage.process_startup()`, which does nothing unless the
environment names a configuration file. `execute_tests_headless.bash` sets that
variable, so the file below is inert for every other use of this Blender, which
is what makes installing it acceptable at all.

MPFB reads coverage the same way and no script in the mpfb2 repository creates
the file, so this step is written here rather than copied.
"""

import os
import subprocess
import sys

# Named to sort early: .pth files in a directory are processed in sorted order,
# and coverage should be started before anything else a .pth might import.
_PTH_NAME = "a1_coverage.pth"
# What the .pth runs, and why it is one line with an exec() in it. Python's
# `site` module executes a .pth line only when it begins with "import "; every
# other line is taken as a directory to add to sys.path. So a multi-line
# startup hook is not a thing a .pth can hold, and the whole of it has to be
# packed behind one import - which is also what the file this Blender may
# already carry does.
#
# Guarded twice over: it does nothing unless the environment asks for coverage,
# and it survives a Blender whose Python has no coverage installed. A bare
# `import coverage` in a .pth would break every start of that Blender the day
# somebody uninstalls it, which is a high price for a test-time convenience.
_PTH_STARTUP = (
    "if os.getenv('COVERAGE_PROCESS_START'):\n"
    " try:\n"
    "  import coverage\n"
    " except ImportError:\n"
    "  pass\n"
    " else:\n"
    "  coverage.process_startup()\n"
)
_PTH_CONTENT = "import os; exec({!r})\n".format(_PTH_STARTUP)

python_exe = None

for root, _dirs, files in os.walk(sys.prefix):
    if "venv" in root:
        continue
    for name in files:
        if name in ("python", "python.exe"):
            python_exe = os.path.join(root, name)
            break
        if name.startswith("python") and os.path.basename(root) == "bin":
            python_exe = os.path.join(root, name)
            break
    if python_exe:
        break

if not python_exe:
    raise IOError("Could not find python executable")

print("Installing pytest and coverage into " + python_exe)

subprocess.call([python_exe, "-m", "ensurepip"])
subprocess.call([python_exe, "-m", "pip", "install", "--upgrade", "pip"])
subprocess.call([python_exe, "-m", "pip", "install", "--upgrade", "pytest"])
subprocess.call([python_exe, "-m", "pip", "install", "--upgrade", "coverage"])


def _site_packages():
    """Blender's own site-packages, asked of Blender's own Python.

    Asked rather than assembled from `sys.prefix` and a version number: this
    script runs inside Blender, where `site` has already resolved the question,
    and the layout differs between platforms and between a system Blender and a
    downloaded one.
    """
    import site  # pylint: disable=import-outside-toplevel

    for directory in site.getsitepackages():
        if os.path.isdir(directory) and directory.startswith(sys.prefix):
            return directory
    return None


site_packages = _site_packages()
if site_packages is None:
    print("Could not find Blender's site-packages; coverage will not be measured. "
          "Create a file called " + _PTH_NAME + " there by hand, containing: " + _PTH_CONTENT)
else:
    pth = os.path.join(site_packages, _PTH_NAME)
    existing = ""
    if os.path.exists(pth):
        with open(pth, encoding="utf-8") as stream:
            existing = stream.read()

    if "process_startup" in existing:
        # Left alone on purpose. This file is shared with anything else that
        # measures coverage in this Blender - MPFB's own harness installs one -
        # and overwriting somebody else's working arrangement to install our
        # own equivalent would be rude and invisible.
        print("Leaving the existing " + pth + " alone; it already starts coverage.")
    else:
        try:
            with open(pth, "w", encoding="utf-8") as stream:
                stream.write(_PTH_CONTENT)
            print("Wrote " + pth)
        except OSError as error:
            print("Could not write " + pth + ": " + str(error))
            print("Coverage will not be measured until that file exists.")

print("\nPytest should now be available")
