"""
What one modeling category's slider reads, on this character.

**One implementation, imported by both commands that read a slider.** See
[`__init__.py`](__init__.py) for why this directory exists beside ``commands/``.
It takes no ``services`` argument: it reaches MPFB not at all, and takes
everything it needs from its caller.

The two names it does need come from
[`target_categories`](target_categories.py) and are imported **by name** rather
than through the module.

A category is not a shape key. MPFB's panel shows one slider per category, and
what that slider reads is computed from one or two shape keys by
``_get_opposed_modifier_value()`` / ``_get_simple_modifier_value()``: an opposed
category has a positive and a negative target of which at most one should be
present, and the negative one reads back **negated**, so a slider at -0.4 is a
shape key at 0.4 under the ``decr`` name.

Two commands have to agree about that number. ``get_target_stack`` reports it,
as ``modifiers`` and as the ``asymmetries`` it derives by subtracting one side
from the other; ``symmetrize_targets`` reads it on both sides to decide what to
copy, and reads it again afterwards to report what the destination became. A
disagreement between the two would not look like a bug in either: it would look
like a character that is symmetric in one command and asymmetric in the other,
and the caller would have no way to tell which one to believe.
``get_target_stack`` reaches it through
[`target_rollup`](target_rollup.py) since FR 034, which is also how
``get_character_summary`` reports the same numbers.

**The lookup is the parameter, because the two differ in what they may read
from.** ``get_target_stack`` changes nothing, so it reads ``key_blocks`` once
and answers every question from that snapshot - which is also what keeps its
``targets`` list and its ``modifiers`` rollup two views of one reading rather
than two reads. ``symmetrize_targets`` writes between readings, so a snapshot
taken before the write would report the old value as the new one. Passing the
pair in reconciles them: one rule, two ways of finding a value, and the
difference between them stated where it is decided rather than buried in two
copies of the rule.

``present`` and ``value_of`` are the pair, and they are two callables rather
than one because MPFB's own lookups are not interchangeable: ``has_target()``
matches the encoded name as well as the given one, while ``get_target_value()``
matches the raw name only. A single helper collapsing them would paper over a
difference that decides whether a long-named target is found at all.
"""

__all__ = (
    "modifier_reading",
)

from .target_categories import category_is_opposed
from .target_categories import target_names_for


def modifier_reading(category, side, present, value_of):
    """One category's slider reading, as MPFB's own getters compute it.

    ``present(target_name)`` answers whether that target is on the mesh and
    ``value_of(target_name)`` its value, both by the caller's rules; an absent
    target reads 0.0 either way, so a category with no shape keys at all is 0.0
    rather than an error - which is the ordinary case for all but a handful of
    the several hundred categories on any character.
    """
    if category_is_opposed(category):
        # _get_opposed_modifier_value(): the positive target wins when both are
        # somehow present, and the negative one is reported negated.
        positive = target_names_for(category, side, "positive")
        negative = target_names_for(category, side, "negative")
        if present(positive):
            return value_of(positive)
        if present(negative):
            return -value_of(negative)
        return 0.0
    # _get_simple_modifier_value().
    return value_of(target_names_for(category, side, "positive"))
