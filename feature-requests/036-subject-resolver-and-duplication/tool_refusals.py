# SPDX-License-Identifier: GPL-3.0-or-later

"""
FR 036's tool-side proof: every refusal sentence, before and after.

The unit suite asserts that a bad argument raises ``ValueError``, and almost
never what the error says. So a move of the shape validators into one module
can keep all 428 tests passing and still reword a refusal. This script covers
that gap. It builds the real server, and for every registered tool it calls the
tool once per parameter per bad value, with every other argument left at a
value that passes. It then writes what happened to a JSON file with sorted
keys:

- the ``ValueError`` sentence, when the tool refused;
- ``<sent>``, when the call got as far as the socket.

**The socket is never reached.** ``backend.send`` is replaced by a function that
raises a ``BaseException`` subclass, so that no tool's own ``except Exception``
(``mpfb_list_urls`` has one, on purpose) can swallow it. Reaching it is
recorded rather than fatal, because "this value is not refused locally" is
itself a finding the diff should show if it changes.

Run it before the tool-side commit and again after it. The two files must be
identical. It needs no Blender.

    PYTHONPATH=src python3 feature-requests/036-subject-resolver-and-duplication/tool_refusals.py OUT.json
"""

from __future__ import annotations

import inspect
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

# Every shape a validator on this side is meant to reject, and a few it is not.
BAD_VALUES = (
    None, 7, -1, 1.5, True, False, "", "   ", "false", "x", [], ["x"], [{}], [{"x": 1}], {},
)

# The least a tool needs for its *other* arguments to be the ones judged.
REQUIRED = dict(
    asset_type="Clothes",
    direction="left_to_right",
    identifier="default",
    name="fr036",
)
BASE = dict(
    mpfb_add_asset=dict(fragment="fr036/fr036.mhclo"),
    mpfb_add_rig=dict(identifier="default"),
    mpfb_set_skin=dict(fragment="fr036.mhmat"),
    mpfb_set_asset_material=dict(fragment="fr036.mhmat"),
    mpfb_save_preset=dict(name="fr036"),
    mpfb_save_expression=dict(name="fr036"),
    mpfb_create_human_from_preset=dict(name="fr036"),
)


class _Sent(BaseException):
    """The call reached the socket."""


def _refuse_to_send(*_args, **_kwargs):
    raise _Sent()


def _outcome(function, arguments):
    try:
        function(**arguments)
    except _Sent:
        return "<sent>"
    except ValueError as error:
        return "ValueError: {:s}".format(str(error))
    except TypeError as error:
        return "TypeError: {:s}".format(str(error))
    return "<returned>"


def refusals():
    from mpfbmcp import backend, build_server  # pylint: disable=import-outside-toplevel
    backend.send = _refuse_to_send
    server = build_server()
    tools = server._tool_manager._tools  # pylint: disable=protected-access
    answers = dict()
    for tool_name in sorted(tools):
        function = tools[tool_name].fn
        parameters = inspect.signature(function).parameters
        base = dict()
        for name, parameter in parameters.items():
            if parameter.default is inspect.Parameter.empty:
                base[name] = REQUIRED[name]
        base.update(BASE.get(tool_name, dict()))
        answers["{:s}()".format(tool_name)] = _outcome(function, base)
        for name in parameters:
            for value in BAD_VALUES:
                arguments = dict(base)
                arguments[name] = value
                key = "{:s}({:s}={!r})".format(tool_name, name, value)
                answers[key] = _outcome(function, arguments)
    return answers


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: tool_refusals.py OUT.json")
    answers = refusals()
    with open(sys.argv[1], "w", encoding="utf-8") as handle:
        json.dump(answers, handle, indent=1, sort_keys=True)
    refused = sum(1 for value in answers.values() if value.startswith("ValueError"))
    print("wrote {:s}: {:d} calls, {:d} refused locally".format(
        sys.argv[1], len(answers), refused))
    return 0


if __name__ == "__main__":
    sys.exit(main())
