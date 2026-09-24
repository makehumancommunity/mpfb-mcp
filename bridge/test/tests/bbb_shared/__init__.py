"""
**The second layer: the shared modules, called directly rather than through a
command.** Reserved by [FR 035](../../../../feature-requests/done/035-bridge-test-layers/README.md)
and created by [FR 036](../../../../feature-requests/done/036-subject-resolver-and-duplication/README.md),
for the shared modules that effort added.

A shared module is used by several commands, so a fault in one is otherwise
reported as a failure in whichever command's module happens to run first, and a
branch no command's fixture reaches is never reached at all. Testing it here,
after the add-on's own machinery and before any command, reports the fault once
and where it is.

**Only the modules FR 036 added are tested here so far.** Direct tests for the
thirteen that existed before it are a separate effort, recorded in
[NEXT_STEPS.md](../../../../feature-requests/NEXT_STEPS.md#direct-tests-of-the-bridges-shared-modules).
Order inside the layer carries no meaning; see
[testing.md](../../../../specifications/testing.md#two-harnesses-split-at-the-directory-boundary).
A test here that makes something keeps the rules in ``ddd_mutating/__init__.py``:
what a test made, the fixture removes.
"""

__all__ = ()
