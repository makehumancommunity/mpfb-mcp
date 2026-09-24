"""
**The first layer: the add-on itself, with no MPFB subject.** The harness, the
parameter contract, dispatch, a real socket round trip, and the two claims kept
in step by hand (the version and the command list).

Every later layer assumes this one passed, and ``-x`` in
[`test_headless.py`](../../test_headless.py) stops the run at the first failure,
so a fault in the transport is reported once, here, rather than as thirty
symptoms in thirty command modules. Order inside the layer carries no meaning;
see [testing.md](../../../../specifications/testing.md#two-harnesses-split-at-the-directory-boundary)
for the rule.

``list_urls`` also declares ``requires_mpfb=False`` and is **not** here: its
subject is still what MPFB answers, so it is in ``ccc_reading/``.
"""

__all__ = ()
