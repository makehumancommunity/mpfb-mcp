# Detail targets

**Status:** Proposed

[FR 006](../done/006-list-targets/README.md) built the catalogue an agent needs in order to find a
modeling target, and closed with the reason it exists: `mpfb_set_target_value` has to be able to
read it. That tool still does not exist. mpfb-mcp can today create a character, describe it, and
list the thousand-odd morphs that could be applied to it — and then apply none of them. Everything
below the phenotype level, which is where a character stops being a mannequin, is unreachable.

The naive shape for this — "set shape key X to value Y" — is not what MPFB's modeling sliders do,
and a tool built that way would produce characters MPFB's own UI cannot represent. A slider in
MPFB corresponds to a `target.json` **category**: a modifier running from -1.0 to +1.0, built from a
*pair* of opposing targets (`nose-flaring-decr` and `nose-flaring-incr`), where the sign selects
which of the two is loaded and the other is explicitly driven to zero. Roughly a fifth of the
categories additionally have separate `l-` and `r-` variants, giving four target files behind one
conceptual control. Shape keys themselves cannot express this: Blender clamps a shape key value to
0.0–1.0, so "flaring -0.4" has no representation except "flaring-decr at 0.4, flaring-incr at 0.0".

So this request works at both levels. The category level is what an agent should normally use and
what keeps a character consistent; the raw shape-key level is the escape hatch for the user's own
installed targets, which have no category and are addressed by the `shapekey_name` FR 006 already
reports. And because a modeling session is dozens of small changes, and every socket round trip
costs about a second, the mutating tool is batched from the outset rather than retrofitted.

## Goals

Primary: read a character's current detail-target stack, and change it — one modifier, one raw
target, or fifty of them in a single call — with the same result MPFB's own modeling sliders
produce, including the on-demand loading of target files that are not on the mesh yet.

