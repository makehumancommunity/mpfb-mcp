# Bridge tests grouped into ordered layers

**Status:** Done

The bridge's test modules in [bridge/test/tests/](../../../bridge/test/tests) carry a three-letter
prefix each, `aaa_bridge_test.py` through `uuu_get_character_summary_test.py`. The prefix was
copied from MPFB's harness, but only its form was copied and not what it is for. In MPFB the prefix
goes on **directories that group tests by what they cover**: `bbb_services/`, `ccc_data/`,
`ddd_entities/`, `eee_ui/`. The ordering means something. The harness runs pytest with `-x`, so
the first failure stops the run, and a failure in a primitive stops it before an aggregate that
depends on that primitive fails a second time and hides the cause.

Here the prefix numbers modules instead of grouping them. The order does not follow any layering:

- **The letter is the order in which modules were written.** `fff_` through `ooo_` are FR 031's
  commands in the order FR 031 migrated them, and `qqq_` through `uuu_` are later additions.
  Adding a tool now means taking the next free letter. Six are left.
- **Read-only commands run after mutating ones.** `ppp_mutating/` sorts between `ooo_` and `qqq_`,
  so `list_urls`, `get_face_units`, `list_expressions` and `get_expression` run after the sixteen
  commands that change a `.blend`. That is backwards if a mutating test relies on the reads being
  sound.
- **The position of `ppp_mutating/` depends on pytest's collection order.** It only lands between
  the flat files because pytest 8 and later sort files and directories together. An older pytest
  collected files first and ran the directory last.
- **The name does not match the command.** Everywhere else in this repository a tool, its command
  and its test share one name. Here the test's name has a letter in front of it that says nothing.

The intent is a short, fixed set of prefixed **directories**, each a layer that assumes every
earlier layer passed, with unprefixed modules inside. That is MPFB's arrangement, and it matches
the hypothesis the ordering exists to serve: if a primitive fails, there is no point running an
aggregate that depends on it.

## Goals

**Primary:** reorganise `bridge/test/tests/` into a small number of prefixed directories that run
in layer order, from the add-on's own machinery, through shared code, then each command, to tests
that span several commands. Test modules lose their prefixes and are named after their subject.

**Primary:** record the rule in [testing.md](../../../specifications/testing.md) so the next effort
adds a module to the right layer instead of taking the next free letter.

