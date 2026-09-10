"""
Payload for ``mpfb_list_urls``: reads MPFB's own web addresses out of its UI module.

Not a module of this package - this file is never imported here. It is read as
a resource and executed inside Blender, on top of the non-raising bootstrap
(see ``mpfbmcp.codegen.assemble``). A linter will flag several names as
undefined because the assembler binds them ahead of this file:

- ``_mpfb_state``, ``_mpfb_candidates``, ``_mpfb_module``, ``_mpfb_services`` -
  the classification from the non-raising bootstrap; the latter two may be None.
  ``sys`` is likewise already imported by that bootstrap.
- ``PARAMS`` - bound but unused: this tool takes no arguments.

**This payload reports raw material, not the answer.** It hands back a key ->
URL mapping and enough state to explain a miss; the merge against mpfb-mcp's
vendored copy, the descriptions and the staleness report are assembled by
``mpfbmcp.tools.list_urls`` on the other side of the socket. That is unlike
every other payload here, and it is deliberate: the same merge has to run when
Blender cannot be reached at all, and sending the vendored table in as PARAMS
to keep the assembly in here would put ~3 KB on the wire - past the add-on's
4 KB chunk - to compute what a local function already computes. One
implementation, used in all four states, is worth the divergence.

**``weburls`` is a UI module reached through ``sys.modules``, never imported.**
MPFB imports its UI during ``register()``, so on an initialized install
``<root>.ui.weburls`` is already there and reading it re-executes nothing.
Importing it instead would violate
[Never import MPFB submodules directly](../../../../specifications/architecture.md#never-import-mpfb-submodules-directly)
and would, on a half-registered install, run MPFB code inside a Blender that is
already broken. Missing from ``sys.modules`` is therefore an ordinary answer
here, reported with a reason, and not something to fix by importing.

Note what makes ``weburls`` safe to read where
``ui/model/_modelsubpanels.py`` - which ``mpfb_set_targets`` deliberately does
*not* read - is not: this module is a dozen string literals with no computation
at import time, so there is no snapshot in it to go stale.

**Enumerated by prefix, not by a list.** Every module-level name beginning
``URL_`` is reported, so a constant MPFB adds later appears here without a
change in mpfb-mcp. A name whose value is not a string is reported under
``skipped_keys`` rather than silently dropped: an absent entry has to be
explainable.
"""

_MPFB_MCP_URL_PREFIX = "URL_"

# Why the live values could not be read, per state. None of these is an error:
# "where do I download MPFB" is asked most often by somebody whose MPFB is not
# working, so the tool answers from mpfb-mcp's vendored copy and says so.
_MPFB_MCP_STATE_REASONS = {
    "absent": "MPFB is not loaded in this Blender instance, so its own web addresses could not "
              "be read; the addresses below are mpfb-mcp's vendored copy of them.",
    "not_initialized": "MPFB is loaded but did not finish initializing, and its weburls module "
                       "is not among the modules it managed to import; the addresses below are "
                       "mpfb-mcp's vendored copy of them.",
}

# Concatenated rather than formatted: a payload never contains a substitution
# point, since parameters reach it as data and never as interpolated source, and
# tests/test_codegen.py holds every payload to that by looking for the braces.
_MPFB_MCP_MISSING_MODULE_PREFIX = "MPFB is loaded and initialized, but '"
_MPFB_MCP_MISSING_MODULE_SUFFIX = (
    "' is not in sys.modules - MPFB normally imports its UI during register(), so this install "
    "is unusual. The addresses below are mpfb-mcp's vendored copy of them."
)


def _mpfb_mcp_dotted(version):
    if version is None:
        return None
    return ".".join([str(part) for part in version])


result = {
    "state": _mpfb_state,
    "package": None,
    "version": None,
    "weburls_module": None,
    "weburls_read": False,
    "urls": None,
    "skipped_keys": None,
    "reason": _MPFB_MCP_STATE_REASONS.get(_mpfb_state),
}

if _mpfb_module is not None:
    result["package"] = _mpfb_module.__name__
    result["version"] = _mpfb_mcp_dotted(getattr(_mpfb_module, "VERSION", None))

    # Attempted whatever the state is: a half-registered MPFB may still have
    # imported its UI, and reading a module that is already loaded costs
    # nothing and cannot make the install any more broken.
    _mpfb_mcp_module_name = _mpfb_module.__name__ + ".ui.weburls"
    result["weburls_module"] = _mpfb_mcp_module_name
    _mpfb_mcp_weburls = sys.modules.get(_mpfb_mcp_module_name)

    if _mpfb_mcp_weburls is None:
        if _mpfb_state == "ok":
            result["reason"] = (_MPFB_MCP_MISSING_MODULE_PREFIX + _mpfb_mcp_module_name
                                + _MPFB_MCP_MISSING_MODULE_SUFFIX)
    else:
        _mpfb_mcp_urls = dict()
        _mpfb_mcp_skipped = []
        for _mpfb_mcp_name in sorted(dir(_mpfb_mcp_weburls)):
            if not _mpfb_mcp_name.startswith(_MPFB_MCP_URL_PREFIX):
                continue
            _mpfb_mcp_value = getattr(_mpfb_mcp_weburls, _mpfb_mcp_name)
            if isinstance(_mpfb_mcp_value, str):
                _mpfb_mcp_urls[_mpfb_mcp_name] = _mpfb_mcp_value
            else:
                # A URL_ name holding something other than a string is not an
                # address, but its absence still has to be accounted for.
                _mpfb_mcp_skipped.append(_mpfb_mcp_name)
        result["weburls_read"] = True
        result["urls"] = _mpfb_mcp_urls
        result["skipped_keys"] = _mpfb_mcp_skipped
        result["reason"] = None
