# Listing and applying expressions

**Status:** Accepted

> **Written against the generated-code path, and that is still correct.**
> [FR 028](../done/028-pivot-to-specific-addon/README.md) decided that MPFB's Blender-side logic
> moves into a bridge add-on, [FR 029](../done/029-bridge-transport-and-skeleton/README.md) built
> the add-on out to where commands can be added to it, and
> [FR 030](../done/030-backend-seam/README.md) built the seam on mpfb-mcp's side and migrated
> exactly one tool across it. Twenty-four tools — including every tool this request touches — are
> still on the generated-code path, and in the default configuration so is the twenty-fifth, so a
> payload, a shared fragment and `send_code()` all still mean what they mean here.
>
> Two things to weigh, neither of which needs this text rewritten. **Scheduling**: a tool that
> lands before [the migration](../NEXT_STEPS.md#a-larger-pivot-an-mpfb-specific-bridge-add-on)
> reaches its capability area is a tool the migration then has to carry — a reason to sequence,
> not a reason to wait. And **there is now a choice**: a new tool could be written as a bridge
> command from the start, registered in `backend.MIGRATED_COMMANDS`, rather than as a payload to
> be migrated later. Whether that is worth doing depends on when this request runs relative to its
> capability area's migration stage, and it is that request's call to make explicitly rather than
> by default.


[FR 026](../026-face-units/README.md) gives an agent the 52 ARKit face units and nothing to do with
them but compose from scratch, unit by unit, every time. MPFB's users do not work that way: an
expression is a **named, saved, weighted combination** — a `smile`, an `angry-shout` — stored as a
JSON file in an asset library, applied at a strength, and stacked with others. That library is what
`ui/apply_assets/useexpression` exposes, and none of it is reachable today.

This request scopes three tools over the **library** half of
[`FaceService`](../../../mpfb2/src/mpfb/services/faceservice.py): one to list what is installed, one
to read what a character is currently wearing, one to change it. It also **extends both of
FR 026's tools**, because the mechanism it exposes silently destroys what they write and that has to
become visible.

It is written to follow FR 026 and depends on it. See
[The dependency, and what happens if the order reverses](#the-dependency-and-what-happens-if-the-order-reverses).

Three boundaries carry over from FR 026 unchanged and are not up for rediscovery: **authoring is out
of scope** (no tool writes an expression file — see
[FR 026's transience section](../026-face-units/README.md#a-composed-face-is-transient) and the
`mpfb_save_expression` entry queued behind it); **visemes and lip sync are out of scope**; and
**`mpfb_set_targets` is left alone**.

## Goals

**Primary:** an agent can find out what expressions are installed, put a character into one at a
chosen strength, blend several, read back what it is wearing, and take them all off — addressing
expressions by an identifier that means the same thing on another machine.

**Secondary:**

- Make the composer/library conflict **visible in a response** rather than discoverable by losing an
  expression to it. This is the requirement the effort turns on; see
  [Two mechanisms, one set of shape keys](#two-mechanisms-one-set-of-shape-keys).
- Complete the round trip [FR 025](../done/025-character-presets/README.md) opened: a preset already
  serializes the applied-expressions stack, so once these tools exist an agent can save a character
  wearing an expression and get it back.
- Confirm and, if warranted, file the defect below in the shape
  [FR 019](../done/019-file-mpfb-defects/README.md) established.

## Functional requirements

### `mpfb_list_expressions` — what is installed

1. Returns one entry per expression JSON discovered by
   `FaceService.list_available_expressions()`, which walks `<root>/expressions/` for every root
   `AssetService.get_asset_roots("expressions")` reports, in priority order, highest-priority root
   winning a duplicate library-relative path. Each entry carries `fragment` (the library-relative
   path, **and the identifier `mpfb_apply_expressions` takes**), `path` (absolute, for a human
   reading the response), `label`, and the metadata `list_available_expressions` already parsed:
   `description`, `tags`, `author`, `license`.
2. **Reports `fragment` beside `path` and says which one is the address**, exactly as
   `mpfb_list_assets` does. The stack stores fragments, so a fragment is what round-trips between
   machines and through a preset; a path is what a human can check.
3. **Reports the roots it scanned** whether or not anything was found, so an empty answer is an
   answer. An empty list with no roots named would leave an agent unable to tell "nothing is
   installed" from "the tool looked in the wrong place" — requirement 2 of
   [FR 025's `mpfb_list_presets`](../done/025-character-presets/README.md), and the same reasoning.
4. **Reports `faceunits01_installed`**, and takes `refresh` for it, in the shape
   [FR 026 established](../026-face-units/README.md#the-asset-pack-is-a-precondition-and-mpfb-reports-its-absence-to-nobody).
   An expression file can exist while the face-unit targets it references do not; the catalogue is
   then a list of things that cannot be applied, and it must say so rather than let
   `mpfb_apply_expressions` discover it. Note that the *file scan* itself is not cached —
   `list_available_expressions` walks the disk every call — so `refresh` means the pack probe only,
   and the description says which.
5. **Not capped, not paged.** An expressions library is tens of files. The docstring says so, so a
   caller does not look for `truncated`. Revisit only if a live run finds otherwise.
6. **Reports unreadable files rather than hiding them.** `list_available_expressions` skips a file
   that fails to parse with only a `_LOG.warn`; the payload counts them and names them, because an
   expression an agent saw in MPFB's panel and cannot find here is otherwise a mystery with no
   evidence.

### `mpfb_get_expression` — what the character is wearing

7. Resolves the basemesh from any object in the character's family and answers `found: false` with a
   sentence rather than raising when it cannot.
8. Returns `applied_expressions` — the persistent stack stored on the basemesh as
   `mpfb_applied_expressions` — one `{fragment, weight}` row each, in the stored order (sorted by
   fragment; see requirement 16), plus `resolved` and the absolute `path` for each row found on
   disk.
9. **Reports a stack row whose file is gone.** `aggregate_expression_stack` skips an unresolvable row
   with a `_LOG.warn` and carries on, so a character loaded from a preset built elsewhere is quietly
   wearing less expression than its stack claims. Each row gets `resolved: true/false` and the
   response says how many were unresolvable, so the count is checkable without scanning the rows.
10. **Reports whether the stack explains the face**, and this is the requirement the tool exists for.
    Compute `FaceService.aggregate_expression_stack(stack)` and compare it against
    `read_current_expression()`; report `matches_stack`, the `aggregate` itself, and — when they
    disagree — `unexplained_face_units`, the units whose live value no stack row accounts for. That
    set is precisely the work a subsequent `mpfb_apply_expressions` call will destroy, and it is
    invisible everywhere else, MPFB's own UI included. See
    [Two mechanisms, one set of shape keys](#two-mechanisms-one-set-of-shape-keys).
11. **Does not restate the live face-unit values.** Those are
    [`mpfb_get_face_units`](../026-face-units/README.md)' answer, and two tools reporting the same 52
    numbers is two answers that can disagree. This tool reports the *aggregate* the stack implies and
    the *difference* from what is live, and names `mpfb_get_face_units` for the raw reading. The
    boundary is stated in both descriptions.
12. Reports `faceunits01_installed` and takes `refresh`, as requirement 4.

### `mpfb_apply_expressions` — wear one, or several

13. **Batched**, for the same reason FR 026's setter is: takes `expressions`, a list of
    `{fragment, weight}` dicts, weight in 0.0-1.0. MPFB's own path is one `set_stack_weight` call per
    slider, and each of those re-reads, re-aggregates and rewrites the whole stack; doing that eight
    times across the socket would be eight round trips to reproduce one saved face.
14. Takes `mode`, either `"merge"` (default — upsert each fragment into the existing stack,
    latest-wins per fragment, matching `set_stack_weight`) or `"replace"` (the stack becomes exactly
    the given rows). A weight of `0.0` **removes** that row, which is `set_stack_weight`'s own rule.
    `mode: "replace"` with an empty list is how an agent clears everything, so no fourth tool is
    needed for it — and the description says that explicitly, because it is not guessable.
    `mode` is one of the narrow local vocabulary checks, in the class
    [`mpfb_set_skin`'s `skin_type` earned](../../specifications/tool-interface.md#validate-before-crossing-the-socket);
    the authoritative check stays in the payload.
15. **Resolves every fragment before mutating the stack.** A fragment that
    `AssetService.find_asset_absolute_path(..., asset_subdir="expressions")` cannot resolve is a
    refusal — `ready: false`, `blocked_by` naming it, `performed: false`, the stack untouched —
    naming the fragments that do exist, capped, per
    [how tools name things that can be added](../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added).
    `aggregate_expression_stack` would otherwise warn and skip, producing a success response for a
    face that did not change.
16. **Writes the stack only through `_write_applied_expressions`**, never by setting the custom
    property directly. That function normalizes each row and sorts by asset; a payload that skipped
    it would produce stacks MPFB's own writes silently reorder, and two readers would disagree about
    whether anything changed.
17. **Refuses when the pack is absent**, per
    [preconditions are answers](../../specifications/mutating-tools.md#preconditions-are-answers) and
    FR 026's requirement 11. Without `faceunits01` the stack is written, `set_expression` finds no
    target file for any unit, the face does not move, and every signal an MCP tool has says it
    worked. This is the worse case of the two, because the stack write **persists** — the character
    is left claiming to wear an expression it has never displayed.
18. **Reports what the aggregate clamped.** `aggregate_expression_stack` sums
    `file_weight * row_weight` per unit and clamps to `[0, 1]`. Two expressions that both open the
    jaw saturate, and an agent that then raises a weight and sees no change has no way to find out
    why. `clamped_face_units` names them.
19. **Reports what it discarded.** If the live state diverged from the stack before the call
    (requirement 10's condition), that composed work is gone — `clear_expression` runs
    unconditionally inside the rebuild. The response names the discarded units. **It does not
    refuse**: an agent that composed a face and then applies a library expression has, on the most
    natural reading, changed its mind. The effort should confirm this against a real session rather
    than treat it as settled; if refusal turns out to be right it needs an override argument, and
    that is a description-budget cost requirement 25 has to fund.
20. Takes `refit` (a real `bool`, default `True`, matching the library panel's `auto_refit`) and uses
    [`refit_blocker.py`](../../src/mpfbmcp/codegen/shared/refit_blocker.py), taking that fragment
    from five payloads to six. `performed` is stamped via
    [`performed.py`](../../src/mpfbmcp/codegen/shared/performed.py).
21. **Returns the resulting aggregate and the resulting stack**, so a caller does not need a second
    call to learn what it is now wearing.

### What this request changes in FR 026

22. **`mpfb_set_face_units` gains the computed divergence warning.** FR 026's requirement 15 puts a
    static sentence in that tool's description saying a composed face is transient. This effort
    replaces it with a computed one: after the write, report `matches_stack: false` and name
    `mpfb_apply_expressions` as the thing that will overwrite it, with the aggregate comparison
    requirement 10 defines. The static sentence stays in the description — it is still true, and it
    is what an agent reads *before* calling.
23. **`mpfb_get_face_units` gains nothing.** It is deliberately left reporting only live values; the
    stack view is `mpfb_get_expression`'s, per requirement 11. Recorded here so the asymmetry reads
    as a decision rather than an omission.

## Non-functional requirements

24. **The conflict must be visible without being alarming.** Every one of requirements 10, 19 and 22
    exists because MPFB destroys work without saying so. The responses must make that legible in the
    normal case — where nothing was composed, `matches_stack` is `true` and there is nothing else to
    read — and loud only when there is genuinely something to lose. A tool that warns every call
    trains an agent to ignore it.
25. **Description budget.** Three tools, and two of them have to instruct about a two-layer model
    FR 026 also instructs about. The conflict is explained **once**, in `mpfb_set_face_units` (which
    FR 026 already spends the bytes on), and the other tools point at it rather than restate it. The
    ceiling change is recorded with its reason beside it in
    [`test_description_budget.py`](../../tests/test_description_budget.py).
26. **Robustness: a refusal is never a partial write.** The pack check and every fragment are settled
    before `_write_applied_expressions` or `set_expression` is called. MPFB's own
    `apply_expression_file` sets the precedent — it validates the file up-front "so we don't mutate
    the stack on a bad file" — and this payload follows it rather than relying on it.
27. **Cost.** All three programs are small — one 4 KB chunk each, one timer tick. Inside Blender the
    picture is uneven and the descriptions should not flatten it: listing walks the disk every call;
    `mpfb_apply_expressions` re-loads and re-aggregates **every file in the stack** on every call, so
    a five-expression stack is five JSON reads per weight change. Batching (requirement 13) is what
    keeps that at one rebuild per call rather than one per expression.

## Architecture

### Two mechanisms, one set of shape keys

This is the single most important thing the effort has to get right, and this request owns it
because it implements the half that does the damage.

The **composer** ([FR 026](../026-face-units/README.md)) writes the 52 `!ex-` shape keys directly.
The **library** — this request — never writes a shape key from a user action at all. It maintains a
stack of `{asset, weight}` rows in a custom property on the basemesh, and every change re-derives
the whole face: `aggregate_expression_stack` → `clear_expression` → `set_expression`.

The consequence is asymmetric and unsignposted. Composed work is invisible to the library, and any
library call — a weight change, an application, a preset load — **destroys it**, because
`clear_expression` runs unconditionally in the rebuild. In MPFB's UI this is survivable: the panels
are in different tabs and a human sees sliders move. Across MCP there is no such feedback.

The divergence check in requirement 10 is a comparison **MPFB never makes anywhere**, and it is
cheap: aggregate the stack, compare to the live read, subtract. That single computation funds
requirements 10, 19 and 22, which is why it is the shared fragment below rather than three
implementations.

### The dependency, and what happens if the order reverses

This request is written to land after [FR 026](../026-face-units/README.md) and uses two things from
it: the asset-pack precondition rule (requirements 4, 12, 17) and the face-unit reading that
requirement 10's comparison needs. Requirement 22 extends a tool FR 026 introduces.

If the order reverses, this effort must carry a reduced form of both: an inline pack check rather
than the standing rule, requirement 11's boundary becomes moot and `mpfb_get_expression` has to
report live face-unit values itself, and requirement 22 has nothing to extend. That is a worse
outcome — the pack rule is FR 026's durable contribution and it should be settled by the effort that
discovered it — so **the intended order is 026 then 027**, and the effort should not be started
otherwise without revisiting these three requirements.

Neither is blocked on the other for usefulness: FR 026 is complete on its own, and a character can
already end up with a non-empty stack today through `mpfb_create_human_from_preset`, which is one
reason `mpfb_get_expression` is worth having even before anything can write a stack from here.

### Reaching the stack, and one import the rules forbid

Two mechanical problems the effort must decide rather than discover.

**The stack accessors are private.** `_read_applied_expressions` and `_write_applied_expressions`
carry a leading underscore, and both `mpfb_get_expression` and `mpfb_apply_expressions` need them.
`HumanService` itself calls the first, with a `pylint: disable=W0212` — so there is precedent, and
the alternative is reimplementing the tolerant decode (the property may hold a JSON string *or* a
list) in a payload, which is a second implementation that can drift. The lean is to call the private
methods and note it in the module docstrings; `APPLIED_EXPRESSIONS_PROP` being public while its two
accessors are not is a small defect worth raising (below).

**MPFB's panel goes stale, and fixing that means importing a UI module.** The expressions-library
panel's sliders are scene properties, synced from the stack by `write_slider_values` in
`ui/apply_assets/useexpression`. `HumanService._apply_expressions_from_human_info` calls it, inside a
try/except, so that a preset load leaves the panel agreeing with the character. An
`mpfb_apply_expressions` that skips it leaves MPFB's UI showing weights the character does not have
— the "two lists that disagree" failure FR 025 named, in a place a human is looking at.

But reaching it means importing an MPFB **UI** submodule from generated code, and
[architecture.md](../../specifications/architecture.md#resolving-mpfb-from-generated-code) says never
to resolve MPFB by importing a submodule: the bootstrap's `sys.modules` scan finds the root module
and `SERVICES`, and UI modules are not in `SERVICES`. The lean is to **do it anyway**, reached by
`getattr` down from the root module the bootstrap already found, wrapped in the same `try/except`
MPFB uses, on the grounds that every other way the stack changes does this and an mpfb-mcp write
that does not would be the odd one out. If the effort decides the other way, the tool description
must say the panel needs a manual resync, and the module docstring must say the choice was made
rather than missed. **This is the sharpest open question in the request** and it should be settled
early, because it decides whether the bootstrap needs a second entry point.

### Three tool modules, three payloads, one fragment

`tools/list_expressions.py`, `tools/get_expression.py`, `tools/apply_expressions.py`, each with the
same-named payload and test module — the ordinary shape. Three `register()` calls in
[`__init__.py`](../../src/mpfbmcp/__init__.py).

**One shared fragment, `expression_divergence.py`.** The divergence computation — aggregate the
stack, read the live units, return the difference — is needed by `get_expression`,
`apply_expressions` and (requirement 22) FR 026's `set_face_units`, and it must give the **same**
answer in all three. That is exactly the bar [FR 015](../done/015-fourth-shared-fragment/README.md)
and [FR 017](../done/017-category-table-cost/README.md) set: a concept payloads would otherwise
disagree about, not merely repeat. It takes the fragment count from six to seven, and
`test_codegen.py`'s drift check must assert that no payload keeps an implementation of its own —
including `set_face_units.py`, which is the one most likely to grow one, since FR 026 ships it
without any.

The ARKit vocabulary is **not** in the fragment: as FR 026 settled, payloads read `ARKIT_FACEUNITS`
and `FACEUNIT_REGIONS` off `FaceService` through the bootstrap handle rather than carry a copy.

Use `MPFB_BOOTSTRAP` (the raising one) for all three.

### Defect candidate

To be confirmed against the running install before filing, per
[FR 019](../done/019-file-mpfb-defects/README.md), in
[`../mpfb2/features/MCP_DISCOVERED_BUGS.md`](../../../mpfb2/features/MCP_DISCOVERED_BUGS.md):

- **The applied-expressions stack has a public constant and private accessors.**
  `APPLIED_EXPRESSIONS_PROP` is public, `_read_applied_expressions` and `_write_applied_expressions`
  are not, and `HumanService` reaches across the underscore with a lint suppression. Either the
  accessors are part of the API or the constant is not. Small, but it is the difference between
  these payloads following a documented interface and copying a private one.

FR 026 carries the two substantive `FaceService` defects (`set_expression` cannot report failure;
the install-check cache is a session-long lie); neither is re-filed here.

## Affected specifications

- [mpfb-integration.md](../../specifications/mpfb-integration.md) — under
  [where MPFB's own code paths disagree](../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it):
  the composer/library split, which is the clearest instance yet — two code paths, one outcome, one
  silently destroying the other's work. FR 026's asset-pack rule is **applied** here, not extended.
- [mutating-tools.md](../../specifications/mutating-tools.md) — a mutating tool that **destroys state
  it did not create and cannot restore**, and what it owes the caller in exchange (name what went,
  before and after). Also the refitting family growing to six.
- [responses.md](../../specifications/responses.md) — reporting a **fact MPFB does not compute**
  (`matches_stack`, `unexplained_face_units`, `clamped_face_units`). The
  [derived-fact convention](../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact)
  likely covers it; check whether it needs extending or only an example.
- [architecture.md](../../specifications/architecture.md) — the
  [shared fragments](../../specifications/architecture.md#shared-fragments) list goes from six to
  seven; and, if the effort decides to reach an MPFB **UI** module, that is an exception to
  [resolving MPFB from generated code](../../specifications/architecture.md#resolving-mpfb-from-generated-code)
  and must be written down as one rather than left in a payload.
- [tool-interface.md](../../specifications/tool-interface.md) — `mode` joins the narrow list of
  locally-checked vocabularies, and the description-budget ceiling moves.
- [vision.md](../../specifications/vision.md#target-tool-catalog) — *Catalogues* 4 → 5,
  *Introspection* 6 → 7, *Creation and modification* 15 → 16 (taking FR 026's counts as the
  baseline).

## Tests

- **`tests/test_list_expressions.py`** — over a real `tempfile` expressions tree in the idiom
  `test_list_rigs.py` and `test_list_targets.py` established. Carries the same library-relative path
  in two roots (highest-priority wins), a malformed JSON file (skipped, but *counted and named*), a
  file with no `name` (label falls back to the basename with underscores replaced), and an empty
  tree. The pack-absent path asserts `faceunits01_installed: false` reaches the response.
- **`tests/test_get_expression.py`** — the divergence check is the centre of this module and needs
  four cases: stack and live agree; live has a unit no row explains (composed work); a stack row
  whose file is missing; and a stack whose aggregate clamped. Plus the requirement-11 boundary: the
  response does **not** carry a full 52-unit listing.
- **`tests/test_apply_expressions.py`** — an unresolvable fragment refusing before the stack is
  touched, asserting the custom property is byte-identical afterwards; `merge` upserting and
  `replace` replacing; weight `0.0` removing a row; `mode: "replace"` with an empty list clearing;
  the pack-absent refusal asserting **nothing was written to the stack**, which is requirement 17's
  whole point; clamping reported; and the requirement-19 case — composed units present beforehand
  are named as discarded.
- **`tests/test_set_face_units.py`** (extended, from FR 026) — the divergence field appears after a
  write, and reports `matches_stack: true` when the character has an empty stack, which is the
  common case and must not read as a warning.
- **One test running the divergence fragment through all three payloads over one character**, in the
  shape `test_get_target_stack.py` and `test_symmetrize_targets.py` already use for
  `modifier_reading.py`: apply an expression, compose a unit on top, and assert all three tools
  report the same divergence. That is what the fragment exists for and it means nothing asserted
  separately.
- **Stubs reproduce the destruction, not a convenient version of it.** Per
  [testing.md](../../specifications/testing.md), the stub `FaceService` must clear every `!ex-` key on
  a stack rebuild exactly as the real one does, and `aggregate_expression_stack` must clamp and drop
  non-positive values. A stub that preserved composed values would make the suite pass on precisely
  the behaviour requirements 19 and 22 exist to expose.
- **`tests/test_codegen.py`** — three payload entries, the new fragment, and its drift check across
  four payloads.
- **`tests/test_description_budget.py`** — ceiling raised, reason in the comment.
- **`tests/test_verification_smoke.py` and `verification/smoke.py`** — three items, with the same
  pack-absent degradation FR 026's smoke items settled. Note that a smoke item for
  `mpfb_apply_expressions` leaves a **custom property on the basemesh**, which the
  [verification README](../../verification/README.md)'s list of what the run cannot put back should
  mention.

**This effort needs a real Blender, and for more than one claim.** Three cannot be reached from this
side: that a composed face is really destroyed by the next `mpfb_apply_expressions` (requirement 19);
that an expression applied through these tools shows up correctly in MPFB's own expressions-library
panel, which is the whole question behind the `write_slider_values` decision; and that an expression
applied here survives a `mpfb_save_preset` / `mpfb_create_human_from_preset` round trip, which is the
secondary goal and the only check that establishes these tools compose with FR 025's. A script in
this subdir does all three against a character carrying a rig and a garment, prints what differed,
and moves to `done/` with the request. What stays behind is the three smoke items.

## References

- [`mpfb2/src/mpfb/services/faceservice.py`](../../../mpfb2/src/mpfb/services/faceservice.py) —
  `APPLIED_EXPRESSIONS_PROP`, `list_available_expressions`, `load_expression`,
  `aggregate_expression_stack`, `set_stack_weight`, `apply_expression_file`,
  `rebuild_expression_stack`, `clear_applied_expressions`, `_read_applied_expressions`,
  `_write_applied_expressions`, `_compute_expression_library_relative_path`.
- [`mpfb2/docs/fileformats/expression.md`](../../../mpfb2/docs/fileformats/expression.md) — the JSON
  format key by key, its `.mhpose` ancestry, and the backwards-compatibility rules a reader must
  honour.
- MPFB's own library UI, which these three tools collapse:
  [`useexpression/__init__.py`](../../../mpfb2/src/mpfb/ui/apply_assets/useexpression/__init__.py),
  which holds `_EXPRESSION_PROP_MAP`, `write_slider_values` and `refresh_expression_sliders`, and
  [`useexpressionpanel.py`](../../../mpfb2/src/mpfb/ui/apply_assets/useexpression/useexpressionpanel.py).
- [`mpfb2/src/mpfb/services/humanservice.py`](../../../mpfb2/src/mpfb/services/humanservice.py) —
  `_populate_human_info_with_expression_info` and `_apply_expressions_from_human_info`, which are
  where a preset meets the stack, and the precedent for both the private-accessor call and the UI
  import.
- [FR 026](../026-face-units/README.md) — the other half: the 52 ARKit units, the asset-pack
  precondition rule this request applies, and the two tools requirement 22 extends.
- [FR 025](../done/025-character-presets/README.md) — the preset tools this request completes the round
  trip for, and the name-not-a-path convention the queued `mpfb_save_expression` will follow.
- [FR 008](../done/008-detail-targets/README.md) — where the batched-tool idiom and the
  resolve-everything-before-writing-anything rule were settled; requirements 13 and 15 reuse both.
- [FR 019](../done/019-file-mpfb-defects/README.md) — the established shape for a defect report, and
  the rule that a candidate is confirmed against a running install before it is filed.
- [NEXT_STEPS: Expressions](../NEXT_STEPS.md#expressions) — the entry this request and FR 026 split
  between them.
