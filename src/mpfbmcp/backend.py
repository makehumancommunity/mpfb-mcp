"""
The seam: which transport a tool's call travels over, decided below the send.

**A tool says what it wants done; this module decides how the request
travels.** That is the whole of the design, and the value of it is entirely in
what a tool does *not* contain: no branch on a backend, no second parameters
dict, no import of a transport client. A tool calls ``backend.send()`` with
exactly what it was already handing to ``codegen.assemble()`` - the payload's
filename, its parameters, its bootstrap - and this module either assembles that
program and sends it to blender_mcp, or looks the payload up in
:data:`MIGRATED_COMMANDS` and sends a named command to the MPFB Bridge instead.
If supporting the bridge ever requires editing a tool module, the seam is in
the wrong place; see
[Supporting a second backend](../../specifications/architecture.md#supporting-a-second-backend).

**The backend is configuration, never a probe.** ``MPFB_MCP_BACKEND`` names it,
and since FR 032 the default is the **bridge**.
Both third-party MCP add-ons answer on 9876 and the bridge on 9877, and no
single probe distinguishes any of them - a NUL-terminated ping leaves the
community add-on's parser waiting for the rest of a message, while an
unterminated one leaves blender lab's doing the same. An unrecognised name is
an **error rather than a fallback**: a typo that quietly leaves every call on
the old path is indistinguishable from the bridge not working, which is the
most expensive shape a configuration mistake can take.

**One table says what has been migrated.** :data:`MIGRATED_COMMANDS` maps a
payload's filename to the bridge command that replaces it. A payload in it
travels over whichever transport is configured; a payload not in it travels the
generated path in *both* configurations, because there is nothing else it could
do. The table is therefore the migration's progress bar, and the last stage of
the pivot deletes it by emptying it.

**The envelope is this package's, and both transports produce it.** ``status``,
``result`` and ``message`` keep their spellings and their meanings, so no
existing caller changes. What is added is ``error``, the slug a caller branches
on, which the bridge writes itself and which an error from the generated path
is given here - ``command_failed``, which is a statement of fact rather than a
guess, since a blender_mcp error envelope is always a program that raised
inside Blender. Nothing else is synthesised: ``protocol_version`` is a fact
about the bridge's protocol and is absent from a generated-code answer rather
than invented for it.
"""

from __future__ import annotations

__all__ = (
    "BACKENDS",
    "BACKEND_BLENDER_MCP",
    "BACKEND_BRIDGE",
    "BACKEND_VARIABLE",
    "ERROR_COMMAND_FAILED",
    "MIGRATED_COMMANDS",
    "as_common_envelope",
    "command_for",
    "preferred_backend",
    "send",
)

import os

from mpfbmcp import bridge_connection, codegen, shared_cache
from mpfbmcp.connection import send_code

BACKEND_VARIABLE = "MPFB_MCP_BACKEND"

BACKEND_BLENDER_MCP = "blender_mcp"
BACKEND_BRIDGE = "bridge"

# In preference order for a reader rather than for the code: the first is the
# default. It became the bridge in FR 032, once every tool that crosses the
# socket had a command and the two paths had been compared field by field
# against one Blender.
BACKENDS = (BACKEND_BRIDGE, BACKEND_BLENDER_MCP)

# What a generated-code failure is called in this package's envelope. The same
# spelling the bridge uses for the same thing, deliberately: a caller branching
# on ``error`` must not have to learn which transport answered it.
ERROR_COMMAND_FAILED = "command_failed"

# Payload filename -> bridge command name. **This is the list of what has been
# migrated**, and it is meant to be read as one: one line per tool that has
# moved, in the order they moved. A tool absent from it has no bridge command
# and takes the generated path whatever is configured.
MIGRATED_COMMANDS = {
    "list_objects.py": "list_objects",
    # FR 031, batch A: the introspection tools, which carry no shared fragment.
    # ``get_status.py`` is the one entry whose command is **not** its payload's
    # name, and the exception is deliberate: the bridge already has a
    # ``get_status`` reporting the *bridge*, and this one reports *MPFB*. Two
    # commands answering "status" about two different pieces of software is a
    # collision that is cheap now and permanent later.
    "get_status.py": "get_mpfb_status",
    "get_object_info.py": "get_object_info",
    "get_macro_details.py": "get_macro_details",
    # Batch B: the first migrated tool carrying a shared fragment, which is
    # what the `shared` / `cached_shared` arguments above exist for.
    "list_presets.py": "list_presets",
    # Batch C: the asset library, and the two fragments whose whole purpose is
    # that a catalogue and an acting tool agree about what an entry means.
    "list_rigs.py": "list_rigs",
    "list_assets.py": "list_assets",
    "list_asset_materials.py": "list_asset_materials",
    # Batch D: the two heaviest, and the ones whose migration removes the
    # session source cache's reason for existing - between them they carried
    # 26 KB of fragment source on every cold call.
    "list_targets.py": "list_targets",
    "get_target_stack.py": "get_target_stack",
    # FR 032, batch A: the first two commands that **change** a .blend, and with
    # them the last two shared fragments. `create_human.py` carries
    # `performed.py` and `refit_human.py` carries `refit_blocker.py`, so after
    # these two no fragment is without a counterpart under
    # `bridge/mpfb_bridge/shared/`.
    "create_human.py": "create_human",
    "refit_human.py": "refit_human",
    # Batch B: the modeling tools. The batched one and the destructive one are
    # here, and between them they are where a mutating command's two hardest
    # obligations get their second implementation - resolve every entry before
    # writing any, and a dry run that reports changes it did not make.
    "set_macro_details.py": "set_macro_details",
    "set_targets.py": "set_targets",
    "symmetrize_targets.py": "symmetrize_targets",
    # Batch C: rigs and assets, and with them the two fragments that stopped
    # straddling - `rig_lookup.py` now has both its catalogue and its acting
    # command on the bridge, and so does `asset_sections.py`.
    "add_rig.py": "add_rig",
    "generate_rigify_rig.py": "generate_rigify_rig",
    "add_asset.py": "add_asset",
    "remove_asset.py": "remove_asset",
    # Batch D: materials. `set_asset_material` is the one command in the table
    # with no service function behind it at all - the mechanism exists only in
    # a UI operator, reimplemented from services with three of its quirks
    # reproduced rather than tidied up.
    "set_skin.py": "set_skin",
    "set_asset_material.py": "set_asset_material",
    # Batch E: the two that write outside the `.blend`, and the one that
    # answers *because* Blender is unreachable. With these the table holds
    # twenty-four entries, which is every tool that crosses the socket -
    # `mpfb_list_docs` has no payload and never did. That is FR 032's finish
    # line and FR 033's precondition.
    "save_preset.py": "save_preset",
    "create_human_from_preset.py": "create_human_from_preset",
    "list_urls.py": "list_urls",
}


