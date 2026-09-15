"""
The commands package: one module per command, and one table naming them.

Read [table.py](table.py) to know everything this add-on can be asked to do.
This file exists to re-export :data:`COMMANDS` so that the rest of the add-on
imports ``from .commands import COMMANDS`` exactly as it did when the whole
vocabulary was one module, and it re-exports nothing else.

Keeping it to that matters more than it looks. The moment this file starts
importing command modules for their own sake, or building the table itself, the
table stops being a thing one file states and becomes a thing several files
agree on - and the security claim is that reading one file is enough.
"""

__all__ = (
    "COMMANDS",
)

from .table import COMMANDS
