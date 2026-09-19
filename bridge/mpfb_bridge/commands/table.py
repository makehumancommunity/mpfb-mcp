"""
The closed command vocabulary. This module *is* the security argument.

Everything this add-on can be made to do from outside is in :data:`COMMANDS`
below. A request names a key of that dict; a name that is not a key is refused
with an error that lists the alternatives. There is no ``exec``, no ``eval``, no
``importlib`` reachable from a request and no path by which a caller's string
becomes Python. That claim is only worth making if it can be checked, and
checking it means reading one short file - this one.

**The table is written out here rather than assembled.** No decorator, no
``__init_subclass__``, no scan of this directory, no registration as an import
side effect. A command module that is not named below is dead code and is
unreachable, which is the property the whole design turns on: a dict assembled
by imports is a dict whose contents depend on import order, and a directory scan
would make adding a command to this add-on a matter of dropping a file in a
folder. That is very nearly the thing a closed vocabulary exists to deny.

**One module per command, from the first two.** Each command's handler and its
parameter specification live in a module named for the command -
``get_status.py``, ``list_commands.py`` - and this file holds the table and
nothing else. The split mirrors ``src/mpfbmcp/tools/`` on the other side of the
socket, deliberately and down to the naming, so that during the migration a tool
and the command it becomes are findable from each other. The difference is that
a tool module registers itself with the MCP server and a command module
registers nothing at all, for the reason in the paragraph above.

Where the record's fields live is a deliberate split too. ``params`` is long and
belongs beside the handler it constrains; ``requires_mpfb`` and ``summary`` are
short and are spelled out *here*, so that the sceptic reading one file learns
not only what this add-on can be asked to do but which of it touches MPFB.
"""

__all__ = (
    "COMMANDS",
)

from . import get_status
from . import list_commands
from . import list_objects
from .command import Command

COMMANDS = {
    "get_status": Command(
        name="get_status",
        handler=get_status.get_status,
        params=get_status.PARAMS,
        # False, and one of very few. This is the command that answers what is
        # wrong when everything else cannot run, so it must not be gated on the
        # thing it reports about.
        requires_mpfb=False,
        summary=get_status.SUMMARY),
    "list_commands": Command(
        name="list_commands",
        handler=list_commands.list_commands,
        params=list_commands.PARAMS,
        # False for the same reason: what this add-on can do does not depend on
        # whether MPFB finished starting, and a client discovering the interface
        # against a broken install should still get an answer.
        requires_mpfb=False,
        summary=list_commands.SUMMARY),
    "list_objects": Command(
        name="list_objects",
        handler=list_objects.list_objects,
        params=list_objects.PARAMS,
        # True, and the first in this table. Everything this command can say is
        # read out of MPFB's ObjectService, so a Blender without MPFB has no
        # answer to give - and "no MakeHuman objects in this scene" would be a
        # plausible-looking lie rather than a missing answer.
        requires_mpfb=True,
        summary=list_objects.SUMMARY),
}
