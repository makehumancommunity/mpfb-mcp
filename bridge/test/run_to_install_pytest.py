"""Open this in Blender's script editor and run it, once, before running the tests.

Installs pytest into Blender's *own* bundled Python, which is where the tests
run. Copied from mpfb2/test/run_to_install_pytest.py; you must have write
permission to Blender's python directory.
"""

import os
import subprocess
import sys

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

print("Installing pytest into " + python_exe)

subprocess.call([python_exe, "-m", "ensurepip"])
subprocess.call([python_exe, "-m", "pip", "install", "--upgrade", "pip"])
subprocess.call([python_exe, "-m", "pip", "install", "--upgrade", "pytest"])