**Secondary:** leave a place for direct tests of `bridge/mpfb_bridge/shared/`, which has none
today. Every shared module is tested only through the commands that use it. Writing those tests is
**not** part of this effort (see [Architecture](#architecture)).

## Functional requirements

1. **Only directories under `bridge/test/tests/` have a three-letter prefix.** No test module
   directly under `tests/` and no module inside a group has one. `__init__.py` and `_fixtures.py`
   stay where they are and are not test modules.
2. **The groups are the following.** Their order is the run order:

   | Directory | Layer | Holds today |
   |-----------|-------|-------------|
   | `aaa_addon/` | The add-on itself, with no MPFB subject: harness, parameter contract, dispatch, socket round trip, and the version and command-list metadata | `bridge_test.py`, `validation_test.py`, `dispatch_test.py`, `roundtrip_test.py`, `metadata_test.py` (the current `aaa_` to `eee_`) |
   | `bbb_shared/` | **Reserved and not created.** Direct tests of `mpfb_bridge/shared/` modules, called without going through dispatch | nothing |
   | `ccc_reading/` | One module per read-only command | the fourteen from `fff_` to `ooo_` and `qqq_` to `ttt_`, for example `list_objects_test.py`, `get_mpfb_status_test.py`, `list_urls_test.py`, `get_expression_test.py` |
   | `ddd_mutating/` | One module per command that changes a `.blend` | the sixteen command modules now in `ppp_mutating/` |
   | `eee_composite/` | Tests whose claim is about **several commands at once** and means nothing when asserted about one | `get_character_summary_test.py` (the summary dispatched beside each detailed command) and `expression_divergence_test.py` (three commands in agreement, then a round trip across them) |

   The names are a proposal. The layering is the requirement.
3. **Each module is named `<subject>_test.py`.** For a command module, the subject is the command
   name exactly, so `ccc_reading/list_rigs_test.py` tests `commands/list_rigs.py`.
4. **Nothing about what is tested changes.** The same 359 test functions run, with the same
   bodies, and the same ones pass and skip. This effort only moves and renames files, apart from
   import paths and prose.
5. **`TEST_MODULE` works for a module and for a whole group.**
   `TEST_MODULE=tests/ddd_mutating` runs one layer, and
   `TEST_MODULE=tests/ccc_reading/list_rigs_test.py` runs one module.
   [bridge/test/README.md](../../../bridge/test/README.md) documents both forms.
6. **Every reference to an old path is updated.** That includes the root
   [CLAUDE.md](../../../CLAUDE.md), [specifications/](../../../specifications/),
   [bridge/test/README.md](../../../bridge/test/README.md), the module docstrings under
   [tests/](../../../tests/) that point at their bridge counterpart, and
   `bridge/mpfb_bridge/commands/add_rig.py`'s docstring. When the effort is finished, a search for
   `[a-u]{3}_[a-z_]+_test\.py` or `ppp_mutating` outside `feature-requests/done/` finds nothing.
   Finished requests are **not** edited. Their mentions describe the tree as it was then, and their
   only markdown links into this directory point at `_fixtures.py` and at `tests/` itself, and
   neither of those moves.

## Non-functional requirements

- **A layer that fails early must mean something.** The value of the ordering comes from `-x` in
  [test_headless.py](../../../bridge/test/test_headless.py). A failure in `aaa_addon/` should stop the
  run before thirty command modules report thirty symptoms of the same fault. The layering is
  right if and only if a failure in layer *n* makes a failure in a later layer uninteresting.
- **The run order does not depend on pytest's collection rules.** Once `tests/` holds only
  directories as collectable entries, the order is the same under either collection rule described
  in the background.
- **Readability, as the project defines it in
  [architecture.md](../../../specifications/architecture.md#readability-and-developer-experience-are-prioritized).**
  The directory tells a reader what obligations a module has: `ddd_mutating/` carries the cleanup
  rules. The module name tells them what it tests, and nothing in the name is noise.
- **History is preserved.** Every move is a `git mv`, so `git log --follow` still finds a module's
  past.

## Architecture

**Imports change by one dot.** A group module imports its helpers as `from .. import bridge_module`
and `from .._fixtures import ...`, as `ppp_mutating/` already does. `tests/__init__.py` (the
`sys.modules` scan) and `_fixtures.py` stay at the top so that every group shares one copy. Each
group needs an `__init__.py` so that the relative imports resolve.

**`ppp_mutating/__init__.py` becomes `ddd_mutating/__init__.py`, and its docstring must be
rewritten.** Its opening claim is that it exists as *"a directory rather than fourteen more
prefixed files, and that is the whole reason this package exists"*, which will no longer be true.
The rules that follow that claim still hold: what a test made, the fixture removes, and a write
outside the `.blend` goes to a redirected location. So does the rule found by FR 032's spike that a
fixture asset tree must be a redirected data root. Keep those rules, and replace the reason.
[testing.md](../../../specifications/testing.md#two-harnesses-split-at-the-directory-boundary) makes
the same claim (*"the prefix goes on a directory once twenty-six letters are not enough"*) and needs
the same correction. This is the lifecycle's "check the claim you are replacing".

**Order inside a group is alphabetical and carries no meaning.** In `aaa_addon/`, dispatch now runs
before validation, although the old order was validation first. That is acceptable: the harness
test (`bridge_test.py`) still sorts first, and the other four are peers. If a later effort finds
that two modules in one group must run in a particular order, that means the group should be split
into two layers. It does not mean the modules should get prefixes back.

**Why `bbb_shared/` is reserved rather than created.** Nothing currently fits it.
`expression_divergence_test.py` is about shared code but asserts it through three commands, so it
is composite. The `macro_drift` tests in the `get_macro_details` module go through dispatch too.
Writing direct tests for thirteen shared modules is a different effort from renaming files. Mixing
the two would also lose this effort's simplest proof, that the before-and-after runs are identical
(requirement 4). When the effort is finished, add an entry to
[NEXT_STEPS.md](../../NEXT_STEPS.md). It should say that
the shared modules are tested only through their commands. It should also name which shared modules
could be tested without MPFB, such as `artifact_names.py` and `performed.py`, which read nothing
from MPFB's services. The coverage report in `bridge/test/coverage/` shows which lines are reached
only through dispatch. Reserving the letter now means the group can be added later without
renaming anything.

**Pitfalls.**

- **Old `__pycache__` directories stay behind.** `git mv` moves tracked files only, so after the
  move a `ppp_mutating/` holding only `__pycache__` is left on disk. It collects nothing, but it
  suggests the old layout still exists. Delete it.
- **Two groups must not have modules with the same name unless both groups have an
  `__init__.py`.** With packages, pytest tells `ccc_reading/x_test.py` and `ddd_mutating/x_test.py`
  apart. Without packages it refuses the second one. Nothing collides today, but a future
  `set_x`/`get_x` pair could.
- **The mapping of module to layer is a judgement, and `list_urls` is the one to watch.** It is
  read-only and one of three commands declaring `requires_mpfb=False`, so it could be argued into
  `aaa_addon/`. It belongs in `ccc_reading/`, because its subject is still what MPFB answers.

## Affected specifications

- [testing.md](../../../specifications/testing.md), in the section
  [Two harnesses, split at the directory boundary](../../../specifications/testing.md#two-harnesses-split-at-the-directory-boundary).
  Replace "alphabetical prefixes to force order" and the twenty-six-letters paragraph with the
  layer rule: the prefix goes only on directories, a directory is a layer that assumes earlier
  layers passed, order inside a layer means nothing, and `bbb_shared/` is reserved. Re-point the
  `ppp_mutating/` mentions further down the file.
- [architecture.md](../../../specifications/architecture.md): one path mention of
  `ppp_mutating/expression_divergence_test.py`, which becomes
  `eee_composite/expression_divergence_test.py`. No decision changes.
- The root [CLAUDE.md](../../../CLAUDE.md), because the layout changes. Update the `bridge/test/` row
  of the bridge table, which describes `tests/ppp_mutating/` as MPFB's way out of running short of
  letters. Also update the bridge paths quoted in the test table.

## Tests

**No new tests, and none are removed.** That is the requirement, and it is also the proof.

Run the bridge suite **before and after** the move, with the Blender from
[local_environment.md](../../../local_environment.md). The two runs must be identical when compared as
the set of `(module name without its prefix, test function, outcome)`: 359 each, the same passes
and the same skips. A short `compare_runs.py` in this subdir parses two saved `-v` logs, strips the
directory and the old prefix from each node ID, and diffs the results. It is this request's
re-runnable check, and it moves to `done/` with it. Also check the order in the "after" log: every
`aaa_addon/` node ID comes before any `ccc_reading/` one, and so on.

The unittest suite (`python3 -m unittest discover -s tests`, 428 tests) should not change, because
only docstrings under `tests/` are edited. Run it anyway. No smoke item is added to
[verification/](../../../verification/), because no tool changes.

## Outcome

Landed as specified, with the proposed directory names. Thirty-eight `git mv`s; three new
`__init__.py` files carrying each layer's obligations; imports one dot deeper; prose and paths
updated everywhere requirement 6 names, plus `_fixtures.py`, the bridge modules' own docstrings and
[FR 036](../036-subject-resolver-and-duplication/README.md), which had been written against this
layout and now points at it.

**Verification.** [`compare_runs.py`](compare_runs.py) against a log saved before the first move and
one after the last edit: 359 results each, 359 passed, none skipped, the normalized sets identical,
and every layer's node IDs ahead of the next layer's. `TEST_MODULE=tests/ddd_mutating` ran 166
tests from that layer only, and `TEST_MODULE=tests/ccc_reading/list_rigs_test.py` ran 11. The
unittest suite ran 428, all passing. The first version of the script read 260 results rather than
359, because `--capture=tee-sys` puts a test's own output between its node ID and its outcome; it
now pairs the two by position rather than expecting them on one line, and reports a node with no
outcome rather than dropping it.

**Found on the way.** The coverage report is overwritten by every run, including a narrowed one,
so the numbers in `bridge/test/coverage/` describe the last run, not the suite. The full-suite
figures for the shared modules (73% to 100%, all through dispatch) went into the
[NEXT_STEPS.md](../../NEXT_STEPS.md#direct-tests-of-the-bridges-shared-modules) entry this request
asked for.

## References

- NEXT_STEPS.md's "Strange naming of bridge tests", where this request came from. The entry
  left the queue when this request was done; what landed is in [HISTORY.md](../../HISTORY.md).
- MPFB's own layout: `../mpfb2/test/tests/`, with `aaa_context_test.py` followed by `bbb_services/`,
  `ccc_data/`, `ddd_entities/` and `eee_ui/`. MPFB still has one flat prefixed module at the top.
  This request goes one step further and has none.
- [FR 032](../032-creation-and-modification-migrated/README.md), which introduced
  `ppp_mutating/` as a way out of running short of letters, and whose cleanup rules this request
  keeps.
- [FR 034](../034-character-summary/README.md), whose summary test is the clearest example of
  a composite test.
