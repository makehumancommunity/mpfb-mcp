# Listing, applying and saving expressions

**Status:** Done

[FR 026](../026-face-units/README.md) landed the face-unit layer: an agent can read the 52 ARKit
units a face is holding and compose a new face from them. What it composes **survives nothing** — not
`mpfb_save_preset`, which serializes MPFB's applied-expressions *stack*, and not the next thing that
rebuilds that stack, which clears every `!ex-` key first. And an agent cannot use the expressions
MPFB's users actually work with: a **named, saved, weighted combination** — a `smile`, an
`angry-shout` — stored as a JSON file in an asset library, applied at a strength, and stacked with
others. That library is what `ui/apply_assets/useexpression` exposes, and none of it is reachable.

This request scopes four tools over the **library** half of
[`FaceService`](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/services/faceservice.py): one to list what is installed, one
to read what a character is currently wearing, one to change it, and one to **save a composed face as
an expression file** — which is what turns FR 026's transient output into something the library,
and therefore a preset, can carry. It also **extends `mpfb_set_face_units`**, because the mechanism
this request exposes silently destroys what that tool writes, and that has to become visible.

Saving was queued in [NEXT_STEPS.md](../../NEXT_STEPS.md) as a separate effort behind this one. It is
folded in here because the two are only useful together: without saving, a face composed through
FR 026 can be applied through nothing; without the library tools, a saved file can be read back
through nothing.

Two boundaries carry over from FR 026 unchanged: **visemes and lip sync are out of scope**, and
**`mpfb_set_targets` is left alone**. FR 026's third — *no tool writes an expression file* — is
lifted, narrowly: `mpfb_save_expression` **creates** a file from the live face. Editing an existing
file's metadata, renaming one and deleting one remain out of scope.

*This request was written before [FR 033](../033-retire-the-generated-code-path/README.md)
retired the generated-code path, and was revised afterwards: it names commands, `bridge/` modules and
`bridge/test/` rather than payloads, fragments and stubs.*

## Goals

**Primary:** an agent can find out what expressions are installed, put a character into one at a
chosen strength, blend several, read back what it is wearing, take them all off, and **save a face it
composed as a named expression** — addressing expressions by an identifier that means the same thing
on another machine.

**Secondary:**

