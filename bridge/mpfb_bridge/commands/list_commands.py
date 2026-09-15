"""
``list_commands``: what this add-on can be asked to do, asked politely.

The vocabulary was already discoverable before this command existed, but only
by guessing wrong: an unknown command comes back refused with the list of names
that *are* known. That is the right thing for a refusal to say and a poor way to
learn an interface, and "closed" should not have to mean "enumerable only by
provoking an error".

So the table describes itself. Every name, every parameter with its type and
bounds, and whether the command needs MPFB - which is the field a caller wants
before it decides what to do about a ``not_initialized`` install.

**It reports the table; it does not have opinions about it.** If a command is in
``COMMANDS`` it is listed, and if it is not it cannot be listed, because this
command reads the same dict the dispatcher reads. A discoverability command that
maintained its own catalogue would be one more thing able to drift from the
vocabulary it claims to describe.
"""

__all__ = (
    "PARAMS",
    "SUMMARY",
    "list_commands",
)

from ..validation import Param
from ..validation import TYPE_BOOLEAN

PARAMS = (
    Param("include_params", TYPE_BOOLEAN, default=True,
          description="Include each command's full parameter specification. Set false for a "
                      "short answer naming only the commands."),
)

SUMMARY = "List every command this bridge dispatches, with its parameters."


def list_commands(params, resolution):  # pylint: disable=unused-argument
    """Describe the whole command table.

    Reads the live table out of the dispatcher rather than importing
    ``COMMANDS`` directly, which matters for exactly one reason: the dispatcher
    holds the table it was *started* with. Were the two ever to differ - a
    developer reloading the package while the server runs - the answer that is
    useful is the one describing what will actually be dispatched.
    """
    from .. import command_server  # pylint: disable=import-outside-toplevel

    table = command_server.registered_commands()
    described = []
    for name in sorted(table):
        command = table[name]
        if params["include_params"]:
            described.append(command.as_dict())
        else:
            described.append({
                "name": command.name,
                "summary": command.summary,
                "requires_mpfb": command.requires_mpfb,
            })

    return {
        "commands": described,
        "command_count": len(described),
        "closed_vocabulary": True,
    }
