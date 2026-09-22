"""
The uniform "it happened" flag every mutating command reports.

**One implementation, imported by every command that needs it.** See
[`__init__.py`](__init__.py) for why this directory exists beside ``commands/``
and what the ``services`` argument is doing there.

**Alone among the seven it takes no ``services`` argument**: it reads nothing
out of MPFB at all. It is one function over a dict the command has already
finished building, which is what makes it the simplest thing in this directory
and the one whose being wrong would be most obvious.

Every mutating command keeps its own verb - ``added``, ``applied``, ``removed``,
``generated``, ``changed``, ``recalculated``, ``refit_performed`` - because
``added: true`` beside ``asset_object_name`` reads better than ``performed:
true`` does, and the tool docstrings on the other side of the socket are written
around it. What the set of verbs costs is a caller writing against more than one
tool: reaching for the wrong name yields ``None`` rather than an error, so the
mistake is silent. FR 013's harness, written with the source open, guessed wrong
on three tools in one session and each wrong guess turned a passing check into
what looked like a tool defect. ``performed`` is the one name that means the
same thing everywhere, and it is added *beside* the verb rather than in place of
it.

The flag is stamped onto the finished answer, once, in a command's last line,
rather than written into each branch that builds one. ``set_asset_material`` has
eleven refusals and one success: writing the key twelve times is twelve chances
to write it wrong, and the refusals are exactly the branches nobody re-reads.
Stamping has one. The two guards below exist for the same reason - a refusal
(``ready: false``) and an unresolved subject (``found: false``) are never
performed whatever the call site passes, so no call site has to remember that.
"""

__all__ = (
    "with_performed",
)


def with_performed(result, done):
    """Add ``performed`` to a command's answer, and return that same dict.

    ``done`` is the command's own judgement that the character was actually
    changed, and it is deliberately written at the call site because it is not
    always the verb. ``symmetrize_targets`` under ``dry_run`` returns a
    populated ``changed`` list having written nothing; ``set_macro_details``
    called with no slider named returns ``ready: true`` having recalculated
    nothing; ``generate_rigify_rig`` returns ``ready: true`` when Rigify
    rejected the meta rig. A helper that guessed from the verb would get all
    three wrong.

    Anything truthy is accepted, since several verbs are lists - ``applied``
    holds one entry per change - and the flag is a real ``bool`` either way,
    because a caller branching on it should not have to know which.
    """
    result["performed"] = bool(
        done
        and result.get("found", True) is not False
        and result.get("ready", True) is not False
    )
    return result
