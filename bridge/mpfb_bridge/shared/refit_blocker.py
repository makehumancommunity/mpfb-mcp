"""
When a refit would silently leave the rig behind.

**One implementation, imported by every command that needs it.** See
[`__init__.py`](__init__.py) for why this directory exists beside
``commands/`` and what the ``services`` argument is doing there.

``HumanService.refit()`` cannot refit a generated Rigify rig: only the meta rig
carries the MakeHuman vertex data it would need, so with no meta rig left in the
scene refit() logs a warning, tries to report through an ``operator`` no command
here has one of, and returns - having refitted the mesh assets, which happen
first, but not the rig. Nothing in its return value says so. Every command that
refits has therefore to detect the condition itself, or answer that it refitted
a rig it never touched.

Four commands need it: ``refit_human``, which refits as its whole purpose, and
``set_macro_details``, ``set_targets`` and ``symmetrize_targets``, which refit
after changing the body. **The condition is here; the wording is not.**
``refit_human`` reports a refit that has already happened ("could not be
refitted, its mesh assets were") while the other three predict one they are
about to attempt ("cannot be refitted to the new body shape"), and a shared
helper exposing one message with a tense argument would be worse than four
sentences written where they are read. Each command keeps a
``rig_refit_blocker()`` of its own that phrases the answer and asks this
function whether there is one to phrase.

That split follows what the two failures cost. Four copies of the *condition* is
the ``rig_lookup.py`` case exactly: one careless edit and a character is
reported refitted by one command and not by another, with nothing in either
answer to say which is right. Four copies of the *message* is at worst four
sentences that read slightly differently, which a caller notices and no caller
is misled by.
"""

# The local bindings below are spelled with MPFB's own capitalisation -
# ``LocationService = services["LocationService"]`` - rather than snake_case,
# so that a body here reads the way MPFB's own source reads and can be
# compared with it line for line. That is the whole reason for the disable.
# pylint: disable=invalid-name

__all__ = (
    "rig_refit_is_blocked",
)


def rig_refit_is_blocked(services, rig):
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
    ObjectService = services["ObjectService"]
    if rig is None:
        return False
    if not ObjectService.object_is_generated_rigify_rig(rig):
        return False
    return ObjectService.find_rigify_metarig_by_rig(rig) is None
