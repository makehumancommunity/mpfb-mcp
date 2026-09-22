# Creation and modification migrated

**Status:** In progress

This is [stage 3 of the pivot](../NEXT_STEPS.md#3-creation-and-modification-migrated), and it is
the last one that adds. [FR 030](../done/030-backend-seam/README.md) built the seam and migrated
`mpfb_list_objects`; [FR 031](../done/031-introspection-and-catalogues-migrated/README.md) migrated
nine more and finished the read-only half of the package. **Fifteen tools are left, and they are
the half that changes things**: thirteen mutating tools, plus `mpfb_list_urls` and
`mpfb_list_docs`. Fourteen bridge commands are needed — `mpfb_list_docs` answers from a local
table and never crosses the socket, so it has nothing to migrate and nothing to prove.

**The size is roughly 2.4× FR 031.** Fourteen payloads totalling 5,450 lines and the two remaining
shared fragments (`performed.py`, `refit_blocker.py`, 113 lines) become add-on code, against
fifteen client-side test modules totalling 6,221 lines whose payload layer — about 60%, the rate
FR 031 measured — stops being where the claim is checked. FR 031 was explicit that it establishes
**nothing** about a tool that changes a character, and this request is planned as though it had not
happened in that respect: mutation, batching, writing outside the `.blend`, restoring what the
caller had selected, and preconditions that must come back as answers are all new here.

**What makes it startable now is that the seam is finished.** `backend.send()` already carries
`shared` and `cached_shared`, `shared_cache` already sits below the seam, and
`bridge_connection.send_command()` already raises `ConnectionError` in exactly the situations
`connection.send_code()` does — which is what `mpfb_list_urls`, the one tool that answers *because*
Blender is unreachable, needs in order to migrate at all.

**And what makes it worth doing as one request rather than two is what comes after it.**
[FR 033](../033-retire-the-generated-code-path/README.md) cannot start until every tool with a
payload has a bridge command; its first requirement is the check that says so. This request exists
to make that check pass.

## Goals

**Primary. Migrate fourteen tools**: `mpfb_create_human`, `mpfb_set_macro_details`,
`mpfb_refit_human`, `mpfb_set_targets`, `mpfb_symmetrize_targets`, `mpfb_add_rig`,
`mpfb_generate_rigify_rig`, `mpfb_add_asset`, `mpfb_remove_asset`, `mpfb_set_skin`,
`mpfb_save_preset`, `mpfb_create_human_from_preset`, `mpfb_set_asset_material` and
`mpfb_list_urls`. After this effort `MIGRATED_COMMANDS` has twenty-four entries, which is every
tool that crosses the socket.

**Primary. Establish what a *mutating* command owes its caller, once, so that fourteen commands do
not answer it fourteen ways.** [mutating-tools.md](../../specifications/mutating-tools.md) is
already written and does not change; what is new is where each of its rules is enforced now that
the far side is ordinary add-on code rather than a program assembled for one call — the `performed`
flag, the before/after report, restoring the caller's selection, a precondition that is an answer
rather than a failure, and a batched tool resolving every entry before writing any.

**Primary. Migrate the last two shared fragments.** `performed.py` is named by all thirteen
mutating tools and `refit_blocker.py` by the four refitting ones. When they land,
`bridge/mpfb_bridge/shared/` holds seven modules, `codegen/shared/` has no fragment without a
counterpart, and [tests/test_fragment_drift.py](../../tests/test_fragment_drift.py) straddles
nothing — every pair it was built for has both halves migrated.

**Primary. Find out how much of MPFB works in a headless Blender.** FR 029 named this as
explicitly unestablished and nothing since has needed to know. This effort does: a bridge test for
`mpfb_generate_rigify_rig` runs a Rigify operator in `blender --background`, and operators in
background mode are where this kind of migration usually breaks. It is the single largest schedule
risk here and is addressed first (see [Architecture](#architecture)).

**Secondary. Flip the default backend to the bridge at the end of the effort**, after the live
check passes. The generated path stays and stays working; it simply stops being what an
unconfigured install uses. FR 033 deletes a path that has been unused for a while rather than one
that was carrying every call until the commit before.

**Explicitly not goals.** Deleting anything on the generated path — that is FR 033 entire, and the
frozen payload layers stay frozen here. Changing any tool's name, arguments, description or answer.
Adding a tool. Refactoring a payload on its way across: FR 030's rule that a command **reproduces
its payload rather than tidying it** is unchanged and matters more here, because the quirks being
reproduced now have side effects.

## Functional requirements

1. **Fourteen commands, one module each, one entry each in
   [commands/table.py](../../bridge/mpfb_bridge/commands/table.py).** The shape FR 029 settled is
   unchanged: a handler, a parameter specification, a `requires_mpfb` flag and a summary. A
   migrated tool's own module changes by one call — `codegen.assemble()` plus `send_code()` becomes
   `backend.send()` — and nothing else, which is FR 030's requirement 3 applied twelve more times.
   Twelve tools still call `codegen`/`send_code` directly today; they move onto the seam **as they
   migrate**, not in bulk, for the reason FR 031 gave.

2. **`performed` and the refit blocker become shared modules, and the two sides are checked against
   each other.** `bridge/mpfb_bridge/shared/performed.py` and `refit_blocker.py`, mirroring
   `codegen/shared/` name for name as the other five do, and added to
   [test_fragment_drift.py](../../tests/test_fragment_drift.py)'s comparison. `performed.py` is the
   one fragment that binds nothing from the bootstrap, so it should compare with no normalisation
   at all; anything the check cannot cover is **named in `UNCOMPARABLE`** rather than skipped,
   which is the rule that test already enforces on itself.

3. **A mutating command reports what it changed, in the spelling
   [mutating-tools.md](../../specifications/mutating-tools.md) already fixes.** Concretely, and
   these are the ones a reimplementation loses quietly:

   - **`performed` means the same thing on both transports**, for all thirteen — it is the flag a
     caller branches on and the reason the fragment exists.
   - **A precondition is an answer, not an exception.** `mpfb_refit_human` detects the
     generated-Rigify-rig-with-no-meta-rig case that `HumanService.refit()` reports only through an
     `operator` the bridge does not have either; the detection moves, the reporting stays a
     successful envelope with `performed: false`.
   - **The caller's selection and active object are restored**, which roughly thirteen payloads do
     today with no shared fragment behind it, and `mpfb_generate_rigify_rig` explicitly cannot —
     it reports `active_object_after` instead. **Reproduce that spread rather than factoring it**:
     a concept that was never a fragment does not become one in the same effort that migrates it,
     because the comparison in requirement 8 is only meaningful against code that behaves the same.
     If it is worth factoring afterwards, that is a line in NEXT_STEPS.md.
   - **`mpfb_set_targets` resolves every entry before writing any**, which is the whole of what
     makes a batched mutating tool safe to offer.
   - **A tool that writes outside the `.blend` keeps its four properties** — a name and never a
     path, the name validated on this side of the socket, `overwrite: False`, and the absolute path
     in every answer. `mpfb_save_preset` and `mpfb_create_human_from_preset` are the two, and the
     preset-name rule then exists in three places with all three live: `preset_names.py`,
     `codegen/shared/preset_files.py` and the bridge module. `test_codegen.py` already runs all
     three over one table of names and keeps doing so until FR 033.
   - **`mpfb_create_human_from_preset`'s failure is not a no-op.** It builds a character in stages
     and names what a mid-way failure left behind in `objects_created`. A command that raises out
     of the middle and lets the dispatcher turn it into `command_failed` loses that, and it is the
     one place in the package where losing it is dangerous.

4. **`mpfb_list_urls` migrates, keeps answering when nothing is running, and its command declares
   `requires_mpfb=False`.** It is the third command to do so, after `get_status` and
   `get_mpfb_status`, and for the same reason: its answer is most valuable precisely on the
   install that cannot run anything. Three specifics:

   - **The merge stays on the client.** The payload returns raw material — a `URL_`-prefixed
     mapping and enough state to explain a miss — and `tools/list_urls.py` merges it against the
     vendored copy. The *stated* reason for that split is the 4 KB chunk, which the bridge removes;
     the *real* reason survives the transport unchanged, and the request should say so rather than
     let the expiring half of the argument take the other half with it: the same merge has to run
     in all four states, including the one where Blender is unreachable and no command runs at all.
     One implementation, used in four states.
   - **The command reads `<root>.ui.weburls` out of `sys.modules` and never imports it.** Being an
     add-on makes importing it possible for the first time, which is exactly why this must be
     written down: it would violate
     [Never import MPFB submodules directly](../../specifications/architecture.md#never-import-mpfb-submodules-directly)
     and would run MPFB code inside a Blender that is already broken. Enumeration stays by prefix,
     and a non-string value stays reported under `skipped_keys`.
   - **A handshake refusal is not a `ConnectionError`.** `bridge_connection.send_command()` raises
     `ConnectionError` when the bridge is unreachable — which is what the tool's existing `except`
     catches — but an incompatible protocol version comes back as an *error envelope* instead. On
     that path the tool would report an error where the generated path reported a fallback answer.
     Decide it deliberately and state the decision in the tool's docstring; this request's
     recommendation is that a refusal is a configuration fault worth surfacing rather than papering
     over with vendored URLs, which means the behaviour differs between the two transports in one
     narrow case and the live check (requirement 8) must expect that rather than flag it.

5. **`mpfb_set_asset_material` keeps its reimplementation.** It has no service function behind it —
   the mechanism exists only in a UI operator, and three of that operator's quirks are reproduced
   rather than tidied. FR 028 established that the tool survives the pivot; the temptation being an
   add-on creates is to import the operator module now that it is reachable, and the answer is the
   same rule as requirement 4's second bullet, applied to its worst case. See
   [A UI module with no service behind it](../../specifications/architecture.md#a-ui-module-with-no-service-behind-it).

6. **Fourteen bridge test modules, against a real MPFB, following FR 031's conventions** — build
   the character with `HumanService.create_human()`, snapshot and delete on the way out, build the
   fixture tree rather than depending on what the developer has installed, redirect
   `LocationService` rather than writing into their real config directory, and skip **with a
   reason** where the install lacks a prerequisite. Two things are new and both need a decision in
   this effort rather than per module:

   - **Cleanup after a mutating command is the suite's own risk now.** A read-only command could
     not leave anything behind; these add rigs, equip assets, create materials and write preset
     files. The fixture must remove what a test made even when the test fails, and a test that
     writes outside the `.blend` must write somewhere redirected.
   - **The alphabetical prefix convention runs out.** `bridge/test/tests/` uses `aaa_`…`ooo_` and
     fifteen are taken; fourteen more need `ppp_`…, and there are eleven left before `zzz_`. Settle
     it once — MPFB prefixes *directories* as well as files, which is the obvious way out — rather
     than discovering it at the twelfth module.

7. **Both paths keep working, and the default flips at the end.** Every tool answers on both
   transports for the whole effort; the last commit changes `preferred_backend()`'s default from
   `blender_mcp` to `bridge`, and with it the documented invocations in
   [CLAUDE.md](../../CLAUDE.md#commands) and [verification/README.md](../../verification/README.md).
   The two-add-on prerequisite for a bridge-configuration verification run does **not** go away
   here — the harness's own bookkeeping still uses `send_code()` until FR 033 rewrites it — so
   flipping the default makes that prerequisite the *default* one. Say so in
   `verification/README.md` rather than leaving it to be met as a puzzle, and note that it is the
   last effort in which it is true.

8. **The two paths are compared against one Blender, field by field, for all fourteen.** This is
   FR 030's claim and FR 031's method, applied to tools that change things — which makes it harder
   in one specific way: a mutating tool cannot be run twice against the same state and compared.
   The comparison has to be *same starting state, one call each, compare the answer and the scene*,
   which the scratch-scene discipline in [verification/](../../verification/) already provides the
   shape for. Differences that are expected must be declared in advance rather than explained
   afterwards — requirement 4's handshake case is one, and MPFB's own caches are another, as
   FR 031 found for `mpfb_list_asset_materials`.

9. **The specifications are updated for what is true when it lands**, per the
   [lifecycle](../CLAUDE.md#lifecycle), and one claim in particular is now the *majority* case
   rather than a special one: [testing.md](../../specifications/testing.md#a-migrated-tool-is-tested-where-it-runs)'s
   "a migrated tool is tested where it runs" stops describing ten tools and starts describing
   twenty-four.

## Non-functional requirements

**Reproduction over improvement, and it is stricter here.** Every earlier stage said this; this is
the stage where breaking it has side effects on a user's `.blend` rather than a different-looking
answer. A quirk found on the way across is documented in the command module and left alone; if it
is a genuine defect, it is a line in NEXT_STEPS.md or a filing against MPFB, not a fix folded into
a migration.

**Staged in batches, each landing green.** FR 031 ran A–D over nine tools and that worked; fourteen
needs the same discipline more. The suggested grouping is in [Architecture](#architecture).

**Honest reporting of what the headless suite cannot reach.** Some of these commands will not be
fully testable in `blender --background` — Rigify is the likely one. A skip with a reason is an
acceptable outcome and a silent pass is not, and whatever ends up unreachable there is what the
effort's own live check has to cover instead.

**No regression in what an MCP client sees.** Same tool names, same descriptions, same envelopes,
same description budget.

## Architecture

**Do the Rigify spike first, before any migration.** `mpfb_generate_rigify_rig` calls an operator,
and operators in `blender --background` fail for context reasons that have nothing to do with this
project's code. The answer changes the shape of requirement 6 for at least one command and possibly
three, and it is a day's work to find out at the start and a disaster to find out at the end. What
the spike must answer: whether Rigify can be enabled in the test Blender at all, whether its
generate operator runs headless, and whether `mpfb_add_rig`'s and `mpfb_add_asset`'s paths through
MPFB use operators anywhere.

**A suggested batching**, smallest risk first, each batch landing with both paths working:

- **A — the cheap ones, and the two fragments.** `mpfb_create_human` (40-line payload, and it
  carries `performed.py`) and `mpfb_refit_human` (which brings `refit_blocker.py`). Between them
  they land both remaining fragments and the first mutating command, which is where the
  before/after and `performed` conventions get settled.
- **B — the modeling tools.** `mpfb_set_macro_details`, `mpfb_set_targets`,
  `mpfb_symmetrize_targets`. The batched one and the destructive one are here; `set_targets` is the
  largest payload in the package at 711 lines.
- **C — rigs and assets.** `mpfb_add_rig`, `mpfb_generate_rigify_rig`, `mpfb_add_asset`,
  `mpfb_remove_asset`. This is where the spike's answer lands, and where `rig_lookup.py` and
  `asset_sections.py` stop straddling.
- **D — materials.** `mpfb_set_skin`, `mpfb_set_asset_material`.
- **E — the file writers and the odd one.** `mpfb_save_preset`,
  `mpfb_create_human_from_preset`, `mpfb_list_urls`. The two preset tools go together because they
  are the only place the JSON one writes and the other reads is checked against itself.
- **F — the default flips** (requirement 7), after the live check.

**Pitfalls:**

- **`mpfb_list_docs` is not in any batch.** It has no payload and never crosses the socket; the
  only thing this effort owes it is not accidentally giving it a command. FR 033's precondition
  check must treat it as the one legitimate exception, which is how it is already written.
- **The frozen payload layers stay frozen.** Do not extend a payload test to cover something a
  command now does; the whole point of the freeze is that the payload's tests stop being the place
  the claim lives. What they still do is hold up half of requirement 8's comparison.
- **`test_fragment_drift.py` grows here and dies in FR 033.** Add the two fragments to it anyway —
  it is what keeps requirement 2 honest for the weeks it exists, and a check that is skipped
  because it will be deleted later is how the last straddling pair breaks.
- **The seam's `MIGRATED_COMMANDS` is the progress bar.** Twenty-four entries is the finish line,
  and FR 033 reads it as a precondition rather than taking anybody's word for it.
- **Do not let this effort start deleting.** Every line of the generated path stays working until
  FR 033. The two efforts have opposite risk profiles and reviewing them as one series loses that.

## Affected specifications

- **[testing.md](../../specifications/testing.md)** — *A migrated tool is tested where it runs*
  becomes the normal case (requirement 9); the 60% rate is confirmed or corrected over fourteen
  more modules; whatever the Rigify spike finds about a headless Blender belongs in *What the suite
  can never establish*.
- **[mutating-tools.md](../../specifications/mutating-tools.md)** — no rule changes, but every rule
  in it acquires a second implementation. Where a rule turns out to be enforced by the transport
  rather than by the tool, say which.
- **[architecture.md](../../specifications/architecture.md)** — *The generated-code path* section's
  count of what has migrated; *Supporting a second backend*'s description of the default;
  *Never import MPFB submodules directly* and *A UI module with no service behind it* gain the two
  cases in requirements 4 and 5, which are the first time the rule has been under real pressure.
- **[mpfb-integration.md](../../specifications/mpfb-integration.md)** — the coercion and
  pick-one-and-name-it rules are mostly enforced in the tools being migrated; confirm each survives
  the move rather than assuming it.
- **[vision.md](../../specifications/vision.md)** — *What runs today* is rewritten once at the end.
- Not affected: [responses.md](../../specifications/responses.md),
  [tool-interface.md](../../specifications/tool-interface.md),
  [observability.md](../../specifications/observability.md) — response shape, argument validation
  and the record are all unchanged by which transport carries a mutating call.

## Tests

**Client-side**, in `tests/`: each migrated tool gains a thin bridge-path class and its payload
class is marked frozen, exactly as the ten migrated tools' modules already read. Nothing is
deleted. `test_fragment_drift.py` gains two fragments (requirement 2). `test_backend.py` gains the
default flip (requirement 7), asserted by which fake server was spoken to.

**Bridge-side**, in `bridge/test/tests/`: fourteen modules (requirement 6), which is where
everything about what these tools *do* is now checked, against a real MPFB in a headless Blender.

**And a live check of this effort's own**, in this subdir as `check_creation_migration.py`,
following [FR 031's](../done/031-introspection-and-catalogues-migrated/check_catalogue_migration.py):
it needs a Blender with MPFB, blender_mcp and the MPFB Bridge, and it runs each of the fourteen
tools on both transports from the same starting state, comparing the answer **and** the resulting
scene (requirement 8). It must declare its expected differences up front. It is run during the
effort and moves into `done/` with it.

What it adds to [verification/](../../verification/) is **nothing**: no tool is introduced, and the
twenty-five smoke items already cover these fourteen. What must be true before the effort is
finished is that the smoke run passes in both configurations — which, after requirement 7, means
the bridge configuration is the one somebody gets by typing nothing.

## References

- [NEXT_STEPS.md, stage 3](../NEXT_STEPS.md#3-creation-and-modification-migrated) — the entry this
  request implements.
- [FR 033](../033-retire-the-generated-code-path/README.md) — the effort this one unblocks, whose
  first requirement is the check that this one has finished.
- [FR 030](../done/030-backend-seam/README.md) — the seam, the first migration, and the rule that a
  command reproduces its payload.
- [FR 031](../done/031-introspection-and-catalogues-migrated/README.md) — nine migrations, the
  batching that worked, `bridge/mpfb_bridge/shared/`, the fragment-drift check, and the 60% rate.
- [FR 029](../done/029-bridge-transport-and-skeleton/README.md) — the command record, the
  `requires_mpfb` precondition, and the headless drive mechanism this effort's tests run on.
- [FR 025](../done/025-character-presets/README.md) — the settled shape for a tool that writes
  outside the `.blend`, which requirement 3 asks two commands to preserve.