def preferred_backend() -> str:
    """Which backend this process has been configured to use.

    **Defaults to the bridge since FR 032**, and the flip was the last thing
    that effort did rather than the first. What earned it: every tool that
    crosses the socket has a command, and the two paths were compared answer by
    answer *and scene by scene* against one Blender before the default moved.

    The generated path stays and stays working - ``MPFB_MCP_BACKEND=blender_mcp``
    is one word - so FR 033 deletes a path that has been unused for a while
    rather than one that was carrying every call until the commit before. That
    ordering is the whole reason the flip is a separate step from the
    migrations.
    """
    configured = os.environ.get(BACKEND_VARIABLE, "").strip()
    if not configured:
        return BACKEND_BRIDGE
    if configured not in BACKENDS:
        raise ValueError(
            "{:s}={!r} is not a backend this server knows. Set it to one of {:s}, or leave it "
            "unset for {:s}.".format(
                BACKEND_VARIABLE, configured, ", ".join(BACKENDS), BACKEND_BRIDGE))
    return configured


def command_for(payload: str) -> str | None:
    """The bridge command that has replaced one payload, or ``None``."""
    return MIGRATED_COMMANDS.get(payload)


def send(payload: str, *, params: dict[str, object] | None = None,
         bootstrap: str = "raising", strict_json: bool = True,
         shared: list[str] | None = None,
         cached_shared: list[str] | None = None) -> dict[str, object]:
    """Perform one tool's call over whichever transport is configured.

    ``payload``, ``params`` and ``bootstrap`` are what the tool would have
    handed to ``codegen.assemble()``, and they are unchanged by a migration:
    **both sides receive the tool's already-validated arguments and neither
    reshapes them**. There is deliberately no escape hatch for a tool whose two
    paths would want different parameters. If one ever does, that is a fact
    worth surfacing as a design problem in that tool's own effort rather than a
    flexibility worth carrying here unused.

    ``shared`` and ``cached_shared`` are likewise passed straight through -
    **on the generated path**, where a fragment is a file concatenated ahead of
    a payload and ``cached_shared`` additionally means "send its source once per
    Blender session" (see :mod:`mpfbmcp.shared_cache`). On the bridge path they
    are **ignored**, because the bridge assembles nothing: what a fragment
    models has become a module in ``bridge/mpfb_bridge/shared/`` that the
    command imports. A tool therefore names its fragments the same way whatever
    transport it is on, which is what keeps the seam below the send for the five
    migrated tools that carry them.

    ``strict_json`` belongs to the generated path alone - it asks blender_mcp
    to fail loudly rather than fall back to ``repr`` for a result that is not
    JSON-safe. The bridge does the equivalent unconditionally, serializing a
    result before it commits to an answer.
    """
    command = command_for(payload)
    if command is not None and preferred_backend() == BACKEND_BRIDGE:
        return bridge_connection.send_command(command, params or {})

    if cached_shared:
        # The session source cache is generated-path machinery and lives below
        # this seam rather than beside the tools, which is what lets a tool
        # carrying fragments be migrated without the tools left behind losing
        # it. It dies with the generated path.
        return as_common_envelope(shared_cache.send(
            payload, params or {}, shared=shared, cached_shared=cached_shared,
            bootstrap=bootstrap, strict_json=strict_json))

    code = codegen.assemble(payload, bootstrap=bootstrap, params=params or {}, shared=shared)
    return as_common_envelope(send_code(code, strict_json=strict_json))


def as_common_envelope(response: object) -> object:
    """Give a generated-code error the slug this package's envelope carries.

    Narrow on purpose, in both directions. A **success** envelope is returned
    exactly as it arrived, in every configuration - which is the rule
    [a success envelope is untouched](../../specifications/observability.md)
    states for diagnostics and which holds here for the same reason. And an
    envelope that already carries an ``error`` is left alone, since the only
    thing that puts one there is the bridge, which knows better than this
    function what went wrong.

    The mapping happens here rather than in ``connection.py`` because that
    module's claim to be a faithful duplicate of blender_mcp's protocol is what
    lets an upstream change be mirrored by hand. The additions stay around the
    protocol, exactly as the observability additions did.
    """
    if not isinstance(response, dict) or response.get("status") != "error":
        return response
    if "error" in response:
        return response
    # Rebuilt rather than mutated, so that ``error`` sits beside ``status``
    # where a reader looks for it, and so that a caller still holding the
    # original dict is not surprised by a key appearing in it.
    mapped: dict[str, object] = {"status": "error", "error": ERROR_COMMAND_FAILED}
    mapped.update({key: value for key, value in response.items() if key != "status"})
    return mapped
