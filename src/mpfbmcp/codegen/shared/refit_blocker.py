"""
Shared fragment: when a refit would silently leave the rig behind.

Not a module of this package - this file is never imported here. It is read as
a resource and concatenated ahead of a payload (see ``mpfbmcp.codegen.assemble``
and its ``shared`` argument), on top of the raising bootstrap. A linter will
flag two names as undefined because the assembler binds them ahead of this file:

- ``_MPFB_SERVICES`` - MPFB's SERVICES dict, from the raising bootstrap.
- ``sys`` - already imported by that bootstrap (unused here, but bound).

``HumanService.refit()`` cannot refit a generated Rigify rig: only the meta rig
carries the MakeHuman vertex data it would need, so with no meta rig left in the
scene refit() logs a warning, tries to report through an ``operator`` no MCP tool
has one of, and returns - having refitted the mesh assets, which happen first,
but not the rig. Nothing in its return value says so. Every tool that refits has
therefore to detect the condition on this side, or answer that it refitted a rig
it never touched.

Four payloads need it: ``refit_human.py``, which refits as its whole purpose,
and ``set_macro_details.py``, ``set_targets.py`` and ``symmetrize_targets.py``,
which refit after changing the body. **The condition is here; the wording is
not.** ``mpfb_refit_human`` reports a refit that has already happened ("could not
be refitted, its mesh assets were") while the other three predict one they are
about to attempt ("cannot be refitted to the new body shape"), and a fragment
exposing one message with a tense argument would be a worse fragment than four
sentences written where they are read. Each payload keeps a
``rig_refit_blocker()`` of its own that phrases the answer and asks this function
whether there is one to phrase.

That split follows what the two failures cost. Four copies of the *condition* is
the ``rig_lookup.py`` case exactly: one careless edit and a character is
reported refitted by one tool and not by another, with nothing in either answer
to say which is right. Four copies of the *message* is at worst four sentences
that read slightly differently, which a caller notices and no caller is misled
by.
"""

ObjectService = _MPFB_SERVICES["ObjectService"]


def rig_refit_is_blocked(rig):
    """Whether refit() would leave this rig untouched. ``None`` is not blocked.

    An unrigged character is the ordinary case rather than a special one, so a
    ``rig`` of ``None`` answers False and every call site can ask before it has
    established that there is a rig at all.

    Both halves come from MPFB: ``object_is_generated_rigify_rig()`` is the same
    test refit() makes, and ``find_rigify_metarig_by_rig()`` walks the rig's own
    back-pointer rather than guessing from names, so a meta rig that has been
    renamed or hidden still counts as present - which it is, and refit() will
    use it.
    """
    if rig is None:
        return False
    if not ObjectService.object_is_generated_rigify_rig(rig):
        return False
    return ObjectService.find_rigify_metarig_by_rig(rig) is None
