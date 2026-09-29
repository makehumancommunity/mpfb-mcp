# Responses

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

**What a tool says back.** The envelope is this package's and is not negotiable; everything else
here is about a single failure mode — a response that a caller reads as a complete, recorded,
authoritative answer when it is none of those. A capped list read as the whole truth, a `[]` read
as "none" when it meant "not computed", a derived value quoted back to the user as fact, a
fragment handed to a file-opening tool.

Input conventions are in [tool-interface.md](tool-interface.md); what a *mutating* tool
additionally owes its caller is in [mutating-tools.md](mutating-tools.md).

## Response shape

Tools return `{"status": "ok", "result": ...}` or
`{"status": "error", "error": "<slug>", "message": ...}` (optionally `stdout`/`stderr`). Callers —
including future mpfb-mcp tools composing on top of others — must check `status` rather than assume
success.

**The envelope was inherited and kept, spellings and all.** `status`, `result` and `message` mean
exactly what they meant on the transport this package started with, which is why a whole second
transport could be introduced and then the first one deleted without a single existing caller
changing. What the bridge added is `error`, and it is part of the contract:

- **A caller branches on `status`, then on `error`, and never on `message`.** The slug is the
  contract; the human sentence beside it may be reworded without notice. The vocabulary is the
  bridge's nine slugs ([the wire](architecture.md#the-wire)), of which two carry most of the meaning
  a caller acts on: `invalid_params` says the request was wrong and names the parameter, and
  `mpfb_unavailable` says the request was fine and the install is not.
- **Every error envelope carries a slug, because one function writes them all.**
  `command_server._error()` is that function, which is what lets a caller branch on `error` without
  first establishing that the failure came from somewhere that fills the field in. The seam
  synthesises nothing: there is nothing left for it to fill in.
- **Nothing else is synthesised, in either direction.** A success envelope is returned exactly as
  it arrived. `protocol_version` is a fact about the bridge's protocol and is *absent* from a
  generated-code answer rather than invented for it, and the mapping never overwrites a slug the
  bridge chose.
