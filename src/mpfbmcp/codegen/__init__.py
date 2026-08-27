"""
Assembly of the Python source that tools send into Blender for execution.

A generated program is three fixed parts, in this order:

1. a **bootstrap** that resolves MPFB (see ``bootstrap``), shared by every tool;
2. a **parameter prelude** binding a single name, ``PARAMS``, from a JSON
   literal;
3. a **payload** - one ordinary ``.py`` file per tool, under ``payloads/``.

The payload is the tool-specific part, and it is a plain file so that it can be
edited as Python is normally edited: with syntax highlighting, working
indentation, and a linter that mostly applies. It contains no placeholders, no
escaped newlines and no doubled braces, because nothing is substituted into it.

Parameters therefore reach the payload as *data*, never as interpolated source:
``json.dumps`` renders the values and ``repr`` renders a Python string literal
holding them, so a caller-supplied string can never alter the structure of the
generated program - which matters in a system whose entire job is to ``exec()``
code it built. The payload reads ``PARAMS["..."]`` and leaves ``result`` bound.

Payload files live inside this package's directory but are deliberately not
modules of it: ``payloads/`` has no ``__init__.py``, and importing a payload
here would fail on ``bpy`` and on MPFB's services anyway. They are read as
package resources instead. That is also why ``pyproject.toml`` both declares
them as package data and disables namespace-package discovery - without the
first, a real (non-editable) install ships a package with no payloads in it;
without the second, setuptools would pick ``payloads/`` up as a package and
ship them as modules.
"""

from __future__ import annotations

__all__ = (
    "assemble",
    "payload_names",
    "read_payload",
)

import importlib.resources
import json

from mpfbmcp.codegen.bootstrap import MPFB_BOOTSTRAP, MPFB_STATUS_BOOTSTRAP

# The two variants documented in specifications/architecture.md, under the
# names used there. "raising" is the default: a tool that does not care whether
# MPFB is usable is the exception, not the rule.
_BOOTSTRAPS = {
    "raising": MPFB_BOOTSTRAP,
    "non_raising": MPFB_STATUS_BOOTSTRAP,
}

_PAYLOAD_DIRECTORY = "payloads"


def _payload_directory():
    # Chained joinpath() calls rather than one "payloads/x.py": multi-segment
    # joinpath on a Traversable is 3.11+, and this package supports 3.10.
    return importlib.resources.files(__name__).joinpath(_PAYLOAD_DIRECTORY)


def payload_names() -> list[str]:
    """Name every payload file, for tests that check all of them at once."""
    return sorted(
        entry.name for entry in _payload_directory().iterdir()
        if entry.name.endswith(".py")
    )


def read_payload(name: str) -> str:
    """Read one payload file's source, without importing it."""
    return _payload_directory().joinpath(name).read_text(encoding="utf-8")


def assemble(payload: str, *, bootstrap: str = "raising",
             params: dict[str, object] | None = None) -> str:
    """
    Build the Python source to send to blender_mcp, for one tool.

    ``payload`` names a file under ``payloads/`` (e.g. ``"create_human.py"``),
    ``bootstrap`` selects ``"raising"`` or ``"non_raising"``, and ``params``
    is bound in the generated program as ``PARAMS``. ``PARAMS`` is always
    bound, as an empty dict when a tool takes no arguments, so a payload can
    rely on the name existing.
    """
    if bootstrap not in _BOOTSTRAPS:
        raise ValueError("Unknown bootstrap {!r}, expected one of {}".format(
            bootstrap, ", ".join(sorted(_BOOTSTRAPS))))

    # repr() of a json.dumps() string: the values are carried as JSON data
    # inside a string literal, so they are parsed by json.loads() at run time
    # and never by the Python parser. See this module's docstring.
    prelude = "import json\nPARAMS = json.loads({!r})\n".format(json.dumps(params or {}))

    # Assembly order is fixed and the seam is labelled, so that a line number
    # reported from inside Blender can be mapped back to a payload file by
    # counting from the marker.
    return "{bootstrap}\n{prelude}\n# --- payload: {payload} ---\n{source}".format(
        bootstrap=_BOOTSTRAPS[bootstrap],
        prelude=prelude,
        payload=payload,
        source=read_payload(payload),
    )
