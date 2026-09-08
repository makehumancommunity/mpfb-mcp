# Responses

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

**What a tool says back.** The envelope is blender_mcp's and is not negotiable; everything else
here is about a single failure mode — a response that a caller reads as a complete, recorded,
authoritative answer when it is none of those. A capped list read as the whole truth, a `[]` read
as "none" when it meant "not computed", a derived value quoted back to the user as fact, a
fragment handed to a file-opening tool.

Input conventions are in [tool-interface.md](tool-interface.md); what a *mutating* tool
additionally owes its caller is in [mutating-tools.md](mutating-tools.md).

## Response shape

Tools return blender_mcp's response envelope largely as-is: `{"status": "ok", "result": ...}`
or `{"status": "error", "message": ...}` (optionally `stdout`/`stderr`). Callers — including
future mpfb-mcp tools composing on top of others — must check `status` rather than assume
success. This mirrors blender_mcp's own tools and avoids inventing a second error convention.

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

**A field that means the same thing in two tools is spelled the same way in both.** `found`,
`ready` and `blocked_by` were, and were never mis-read; the success flag was not, and was — see
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
object as it is now — which rig the bone names look like, which material the node tree looks like —
can disagree with values *recorded* when something was loaded, because nothing rewrites a record
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
- **A filtered call still reports what it filtered out of.** `counts_by_subdir` is what turns an
  over-broad call from merely truncated into informative: it says where the entries are, so the
  caller can pick a narrower filter for the next call rather than paging blindly through everything.
- **Say in the docstring which field to check before concluding something is absent.** The failure
  this whole convention guards against is an agent reporting that an asset is not installed because
  it was not on page one.

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

- **The tool can be the stale one, and must say so.**
  `AssetService.alternative_materials_for_asset()` caches its scan per `(asset_source,
  asset_subdir)` in a module-level dict with no invalidation, so `mpfb_list_asset_materials` reports
  a snapshot taken the first time anything in that Blender session asked about the asset. A material
  installed afterwards is on disk, is applicable, and will not appear — and no `refresh` argument
  could change that, because there is nothing to call. Where the staleness is *ours* rather than
  MPFB's, the obligation is the same: name it in the docstring and in the response, so a caller who
  meets it does not read it as a bug.

Prefer describing what is actually on disk, and label the part MPFB will not show — rather than
either papering over the difference or quietly inheriting the limitation. Where the difference is
a limitation of MPFB rather than of the tool, that is worth recording as a candidate mpfb2 issue
as well as reporting.