- **Which backend answered is not in the envelope.** It is in the log line and in the record, which
  is where a question about the transport belongs — and a `backend` field would have to be added to
  an unmigrated tool's answer to be useful, which is exactly the tool edit the seam exists to
  forbid ([Supporting a second backend](architecture.md#supporting-a-second-backend)).

**`null` and `[]` are different answers, and the difference is load-bearing.** `[]` means "none
of them"; `null` means "not known" or "not computed". FR 006 established it; FR 013's live run
found two places where it had quietly been broken, in code that had been reviewed twice.
`mpfb_symmetrize_targets` under `dry_run: true` reported `targets: []` for each category it would
change, where what it meant was that it had not done the write and therefore could not say which
files it would touch — so it now reports `null`. And `mpfb_remove_asset`'s `mask_modifiers_present`
reported every MASK modifier on the basemesh, including MPFB's own `Hide helpers`, in a field read
by somebody about to delete a modifier by hand.

Both were written by somebody who knew the rule, which is why it is worth stating here rather than
leaving as a habit. The test to apply to a field returning a container: **would an empty one be a
true statement about the world?** If the answer is "we did not look", it is `null`.

The same test applies to a *filter*. A field that answers "which of these is the one you are
looking for?" must not include entries that are certainly not, however honestly they belong to
the collection it was read from.

**A field that means the same thing in two tools is spelled the same way in both**, and one
spelling never means two things; [the glossary](tool-interface.md#the-glossary) is the list. `found`,
`ready` and `blocked_by` always were, and were never mis-read; the success flag was not, and was — see
[the uniform success flag](mutating-tools.md#the-flag-a-caller-branches-on-is-called-performed)
for what a mutating tool reports and why the tool's own verb is kept beside it rather than
replaced.

## How tools report the asset behind an object

MPFB records what an object was made from as a short *fragment* — `"fedora/fedora.mhclo"`, one
directory level plus a filename — which is resolved to a file by walking the configured asset
roots. Any tool reporting that follows three conventions:

- **Report the fragment and the resolved path as separate fields**, and make every `*_path` either
  an absolute path or `null`, never a fragment. A fragment looks path-shaped, and a caller that
  hands one to a file-opening tool gets a confusing failure far from here.
- **Keeping both is also what tells two situations apart.** A `null` fragment means the object
  records no such asset: it was built rather than imported, or it is using a default. A fragment
  with a `null` path means the asset *is* recorded but is not installed under any asset root this
  Blender can see — the user moved or uninstalled the pack. The first is ordinary; the second is
  something a caller may want to raise with the user, and one undifferentiated `null` would hide it.
- **Let the keys vary by object type rather than unioning them and nulling what does not apply.**
  `mhclo_path: null` on a skeleton reads as "we looked for its mhclo and failed", a different and
  much more alarming claim than "a skeleton does not have one". The keys present say which question
  was asked; their values say whether it could be answered.

Two cautions belong in the docstring of any tool reporting these. Values *identified* from the
object as it is now — which rig the bone names look like, which material the node tree looks like,
reported as `rig_identified_as` and `material_identified_as` — can disagree with values *recorded*
when something was loaded, because nothing rewrites a record
when the object is later edited by hand; where they disagree, the identified value describes
reality, and both are heuristics rather than authorities. And resolving a fragment is an `os.walk`
of the asset roots, so it must happen only when there is a fragment to resolve.

## How tools bound a large answer

Some answers do not fit. `mpfb_list_assets` reports an asset library that runs to hundreds or
thousands of entries on an ordinary install, and an unfiltered listing is not something an agent can
afford to read. Such a tool caps its answer, and the cap brings one obligation: **a capped or
filtered response must never be readable as a complete one.**

- **Always report the size of the matched set, not only the page.** A `total_count` counted before
  the cap is applied, and a `truncated` flag that is **always present** — not omitted when false,
  since a caller that has to infer the field's absence will not.
- **Echo the paging back.** `offset` and `limit` in the response, so the next page can be asked for
  without the caller tracking state it did not send.
- **Order deterministically before paging.** The underlying listing usually comes from a directory
  walk, whose order is filesystem-dependent. Sorting after paging, or not at all, makes two pages of
  one query silently skip and repeat entries.
- **A filtered call still reports what it filtered out of.** `counts_by_asset_subdir` is what turns an
  over-broad call from merely truncated into informative: it says where the entries are, so the
  caller can pick a narrower filter for the next call rather than paging blindly through everything.
- **Say in the docstring which field to check before concluding something is absent.** The failure
  this whole convention guards against is an agent reporting that an asset is not installed because
  it was not on page one.

**A filter on sections is the same obligation in a different shape.** `mpfb_get_material_settings`
answers 21-22 KB for a character with procedural eyes, a layered skin and six mesh assets, of which
the skin's nine groups are 16 KB, so it takes a `section` argument - added because the answer was
measured past the line, not in advance of it. A section left out is `null` rather than absent or
empty, which is [the `null` versus `[]` rule](#response-shape) - not computed, rather than none -
and `requested_section` echoes the filter.

## How tools report a derived rather than recorded fact

[How tools report the asset behind an object](#how-tools-report-the-asset-behind-an-object) draws a
line between values *identified* from an object as it is now and values *recorded* when it was
loaded. A third kind turns up in catalogue tools: a value **derived from a convention**, where
neither MPFB nor the file records the fact at all. `mpfb_list_assets`' `pack` is one — MPFB stores
no link from an installed file back to the pack that installed it, so the attribution is a match of
the asset's containing directory name against the asset names in the installed packs' metadata.

- **Say in the docstring that it is derived, and from what.** A field that looks recorded will be
  quoted back to the user as fact.
- **Give the caller a way to see when the derivation is unsafe**, rather than only documenting that
  it might be. `pack_ambiguous` is that: when two packs claim a name, the reported one is a coin
  toss, and without the flag a wrong attribution is indistinguishable from a right one. Measured on
  a real install, 9% of assets are ambiguous — "rare" is not a safe assumption about a convention.
- **Report the miss as ordinary.** A derivation that finds nothing (`pack: null` for a
  hand-installed asset) is not a failure and must not be reported as one.
- **Never let the derivation become the source of truth.** Filter and count the things actually
  found, then derive; do not answer from the metadata the derivation reads. Pack metadata lists
  assets a user may since have deleted, and building the response from it would report assets that
  are not installed.
- **Know where the convention does not hold.** The join above keys on a containing directory, so an
  asset lying directly in an asset root has no directory of its own to key on, and pack metadata
  lives only under the user data root, so an asset under another root cannot be attributed even when
  it did come from a pack. Both are cases to detect and report as `null`, not cases to guess at.
- **A fact read from the filesystem is this same kind**, and the convention covers it unchanged.
  `mpfb_list_presets` reports `size_bytes` and `modified` per preset; MPFB's own list is bare names
  and records neither, so both come from `os.stat` here and the docstring says so. The three clauses
  above all apply as written: the miss is ordinary (`exists: false` is what MPFB's cached list
  naming a deleted file looks like), the derivation never becomes the source of truth (the entries
  are MPFB's names, annotated, not a directory listing dressed up as MPFB's answer), and the place
  the convention does not hold is named — a preset MPFB lists under a name these tools will not
  accept carries `addressable: false` rather than being quietly dropped or quietly offered.
- **A comparison MPFB never makes is this kind too, and it owes one thing more: its tolerance.**
  `matches_stack` and `unexplained_face_units` ([FR 027](../feature-requests/done/027-expression-library/README.md))
  compare MPFB's own aggregate of the applied-expressions stack against the live shape keys; neither
  side of the comparison is recorded anywhere as agreeing or not. The clauses above hold - the
  derivation is from MPFB's own numbers (`aggregate_expression_stack()`, `read_current_expression()`),
  never a recomputation standing in for them, and "nothing on the stack, nothing composed" is the
  ordinary answer `true` - and a numeric comparison adds that **the tolerance is part of the
  definition** and lives in one place: shape keys store 32-bit floats and expression files four
  decimals, so exact equality would call every saved face unexplained. `clamped_face_units` is the
  same kind again: MPFB clamps each unit's sum to `[0, 1]` and keeps no record that it did, so the
  unclamped sum is recomputed over the same rows and reported beside the value MPFB applied.
- **A value converted into the caller's terms is this kind, and is never accepted back.** A colour
  socket holds scene-linear RGBA, and an agent that thinks in sRGB picks colours that come out too
  light. So every colour `mpfb_get_material_settings` and `mpfb_set_material_settings` report
  carries an `srgb_hex` beside it: each channel clamped to 0-1, put through the sRGB transfer
  function and rounded to a byte, alpha dropped. Neither the node nor a preset records it, the
  descriptions say it is derived, and the write takes only the linear value - accepting hex would
  need a second key per entry and a conversion the read could not round-trip exactly
  ([FR 040](../feature-requests/done/040-procedural-material-settings/README.md)).

## A response says which source answered it

Most tools have one source: they ask MPFB, and the answer is MPFB's. Where a tool has **more than
one** — a live read with a local fallback behind it — the caller is going to quote the answer to a
user, and "MPFB says this URL" and "mpfb-mcp's copy of what MPFB said some months ago says this
URL" are different claims. **A caller must never have to infer which one it got.**

**This is about two sources of an answer, not two routes to one source.** Which backend carried a
call is not a source in this sense: the generated path and the bridge both end in the same MPFB
inside the same Blender, and FR 030 measured them answering identically field by field for one
tool, FR 031 for nine more. So there is no `backend` field, and the rule below is not an argument
for one — the question it exists to answer is "who is making this claim", and for a migrated tool
the answer is MPFB either way.

**Two of those nine make a statement about the source rather than only about the answer, and both
survive the change of transport unchanged**, which is worth recording because it was checked rather
than assumed. `mpfb_list_asset_materials` reports a scan MPFB caches per asset and invalidates
never, so its answer is a **snapshot** and its `message` says so; the caching is MPFB's, not the
transport's, and the same first call warms the same dict whichever way the request arrived. And
`mpfb_list_presets` reports `missing_from_mpfb_list` — what MPFB's cached list *would gain* from a
rescan — which is an observation of the filesystem beside MPFB's own answer, not a prediction, and
is computed inside Blender in both configurations. A comparison of the two paths has to allow for
the first: the first of two calls in one Blender warms a cache the second reads, so a difference
there is a fact about MPFB rather than a migration defect, and FR 031's live check establishes
self-consistency on one backend before it compares across two.

- **Name the source in a field of its own**, not by the presence or absence of some other field.
  `source_of_truth` is `"mpfb"` or `"builtin_fallback"`; the reason for a degradation sits beside it
  in `fallback_reason`, and is `null` when there was none.
- **The live source wins every disagreement, in both directions.** A value it has changed is
  reported as it now is; a key it no longer has is *not* resurrected from the copy. A fallback that
  can override the source is not a fallback.
- **Report the disagreement rather than only resolving it**, and say what kind it is. `changed`,
  `added_by_mpfb` and `missing_from_mpfb` call for different repairs, and collapsing them into one
  "stale" flag loses the part that says what to do.
- **"They agree" and "we could not compare" are not the same answer**, so they are not spelled the
  same way. When nothing live was read, the staleness fields are `null` — the
  [`null` versus `[]` rule](#response-shape) applied to a comparison rather than a container.
- **Degrading is not failing.** Every state the tool can be in is a successful envelope: this is
  [absence is an answer](#response-shape) extended past MPFB's absence to the transport's. What it
  must not swallow is a *defect* — a command that failed inside Blender still surfaces as an error,
  or the bug is hidden for good.

## A deliberately partial answer carries the size of the whole

[How tools bound a large answer](#how-tools-bound-a-large-answer) covers an answer capped because
it did not fit. A **curated** one is the other case: it is short because somebody chose what goes
in it, and the caller has no cap or `total_count` to notice that by. `mpfb_list_docs` returns
nineteen of MPFB's 105 documentation files.

The obligation is the same as
[an absent entry must be explainable](tool-interface.md#how-tools-name-things-that-can-be-added),
and it is discharged with three fields rather than a sentence in the docstring: a flag saying the
answer is curated, the **size of the collection it was drawn from**, and the **address of the
whole**. Nineteen of nineteen reads as complete; nineteen of 105, with a link, reads as a
selection and sends a caller looking rather than concluding. All three are present on every
answer, including the unfiltered one — which is the answer most likely to be mistaken for the
whole — and including an empty one, where the temptation to report "nothing found" is strongest
and most wrong.

## A summary is never a second opinion

A summary tool answers several detailed tools' questions at once, and is only worth having if an
agent can trust it as much as the tools it stands in for. `mpfb_get_character_summary`
([FR 034](../feature-requests/done/034-character-summary/README.md)) is the one there is, and the
contract it set applies to any other:

- **Each section is a subset of one detailed tool's answer, under the same field names.** A caller
  that learned `rigify_role` or `unexplained_face_units` from one tool reads it the same way in the
  other, and the summary's description spends nothing explaining a field the detailed tool's
  description already does.
- **The two never disagree about one subject in one state.** An agent that reads "no rig" in the
  summary and "rig `default`" from `mpfb_get_object_info` has been handed a contradiction it cannot
  resolve, and will act on whichever it read last. This is made true by construction rather than
  by testing: each section is read by the implementation its detailed tool uses, shared in the
  bridge ([a summary and its detailed tool are one implementation](architecture.md#shared-modules-and-what-warrants-one)),
  and a bridge test dispatches both and compares, to keep it true after the reason is forgotten.
  It also rules out composing the summary by calling the other commands' handlers.
- **It reports no fact a detailed tool does not.** It selects and it counts; it does not derive. A
  finding that joins two sections — "the rig cannot be refitted *and* there are garments on it" —
  would be the one part of the answer the caller could not check against another tool, so it is
  left to the caller to join. Where a new fact was wanted (`macro_drift`), it was added to the
  detailed tool too, so the rule still holds.
- **It names the detailed tool behind each section, once, in its description** rather than in
  every response, so a caller wanting more than the summary carries knows where to go.
- **What it cuts, it says it cut**, per [how tools bound a large answer](#how-tools-bound-a-large-answer)
  — and no more: a summary takes no filter, paging or `include_*` switch, since each would turn one
  question into dozens and a caller wanting a slice has the detailed tool. The one cut in
  `mpfb_get_character_summary` is the target rollup, which grows with a character; it keeps the
  entries furthest from zero, **in the detailed tool's own order**, so a capped list is still a
  sub-list of the whole, and reports the whole's size beside an always-present
  `rollup_truncated`. `truncated` itself was not reused, because `mpfb_get_target_stack` already
  uses that name for something else, and the first rule above forbids one name meaning two things.

## A tool may report a fact MPFB's own UI does not show

Where a tool's answer can legitimately disagree with what the user sees in Blender, **the docstring
must say so**, or the discrepancy will be read as the tool being wrong. Two of these turn up in
`mpfb_list_targets`, and both are worth reporting rather than suppressing:

- **The tool is more current than MPFB.** MPFB's modeling panels build their target list at *module
  import time*, so they only ever show what existed when Blender started. A tool that scans per call
  reports a target installed since — which is correct, and is a difference the user will notice.
- **The tool is less selective than MPFB.** MPFB's scan of `<user data>/targets/` matches only
  `*.target`, so a `*.target.gz` sitting there is on disk and loadable but absent from its panels.
  Report it, with a field saying which ones MPFB will show. Silently matching MPFB's narrower
  behavior would hide a real file; reporting it without the flag would look like a bug here.

A third turns up in `mpfb_get_target_stack`, and it is the sharpest of them:

- **The tool can see something MPFB cannot address at all.** `TargetService.get_target_stack()`
  excludes any shape key whose lowercased name *contains* `"basis"`, not merely equals it, so a
  user target called `basis-nose-widen` is on the mesh, is deforming it, and is invisible to
  `has_target()`, `get_target_value()` and every write MPFB can perform. The read tool goes to
  `key_blocks` directly rather than inheriting the blind spot, and flags what it found with
  `visible_to_targetservice: false`. Every **write** still goes through `TargetService`, or the
  read and write halves of the same tool would disagree about what exists.

And the same convention has a fourth form, seen from the other side:

- **The tool can be the stale one, and must say so - and where it can be lifted, offer that too.**
  `AssetService.alternative_materials_for_asset()` caches its scan per `(asset_source,
  asset_subdir)` in a module-level dict that nothing invalidates automatically, so a plain call to
  `mpfb_list_asset_materials` reports a snapshot taken the first time anything in that Blender
  session asked about the asset. A material installed afterwards is on disk, is applicable, and
  will not appear by default. Where the staleness is *ours* rather than MPFB's, the obligation is
  the same: name it in the docstring and in the response, so a caller who meets it does not read it
  as a bug.

  **Say only what was checked.** This entry used to end "and no `refresh` argument could change
  that, because there is nothing to call", which was false —
  `AssetService.invalidate_alternative_materials_cache()` exists, and the live run found it. A
  limitation attributed to MPFB is a claim about MPFB, and carries the same burden of evidence as
  a defect report does. [FR 018](../feature-requests/done/018-alternative-material-refresh/README.md)
  wired that invalidator up as `refresh`, so the tool now offers a way past its own staleness -
  and because the invalidator takes no arguments and clears every asset's cached scan at once, the
  response says so explicitly through `cache_invalidated` rather than leaving a global side effect
  implicit in a per-asset call.

And a fifth, where MPFB's UI says the opposite of what MPFB does:

- **The tool reports what MPFB's own UI misdescribes.** A user-saved expression in user data is
  hidden whenever a higher-priority data root holds a file of the same name, while MPFB's composer
  panel and its data README both say user files take priority. `mpfb_list_expressions` reports each
  hidden file under `shadowed`, with the file that hides it, and `mpfb_save_expression` refuses to
  create one. A tool that followed the panel's description would report a file as available that
  nothing in MPFB will ever load.

And a sixth, where the fact is about what a write *would* do:

- **The tool reports what makes a write useless or wider than asked.** On MPFB's layered skin most
  region colours - `bodygroup`'s `SkinColor`, `facegroup`'s `EyelidColor`, the nails' colour - are
  driven by a link from the `color` group, and so is a MakeSkin `diffuseIntensity`'s `Color2`, from
  its texture. Writing a linked socket's default value succeeds and changes nothing, and MPFB's
  serializer saves it anyway. `mpfb_get_material_settings` reports each link as the node and
  socket it comes from (`linked`), and the write refuses one, naming the socket that drives it.
  Likewise a material is a datablock, and every object using it changes with it:
  `material_shared_with` names the objects outside the section that would change too - another
  character, or an export copy - on the read, and `materials_written` on the write. And a declared
  range MPFB's own value already contradicts is named (`values_outside_range`) rather than left for
  the caller to meet as a refusal ([FR 040](../feature-requests/done/040-procedural-material-settings/README.md)).

Prefer describing what is actually on disk, and label the part MPFB will not show — rather than
either papering over the difference or quietly inheriting the limitation. Where the difference is
a limitation of MPFB rather than of the tool, that is worth recording as a candidate mpfb2 issue
as well as reporting.
