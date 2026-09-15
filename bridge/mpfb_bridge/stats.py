"""
What the server has been doing, for the panel to paint.

A listening socket that gives no sign of life is hard to trust and harder to
debug: with nothing but a start button, the only way to learn whether the bridge
has ever answered anything is to ask it something and watch the client. So the
dispatcher records four facts here and the preferences panel reads them.

**Deliberately four facts and not a log.** This is a counter, the last command,
the last failure and when each happened - enough to answer "is it alive, and did
the last thing work". It is not a per-call record of the kind mpfb-mcp keeps
under ``MPFB_MCP_RECORD_DIR``; that is a bigger thing with a design question
attached (what the unit of a record is, once a command replaces a program) and
it belongs with the effort that answers it.

Nothing here writes to disk, and ``bpy`` is not imported: the server records,
the panel reads, and neither knows about the other.
"""

__all__ = (
    "record_dispatch",
    "record_failure",
    "snapshot",
    "reset",
)

import time

from .log import get_logger

_LOG = get_logger("stats")


class _Stats:
    """The counters, reset whenever the server starts."""

    __slots__ = (
        "requests_served",
        "failures",
        "last_command",
        "last_command_at",
        "last_error",
        "last_error_at",
        "started_at",
    )

    def __init__(self):
        self.requests_served = 0
        self.failures = 0
        self.last_command = ""
        self.last_command_at = 0.0
        self.last_error = ""
        self.last_error_at = 0.0
        self.started_at = 0.0


_stats = _Stats()


def reset():
    """Start the counters over. Called when the server starts, not when it stops.

    Leaving them alone on stop is the useful behaviour: the question a developer
    has after stopping the server is usually what happened while it was up.
    """
    global _stats  # pylint: disable=global-statement
    _stats = _Stats()
    _stats.started_at = time.time()


def record_dispatch(name):
    """Note that one command was dispatched."""
    _stats.requests_served += 1
    _stats.last_command = name
    _stats.last_command_at = time.time()


def record_failure(slug, message):
    """Note that one request came back as an error envelope.

    Both halves are kept: the slug is what a caller branched on and the sentence
    is what a human reads off the panel. A failure counts as served - it was
    answered - so this does not touch the request counter.
    """
    _stats.failures += 1
    _stats.last_error = "{:s}: {:s}".format(slug, message)
    _stats.last_error_at = time.time()
    _LOG.debug("Recorded failure %s", slug)


def snapshot():
    """The counters as a plain dict, for drawing or reporting."""
    return {
        "requests_served": _stats.requests_served,
        "failures": _stats.failures,
        "last_command": _stats.last_command,
        "last_command_at": _stats.last_command_at,
        "last_error": _stats.last_error,
        "last_error_at": _stats.last_error_at,
        "started_at": _stats.started_at,
    }
