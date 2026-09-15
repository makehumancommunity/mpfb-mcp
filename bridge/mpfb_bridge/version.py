"""
The add-on's own version, and the one thing to remember about it.

``BRIDGE_VERSION`` must equal the ``version`` in ``blender_manifest.toml``.
There are two of them because the manifest is data Blender reads and this is a
value a command reports, and nothing in the extension format publishes the
former to the latter - so they are kept in step by hand.

A comment saying so is what this was before, and a comment is not a check. The
bridge's own test suite now parses the manifest and asserts the two agree, which
is the cheapest possible guard against the failure this arrangement invites: a
released add-on that tells every client it is a version it is not.

This lives in a module of its own rather than beside a command because three
different places need it - the status command, the preferences panel and the
table - and none of them is a natural owner.
"""

__all__ = (
    "BRIDGE_VERSION",
)

BRIDGE_VERSION = "0.2.0"
