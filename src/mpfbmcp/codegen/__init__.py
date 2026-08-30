"""
Assembly of the Python source that tools send into Blender for execution.

A generated program is assembled in this fixed order:

1. a **bootstrap** that resolves MPFB (see ``bootstrap``), shared by every tool;
2. a **parameter prelude** binding a single name, ``PARAMS``, from a JSON
   literal;
3. zero or more **shared fragments** - files under ``shared/``, each modelling
   one concept that several payloads need identically;
4. a **payload** - one ordinary ``.py`` file per tool, under ``payloads/``.

The payload is the tool-specific part, and it is a plain file so that it can be
edited as Python is normally edited: with syntax highlighting, working
indentation, and a linter that mostly applies. It contains no placeholders, no
escaped newlines and no doubled braces, because nothing is substituted into it.

Parameters therefore reach the payload as *data*, never as interpolated source:
``json.dumps`` renders the values and ``repr`` renders a Python string literal
holding them, so a caller-supplied string can never alter the structure of the
generated program - which matters in a system whose entire job is to ``exec()``
code it built. The payload reads ``PARAMS["..."]`` and leaves ``result`` bound.

A **shared fragment** is the answer to a concept two or more payloads model the
same way - the ``target.json`` category table that ``mpfb_set_targets``,
``mpfb_symmetrize_targets`` and ``mpfb_get_target_stack`` all need. It is
ordinary Python like a payload, it is named in the ``shared`` argument by the
payload's own tool module, and it is concatenated ahead of the payload so that
the payload can simply call its functions. Fragments come *after* the prelude,
so a fragment may read ``PARAMS`` if it ever needs to. This does not weaken the
rule that adding an ordinary tool touches no shared code-generation module:
adding a tool still adds a tool module, a payload and a ``register()`` call, and
a fragment is opted into rather than edited.

Payload and fragment files live inside this package's directory but are
deliberately not modules of it: neither directory has an ``__init__.py``, and
importing one here would fail on ``bpy`` and on MPFB's services anyway. They are
read as package resources instead. That is also why ``pyproject.toml`` both
declares them as package data - one glob per directory, since a package-data
glob does not descend - and disables namespace-package discovery: without the
first, a real (non-editable) install ships a package with no payloads in it;
without the second, setuptools would pick the directories up as packages and
ship their contents as modules.
"""

from __future__ import annotations

__all__ = (
    "assemble",
    "payload_names",
    "read_payload",
    "shared_names",
    "read_shared",
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
_SHARED_DIRECTORY = "shared"


def _resource_directory(name: str):
    # Chained joinpath() calls rather than one "payloads/x.py": multi-segment
    # joinpath on a Traversable is 3.11+, and this package supports 3.10.
    return importlib.resources.files(__name__).joinpath(name)


def _names_in(directory: str) -> list[str]:
    return sorted(
        entry.name for entry in _resource_directory(directory).iterdir()
        if entry.name.endswith(".py")
    )


def _read_in(directory: str, name: str) -> str:
    return _resource_directory(directory).joinpath(name).read_text(encoding="utf-8")


def payload_names() -> list[str]:
    """Name every payload file, for tests that check all of them at once."""
    return _names_in(_PAYLOAD_DIRECTORY)


def read_payload(name: str) -> str:
    """Read one payload file's source, without importing it."""
    return _read_in(_PAYLOAD_DIRECTORY, name)


def shared_names() -> list[str]:
    """Name every shared fragment, for tests that check all of them at once."""
    return _names_in(_SHARED_DIRECTORY)


def read_shared(name: str) -> str:
    """Read one shared fragment's source, without importing it."""
    return _read_in(_SHARED_DIRECTORY, name)


def assemble(payload: str, *, bootstrap: str = "raising",
             params: dict[str, object] | None = None,
             shared: list[str] | None = None) -> str:
    """
    Build the Python source to send to blender_mcp, for one tool.

    ``payload`` names a file under ``payloads/`` (e.g. ``"create_human.py"``),
    ``bootstrap`` selects ``"raising"`` or ``"non_raising"``, and ``params``
    is bound in the generated program as ``PARAMS``. ``PARAMS`` is always
    bound, as an empty dict when a tool takes no arguments, so a payload can
    rely on the name existing.

    ``shared`` names files under ``shared/`` to concatenate ahead of the
    payload, in the order given, each behind its own seam comment. A payload
    that names one may call its functions directly.
    """
    if bootstrap not in _BOOTSTRAPS:
        raise ValueError("Unknown bootstrap {!r}, expected one of {}".format(
            bootstrap, ", ".join(sorted(_BOOTSTRAPS))))

    # repr() of a json.dumps() string: the values are carried as JSON data
    # inside a string literal, so they are parsed by json.loads() at run time
    # and never by the Python parser. See this module's docstring.
    prelude = "import json\nPARAMS = json.loads({!r})\n".format(json.dumps(params or {}))

    # Assembly order is fixed and every seam is labelled, so that a line number
    # reported from inside Blender can be mapped back to the file it came from
    # by counting from the nearest marker above it.
    parts = ["{}\n{}\n".format(_BOOTSTRAPS[bootstrap], prelude)]
    for fragment in shared or []:
        parts.append("# --- shared: {} ---\n{}\n".format(fragment, read_shared(fragment)))
    parts.append("# --- payload: {} ---\n{}".format(payload, read_payload(payload)))

    return "".join(parts)
