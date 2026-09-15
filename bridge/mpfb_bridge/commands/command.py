"""
What one entry in the command table is.

A command used to be a bare function, which was enough when there was one of
them and it took no parameters. It is not enough for twenty-five: a command has
a contract (what it takes), a precondition (whether it needs MPFB at all) and a
sentence describing it, and all three belong beside the handler rather than
inside it.

**The record carries no behaviour.** It is four fields and a way to describe
itself as JSON. Everything that *acts* on a command - validating a request
against its parameters, refusing it when MPFB is missing, calling it - lives in
the dispatcher, in one place, applied identically to every entry. A record that
could validate itself would be a record each command could quietly opt out of.
"""

__all__ = (
    "Command",
)


class Command:
    """One named command: its handler, its contract, and its precondition.

    ``handler`` is called as ``handler(params, resolution)`` - always both, even
    by the handlers that ignore one. A uniform signature is worth more than the
    unused argument it costs, because the dispatcher calls every handler the same
    way and nothing has to remember which kind this one is.

    ``params`` is a tuple of :class:`..validation.Param`. ``requires_mpfb`` says
    whether the dispatcher should refuse the call outright when MPFB is absent or
    half-registered; it is ``True`` for nearly everything, and the handful of
    commands for which it is ``False`` are the ones that can still say something
    useful about a broken install.
    """

    __slots__ = ("name", "handler", "params", "requires_mpfb", "summary")

    def __init__(self, name, handler, params=(), requires_mpfb=True, summary=""):
        self.name = name
        self.handler = handler
        self.params = tuple(params)
        self.requires_mpfb = requires_mpfb
        self.summary = summary

    def as_dict(self):
        """This command as the JSON ``list_commands`` hands out."""
        return {
            "name": self.name,
            "summary": self.summary,
            "requires_mpfb": self.requires_mpfb,
            "params": [param.as_dict() for param in self.params],
        }