- Make the composer/library conflict **visible in a response** rather than discoverable by losing an
  expression to it. This is the requirement the effort turns on; see
  [Two mechanisms, one set of shape keys](#two-mechanisms-one-set-of-shape-keys).
- Close the gap [FR 026 named](../026-face-units/README.md#a-composed-face-is-transient): a
  composed face, once saved and applied, is carried by the stack like any other expression — so it
  survives the next library call and a [FR 025](../025-character-presets/README.md) preset round
  trip, which already serializes the stack.
- Confirm and, if warranted, file the defects below — and FR 026's two, which it confirmed but did
  not file — in the shape [FR 019](../019-file-mpfb-defects/README.md) established.

## Functional requirements

### `mpfb_list_expressions` — what is installed

1. Returns one entry per expression JSON discovered by
   `FaceService.list_available_expressions()`, which walks `<root>/expressions/` for every root
   `AssetService.get_asset_roots("expressions")` reports, in priority order (`mpfb_data`, `mh_data`,
   `user_data`, `second_root`), the first root winning a duplicate library-relative path. Each entry
   carries `fragment` (the library-relative path, **and the identifier `mpfb_apply_expressions`
   takes**), `path` (absolute, for a human reading the response), `label`, and the metadata
   `list_available_expressions` already parsed: `description`, `tags`, `author`, `license`.
2. **Reports `fragment` beside `path` and says which one is the address**, exactly as
   `mpfb_list_assets` does. The stack stores fragments, so a fragment is what round-trips between
   machines and through a preset; a path is what a human can check.
3. **Reports the roots it scanned** whether or not anything was found, so an empty answer is an
   answer — requirement 2 of [FR 025's `mpfb_list_presets`](../025-character-presets/README.md),
   and the same reasoning.
4. **Reports `faceunits01_installed`**, and takes `refresh` for it, per
   [a capability that depends on an optional asset pack](../../../specifications/mpfb-integration.md#a-capability-that-depends-on-an-optional-asset-pack).
   An expression file can exist while the face-unit targets it references do not; the catalogue is
   then a list of things that cannot be applied, and it must say so rather than let
   `mpfb_apply_expressions` discover it. The *file scan* itself is not cached —
   `list_available_expressions` walks the disk every call — so `refresh` means the pack probe only,
   and the description says which.
5. **Not capped, not paged.** An expressions library is tens of files. The docstring says so, so a
   caller does not look for `truncated`. Revisit only if a live run finds otherwise.
6. **Reports unreadable files rather than hiding them.** `list_available_expressions` skips a file
   that fails to parse with only a `_LOG.warn`; the command counts them and names them, because an
   expression an agent saw in MPFB's panel and cannot find here is otherwise a mystery with no
   evidence.
7. **Reports a file that is shadowed.** Because the first root wins, a file in `user_data` is
   invisible whenever a higher-priority root holds the same library-relative path — and
   [requirement 29](#mpfb_save_expression--keep-a-composed-face) makes that the case a saved
   expression can land in. Each shadowed file is named with the file that shadows it, so an agent
   that just saved an expression and cannot find it is told why.

### `mpfb_get_expression` — what the character is wearing

8. Resolves the basemesh from any object in the character's family and answers `found: false` with a
   sentence rather than raising when it cannot.
9. Returns `applied_expressions` — the persistent stack stored on the basemesh as
   `mpfb_applied_expressions` — one `{fragment, weight}` row each, in the stored order (sorted by
   fragment; see requirement 17), plus `resolved` and the absolute `path` for each row found on
   disk.
10. **Reports a stack row whose file is gone.** `aggregate_expression_stack` skips an unresolvable row
    with a `_LOG.warn` and carries on, so a character loaded from a preset built elsewhere is quietly
    wearing less expression than its stack claims. Each row gets `resolved: true/false` and the
    response says how many were unresolvable, so the count is checkable without scanning the rows.
11. **Reports whether the stack explains the face**, and this is the requirement the tool exists for.
    Compute `FaceService.aggregate_expression_stack(stack)` and compare it against
    `read_current_expression()`; report `matches_stack`, the `aggregate` itself, and — when they
    disagree — `unexplained_face_units`, the units whose live value no stack row accounts for. That
    set is precisely the work a subsequent `mpfb_apply_expressions` call will destroy, and it is
    invisible everywhere else, MPFB's own UI included. It is also exactly what
    `mpfb_save_expression` exists to rescue, and the response says so when the set is non-empty.
    See [Two mechanisms, one set of shape keys](#two-mechanisms-one-set-of-shape-keys).
12. **Does not restate the live face-unit values.** Those are
    [`mpfb_get_face_units`](../026-face-units/README.md)' answer, and two tools reporting the
    same 52 numbers is two answers that can disagree. This tool reports the *aggregate* the stack
    implies and the *difference* from what is live, and names `mpfb_get_face_units` for the raw
    reading. The boundary is stated in both descriptions.
13. Reports `faceunits01_installed` and takes `refresh`, as requirement 4.

### `mpfb_apply_expressions` — wear one, or several

14. **Batched**, for the same reason `mpfb_set_face_units` is: takes `expressions`, a list of
    `{fragment, weight}` dicts, weight in 0.0-1.0. MPFB's own path is one `set_stack_weight` call per
    slider, and each of those re-reads, re-aggregates and rewrites the whole stack; doing that eight
    times across the socket would be eight rebuilds to reproduce one saved face.
15. Takes `mode`, either `"merge"` (default — upsert each fragment into the existing stack,
    latest-wins per fragment, matching `set_stack_weight`) or `"replace"` (the stack becomes exactly
    the given rows). A weight of `0.0` **removes** that row, which is `set_stack_weight`'s own rule.
    `mode: "replace"` with an empty list is how an agent clears everything, so no fifth tool is
    needed for it — and the description says that explicitly, because it is not guessable.
    `mode` is one of the narrow local vocabulary checks, in the class
    [`mpfb_set_skin`'s `skin_type` earned](../../../specifications/tool-interface.md#validate-before-crossing-the-socket);
    the authoritative check stays in the command.
16. **Resolves every fragment before mutating the stack**, per
    [a batched mutating tool resolves before it writes](../../../specifications/mutating-tools.md#a-batched-mutating-tool-resolves-before-it-writes).
    A fragment that `AssetService.find_asset_absolute_path(..., asset_subdir="expressions")` cannot
    resolve is a refusal — `ready: false`, `blocked_by` naming it, `performed: false`, the stack
    untouched — naming the fragments that do exist, capped, per
    [how tools name things that can be added](../../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added).
    `aggregate_expression_stack` would otherwise warn and skip, producing a success response for a
    face that did not change. Note that `find_asset_absolute_path` matches by **basename** across
    every root and falls back to the first match; where it resolves a fragment to a file other than
    the one `mpfb_list_expressions` listed under it, the response says which file it used.
17. **Writes the stack only through `_write_applied_expressions`**, never by setting the custom
    property directly. That function normalizes each row and sorts by asset; a command that skipped
    it would produce stacks MPFB's own writes silently reorder, and two readers would disagree about
    whether anything changed.
18. **Refuses when the pack is absent**, per
    [preconditions are answers](../../../specifications/mutating-tools.md#preconditions-are-answers) and
    [the asset-pack rule](../../../specifications/mpfb-integration.md#a-capability-that-depends-on-an-optional-asset-pack).
    Without `faceunits01` the stack is written, `set_expression` finds no target file for any unit,
    the face does not move, and every signal an MCP tool has says it worked. This is worse than
    `mpfb_set_face_units`' version of the case, because the stack write **persists** — the character
    is left claiming to wear an expression it has never displayed.
19. **Reports what the aggregate clamped.** `aggregate_expression_stack` sums
    `file_weight * row_weight` per unit and clamps to `[0, 1]`. Two expressions that both open the
    jaw saturate, and an agent that then raises a weight and sees no change has no way to find out
    why. `clamped_face_units` names them.
20. **Reports what it discarded.** If the live state diverged from the stack before the call
    (requirement 11's condition), that composed work is gone — `clear_expression` runs
    unconditionally inside the rebuild. The response names the discarded units and names
    `mpfb_save_expression` as what would have kept them. **It does not refuse**: an agent that
    composed a face and then applies a library expression has, on the most natural reading, changed
    its mind — and now that saving exists, it had a way not to lose the work. The effort should
    confirm this against a real session rather than treat it as settled; if refusal turns out to be
    right it needs an override argument, and that is a description-budget cost requirement 36 has to
    fund.
21. Takes `refit` (a real `bool`, default `True`, matching the library panel's `auto_refit`, which is
    `True` in `ExpressionsLibraryProperties`) and detects the unrefittable rig through
    [`shared/refit_blocker.py`](../../../bridge/mpfb_bridge/shared/refit_blocker.py)'s
    `rig_refit_is_blocked`, phrasing its own sentence as that module requires — the sixth command to
    use it. `performed` is stamped through
    [`shared/performed.py`](../../../bridge/mpfb_bridge/shared/performed.py)'s `with_performed`.
22. **Returns the resulting aggregate and the resulting stack**, so a caller does not need a second
    call to learn what it is now wearing.

### `mpfb_save_expression` — keep a composed face

23. **Saves the character's live face**, read with `FaceService.read_current_expression(basemesh)`,
    through `FaceService.save_expression`, which already filters zero-valued units, drops names not
    in `ARKIT_FACEUNITS`, rounds to four decimals and defaults the metadata. Subject resolution is
    requirement 8's.
24. **Reads the shape keys, not MPFB's composer sliders, and says so.** MPFB's own save operator
    (`ui/create_assets/makeexpression/operators/save.py`) builds the file from the composer panel's
    scene properties, `MPFB_EX_<unit>` — which `mpfb_set_face_units` does not write, since it goes
    through `FaceService.set_expression` directly. Reproducing the operator would save the panel's
    stale sliders rather than the face the agent composed. This is a case of
    [MPFB's own code paths disagreeing](../../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it),
    and the command docstring names the choice. A consequence worth stating in the description: the
    live face includes whatever the stack contributed, so what is saved is **the whole face**, not
    only the part composed on top of the stack.
25. **Addresses the file by name, never by a path**, per
    [a tool whose effect is outside the `.blend` owes more](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more).
    The file is `<name>.json` directly in `LocationService.get_user_data("expressions")`, and
    `fragment` is `<name>.json`. The command builds that absolute path itself and hands
    `save_expression` a path with a directory part, as MPFB's operator does, so that
    `save_expression`'s bare-name branch — which appends `.json` only when it is absent — never
    decides what the file is called.
26. **The name is validated on this side of the socket, by the rule presets already use.** Letters,
    digits, `_`, `-` and `.`, at most 64 characters, not starting with a dot — stricter than MPFB's
    operator, which rejects only `/`, `\`, `.` and `..`, and strict in the direction the specification
    requires. The name is saved **as given**: the composer's `expression_name` property says names
    are "lowercased and dash-separated when saved", which nothing in MPFB does; that is a defect
    candidate below, not a behaviour to invent. See
    [One name rule, two artifacts](#one-name-rule-two-artifacts) for where the rule lives.
27. **`overwrite: False` by default**, and an existing file is a refusal carrying its size and
    modification time. `user_data/expressions/` is also where an **installed asset pack** puts its
    expressions, so `overwrite: True` can replace a file the user did not write; the description says
    so in one clause.
28. **`path` and `fragment` are in every answer**, refusals included.
29. **Refuses a name that would be shadowed.** `user_data` is third in root priority. A `smile.json`
    saved there while `mpfb_data` or `mh_data` holds an expression file with the same library-relative
    path would be written, and then never listed (`list_available_expressions` keeps the first root's
    copy), never applied, and never restored from a preset — and because `find_asset_absolute_path`
    matches by basename, a same-named file in *any subdirectory* of a higher-priority root has the
    same effect on application. The command refuses with `blocked_by: "name_shadowed"`, naming the
    file that would win. MPFB's own panel says the opposite of what its code does — the composer's
    `available_expression` property claims "user-saved expressions take priority over system-shipped
    ones" — which is a defect candidate below and has to be **confirmed live** before the refusal is
    built on it.
30. **Refuses an empty face** with `blocked_by: "empty_expression"`. The file format says an
    expression with no non-zero face units is not valid, and MPFB's operator refuses one; without the
    check, `save_expression` would write a file with an empty `face_units`.
31. **Takes the metadata as flat optional arguments**: `description`, `tags` (a list of strings),
    `author`, `copyright`, `license`, `homepage`. The file's `name` field is the name. `license`
    follows the composer panel's default of `"CC0"` rather than `save_expression`'s empty string, per
    [where MPFB's UI re-defaults a service argument](../../../specifications/mpfb-integration.md#where-mpfbs-ui-coerces-or-re-defaults-a-service-argument-mpfb-mcp-does-the-same-and-reports-both),
    and the response reports the metadata written. A licence is a statement made on the user's
    behalf; if the effort finds that default wrong for an agent to apply silently, it records why
    and departs from the panel explicitly.
32. **Reports what it wrote**: the `face_units` as stored (after rounding and zero-dropping, so a
    caller comparing with its own request sees the file rather than the request), `overwrote`, and
    `previous_file` in FR 025's shape.
33. **Does not touch the character, and says what makes the face durable.** Saving writes a file and
    nothing else: the face on the character is still transient until the stack references it. The
    response names the next call — `mpfb_apply_expressions` with `mode: "replace"` and the new
    `fragment` at `1.0`. **Replace, not merge**: the saved file already contains whatever the stack
    contributed (requirement 24), and merging would count it twice. The tool deliberately does **not**
    offer to apply as well: one call with two effects is a call whose second half can refuse after
    its first has written a file, which is the partial outcome
    [the robustness requirement](#non-functional-requirements) forbids.
34. **Makes the new file visible to MPFB's library panel**, as MPFB's save operator does by calling
    `refresh_expression_sliders()` — the panel's sliders are registered once at import, so a file
    saved without it has no slider until Blender restarts. This is the same UI-module question as
    `write_slider_values` and is settled with it; see
    [Keeping MPFB's panel honest means calling into a UI module](#keeping-mpfbs-panel-honest-means-calling-into-a-ui-module).

### What this request changes in `mpfb_set_face_units`

35. **`mpfb_set_face_units` gains the computed divergence**, per the last paragraph of
    [a tool whose effect is known in advance to be transient](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-known-in-advance-to-be-transient).
    After the write it reports `matches_stack` and `unexplained_face_units` as requirement 11 defines
    them, and names `mpfb_apply_expressions` as what will overwrite the face and
    `mpfb_save_expression` as what will keep it. Two things in the landed tool change with it:
    - **The static sentence leaves the response.** FR 026 put "A composed face is transient…" in the
      tool description *and*, in the command's `_message_for`, in every successful answer — the
      per-response form that specification says not to use. The computed field replaces the one in
      the message. The one in the description stays, reworded: it is still true, and it is what an
      agent reads *before* calling. Its "applying a saved expression once that tool exists" becomes
      the tool's name.
    - **The stated reason for `refit`'s default is wrong and gets corrected.** The command
      docstring, the tool, [HISTORY.md](../../HISTORY.md) and the root CLAUDE.md all say
      `mpfb_set_face_units` defaults `refit` to `True` "matching the composer panel's `auto_refit`".
      The composer's `auto_refit`
      (`ui/create_assets/makeexpression/properties/auto_refit.json`) defaults to **`False`**; it is
      the *library* panel's that defaults to `True`. The effort decides whether the default stays
      `True` on its merits — composing is usually one call, and garments do not follow the face
      without a refit — or moves to `False` to follow the panel, and in either case the reason
      written down becomes a true one.
    - **`mpfb_get_face_units` gains nothing.** It is deliberately left reporting only live values;
      the stack view is `mpfb_get_expression`'s, per requirement 12. Recorded here so the asymmetry
      reads as a decision rather than an omission.

## Non-functional requirements

36. **The conflict must be visible without being alarming.** Requirements 11, 20 and 35 all exist
    because MPFB destroys work without saying so. The responses must make that legible in the normal
    case — where nothing was composed, `matches_stack` is `true` and there is nothing else to read —
    and loud only when there is genuinely something to lose. A tool that warns every call trains an
    agent to ignore it.
37. **Description budget.** Four tools, and three of them have to instruct about a two-layer model
    FR 026 also instructs about. The conflict is explained **once**, in `mpfb_set_face_units` (which
    already spends the bytes on it), and the other tools point at it rather than restate it.
    `mpfb_save_expression`'s six metadata arguments are the largest new schema cost; they are one
    line each and the description does not re-explain the file format. The ceiling change is
    recorded with its reason beside it in
    [`test_description_budget.py`](../../../tests/test_description_budget.py).
38. **Robustness: a refusal is never a partial write.** In `mpfb_apply_expressions` the pack check
    and every fragment are settled before `_write_applied_expressions` or `set_expression` is called;
    MPFB's own `apply_expression_file` sets the precedent — it validates the file up-front "so we
    don't mutate the stack on a bad file" — and this command follows it rather than relying on it.
    In `mpfb_save_expression` the name, the existing file, shadowing and the empty face are all
    settled before the file is opened.
39. **Cost.** Transport is no longer a cost worth estimating here. Inside Blender the picture is
    uneven and the descriptions should not flatten it: listing walks the disk every call;
    `mpfb_apply_expressions` re-loads and re-aggregates **every file in the stack** on every call,
    so a five-expression stack is five JSON reads per change, and the shadowing check in
    requirement 29 is a walk of every expressions root. Batching (requirement 14) is what keeps the
    rebuild at one per call rather than one per expression.

## Architecture

### Two mechanisms, one set of shape keys

This is the single most important thing the effort has to get right, and this request owns it
because it implements the half that does the damage — and, now, the bridge between the two halves.

The **composer** ([FR 026](../026-face-units/README.md)) writes the 52 `!ex-` shape keys
directly. The **library** — this request — never writes a shape key from a user action at all. It
maintains a stack of `{asset, weight}` rows in a custom property on the basemesh, and every change
re-derives the whole face: `aggregate_expression_stack` → `clear_expression` → `set_expression`.

The consequence is asymmetric and unsignposted. Composed work is invisible to the library, and any
library call — a weight change, an application, a preset load — **destroys it**, because
`clear_expression` runs unconditionally in the rebuild. In MPFB's UI this is survivable: the panels
are in different tabs and a human sees sliders move. Across MCP there is no such feedback.

**Saving is the only way across.** `mpfb_save_expression` turns a composed face into a file the
library can reference; `mpfb_apply_expressions` in `replace` mode then makes the stack explain the
face exactly, and from that point on the library's rebuilds reproduce it rather than erase it. That
sequence is what the responses of requirements 11, 20, 33 and 35 point an agent at.

The divergence check in requirement 11 is a comparison **MPFB never makes anywhere**, and it is
cheap: aggregate the stack, compare to the live read, subtract. That single computation funds
requirements 11, 20 and 35, which is why it is the shared module below rather than three
implementations.

### What FR 026 left, and what this builds on

FR 026 has landed, and this request uses three things it shipped: the asset-pack rule, now standing
in [mpfb-integration.md](../../../specifications/mpfb-integration.md#a-capability-that-depends-on-an-optional-asset-pack)
(requirements 4, 13 and 18 apply it without extending it); the face-unit reading requirement 11's
comparison needs; and the `set_face_units` command requirement 35 extends. The ARKit vocabulary is
read off `FaceService`'s module through `sys.modules[face_service.__module__]`, the way
`set_face_units` already reads `ARKIT_FACEUNITS`, and is not copied into a shared module.

A character can already end up with a non-empty stack today, through
`mpfb_create_human_from_preset`, which is one reason `mpfb_get_expression` is worth having even
before anything here writes a stack.

### Reaching the stack, and the private accessors

**The stack accessors are private.** `_read_applied_expressions` and `_write_applied_expressions`
carry a leading underscore, and both `mpfb_get_expression` and `mpfb_apply_expressions` need them.
`HumanService` itself calls the first, with a `pylint: disable=W0212` — so there is precedent, and
the alternative is reimplementing the tolerant decode (the property may hold a JSON string *or* a
list) in a command, which is a second implementation that can drift. The lean is to call the private
methods through the `FaceService` the resolver hands over, and to say so in the command docstrings;
`APPLIED_EXPRESSIONS_PROP` being public while its two accessors are not is a small defect worth
raising (below).

### Keeping MPFB's panel honest means calling into a UI module

**This is the sharpest open question in the request, and it should be settled first**, because two
of the four commands depend on the answer.

The expressions-library panel's sliders are scene properties, one per expression file, registered
**once, when `ui/apply_assets/useexpression` is imported** (`_register_expression_sliders()` runs at
module level and fills `_EXPRESSION_PROP_MAP`). Two MPFB functions in that module keep the panel
agreeing with the character:

- `write_slider_values(scene, stack)` syncs the slider values from a stack.
  `HumanService._apply_expressions_from_human_info` calls it, inside a try/except, so that a preset
  load leaves the panel right. An `mpfb_apply_expressions` that skips it leaves MPFB's UI showing
  weights the character does not have — the "two lists that disagree" failure FR 025 named, in a
  place a human is looking at.
- `refresh_expression_sliders()` registers a slider for any file that appeared since. MPFB's save
  operator calls it, inside a try/except. An `mpfb_save_expression` that skips it leaves the new
  file absent from MPFB's panel until Blender restarts — and `write_slider_values` silently ignores a
  stack row with no slider, so the gap compounds.

The standing rules in [architecture.md](../../../specifications/architecture.md#never-import-mpfb-submodules-directly)
cover **reading** a UI module, and only one kind: a constant table, reached through `sys.modules`
rather than imported, as `list_urls` reads `<root>.ui.weburls`. This would be something new —
**calling** a UI module's functions for their side effect on MPFB's own UI state, one of which
registers Blender properties — and `useexpression` is not a constant table; its map is exactly the
import-time snapshot [the modifier case](../../../specifications/mpfb-integration.md#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not)
was a reason not to depend on. Here, though, calling it is how the snapshot is *corrected*, not how
it is relied on.

The lean is to **do it**, under the rules that already bind the `weburls` read: the module is found
with `sys.modules.get("<root>.ui.apply_assets.useexpression")`, the root coming from the resolver's
module scan, **never** `importlib`; a miss is an ordinary answer; each call is wrapped in the same
try/except MPFB wraps it in; and the response reports `panel_synced` (with a reason when `false`)
rather than leaving the outcome implicit. The argument is that every other way the stack or the
library changes inside MPFB does this, and an mpfb-mcp write that did not would be the odd one out.
That `useexpression` is in `sys.modules` on a normal install is a claim only the live check can make.
If the effort decides the other way, both tool descriptions must say the panel needs a manual resync
and both command docstrings must say the choice was made rather than missed. Either way the decision
is written into [architecture.md](../../../specifications/architecture.md#a-ui-module-with-no-service-behind-it)
as a third case, not left in two commands.

### One name rule, two artifacts

`mpfb_save_expression` needs exactly the character rule presets have, for exactly the reason
presets have it: a name that becomes a path. That rule already exists twice —
`src/mpfbmcp/preset_names.py` (now [`artifact_names.py`](../../../src/mpfbmcp/artifact_names.py)) before the socket and
[`bridge/mpfb_bridge/shared/preset_files.py`](../../../bridge/mpfb_bridge/shared/preset_files.py) before
`open()` — with a drift test in `tests/test_save_preset.py` running both over one table. But both are
written around `human.<name>.json`, and their rejection sentences say "preset".

Copying them would make four copies of a rule whose two-copy form is already justified only by the
consequence of a gap; FR 025's reason for the second copy does not argue for a third and fourth. The
lean is to **generalise the rule once on each side** — the pattern, the length and the dot rules
stay single; the noun in the sentence and the "addressed by name" hint become arguments — and to
extend the drift test to cover both artifacts. What stays per artifact is the path: presets keep
`human.<name>.json` in the config directory, expressions get `<name>.json` in
`user_data/expressions/`.

This touches shared code on both sides of the socket, which is a deliberate exception to the root
CLAUDE.md's "adding a tool touches exactly four things", and the effort says so rather than letting
it read as drift. If the effort decides to copy instead, it records why.

### Four tool modules, four commands, one shared module

`tools/list_expressions.py`, `tools/get_expression.py`, `tools/apply_expressions.py` and
`tools/save_expression.py`, four `register()` calls in [`__init__.py`](../../../src/mpfbmcp/__init__.py);
the same-named command modules in [`bridge/mpfb_bridge/commands/`](../../../bridge/mpfb_bridge/commands),
and four entries in [`commands/table.py`](../../../bridge/mpfb_bridge/commands/table.py), each declaring
`requires_mpfb=True`. None of the four is meaningful without a working MPFB.

**One new shared module, `bridge/mpfb_bridge/shared/expression_divergence.py`.** The divergence
computation — aggregate the stack, read the live units, return the difference — is needed by
`get_expression`, `apply_expressions` and `set_face_units` (requirement 35), and it must give the
**same** answer in all three. That is the bar
[shared modules, and what warrants one](../../../specifications/architecture.md#shared-modules-and-what-warrants-one)
sets: a number two or more commands report and act on, where a disagreement would look like a bug in
neither. It is handed `services`, like every shared module that reads MPFB, and takes the count
from seven to eight. `set_face_units.py` is the command most likely to grow a copy of its own, since
it currently has none; the bridge test in [Tests](#tests) that runs all three over one character is
what catches that.

**[FR 034](../034-character-summary/README.md) is ordered after this request and reads through it.**
`mpfb_get_character_summary` reports `applied_expressions`, `matches_stack` and
`unexplained_face_units` by calling the same implementation `get_expression` does, so keep the
stack read (the `{fragment, weight, resolved}` rows) callable apart from the command: either in
`expression_divergence.py` or in a function FR 034 can move there without changing
`get_expression`'s answer.

### Defect candidates

Each to be confirmed against the running install before filing, per
[FR 019](../019-file-mpfb-defects/README.md), in
`../mpfb2/features/MCP_DISCOVERED_BUGS.md`:

- **User-saved expressions are shadowed, and the panel says the opposite.** The composer's
  `available_expression` property says "user-saved expressions take priority over system-shipped
  ones with the same name"; `list_available_expressions` scans `mpfb_data`, `mh_data`, `user_data`,
  `second_root` in that order and keeps the first. The substantive one here, and requirement 29's
  premise.
- **`find_asset_absolute_path` resolves an expression fragment by basename.** Two expressions with
  the same file name in different subdirectories, or different roots, resolve to whichever was found
  first unless the parent directory happens to match — so a stack row's fragment does not reliably
  name one file. Shared with every other asset type; worth one report rather than one per type.
- **`expression_name` promises normalisation nothing performs.** "Will be lowercased and
  dash-separated when saved"; neither the operator nor `save_expression` does either.
- **The applied-expressions stack has a public constant and private accessors.**
  `APPLIED_EXPRESSIONS_PROP` is public, `_read_applied_expressions` and `_write_applied_expressions`
  are not, and `HumanService` reaches across the underscore with a lint suppression. Either the
  accessors are part of the API or the constant is not.

FR 026 confirmed two substantive `FaceService` defects (`set_expression` cannot report failure; the
install-check cache is never invalidated on install) and
[left them unfiled](../026-face-units/README.md#verification-status). This effort files them
together with its own, since it touches the same service and the same shape of report.

## Affected specifications

- [mpfb-integration.md](../../../specifications/mpfb-integration.md) — under
  [where MPFB's own code paths disagree](../../../specifications/mpfb-integration.md#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it):
  the composer/library split, which is the clearest instance yet — two code paths, one outcome, one
  silently destroying the other's work — and the save operator reading panel sliders where this
  saves shape keys. The asset-pack rule is **applied**, not extended. Under
  [where MPFB's UI re-defaults a service argument](../../../specifications/mpfb-integration.md#where-mpfbs-ui-coerces-or-re-defaults-a-service-argument-mpfb-mcp-does-the-same-and-reports-both),
  the `license` default, however requirement 31 settles.
- [mutating-tools.md](../../../specifications/mutating-tools.md) — a mutating tool that **destroys state
  it did not create and cannot restore**, and what it owes the caller in exchange (name what went,
  and what would have kept it). The last paragraph of
  [known in advance to be transient](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-known-in-advance-to-be-transient)
  anticipates this effort and is rewritten from "a later effort can" to what it did.
  [Outside the `.blend`](../../../specifications/mutating-tools.md#a-tool-whose-effect-is-outside-the-blend-owes-more)
  gains its second artifact and one new obligation: **refuse to write where the result cannot be
  found** (requirement 29). The refitting family grows to six.
- [responses.md](../../../specifications/responses.md) — reporting a **fact MPFB does not compute**
  (`matches_stack`, `unexplained_face_units`, `clamped_face_units`, a shadowed file). The
  [derived-fact convention](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact)
  likely covers it; check whether it needs extending or only an example.
- [architecture.md](../../../specifications/architecture.md) — the
  [shared modules](../../../specifications/architecture.md#shared-modules-and-what-warrants-one) list
  goes from seven to eight, and `preset_files.py`'s entry changes if the name rule is generalised;
  and, if the effort decides to call into `useexpression`, a third case under
  [a UI module with no service behind it](../../../specifications/architecture.md#a-ui-module-with-no-service-behind-it),
  written down as one rather than left in two commands.
- [tool-interface.md](../../../specifications/tool-interface.md) — `mode` joins the narrow list of
  locally-checked vocabularies, and the description-budget ceiling moves.
- [vision.md](../../../specifications/vision.md#target-tool-catalog) — *Catalogues* 4 → 5,
  *Introspection* 6 → 7, *Creation and modification* 15 → 17, and that row's "**keep** it, as a
  preset" gains "and a face as an expression". Twenty-seven tools become thirty-one, and twenty-six
  commands thirty; the root CLAUDE.md's tool and test tables gain four rows each.

## Tests

Split as [testing.md](../../../specifications/testing.md#a-tool-is-tested-where-it-runs) requires:
`tests/` holds each tool's own validation and what reaches the wire, against `fake_bridge`; everything
about what a tool *answers* is asserted against a real MPFB in `bridge/test/`.

- **`tests/test_list_expressions.py`, `tests/test_get_expression.py`** — `refresh` must be a real
  `bool`, the subject name's shape, and what reaches the wire.
- **`tests/test_apply_expressions.py`** — entry shape exhaustively: a non-list, a non-dict entry, an
  unknown key, a missing key, a weight outside 0.0-1.0; `mode` checked locally against its two
  values; `refit` as the string `"false"`. That the fragment vocabulary is deliberately *not* checked
  here.
- **`tests/test_save_expression.py`** — the name rule, exhaustively and **before anything is sent**,
  as `test_save_preset.py` does for presets; `overwrite` a real `bool`; `tags` a list of strings; each
  metadata argument a string. The two-way drift check between the two copies of the name rule
  extended to cover the expression artifact, wherever it ends up living.
- **`bridge/test/tests/sss_list_expressions_test.py`** — over a real expressions tree in redirected
  data roots (`only_these_data_roots` in [`_fixtures.py`](../../../bridge/test/tests/_fixtures.py)): the
  same library-relative path in two roots (first root wins, and the loser reported as shadowed), a
  malformed JSON file (skipped, but *counted and named*), a file with no `name` (label falls back to
  the basename with underscores replaced), and an empty tree. The pack-absent path asserts
  `faceunits01_installed: false`.
- **`bridge/test/tests/ttt_get_expression_test.py`** — the divergence check is the centre of this
  module and needs four cases: stack and live agree; live has a unit no row explains (composed work);
  a stack row whose file is missing; a stack whose aggregate clamped. Plus requirement 12's boundary:
  the response does **not** carry a full 52-unit listing.
- **`bridge/test/tests/ppp_mutating/apply_expressions_test.py`** — an unresolvable fragment refusing
  before the stack is touched, asserting the custom property is byte-identical afterwards; `merge`
  upserting and `replace` replacing; weight `0.0` removing a row; `replace` with an empty list
  clearing; the pack-absent refusal asserting **nothing was written to the stack**, which is
  requirement 18's whole point; clamping reported; and requirement 20's case — composed units present
  beforehand are named as discarded.
- **`bridge/test/tests/ppp_mutating/save_expression_test.py`** — writing into a redirected
  `user_data`, per `ppp_mutating/__init__.py`'s rule for anything written outside the `.blend`: the
  file's contents after rounding and zero-dropping; the overwrite refusal carrying size and mtime; the
  shadowed-name refusal against a higher-priority root holding the same name; the empty-face refusal;
  and that the character's stack and shape keys are unchanged by a save.
- **`bridge/test/tests/ppp_mutating/set_face_units_test.py`** (extended) — the divergence fields
  appear after a write, and report `matches_stack: true` when the character has an empty stack and
  composes nothing, which is the common case and must not read as a warning.
- **One bridge test running all three divergence users over one character**, in the shape the
  `modifier_reading.py` users share: apply an expression, compose a unit on top, and assert all three
  commands report the same divergence. That is what the shared module exists for, and it means
  nothing asserted separately.
- **One bridge test for the round trip that closes FR 026's gap**: compose, save, apply the saved
  fragment with `replace` at `1.0`, and assert the face is unchanged within the file's four-decimal
  rounding and `matches_stack` is now `true`.
- **Fixtures reproduce the install, not a convenient version of it**, per
  [testing.md](../../../specifications/testing.md#a-fixture-reproduces-the-install-never-a-convenient-one):
  expression files in a fixture are written by `FaceService.save_expression` or copied from
  [the format document](https://github.com/makehumancommunity/mpfb2/blob/master/docs/fileformats/expression.md), not hand-simplified JSON.
- **`tests/test_description_budget.py`** — ceiling raised, reason in the comment.
- **`tests/test_verification_smoke.py` and `verification/smoke.py`** — four items, with the
  pack-absent degradation FR 026's items settled. Two leave something behind that the
  [verification README](../../../verification/README.md) must say: `mpfb_apply_expressions` leaves a
  **custom property on the basemesh**, and `mpfb_save_expression` writes a **second file outside the
  `.blend`**, into the user's expression library, where MPFB's panel will show it. That item follows
  `mpfb_save_preset`'s: one constant name that says where it came from, and `overwrite=True` so a
  second run is not refused. The README's "exactly one file" becomes two, and the effort decides
  whether that is acceptable or whether the item stays refusal-only.

**This effort needs a real Blender, and for more than one claim.** Five cannot be reached from this
side: that a composed face is really destroyed by the next `mpfb_apply_expressions` (requirement 20);
that `ui.apply_assets.useexpression` is in `sys.modules` on a normal install and that the panel's
sliders agree with the character after an apply and gain a slider after a save — the whole question
behind [the UI-module decision](#keeping-mpfbs-panel-honest-means-calling-into-a-ui-module); that a
user-saved file really is shadowed by a same-named higher-priority one (requirement 29, and the first
defect candidate); that an expression applied here survives a `mpfb_save_preset` /
`mpfb_create_human_from_preset` round trip; and that the full sequence — compose, save, apply,
preset round trip — returns the composed face, which is the secondary goal. A script in this subdir
does all five against a character carrying a rig and a garment, prints what differed, and moves to
`done/` with the request. What stays behind is the four smoke items.

## Verification status

All of it ran, against Blender 5.1.0 with MPFB 2.0.17 from source and this machine's own
`faceunits01` pack.

- **[`live_check.py`](live_check.py)**, in this subdir: 23 checks, through the **real tools over the
  real socket** to a headless Blender the script starts itself, on a character carrying a rig and a
  garment. All passed. It confirmed the five claims in [Tests](#tests): a composed unit really is
  gone after the next `mpfb_apply_expressions`, which names it; `useexpression` is in `sys.modules`
  headless, so `panel_synced` is true and a save registers a slider (the windowed half was checked
  separately, in the developer's GUI Blender, where the module was loaded with both user expressions'
  sliders registered); a user-data file is shadowed by a same-named `mpfb_data` one, both in MPFB's
  listing and for `mpfb_save_expression`; an applied expression survives a preset round trip; and the
  whole sequence - compose, save, apply `replace`, preset - returns the composed face within
  4e-5. It writes into the developer's real directories and removes what it wrote.
- **Bridge tests**: `sss_list_expressions_test.py` (7), `ttt_get_expression_test.py` (7),
  `ppp_mutating/apply_expressions_test.py` (13), `ppp_mutating/save_expression_test.py` (10),
  `ppp_mutating/expression_divergence_test.py` (3: the three divergence users agree about one
  character, the no-stack case is not a warning, and the compose-save-apply round trip) and two more
  in `set_face_units_test.py`. **349** in all, green.
- **Unit tests**: four new modules and the generalised drift check, **423** in all, green; the
  description budget raised to 68,300 and the schema budget to 12,100, reasons in
  `tests/test_description_budget.py`.
- **Four smoke items**; the run is 33 items, all passing, in 1.5 s against a headless Blender.

### What landed differently from the text above, and why

- **Three shared modules, not one.** `expression_divergence.py` as planned; `expression_panel.py`,
  because two commands reach the `useexpression` UI module and must agree on how and on what
  `panel_synced` means; and `artifact_names.py`, which is where the generalised name rule went on
  the bridge side rather than staying in `preset_files.py` (which now imports it). On the tool side
  `preset_names.py` was renamed `artifact_names.py`. The two `os.stat` helpers behind
  `previous_file` moved with the rule, since both saving commands report with them.
- **The UI-module question was settled the way the request leaned**: call it, through
  `sys.modules`, never import it, report `panel_synced`. Written into
  [architecture.md](../../../specifications/architecture.md#a-ui-module-with-no-service-behind-it) as
  the third case.
- **`mode` is not a local-vocabulary exception** ([requirement 15](#mpfb_apply_expressions--wear-one-or-several)
  and [Affected specifications](#affected-specifications) said it would be). That exception is for
  an MPFB enum MPFB checks only after doing damage; no MPFB function ever sees `mode`, so it is
  this package's own vocabulary and a shape. Recorded in
  [tool-interface.md](../../../specifications/tool-interface.md#validate-before-crossing-the-socket).
- **`discarded_face_units` is measured on both sides of the write** (requirement 20). As first
  written it was the divergence before the call, and the round-trip bridge test showed that reported
  the save-then-replace sequence as discarding every composed unit, when the new stack reproduces
  all of them. It is now the units the stack did not explain *and* the rebuild moved. Refusal was
  not adopted: the live check confirmed the loss is real, and the list is the cheaper answer.
- **The pack refusal (requirement 18) covers additions only.** A call that only removes rows is
  allowed without the pack, because removing a row claims nothing, and a row whose file is gone is
  how a stack from another machine gets cleaned up — so removal is never resolved against the disk.
- **A fragment may appear once per call**, refused on both sides: two weights for one row in one
  batch has no reading more likely right than the other.
- **`mpfb_apply_expressions` takes `fragment` only**, a departure from
  [an acting tool accepts every identifier its catalogue reports](../../../specifications/tool-interface.md#an-acting-tool-accepts-every-identifier-its-catalogue-reports),
  recorded there: a stack row *is* a fragment, and MPFB's path-to-fragment conversion returns a bare
  basename for a file outside every root.
- **`license` stays `CC0`** (requirement 31): the description names the default, so an agent
  applying it has read it, and MPFB's own panel applies the same one.
- **`mpfb_set_face_units`' `refit` stays `true`** (requirement 35), for the reason now written in
  its command docstring, tool docstring, HISTORY.md and CLAUDE.md: the composer panel's `false`
  exists because a dragged slider would refit dozens of times, and a composing call is one batch.
  It also gained `applied_expression_count` beside the two divergence fields, and the selection
  restore around `refit()` every other refitting command has — added to `mpfb_apply_expressions`
  too. No disturbance of the selection could be provoked on this install, even with a garment
  equipped, so the test that pins it says it would pass without the fix.
- **The smoke run now writes two files outside the `.blend`**, and that was judged acceptable
  rather than keeping the save item refusal-only: a mutating item must come back
  `performed: true`, and one that never writes would never notice writing had broken.
  [verification/README.md](../../../verification/README.md) names both files.

### Defect candidates

**Filed**, as items 8-10 of `mpfb2/features/MCP_DISCOVERED_BUGS.md`, each with a reproduction a
fixed MPFB would make fail:

- 8: user-saved expressions are hidden behind system ones, while the composer panel, the system
  expressions README and `list_available_expressions()`' docstring all say the opposite
  (`live_check.py` claims 3a/3b).
- 9 and 10: FR 026's two — `set_expression()` cannot report that it did nothing, and
  `is_faceunits01_installed()`'s cache is invalidated by nothing that installs a pack.

**Not filed**, deliberately:

- `find_asset_absolute_path()`'s basename match is real and is the mechanism behind item 8, but no
  case was provoked here where it chose the wrong file *among expressions* for a reason other than
  root priority. It stays a candidate, and `mpfb_apply_expressions` reports `resolved_path` beside
  `listed_path` so a caller sees it if it happens.
- `expression_name`'s "lowercased and dash-separated when saved" was read from the property
  description and the operator's source; the operator itself was not run, and per
  [FR 019](../019-file-mpfb-defects/README.md) a claim read from source is a hypothesis.
  `mpfb_save_expression` saves the name as given either way.
- `APPLIED_EXPRESSIONS_PROP` public beside private accessors is an API observation, not a defect;
  the commands cross the underscore the way `HumanService` does, and say so.

## References

- [`mpfb2/src/mpfb/services/faceservice.py`](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/services/faceservice.py) —
  `APPLIED_EXPRESSIONS_PROP`, `save_expression`, `list_available_expressions`, `load_expression`,
  `aggregate_expression_stack`, `set_stack_weight`, `apply_expression_file`,
  `rebuild_expression_stack`, `clear_applied_expressions`, `_read_applied_expressions`,
  `_write_applied_expressions`, `_compute_expression_library_relative_path`.
- [`mpfb2/src/mpfb/services/assetservice.py`](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/services/assetservice.py) —
  `get_available_data_roots` (the root order requirement 29 rests on), `get_asset_roots`,
  `find_asset_absolute_path` (the basename match).
- [`mpfb2/docs/fileformats/expression.md`](https://github.com/makehumancommunity/mpfb2/blob/master/docs/fileformats/expression.md) — the JSON
  format key by key, its `.mhpose` ancestry, and the backwards-compatibility rules a reader must
  honour.
- MPFB's own library UI, which three of these tools collapse:
  [`useexpression/__init__.py`](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/ui/apply_assets/useexpression/__init__.py),
  which holds `ExpressionsLibraryProperties`, `_EXPRESSION_PROP_MAP`, `write_slider_values` and
  `refresh_expression_sliders`, and
  [`useexpressionpanel.py`](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/ui/apply_assets/useexpression/useexpressionpanel.py).
- MPFB's own save path, which `mpfb_save_expression` departs from in its source of values:
  [`makeexpression/operators/save.py`](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/ui/create_assets/makeexpression/operators/save.py)
  and the composer's [`properties/`](https://github.com/makehumancommunity/mpfb2/tree/master/src/mpfb/ui/create_assets/makeexpression/properties),
  which hold the `license`, `expression_name`, `available_expression` and `auto_refit` defaults
  cited above.
- [`mpfb2/src/mpfb/services/humanservice.py`](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/services/humanservice.py) —
  `_populate_human_info_with_expression_info` and `_apply_expressions_from_human_info`, which are
  where a preset meets the stack, and the precedent for both the private-accessor call and the call
  into `useexpression`.
- [`bridge/mpfb_bridge/commands/list_urls.py`](../../../bridge/mpfb_bridge/commands/list_urls.py) — the
  one existing command that reaches an MPFB UI module, through `sys.modules` and never an import.
- [`bridge/mpfb_bridge/commands/set_face_units.py`](../../../bridge/mpfb_bridge/commands/set_face_units.py)
  and [`save_preset.py`](../../../bridge/mpfb_bridge/commands/save_preset.py) — the command requirement 35
  extends, and the one whose outside-the-`.blend` shape `mpfb_save_expression` follows.
- [FR 026](../026-face-units/README.md) — the other half: the 52 ARKit units, the asset-pack
  precondition rule this request applies, and the tool requirement 35 extends.
- [FR 025](../025-character-presets/README.md) — the preset tools this request completes the
  round trip for, and the name-not-a-path convention `mpfb_save_expression` follows.
- [FR 008](../008-detail-targets/README.md) — where the batched-tool idiom and the
  resolve-everything-before-writing-anything rule were settled; requirements 14 and 16 reuse both.
- [FR 019](../019-file-mpfb-defects/README.md) — the established shape for a defect report, and
  the rule that a candidate is confirmed against a running install before it is filed.
- [NEXT_STEPS: Expressions](../../NEXT_STEPS.md#expressions) — the entry this request and FR 026 split
  between them, and where saving was queued before it was folded in here.
