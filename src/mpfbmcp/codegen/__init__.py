"""
Assembly of the Python source that tools send into Blender for execution.

A generated program is assembled in this fixed order:

1. a **bootstrap** that resolves MPFB (see ``bootstrap``), shared by every tool;
2. a **parameter prelude** binding a single name, ``PARAMS``, from a JSON
   literal;
3. zero or more **shared fragments** - files under ``shared/``, each modelling
   one concept that several payloads need identically;
4. zero or more **cached shared fragments** - the same files, sent once per
   Blender session rather than once per call, behind the loader in
   ``shared_loader`` (see ``assemble``'s ``cached_shared``);
5. a **payload** - one ordinary ``.py`` file per tool, under ``payloads/``.

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
    "shared_fingerprint",
    "shared_key",
    "shared_names",
    "read_shared",
)

import hashlib
import importlib.resources
import json

from mpfbmcp.codegen.bootstrap import MPFB_BOOTSTRAP, MPFB_STATUS_BOOTSTRAP
from mpfbmcp.codegen.shared_loader import SHARED_SOURCE_LOADER

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


def shared_fingerprint(name: str) -> str:
    """A short digest of one fragment's source, which is its cache key.

    A hash rather than a version number, because a version number is a thing
    somebody has to remember to change and the consequence of forgetting is a
    Blender running one copy of a fragment while the tool believes it is running
    another.
    """
    return hashlib.sha256(read_shared(name).encode("utf-8")).hexdigest()[:12]


def shared_key(name: str) -> str:
    """How the session cache inside Blender addresses one fragment."""
    return "{}@{}".format(name, shared_fingerprint(name))


def assemble(payload: str, *, bootstrap: str = "raising",
             params: dict[str, object] | None = None,
             shared: list[str] | None = None,
             cached_shared: list[str] | None = None,
             carry_sources: bool = True) -> str:
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

    ``cached_shared`` names fragments to send through the session source cache
    instead (see ``shared_loader``): each is either carried with its source or
    referred to by name and fingerprint, according to ``carry_sources``, and
    either way it is executed into the program's own globals - so a payload
    cannot tell the difference. Fragments named here run after any named in
    ``shared``. ``carry_sources=False`` produces a program that fails, with a
    recognisable marker, against a Blender that does not already hold them;
    ``mpfbmcp.shared_cache`` is what decides which to ask for and what to do
    with that failure.
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
    # by counting from the nearest marker above it. The payload marker has a
    # second consumer: observability.tool_name_from_program() reads the tool's
    # name out of it, which is why send_code() needs no extra argument to say
    # who called it. Its exact format is therefore pinned by tests here and in
    # tests/test_observability.py rather than by this comment.
    parts = ["{}\n{}\n".format(_BOOTSTRAPS[bootstrap], prelude)]
    for fragment in shared or []:
        parts.append("# --- shared: {} ---\n{}\n".format(fragment, read_shared(fragment)))
    if cached_shared:
        parts.append("# --- shared loader ---\n{}\n".format(SHARED_SOURCE_LOADER))
        for fragment in cached_shared:
            parts.append(_cached_shared_call(fragment, carry_sources))
    parts.append("# --- payload: {} ---\n{}".format(payload, read_payload(payload)))

    return "".join(parts)


def _cached_shared_call(fragment: str, carry_source: bool) -> str:
    """One line asking Blender to run a fragment, with or without its source.

    The source is embedded as a raw triple-single-quoted string so that the
    record FR 012 keeps stays readable Python rather than one enormous escaped
    line, and so that line numbers inside the fragment are the file's own. Both
    depend on the fragment containing no ``'''`` and not ending in a backslash,
    which tests/test_codegen.py asserts of every fragment rather than leaving to
    the day one does.
    """
    marker = "# --- cached shared: {} ({}) ---\n".format(
        shared_key(fragment), "carried" if carry_source else "reused")
    call = '_mpfb_mcp_shared("{}", "{}", '.format(fragment, shared_fingerprint(fragment))
    if not carry_source:
        return marker + call + "None)\n"
    return marker + call + "r'''" + read_shared(fragment) + "''')\n"
