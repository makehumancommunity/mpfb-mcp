"""
The ``mpfb_list_objects`` tool: finds MakeHuman objects in the current scene.

The cheap orienting tool: a scene iteration and a property read per object, with
no file lookups anywhere, so it is safe to call before deciding what to do. That
is also why it reports only names and types - see ``mpfb_get_object_info`` for
what an object was made from.

The type vocabulary is not duplicated on this side of the socket. A hardcoded
list here would drift silently from MPFB's own, and this one is user-facing
guidance an agent will act on, so both ``known_object_types`` and
``object_type_recognized`` are answered from inside Blender instead.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp import backend


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="List MakeHuman Objects",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        )
    )
    def mpfb_list_objects(object_type: str | None = None) -> dict[str, object]:
        """
        List the MakeHuman objects in the connected Blender's current scene,
        optionally filtered by MPFB object type. Changes nothing.

        Use this to find a subject for the other MPFB tools when you did not
        create the character yourself, then pass a returned `name` to
        `mpfb_get_object_info` to learn what that object actually is.

        `object_type` is one of MPFB's own type names (`"Basemesh"`,
        `"Skeleton"`, `"Subrig"`, `"Proxymeshes"`, `"Clothes"`, `"Eyes"`,
        `"Eyelashes"`, `"Eyebrows"`, `"Teeth"`, `"Tongue"`, `"Hair"`); omit it
        to get every MakeHuman object. **Matching is MPFB's own, a
        case-insensitive substring test rather than equality**: `"rig"` matches
        `Subrig`, and `"mesh"` matches both `Basemesh` and `Proxymeshes`. That
        is deliberate on MPFB's side and is not a bug here.

        Only the current scene is searched, so results match what the user is
        looking at. An object that exists in the .blend without being linked
        into the scene is not listed - `mpfb_get_object_info` will still
        resolve it by name and say so.

        `result` carries `objects`, one entry per match with `name` (the
        Blender object name, which is how every other tool addresses it),
        `object_type` (MPFB's type) and `blender_type` ("MESH", "ARMATURE",
        ...); `count`; `requested_object_type`, the filter as given or null;
        `object_type_recognized`, whether it matched a type MPFB knows -
        **check this before concluding anything from an empty list**, since
        "no basemeshes in this scene" and "you asked for `Basemseh`" are
        otherwise the same answer; and `known_object_types`, MPFB's full type
        vocabulary read from MPFB itself, so a misspelling can be corrected
        from this same response.

        The result is an address other tools will act on. Re-call rather than
        cache: loading another .blend, or the user deleting an object,
        invalidates it entirely.
        """
        # `result` (built in bridge/mpfb_bridge/commands/list_objects.py) is plain
        # JSON-safe data. The bridge serializes a result before it commits to an
        # answer, so a value that is not JSON-safe would be a failed command
        # rather than a repr() quietly standing in for one.
        return backend.send(
            "list_objects",
            # An empty filter is not merely useless: MPFB matches a type by
            # substring, so it would match every type rather than none, and the
            # caller would get a full listing back from a narrow question.
            params={"object_type": arguments.validated_text(
                object_type, "object_type", "omit it to list every MakeHuman object")},
        )
