#!/bin/bash

# Trailing-whitespace hygiene, mirroring MPFB's fixfiles.bash
# (https://github.com/makehumancommunity/mpfb2/blob/master/fixfiles.bash). MPFB has no
# black, ruff or isort: formatting is convention plus this script, and
# correctness is pylint.

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

find "$SCRIPT_DIR/mpfb_bridge" -name "*.py" -exec "sed" "-i" "-e" 's/[ \t]*$//' {} ";"
find "$SCRIPT_DIR/test" -name "*.py" -exec "sed" "-i" "-e" 's/[ \t]*$//' {} ";"
