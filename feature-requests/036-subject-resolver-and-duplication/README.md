# One subject resolver, and the rule for what else to share

**Status:** In progress

Eighteen bridge commands take a subject: the object the caller named, or the active one if it
named none. Sixteen of them then go on to that object's basemesh. The rules are in the
specifications, and today they exist as sixteen local copies plus one shared function, which
[FR 034](../done/034-character-summary/README.md) moved into `shared/macro_reading.py`. The copies
have the same code and differ only in wording, and some of that wording has drifted.

The NEXT_STEPS entry also asked for a scan of the rest of the code. [census.py](census.py) found
39 function names defined in more than one module, and three patterns written under several names.
Judging those against the architecture's rule on shared code
([Shared modules, and what warrants one](../../specifications/architecture.md#shared-modules-and-what-warrants-one))
exposed a problem with the rule itself. It has two halves:

- **The warrant.** Share whatever must not drift. This still holds.
- **The restraint.** Being identical is not a reason, and neither is a five-line helper. This half
  was set when a shared fragment was source text pasted into every generated program that used it.
  That cost bytes on the wire (FR 017), confused the linter and put traceback line numbers in the
  wrong place (FR 002). The pivot made sharing an ordinary `import`, but the migration carried the
  restraint across unchanged, and the spec still backs it with a census of programs that FR 033
  deleted.

This request therefore rewrites the rule first, derives [census.md](census.md)'s verdicts from the
rewritten rule, and then does what those verdicts say.

## Goals

**Primary:** the rule for shared code rests on what sharing costs now that the bridge is an
ordinary add-on and this package an ordinary package, and the census evidence it cites is current.

**Primary:** there is one implementation of subject resolution, and all eighteen commands that
take a subject use it. Each command still chooses its own wording for a miss.

**Primary:** every other group that the rewritten rule says to share ends up with one
implementation. That covers the four groups whose drift would mislead a caller, and the identical
helpers that can be named as one concept, on both sides of the socket.

**Primary:** every duplicate that remains has a recorded reason, so the next census confirms the
decisions instead of reopening them. `census.py --check` enforces this.

**Secondary:** correct the "in both copies" in mutating-tools.md. That table has described one
copy since FR 033, and this effort changes the row anyway.

**Not a goal:** changing a response's fields or how any tool behaves. This is a refactoring. The
only change a caller can see is listed in requirement 3.

## Functional requirements

1. **The rule is rewritten, and the verdicts follow from it.** The rewritten rule is stated under
   [Architecture](#the-rule-restated). census.md's verdicts are derived from it rather than from
   the current text. If review changes the rule, the verdicts are derived again before any code
   moves. The rule is folded into architecture.md when the effort completes, as usual, together
   with this census as its evidence, replacing the deleted-payload census.
2. **One subject resolver.** A shared module resolves a subject from a requested name or from the
   active object. It can stop at the subject, or go on to the subject's basemesh through
   `ObjectService.find_object_of_type_amongst_nearest_relatives()`. It returns the sentence for a
   miss, and it returns `subject_resolved_by`, so that no command computes that value on a
   separate line. All eighteen commands use it. That means the sixteen with local copies, together
   with `get_macro_details` and `get_character_summary`, which currently go through
   `macro_reading.resolve_basemesh()`. That function moves to the new module, and
   `macro_reading.py` keeps only the reading.
3. **The wording stays with each command, and one sentence changes on purpose.** Each command
   passes in two phrases: the one that says what did not happen (such as `nothing was changed`, or
   nothing for a reading command), and the one that finishes the no-basemesh miss (such as `it has
   no target stack`). Every other sentence stays word for word as it is today. **The one
   deliberate change** is that the five commands whose no-basemesh miss does not point the caller
   at `mpfb_get_object_info` will start to do so: `get_face_units`, `get_expression`,
   `set_face_units`, `apply_expressions` and `save_expression`. The census found no reason for
   them to be different ([census.md](census.md#subject-resolution)).
4. **No response field changes.** `found`, `subject_name`, `basemesh_name`, `subject_resolved_by`,
   every `error` and `blocked_by` slug, and the order in which a command checks its refusals are
   all the same before and after. `get_object_info` keeps its `resolved_from: "active_object"`.
   See [Architecture](#pitfalls) for why that difference in vocabulary is recorded here rather
   than fixed.
5. **`set_macro_details` reads through `macro_reading.py`.** Its `_as_float`,
   `_macro_details_of`, `_race_sum_of` and `_RACE_SUM_TOLERANCE` are removed. After a write, the
   `macro_details` and `race_sum` it reports come from the same code that
   `mpfb_get_macro_details` reports them from.
6. **One rule for where a target lives on the mesh.** The rule is to look for the raw name first,
   then for `TargetService.encode_shapekey_name()`'s encoded form. It is implemented once. The
   snapshot lookup (`target_rollup.value_lookup()`, used by `get_target_stack` and the summary)
   and the live lookup (used by `set_targets` and `symmetrize_targets`, which currently have
   identical private copies) both apply it. Both lookups are still passed into
   `modifier_reading()` exactly as they are today.
7. **One way to read what MPFB does not publish.** One shared function reads a name kept on a
   service's module, applying [the three rules](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish).
   One reads a `BlenderConfigSet` string property as `None` when it is unset. One coerces a path
   that MPFB may hand back as a `pathlib.Path`. All eighteen `sys.modules` reaches in `commands/`
   and `shared/` go through the first. All six copies of `_property_value` and all seven of
   `_as_path`/`as_path` are replaced by the other two. That includes the public `as_path` that
   `asset_sections`, `rig_lookup` and `target_categories` each export today.
8. **One way to restore the caller's selection.** All ten `finally` blocks that put back the
   resolved object's selection state and the active object use one shared construct, so the
   specification's "in a `finally`, around every `refit()` and every operator call" is enforced in
   a single place that can be searched for. What is restored stays exactly as it is now.
9. **The identical helpers that name one concept are shared, on both sides of the socket.** This
   is what the rewritten rule adds, and [census.md](census.md#shared-as-one-concept) lists the
   groups:
   - **Bridge side:** reading plain Blender data (`_object_names`, `_vertex_group_names` and
     `_material_names`), and formatting a version tuple (`_dotted`).
   - **Tool side:** the shape validators: the optional subject name, the real-`bool` flag
     (`_validated_flag` and `_validated_refresh` are one rule), the non-negative count, and the
     optional non-empty text (`_validated_text` and `_validated_optional_text` are one rule under
     two names).

   Where a copy differs on purpose, the difference becomes a parameter passed at the call site,
   or the copy stays and is listed in `KEPT` with its reason. Examples are the three tools whose
   `name` is required and whose refusal explains why, and `create_human_from_preset`'s text
   validator, which returns the value stripped. **Every refusal sentence stays word for word.**
10. **Every remaining duplicate is judged.** When the effort is done, `census.py --check` exits 0.
    Every function name still defined in more than one searched module is either listed in its
    `KEPT` table, with a pointer to the section of census.md that gives the reason, or has been
    removed. A name listed in `KEPT` that is no longer duplicated also fails the check.
11. **The census's out-of-scope findings reach NEXT_STEPS.** These are the 29 test helpers that
    reach FastMCP's private `_tool_manager`, the `resolved_from` / `subject_resolved_by`
    vocabulary, and the fact that selection restore does not cover objects an operator newly
    selected. Each gets an entry that names what the census found.

## Non-functional requirements

- **Behaviour is preserved, and that is proven.** Proving it matters more here than anywhere else,
  because every change is meant to be invisible. There are two proofs, one per side of the socket.
  On the bridge side it is the snapshot diff described in
  [testing.md](../../specifications/testing.md#two-patterns-for-a-claim-about-more-than-one-command).
  On the tool side it is a diff of refusal sentences. Both should be empty apart from the five
  sentences in requirement 3 (see [Tests](#tests)).
- **A command still reads like a command.** The phrases a command owns are passed at the call
  site, so a reader of `set_skin.py` can still see that `set_skin` says "no skin was applied"
  without opening the shared module. This is the reason [refit_blocker.py](../../bridge/mpfb_bridge/shared/refit_blocker.py)
  keeps its wording per command, and it applies here too: **the condition is shared and the
  wording is not.** A resolver or a validator that looked up its messages in a table keyed by tool
  name would fail this requirement.
- **A shared module is named for a concept.** No `utils.py`, `helpers.py` or `common.py` on either
  side. If a helper has no module it naturally belongs in, that is a reason to keep it duplicated
  (see [the rule](#the-rule-restated)), not a reason to create a grab-bag module.
- **It stays familiar to MPFB's developers.** The bridge follows
  [MPFB's conventions](../../specifications/architecture.md#readability-and-developer-experience-are-prioritized)
  and passes its `.pylintrc` and pyright configuration with no new suppressions. A shared module
  that reproduces MPFB's own call keeps the comment that names which MPFB panel makes that call.
- **Adding a tool is still four files.** A new command imports the resolver, and a new tool
  imports the validators. Neither edits them. If this effort ever needs a tool-specific branch
  inside a shared function, the design is wrong.
- **Each group lands separately.** There is one commit per group in
  [census.md](census.md), and each commit has a diff of its own. If one diff is not empty, it
  should be obvious which group caused it. The rule rewrite in this README comes first, as part of
  accepting this request.

## Architecture

### The rule, restated

This is the text proposed to replace the restraint half of
[Shared modules, and what warrants one](../../specifications/architecture.md#shared-modules-and-what-warrants-one).
The warrant bullets stay as they are, apart from the additions listed under
[Affected specifications](#affected-specifications).

> **What sharing costs, now.** A shared module is an ordinary import. It costs nothing on the
> wire, and the linter, pyright and tracebacks all work across it. What it does cost is
> indirection, because a reader opens a second file, and coupling, because one edit reaches every
> caller. Those costs are real, but they are small next to what sharing cost when a fragment was
> pasted into every program that used it. That is when the old restraint was set, and it no longer
> applies.
>
> 1. **Code whose drift would mislead a caller is always shared**, whatever its size. That is the
>    warrant above.
> 2. **An identical helper that can be named as one concept is shared** when a natural home for it
>    exists, or can be created and named for that concept. Being identical *is* now a reason. The
>    burden is on keeping a copy, and a kept copy is recorded with its reason.
> 3. **A convention whose body differs per tool is not shared.** `_blocked`, `_refusal` and
>    `_message_for` are one idea applied per tool. A mechanism to generate "this tool's null
>    response" would be larger than the copies and would hide the fields each tool owns. This never
>    depended on code generation, and it still holds.
> 4. **The wording stays at the call site.** Where the condition is shared, each caller still
>    phrases its own answer, as `refit_blocker.py` established.

Rule 2 is the change. Under the old rule the burden was on sharing, and a helper stayed duplicated
unless someone could show that its drift would do harm. Under the new rule the burden is on
keeping the copy.

### Where things go

These are proposals. The requirement is one implementation per group, not a particular set of file
names.

| Group | Proposed home | Note |
|-------|---------------|------|
| Subject resolution | new `shared/subject.py` | Like `performed.py`, it reads nothing out of a services dict for the subject step. The basemesh step takes `services` as its first argument, following the rule for this directory. |
| Phenotype reading | the existing `shared/macro_reading.py` | Only the call sites in `set_macro_details` change. |
| Target name rule | the existing `shared/target_rollup.py` | It already holds `_encoded` and the snapshot lookup. A live lookup placed next to it keeps both constructors of the pair that `modifier_reading()` takes in one module. |
| Unpublished surface | new `shared/mpfb_surface.py` (name open) | `asset_info.Lookup` builds on it rather than being replaced by it. `Lookup` exists to gather its reaches once per call, and that still makes sense. |
| Selection restore | new `shared/selection.py` (name open), a context manager | It restores the state and does not activate anything. Each command still activates what it needs inside the block, because what gets activated differs: `set_asset_material` activates the asset. |
| Plain Blender data | new `shared/blender_data.py` (name open) | Names of objects, vertex groups and material slots, read without MPFB. It takes no `services`. `target_rollup`'s key-block helpers could live here as well. Which module is more natural is for the implementer to decide. |
| Version tuple | wherever `get_status` and `get_mpfb_status` can both reach naturally | If no home is natural, rule 2 says keep the copies and record why. A single function is not worth a module of its own. |
| Tool-side shape validators | new `src/mpfbmcp/arguments.py` (name open), beside `artifact_names.py` | This is not under `tools/`, because a module there is a tool and has a `register()`. |

That brings the bridge's shared modules from thirteen to about seventeen, and adds one module on
the tool side. The count is a result of the rule, not a target.
[shared/__init__.py](../../bridge/mpfb_bridge/shared/__init__.py) says "the count is not a
coincidence" and dates each module back to the fragment it mirrors. That paragraph is rewritten,
not extended: the count follows from the rule, and after the pivot the fragment ancestry is
history. Its list of modules that take no `services` gains `subject` (for the subject step),
`selection` and `blender_data`.

**A proposed signature for the resolver, as a starting point:**

```python
subject, resolved_by, message = subject.resolve_subject(
    requested_name, not_done="nothing was generated")
basemesh, subject, resolved_by, message = subject.resolve_basemesh(
    services, requested_name, not_done="nothing was changed",
    not_a_character="there are no targets to set")
```

`not_done=None` is the reading form: no clause is added. The phrase in `not_a_character` absorbs
the extra clause that `add_asset`, `add_rig` and `set_skin` use. For example, "there is nothing to
equip, since mesh assets attach to a basemesh" replaces a sentence that currently has a semicolon
in the middle. **That rewording changes three messages**, which is beyond requirement 3's five.
Either the parameter is designed so those three come out word for word, or the three are added to
requirement 3's list. They must not change without anyone deciding it. `get_object_info`'s first
miss says "Select an object" rather than "Select a MakeHuman object", because any object is a
valid subject for it, so the subject step needs a way to express that as well.

The same pattern works on the tool side. `validated_name(name, required_because=...)` takes the
three required-name tools' explanations as a phrase at the call site. The empty-text validator
already takes its `hint` that way.

### Pitfalls

- **Refusal order.** `save_preset` and `save_expression` do not stop at a subject miss. They
  record it in `request.subject_message` and go on to validate the name and the file, and
  `_refusal` then decides which refusal to report. `add_rig` resolves the rig identifier before
  it refuses on the subject. The shared resolver must return values. It must not raise and it must
  not short-circuit, so that each command keeps the order it has now. Requirement 4 includes this.
- **`str(requested_name)` in the message** exists so that a non-string name cannot crash the
  formatting. The tool side makes that impossible, but a socket can be reached by other clients
  (see [both ends validate](../../specifications/architecture.md#both-ends-validate-deliberately)).
  Keep it.
- **`get_object_info`'s `resolved_from` vocabulary is not fixed here.** Renaming a response key,
  or changing `"active_object"` to `"active"`, breaks any caller that reads it, and this effort
  promises that no field changes. The resolver returns `"active"`, and `get_object_info` maps it
  at its own call site. The mapping should carry a comment that points at the NEXT_STEPS entry
  from requirement 11.
- **The three public `as_path` exports have callers in other modules.** Find them with grep before
  removing the exports. A shared module importing from another shared module is fine. A command
  importing `as_path` from `rig_lookup` only because it happens to be there is the drift this
  effort removes.
- **Four reaches have no fallback, and the shared function has to decide what happens to them.**
  `get_face_units`, `set_face_units`, `get_character_summary` and `expression_divergence` read
  `FaceService`'s `ARKIT_FACEUNITS` (and `FACEUNIT_REGIONS`) as plain attributes, so a rename in
  MPFB raises inside the handler ([census.md](census.md#mpfbs-unpublished-surface)). There are two
  options. One is to give them a fallback and a refusal that names what is missing. The other is
  to give the shared function a *required* form, and write the exception into the architecture
  rule that says "always with a fallback". Either is defensible. Routing them through the shared
  function unchanged, so that it silently adopts one behaviour, is not.
- **Reconciling two variants is a behaviour change, even when it looks cosmetic.** `_object_names`
  wraps each name in `str()` in one copy and not in the others. `_dotted` checks for a tuple or a
  list in `get_status`, and only for `None` in the two MPFB copies. Pick the stricter form, note
  the choice in the commit, and let the snapshot confirm that nothing a caller sees has moved.
- **The unit tests do not pin refusal sentences.** Almost all of them assert `ValueError` and
  nothing about its text, so the 428 passing after the tool-side move proves the verdicts and not
  the wording. The sentence diff under [Tests](#tests) exists to cover that gap.
- **`_shapekey_present` is not a duplicate**, even though the census lists it as one. The
  `get_face_units` version returns a bool and the `set_face_units` version returns a value. It
  goes in `KEPT`. Do not merge the two.
- **FR 035 moved every bridge test file**, and is `Done`, so this effort's new tests go straight
  into the layers FR 035 created (see [Tests](#tests)). The layer rule is in
  [testing.md](../../specifications/testing.md#two-harnesses-split-at-the-directory-boundary).

## Affected specifications

- [architecture.md, "Shared modules, and what warrants one"](../../specifications/architecture.md#shared-modules-and-what-warrants-one):
  **this is the main change.**
  - Replace the restraint with [the rule, restated](#the-rule-restated).
  - Replace the "being identical is not by itself a reason" paragraph and its deleted-payload
    census with this census.
  - Add warrant bullets for subject resolution and selection restore. Both are conventions that
    many commands must follow identically, which is the `performed.py` case. Add one for the
    unpublished surface, which is a rule that fails silently.
  - Replace the FR 034 bullet's "the other resolvers were not consolidated (see NEXT_STEPS)", which
    this effort makes false.
  - Check "What the bootstrap used to bind above a fragment is a parameter here". It explains the
    present by the past, and it may now belong in HISTORY.md.
  - Drop the "there are thirteen" count, or say that it follows from the rule.
- [architecture.md, "Reading module-level names MPFB does not publish"](../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish):
  the three rules now live in one shared function. Say which one, and record the decision on the
  four face-unit reads.
- [tool-interface.md, "Validate before crossing the socket"](../../specifications/tool-interface.md#validate-before-crossing-the-socket):
  the shape rules now live in one module on this side. Say which one.
- [mutating-tools.md, "Where these rules are enforced"](../../specifications/mutating-tools.md#where-these-rules-are-enforced):
  "The far side, in both copies" becomes the shared resolver, and the selection row names the
  shared construct. Also check the claim next to it, "no rule in this document changed when those
  commands were written", which should still be true.
- [tool-interface.md, "How a tool addresses an object"](../../specifications/tool-interface.md#how-a-tool-addresses-an-object):
  the paragraph on "whatever is active" says how the subject is read. Add that it is read in one
  place.
- [testing.md](../../specifications/testing.md#two-patterns-for-a-claim-about-more-than-one-command):
  add the subject-resolution composite test as a third example of "two commands agree", with
  eighteen commands instead of two.
- The root [CLAUDE.md](../../CLAUDE.md), because the layout changes. The `bridge/mpfb_bridge/shared/`
  row says "Thirteen modules" and names what they share. The package module table gains the
  validator module, and "What is validated on this side of the socket" can point at it rather
  than describing each rule from scratch.

## Tests

**The unittest suite still reports every existing test passing**, and no existing test has its
assertions edited. There are 428 today. The new tool-side module gets its own test module,
following [the exception for what is entirely on this side of the socket](../../specifications/testing.md#the-exception-what-is-entirely-on-this-side-of-the-socket).
It tests each validator directly, including the parameters that carry a tool's own wording.

**Refusal sentences, before and after: `tool_refusals.py`, in this subdir.** For every registered
tool, it calls the tool with each invalid argument shape the tool's validators reject: a wrong
type, an empty string, a non-`bool` flag, a negative count and a `bool` count. `backend.send` is
replaced by a function that fails the script if it is ever reached. It writes every `ValueError`
sentence to a JSON file with sorted keys. Run it before the tool-side commit and again after it.
The diff must be empty. It needs no Blender, and it moves to `done/` with this request.

**The bridge suite gains tests at two layers.** This assumes FR 035's layout:

- **`bbb_shared/`**, which FR 035 reserved and did not create, is created here. It holds direct
  tests of the new shared modules. Those modules are new code, and each is small enough to test
  without going through dispatch. The subject resolver, the selection construct and the plain
  Blender reads need `bpy` but no MPFB, apart from the basemesh step. This does **not** also take
  on direct tests for the thirteen existing shared modules. FR 035 recorded that as a separate
  effort ([NEXT_STEPS.md](../NEXT_STEPS.md#direct-tests-of-the-bridges-shared-modules)), and it
  stays one.
- **`eee_composite/subject_resolution_test.py`** dispatches all eighteen subject-taking commands in
  each of the three miss states: nothing active, a name that does not exist, and an object with no
  basemesh (a plain cube). For every command it asserts the same `found`, `subject_name` and
  `subject_resolved_by`, and that the message starts with the shared sentence. This is the "two
  commands agree" pattern from testing.md, and it keeps the resolver shared after the reason for
  sharing it is forgotten. The census shows it covers a real gap: only seven of the eighteen
  commands test even one miss today, and only two test the nothing-active miss.

**Live check: a snapshot diff, in this subdir.** `snapshot.py` follows FR 034's `live_check.py`.
It starts a headless Blender with the bridge on a spare port, using the Blender from
[local_environment.md](../../local_environment.md), and writes a JSON snapshot with sorted keys for
each of these:

- all eighteen commands in the three miss states;
- every read-only command among them on a real character;
- `set_macro_details`, `set_targets` and `symmetrize_targets` (with `dry_run`) on a real
  character, because those are the answers requirements 5 and 6 touch;
- `get_status`, `get_mpfb_status` and `list_urls`, for the version strings requirement 9 touches;
- `add_asset` and `remove_asset` on a real character, since both read vertex groups and object
  names through what requirement 9 moves.

Take the snapshot once before the first commit, then once after each bridge-side group lands. The
diff for every group should be empty, except for the subject resolver's, which should name exactly
the sentences requirement 3 lists. The script and its before-and-after snapshots move to `done/`
with this request.

**No smoke item** is added to [verification/](../../verification/), because no tool is added. Run
the smoke run once at the end anyway. It is under 2 s, and it is the only check that goes through
the real MCP tools.

**`census.py --check` is this request's structural check.** Run it at the end. It needs no
Blender.

## References

- [NEXT_STEPS.md: "Basemesh resolver and other code duplications"](../NEXT_STEPS.md#one-basemesh-resolver),
  where this request came from.
- [census.md](census.md) is the full census and gives the verdict and reason for each group.
  [census.py](census.py) is the script that produced it. The script reads source only and needs
  no Blender.
- Where the old restraint came from:
  - FR 013's [review](../done/013-live-verification/review.md#is-the-duplication-a-risk-or-an-economy),
    which called sixteen identical payload helpers "an economy, not a risk".
  - [FR 015](../done/015-fourth-shared-fragment/README.md), which applied that judgement.
  - [FR 002](../done/002-codegen-structure/README.md) and
    [FR 017](../done/017-category-table-cost/README.md), for what a fragment cost when it was
    pasted into every program.
  - [shared/__init__.py](../../bridge/mpfb_bridge/shared/__init__.py), for the seven modules that
    mirror a deleted fragment "name for name".
- [FR 034](../done/034-character-summary/README.md) moved the first resolver into
  `macro_reading.py`, and its `live_check.py --snapshot` is the model for this request's live
  check.
- [FR 035](../done/035-bridge-test-layers/README.md) reserved `bbb_shared/`, which this request creates.
- [shared/refit_blocker.py](../../bridge/mpfb_bridge/shared/refit_blocker.py) is the precedent for
  sharing the condition and keeping the wording per command.