Secondary: make left/right symmetry a first-class operation, both as a property of a change ("set
both sides") and as a repair of a stack that has drifted asymmetric.

Also: keep the catalogue and the setter honest with each other. Every identifier this tool accepts
must be one [`mpfb_list_targets`](../done/006-list-targets/README.md) reports, and vice versa.

## Functional requirements

Three tools.

### `mpfb_get_target_stack`

Read-only, always answers. Arguments:

- `name` (optional string) — subject, resolved to a basemesh as in
  [FR 007](../007-macro-details/README.md).
- `include_macro` (optional bool, default `false`) — whether to include the `$md-` macro shape keys.
  Off by default because they are [FR 007](../007-macro-details/README.md)'s subject and there are
  typically a dozen of them cluttering the answer; available because "why is this character shaped
  like that" sometimes has a macro answer.
- `include_expressions` (optional bool, default `false`) — the `!ex-` prefixed expression shape keys.
  Same reasoning; they are neither macro nor modeling targets and belong to a future expressions
  effort.
- `name_contains`, `limit`, `offset` — the filter-and-page convention from
  [How tools bound a large answer](../../specifications/architecture.md#how-tools-bound-a-large-answer).

`result` carries `basemesh_name`, `subject_resolved_by`, `found`, `message`, the paging fields, and:

- `targets` — one entry per shape key, each `{shapekey_name, decoded_name, value, kind, category,
  section, side, polarity, listed_in_target_json}`:
  - `shapekey_name` is the raw Blender name, and the address `mpfb_set_targets` takes.
  - `decoded_name` is `TargetService.decode_shapekey_name()`'s output — for anything encoded (over
    60 characters, or any macro target) the raw name is unreadable, and the decoded one is what a
    human or an agent should reason about. Both are reported because only one of them works as an
    address; this is the same split FR 006 drew between `name` and `shapekey_name`, seen from the
    other end.
  - `kind` is `"macro"` / `"expression"` / `"detail"` / `"unknown"`, from the `$md-` and `!ex-`
    prefixes.
  - `category`, `section`, `side` and `polarity` place a detail target back into the `target.json`
    modifier it belongs to — `nose-flaring-incr` is section `nose`, category
    `nose-flaring-decr-incr`, side `unsided`, polarity `positive`. `null` for a user target that is
    in no category. Without this a caller can read the stack but cannot express any of it back as a
    modifier change.
- `modifiers` — the same information rolled up the other way: one entry per *category* that has any
  non-zero target on this mesh, each `{section, category, side, value}` with `value` in -1.0..+1.0,
  computed the way `_get_opposed_modifier_value()` computes it. This is the view that round-trips
  into `mpfb_set_targets`, and the view that matches what the user sees in MPFB's panel.
- `counts_by_kind` and `counts_by_section` — the "a filtered call still reports what it filtered out
  of" clause of the paging convention.
- `asymmetries` — categories where the left and right values differ by more than a small epsilon,
  each `{section, category, left, right}`. This is what makes `mpfb_symmetrize_targets` actionable
  rather than a blind operation, and it is a fact MPFB's own UI does not surface anywhere.

### `mpfb_set_targets`

Mutating, batched. Arguments:

- `name` (optional string) — subject.
- `modifiers` (optional list) — category-level changes, each entry
  `{section, category, value, side}`:
  - `section` and `category` name a `target.json` section and one of its categories, or a
    synthesized user section, exactly as `mpfb_list_targets` reports them.
  - `value` is -1.0..+1.0 for a category with `opposites`, 0.0..1.0 for one without.
  - `side` is `"left"`, `"right"` or `"unsided"`, defaulting to `"unsided"` for a category with
    `has_left_and_right: false` and being **required** for one where it is true. Defaulting a sided
    category to one side would be a coin flip; refusing is the honest answer.
- `targets` (optional list) — raw shape-key-level changes, each `{shapekey_name, value}` with
  `value` in 0.0..1.0. The escape hatch for user targets and for anything a category cannot express.
- `symmetry` (optional bool, default `false`) — when a `modifiers` entry names a sided category,
  also apply the mirrored value to the other side. MPFB's own `symmetry` scene setting and its own
  default.
- `prune` (optional bool, default `true`) — delete a target's shape key when its value reaches
  zero, as `delete_target_on_zero`. MPFB's default.
- `refit` (optional bool, default `false`) — as in [FR 007](../007-macro-details/README.md); the
  standalone `mpfb_refit_human` from that request is what makes this default workable.

Both lists are optional and either may be empty, but a call with neither is a no-op that answers
saying so rather than doing anything.

`result` carries `basemesh_name`, `subject_resolved_by`, `message`, and:

- `applied` — one entry per requested change, in request order, each reporting what actually
  happened: the target file names touched, `previous_value` and `new_value` for each, whether the
  target was `loaded_from` disk on this call or was already present, and whether it was removed by
  pruning. A single sided modifier change with `symmetry: true` touches up to four shape keys and
  the response has to be able to say so.
- `resolution_errors` — entries that could not be resolved, each with the reason: unknown section,
  unknown category, a `side` given for an unsided category or omitted for a sided one, a value out
  of range for that category's kind, a `shapekey_name` naming nothing that exists and nothing that
  can be loaded. When this list is non-empty **nothing at all is applied** (see the non-functional
  requirements).
- `known_sections` / `known_categories_in_section` when a name was not recognized — the
  self-correction machinery from
  [Validate before crossing the socket](../../specifications/architecture.md#validate-before-crossing-the-socket),
  scoped to what the caller got wrong rather than dumping the whole vocabulary.
- `refit_performed`, `assets_possibly_stale` — as in FR 007.

### `mpfb_symmetrize_targets`

Mutating. Makes an already-asymmetric detail stack symmetric. Arguments:

- `name` (optional string) — subject.
- `direction` (string, required) — `"left_to_right"` or `"right_to_left"`. Required rather than
  defaulted: which half of a character's face is the good one is not something a tool can guess, and
  guessing wrong destroys work.
- `section` (optional string) — restrict to one section, so "make the eyes symmetric" does not also
  flatten deliberate asymmetry in the hands.
- `dry_run` (optional bool, default `false`) — report what would change without changing it. This
  operation is destructive in a way nothing else in this request is: it overwrites values the user
  may have set deliberately, and there is no undo across the socket.
- `prune`, `refit` — as above.

`result` reports the categories changed with before/after values per side, and the categories that
were already symmetric. With `dry_run` the same answer, and nothing written.

MPFB has no equivalent of this operation — its `symmetry` setting only affects changes made while it
is on, and explicitly does not touch previously set values. This is therefore a deliberate addition
rather than a wrapper, which the docstring must say.

**Not in scope.** Macro details, which are [FR 007](../007-macro-details/README.md);
`TargetService.symmetrize_shape_key()`, which mirrors vertex *coordinates* inside one custom shape
key using `hm08.mirror` and belongs to MakeTarget/asset authoring rather than modeling; expressions
and visemes (`!ex-`), which need their own request; saving or loading `.mhm` files; randomization,
which `RandomizationService` already implements inside MPFB and which should wrap that rather than
be rebuilt here; and creating new target *files*.

## Non-functional requirements

- **The same result MPFB's own sliders produce**, as in [FR 007](../007-macro-details/README.md) —
  and here the bar is higher, because the category mechanics (clearing the opposite, choosing
  `.target.gz` versus `.target`, the `l-`/`r-` prefixes) are things a reimplementation gets subtly
  wrong in ways that only show up as a slider reading the wrong value back in the UI.
- **All-or-nothing resolution.** Every entry in both lists is resolved and validated *before*
  anything is written. A batch of thirty changes with one typo in it must apply zero of them, not
  twenty-nine — a half-applied batch leaves a character in a state neither the agent nor the user
  can describe, and the agent cannot tell from the response which half to retry. Once resolution
  succeeds, application proceeds and per-entry results are reported.
- **Batched by default because latency dominates.** A round trip is roughly a second
  ([FR 005](../done/005-list-assets/README.md)); the work inside is milliseconds unless a target has
  to be read off disk. Thirty separate calls to a single-value tool would be half a minute of
  waiting for a fraction of a second of work.
- **Destructive operations announce themselves.** `prune` deletes shape keys; `symmetrize`
  overwrites deliberate values. Both are reported entry by entry, and `symmetrize` has a `dry_run`.
- **Preconditions are answers, and so are unknown names.** Same stance as FR 007 for OBJECT mode and
  missing shape keys; and a misspelled category comes back as a recognizable "no" with the valid
  alternatives, never as a traceback.

## Architecture

- Three tool modules, three payloads, three `register()` calls, per
  [the code-generation layout](../../specifications/architecture.md#code-generation-layout).
  **Raising bootstrap** for all three.
- **The category table has to be built in the payload, not imported.** The setter needs
  `target.json` plus the synthesized user sections — the same data
  [`payloads/list_targets.py`](../../src/mpfbmcp/codegen/payloads/list_targets.py) already assembles.
  `mpfb/ui/model/_modelsubpanels.py` builds exactly this at module level and **must not be
  imported**, for the reason
  [FR 006](../done/006-list-targets/README.md) records and
  [architecture.md](../../specifications/architecture.md#never-import-mpfb-submodules-directly)
  requires: its scan is a snapshot from when Blender started, so a target the user installed since
  would be invisible to the setter while being visible to `mpfb_list_targets`. That inconsistency
  between two mpfb-mcp tools would be worse than either behavior on its own. Reimplement, as FR 006
  did, and consider whether the shared part of the two payloads is worth factoring — noting that
  payloads are resources rather than modules, so "shared" means a second resource file the
  assembler concatenates, and that is a change to `codegen/` which
  [FR 002](../done/002-codegen-structure/README.md) deliberately kept tools out of. Duplicating the
  scan is the safer first move; if it is duplicated, say so in both payload docstrings.
- **`_set_opposed_modifier_value()` is the reference implementation** for a category change, and it
  is worth following statement for statement. Its order matters: zero the opposing target *first*
  (both opposites when the value is near zero), then set or load the selected one. Doing it the
  other way leaves both halves of a pair briefly non-zero, and with `prune` on, leaves the wrong one
  deleted.
- **`_set_simple_modifier_value()` is the reference for a category with no `opposites`** — chiefly
  the synthesized user-target categories, where the category carries a `full_path` and the file is
  loaded from there rather than from the system targets directory.
- **Pitfall — the two reference functions disagree about the file extension.**
  `_set_simple_modifier_value()` tries `<name>.target.gz` and falls back to `<name>.target`;
  `_set_opposed_modifier_value()` builds `<name>.target.gz` only and will happily hand a
  non-existent path to `load_target()`, which raises `IOError`. Bundled targets are all gzipped so
  it never bites in practice, but a payload that copies the opposed function verbatim inherits a
  latent crash. Try both extensions in both paths, and resolve the path during the *resolution*
  phase so a missing file is a `resolution_errors` entry rather than a half-applied batch.
- **Pitfall — `set_target_value()` on an absent target is a silent no-op.** It iterates the key
  blocks looking for a name match and does nothing if there is none. It does *not* load the target
  and does *not* raise. So every set must be preceded by `TargetService.has_target()` and, when
  false, by a `load_target()` with the value as its `weight`. `get_target_value()` has the mirror
  problem: it returns `0.0` for a name that does not exist, indistinguishable from a target that
  exists at zero. Report existence separately from value.
- **Pitfall — Blender clamps a shape key value to 0.0–1.0.** MPFB never touches `slider_min` /
  `slider_max`, so the default range applies and assigning -0.4 stores 0.0. This is precisely why
  the category level exists, and why the raw `targets` list is restricted to 0.0–1.0 while
  `modifiers` accepts -1.0..+1.0. Confirm the clamp live rather than trusting this paragraph.
- **Pitfall — `get_target_stack()` excludes any shape key whose lowercased name *contains*
  "basis"**, not merely equals it (`exclude = "basis" in sk_name`). A user target named
  `basis-nose-widen` is invisible to `has_target()`, `get_target_value()` and the whole stack. Note
  it in `mpfb_get_target_stack`'s docstring and consider reading `key_blocks` directly there so the
  read tool does not inherit the blind spot — while every *write* must still go through
  `TargetService`, or the two will disagree. This is a candidate mpfb2 issue.
- **Pitfall — encoded names.** A user target over 60 characters is stored under its encoded name
  (FR 006 verified this end to end: a 76-character target became
  `$yn-$fe-$av-$ca-$un-$pr-$wg-$hg-experiment`). `has_target()` checks both the given name and its
  encoding, but `set_target_value()` and `get_target_value()` match the raw name only. Accept the
  `shapekey_name` FR 006 reports — which is already the encoded one — and do not re-encode it.
- **Pitfall — do not call `reapply_all_details()` to "refresh" the stack.** Same reasoning as
  [FR 007](../007-macro-details/README.md): it resolves every stack entry back to a file through
  `target_full_path()`, which cannot resolve an encoded name and which falls back to a *prefix*
  match — so it can silently drop a target or load a differently-named one. Nothing in this request
  needs it.
- **`target_full_path()`'s prefix fallback** is worth avoiding generally. It prefers an exact
  basename match and falls back to any file whose name merely *starts with* the requested string, so
  `nose-scale-depth` resolves to `nose-scale-depth-decr`. Build paths explicitly from the category
  data, as MPFB's panel does, and use `target_full_path()` only where there is nothing else — and
  when used, report the path that was resolved so a wrong match is visible.
- **Activation, mode and restoration** as in [FR 007](../007-macro-details/README.md):
  `_set_modifier_value()` activates the basemesh before doing anything, `create_shape_key()`
  asserts OBJECT mode, and the payload restores the previous active object and selection.
- **Symmetrize is built on the category table, not on names.** Pairing `l-foo` with `r-foo` by
  string manipulation would be a guess; the `opposites` table names all four targets of a sided
  category explicitly, and a category with `has_left_and_right: false` has no partner at all. Walk
  the categories, not the shape keys.
- Input validation per
  [Validate before crossing the socket](../../specifications/architecture.md#validate-before-crossing-the-socket):
  validate the *shape* of every list entry locally — that it is a dict, that its keys are known,
  that `value` is a real number in the right range, that `side` is one of three strings, that
  `direction` is one of two — and **not** the vocabulary of sections, categories or shape key names,
  which is partly synthesized from the user's own directories and is answered from inside Blender.
- Response envelope unchanged: `send_code(...)` as-is with `strict_json=True`.

## Affected specifications

- [vision.md](../../specifications/vision.md#target-tool-catalog) — the `mpfb_set_target_value`
  entry under "Creation and modification" is superseded by `mpfb_set_targets` and should be rewritten
  rather than merely marked implemented: the planned tool was a single named target, and what is
  proposed here is a batched, two-level tool. `mpfb_get_target_stack` and `mpfb_symmetrize_targets`
  are new entries. The `mpfb_list_targets` entry should gain a line saying which of its reported
  identifiers feeds which of the two levels, since that pairing is the whole contract between the
  two requests.
- [architecture.md](../../specifications/architecture.md) — conventions to follow, and two
  candidates.
  - **To follow:**
    [How tools name things that can be added](../../specifications/architecture.md#how-tools-name-things-that-can-be-added)
    (this is the tool that consumes FR 006's identifiers, and is where that convention is finally
    tested),
    [How tools bound a large answer](../../specifications/architecture.md#how-tools-bound-a-large-answer)
    for the stack listing, and
    [A tool may report a fact MPFB's own UI does not show](../../specifications/architecture.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show)
    for `asymmetries` and for the `"basis"` blind spot.
  - **Plus the three additions [FR 007](../007-macro-details/README.md) proposes** — how a mutating
    tool takes its subject, reporting before and after, and preconditions as answers. Whichever of
    the two requests lands first should record them; the second should follow them.
  - **New — a batched mutating tool resolves everything before it writes anything.** The
    all-or-nothing rule above, stated generally: an agent's typo in entry 17 must not leave a
    half-modified character, and a partial success is not something the response format can usefully
    describe. It applies to any later *batch* tool — but note that
    [FR 010](../010-mesh-assets/README.md) deliberately does not make `mpfb_add_asset` one, because
    loading an MHCLO costs seconds of real work rather than milliseconds, so the latency argument
    that forces batching here does not carry over.
  - **New, smaller — when mpfb-mcp models a concept MPFB's UI has but its services do not.** A
    modifier/category is not a `TargetService` concept at all; it lives in `target.json` and in a UI
    module. This tool lifts it out of the UI into the tool layer, and the rule worth recording is
    that when it does, the mechanics are reproduced from MPFB's UI code rather than reinvented, and
    the divergences (like the extension fallback above) are documented rather than silently
    normalized.

## Tests

Two layers, as established. The stubs need extending in the direction FR 006 already went — a real
`tempfile` target tree, since path resolution and on-demand loading are most of what the payload
does, plus a `target.json` fixture with the four category shapes that matter: an unsided category
with `opposites`, a sided one with all four `l-`/`r-` entries, a category with no `opposites` at
all, and a synthesized user category carrying a `full_path`.

`StubTargetService` needs the write half of the real one, reproducing behavior rather than
convenience:

- `set_target_value()` that is a **silent no-op** for a name not in the stub key blocks, and
  `get_target_value()` that returns `0.0` for one. A helpful stub that raised instead would make the
  `has_target`-then-`load_target` logic look unnecessary and let the bug it prevents through.
- Shape key values **clamped to 0.0–1.0** on assignment, so a payload that tried to store a negative
  modifier value directly fails here rather than in Blender.
- `get_target_stack()` excluding anything *containing* "basis", with a fixture target named to
  exercise it.
- `has_target()` checking the encoded name as the real one does, and an over-60-character user
  target in the tree so encoded addressing is under test.
- `load_target()` that raises `IOError` for a missing path, so the `.target.gz`/`.target` fallback
  and the resolve-before-write ordering are both genuinely exercised.

Cases worth naming: a positive modifier value loads the positive target and zeroes the negative one,
and the reverse; a value at zero clears both; `symmetry: true` on a sided category touches all four
targets and on an unsided one touches two; `side` omitted on a sided category is a resolution error,
and `side` given on an unsided one likewise; a batch with one bad entry writes **nothing** and every
other entry appears in `resolution_errors`-adjacent form rather than as applied; `prune` removes a
zeroed shape key and `prune: false` keeps it at zero; the modifier round trip — set a value, read
`mpfb_get_target_stack`'s `modifiers`, get the same number back; and `symmetrize` with `dry_run`
writing nothing while reporting the same changes the real run makes.

**Live verification against a running Blender is required**, with the full FR 004–006 revert
discipline (snapshot every datablock collection, compare after, never save). Specifically:

- **The slider round trip, which is the whole point.** Set a modifier through the tool, then open
  MPFB's model panel and confirm the corresponding slider reads the value that was set — including
  a negative one, a sided one, and one at exactly zero. Then move the slider in the UI and confirm
  `mpfb_get_target_stack` reports the same value back. Nothing on this side of the socket can
  establish this.
- That a target not previously on the mesh is loaded on demand from the right file, and that the
  shape key created is named as `mpfb_list_targets` said it would be — the same check FR 006 ran
  from the catalogue side, now from the setter side.
- That a **user** target from `mpfb_list_targets`, addressed by its `shapekey_name` through the raw
  `targets` list, applies and reads back — including a name long enough to be encoded, which FR 006
  proved fails silently when addressed by filename.
- The Blender 0.0–1.0 clamp on shape key values, observed rather than assumed.
- The `"basis"`-substring exclusion, observed by installing a user target whose name contains it.
- `symmetrize` on a character made deliberately asymmetric, in both directions, with `dry_run` first.
- Batch cost against FR 005's ~1.0 s baseline: thirty modifier changes in one call versus thirty
  calls, and how much of the difference is target files being read off disk.
- Interaction with [FR 007](../007-macro-details/README.md): a macro change after detail targets are
  set must leave the detail stack intact — `reapply_macro_details()` should touch only `$md-` keys.
  If it does not, one of the two requests is wrong and this is where it surfaces.

Record the outcome in a `## Verification status` section here.

## References

- MPFB `ui/model/_modelsubpanels.py` — the reference implementation for everything in
  `mpfb_set_targets`: `_set_opposed_modifier_value()`, `_set_simple_modifier_value()`,
  `_get_opposed_modifier_value()`, `_set_modifier_value()` (activation and refit), and the
  module-level `target.json` load and user-section synthesis this payload must reimplement rather
  than import.
- MPFB `ui/model/modelpanel.py` and `ui/model/properties/` — the `prune`, `refit` and `symmetry`
  settings whose defaults this request inherits, and `symmetry`'s description, which says in so many
  words that toggling it does not affect previously set values — the gap `mpfb_symmetrize_targets`
  fills.
- MPFB `services/targetservice.py` — `has_target()`, `get_target_value()`, `set_target_value()`,
  `load_target()`, `bulk_load_targets()`, `get_target_stack()`, `prune_shapekeys()`,
  `decode_shapekey_name()`, `shapekey_is_target()`, `expression_name_to_shapekey_name()`, and
  `target_full_path()` with its prefix fallback.
- MPFB `services/randomizationservice.py` — `_detail_targets_for_category()` and
  `_append_detail_entry()` are a second, independent reading of the same `opposites`/side mechanics,
  written more recently and more compactly than the UI's; useful for cross-checking the payload, and
  the natural thing to wrap if randomization is ever exposed.
- MPFB `data/targets/target.json` — the category shapes: `has_left_and_right`, the six-key
  `opposites` table (`positive-`/`negative-` × `left`/`right`/`unsided`, with the unused half empty
  strings), and the `targets` list.
- [FR 006](../done/006-list-targets/README.md) — the catalogue whose identifiers this request
  consumes, and its Verification status section, which is where the encoded-name failure mode was
  observed rather than inferred.
