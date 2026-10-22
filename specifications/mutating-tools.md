# Mutating tools

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

**Tools that change a character.** Everything a read-only tool owes its caller
([responses.md](responses.md)) still applies; this document is the additional obligations that
come with changing something the caller cannot undo across the socket.

They fall into a sequence: take the subject, check that the world is ready, do only what was
asked, put back what was borrowed, and report what changed — including what changed as a
consequence, and what the change has now invalidated, under one flag name shared by every tool
here. Three further sections cover the cases MPFB makes hard: an ordering constraint nothing
enforces, a batch that must be all-or-nothing, and the one kind of change Blender's undo stack
does not reach at all.

## Where these rules are enforced

A reader looking for the enforcement should not have to guess, and the answer is not the same for
all of them. "The far side" is the twenty-two mutating commands in `bridge/mpfb_bridge/commands/`;
"the near side" is the tool module, which runs before anything is sent.

**No rule in this document changed when those commands were written**, nor when
[FR 036](../feature-requests/done/036-subject-resolver-and-duplication/README.md) moved the parts
they share into shared modules — that effort's before-and-after snapshot of every command was
empty apart from ten deliberately reworded miss sentences.
[FR 032](../feature-requests/done/032-creation-and-modification-migrated/README.md) worked under
reproduction-over-improvement, which is stricter for a mutating tool than anywhere else, because
breaking it has side effects on somebody's `.blend` rather than a different-looking answer.

| Rule | Enforced by |
|------|-------------|
| Any object in the family is a valid subject | A **shared module**, [`bridge/mpfb_bridge/shared/subject_resolution.py`](../bridge/mpfb_bridge/shared/subject_resolution.py), used by every command that takes a subject. Resolution needs MPFB's relationship walk |
| A precondition is an answer, not an exception | The **far side**. Every `blocked_by` branch runs before the mutating call |
| `performed` means the same thing everywhere | A **shared module**, [`bridge/mpfb_bridge/shared/performed.py`](../bridge/mpfb_bridge/shared/performed.py), imported by every mutating command |
| The before/after report | The **far side**, which is the only place that can observe both |
| The caller's selection is restored | A **shared module**: `with selection.restored(...)`, from [`bridge/mpfb_bridge/shared/selection.py`](../bridge/mpfb_bridge/shared/selection.py), around every `refit()` and every operator call. It puts back the active object and the borrowed object's own selection, and **not** the selection of other objects an operator selected, such as a new armature ([NEXT_STEPS](../feature-requests/NEXT_STEPS.md#selection-restore-covers-one-object)). The two export commands use `selection.restored_all()`, which puts back every object's selection and leaves what the command created deselected ([FR 039](../feature-requests/done/039-exporting-characters/README.md)). `mpfb_generate_rigify_rig` reports `active_object_after` instead |
| A batch resolves before it writes | The **far side**. It is a property of the *code*, and nothing below the socket would enforce it |
| A name that becomes a path is a name and never a path | **Both sides, deliberately.** `artifact_names.py` before anything is sent, `shared/artifact_names.py` as the last statement before `open()` - one rule for presets, saved expressions and exports |
| The directory of an export is the human's | The **add-on**: [`bridge/mpfb_bridge/export_directory.py`](../bridge/mpfb_bridge/export_directory.py) reads the bridge's preference or `--export-dir`. The near side has nothing to enforce, because no tool takes a directory |
| `overwrite: False`, and the absolute path in every answer | The **far side** |
| Refuse to write where the result cannot be found | The **far side**, which alone can walk MPFB's roots |
| Argument shape and range | The **near side**, before anything is sent, mostly through [`src/mpfbmcp/arguments.py`](../src/mpfbmcp/arguments.py) — see [Validate before crossing the socket](tool-interface.md#validate-before-crossing-the-socket) |

**One rule is enforced by neither and is worth naming as such.** Nothing makes a *failure*
atomic. `mpfb_create_human_from_preset` builds a character in stages and a mid-way failure leaves
what it built; `mpfb_add_rig`'s `AssertionError` path leaves a partly built armature;
`mpfb_add_asset`'s failed import may leave an object; and `mpfb_create_export_copy` processes a copy
in MPFB's stages, so a failure after the copy leaves a partly processed one (`copy_failed`). What the
rules require in those cases is not a rollback — there is none to be had across a socket — but that
the answer **names what was left behind**, which `objects_created` and `partial_objects_created` do.

## How a mutating tool takes its subject

A tool that changes a character accepts **any object in that character's family** — the basemesh,
its rig, a garment fitted to it — and resolves from there to the object it will actually modify,
through `ObjectService.find_object_of_type_amongst_nearest_relatives()`. That is the same call
MPFB's own panels make, and the reason for it is
[how tools name things](tool-interface.md#how-a-tool-addresses-an-object):
an agent got the name it is holding out of `mpfb_list_objects`, which does not say which member
of a family owns a given property.
Requiring the caller to know that would make every mutating tool need a lookup step first.

- **The response names the object that was modified, not the argument.** `basemesh_name` beside
  `subject_name`, so a caller that passed a rig can see what the change actually landed on.
- **The walk is MPFB's, not a reimplementation.** It descends through children, ascends through
  parents, and takes each parent's other branches on the way — which is what finds a garment from
  the basemesh on a rigged character, since MPFB parents garments to the *rig*.
- **The object resolved to is not always the basemesh.** It is for every phenotype and modeling
  tool, and for `mpfb_add_rig`, because that is what carries what they change. It is not for
  `mpfb_generate_rigify_rig`, which narrows to the character's `Skeleton` and then asks
  `RigService.identify_rig()` which kind it found — the meta rig is the thing being operated on.
  Resolve to whatever owns the change, name it in the response (`metarig_name` rather than
  `basemesh_name` there), and take the subject from anywhere in the family either way.
- **A narrowing step can need the whole set rather than the first match.**
  `find_object_of_type_amongst_nearest_relatives()` returns one object; where two objects of the
  same MPFB type mean different things, take them all and classify. After Rigify generation a
  character's `Skeleton` relative is the *generated* rig, since `adjust_children_for_rigify()`
  re-parents the character onto it — so "already generated" and "that is not a meta rig" are
  different answers that a single lookup could not tell apart.
- **Failing to resolve is an answer**, `found: false` with a sentence, exactly as for the read-only
  tools. A mutating tool also says `ready: false` and `blocked_by: "subject_not_found"`, so that a
  caller branching on `blocked_by` sees every refusal it can get, this one included. Five tools
  answered without the slug until [FR 038](../feature-requests/done/038-subject-not-found-everywhere/README.md),
  and `eee_composite/subject_resolution_test.py` now asks it of every command whose answer carries
  `performed`.

## A mutating tool reports before and after

The mutation-side counterpart of "an empty answer must never be ambiguous": a tool that changes
something and reports only that it succeeded has told the caller very little, and a tool that
changes something with side effects and mentions none of them has told the caller something false
by omission.

- **Report the prior value beside the new one**, per changed field, so the change is verifiable
  without a second round trip — and report a field the caller named even when the value it already
  had was the one requested. "You asked for this and it was already so" is not the same claim as
  not mentioning it.
- **Report what changed as a consequence**, not only what was asked for. `mpfb_set_macro_details`
  returns the macro shape keys before and after, and the removed and added lists, because pruning
  deletes shape keys the caller never mentioned and would otherwise see vanish unexplained.
- **Report what is now stale.** Changing a body's shape invalidates the fit of everything on it,
  and MPFB's own auto-refit defaults to off. So the tool reports `refit_performed`, and when it is
  false, what is left needing attention (`assets_possibly_stale`) and which tool addresses it. An
  expensive default left off is defensible only when the response says what it left undone.
- **Do only what was asked.** A call that names nothing to change must not "helpfully" recalculate:
  it answers immediately, saying that nothing was named. A no-op is a common agent mistake, and a
  full macro rebuild costs seconds.
- **Restore what was borrowed.** Where the command has to activate or select an object to do its
  work — MPFB's own slider callback does — put the previous active object and selection back, in a
  `finally`, so a failure part-way through does not leave the user's scene rearranged. Where it
  genuinely *cannot* — `RigService.generate_rigify_rig()`'s own final act is to select and activate
  the rig it produced, so there is no state left to restore to — say what the selection now is
  (`active_object_after`) rather than quietly leaving the caller to assume nothing moved.
- **A write that preserves something reports how well it did**, as a measured number rather than
  that it ran. `mpfb_set_pose_switches` snaps a limb so that changing a switch does not move it,
  and reports `snap_error`: the furthest any joint of the limb's deforming chain moved
  ([FR 042](../feature-requests/done/042-posing-bones-switches-and-reset/README.md)). A snap that failed then shows up as millimetres, which the effort
  found is not hypothetical: a limb `IK_Stretch` has stretched snaps back to IK a millimetre or
  two out, because Blender's stretching IK shares the stretch between the segments differently.

## The flag a caller branches on is called `performed`

Every mutating tool reports `performed`, a real boolean, **true exactly when the operation was
carried out**. It is false in every refusal (`ready: false`), false when the subject could not be
resolved (`found: false`), and false when the tool completed successfully without doing anything it
was asked to do.

Most tools kept their own verbs beside it — `added`, `applied`, `removed`, `generated`, `changed`,
`recalculated`, `refit_performed`, `saved`, `created` — because `added: true` beside
`asset_object_name` reads better than `performed: true` does, and each response is written around
its own verb. **A key that is one tool's verb is never a list, or a number, in another**
([FR 037](../feature-requests/done/037-one-word-per-concept/README.md)'s R3): the four batch tools
(`mpfb_set_macro_details`, `mpfb_set_targets`, `mpfb_symmetrize_targets`,
`mpfb_set_face_units`) report their per-entry writes as `changes`, with `change_count` where they
count them, and have no verb beside `performed` at all. Their list used to be called `applied` in
two of them and `changed` in the other two, which is what `mpfb_set_skin`'s `applied` and
`mpfb_apply_expressions`' `changed` mean as booleans. What the set of
verbs cost is a caller working across more than one tool: reaching for the wrong name yields `None`
rather than an error, so the mistake is silent. [FR 013](../feature-requests/done/013-live-verification/README.md)'s
harness, written with the source open, guessed wrong on three tools in one session, and each wrong
guess turned a passing check into what looked like a tool defect. The refusal fields `found`,
`ready` and `blocked_by` already meant the same thing everywhere and were never mis-read, which is
what says the problem was the *variation* rather than the naming.

- **The flag is not always the verb**, which is what makes it worth having rather than a rename
  away. `mpfb_symmetrize_targets` under `dry_run: true` returns a populated `changes` and has
  written nothing. `mpfb_set_macro_details` called with no slider named returns `ready: true`
  having recalculated nothing, per *do only what was asked* above. `mpfb_set_targets` fails a whole
  batch on one bad entry and returns `ready: true` with an empty `changes`.
- **Where a verb already means exactly this, the flag is derived from it, not written beside it.**
  `mpfb_refit_human`'s `refit_performed` is that field, and setting `performed` from it is what
  keeps the two from disagreeing about the one case they could: a generated Rigify rig with no meta
  rig, which refits the mesh assets and leaves the rig.
- **It is stamped once, at the bottom of the command, rather than written into each branch.**
  `mpfb_set_asset_material` builds eleven refusals and one success; a key written twelve times is
  twelve chances to write it wrong, and the refusals are the branches nobody re-reads. The two
  universal falsehoods — a refusal and an unresolved subject are never performed — live in
  `bridge/mpfb_bridge/shared/performed.py` with the stamping, so no call site has to remember
  them.
- **Nothing was renamed to get it.** A response-shape change across eleven tools at once must not be
  able to break a caller; every existing verb still means what it meant.

## Preconditions are answers

Related to, but distinct from, [FR 001](../feature-requests/done/001-mpfb-get-status/README.md)'s
"absence is an answer": there the request named something that is not there, while here the request
is well-formed and the **world** is not ready. Check in the command and return a sentence naming the
problem, rather than letting MPFB's own guard surface as a traceback in an error envelope.

- **OBJECT mode.** `TargetService.create_shape_key()` opens with a bare `assert
  blender_object.mode == "OBJECT"`, reached whenever a macro target has to be loaded. An
  `AssertionError` with no message is the worst possible form of a very ordinary situation: the
  user left the mesh in edit mode.
- **Presence of shape keys.** `reapply_macro_details()` on a mesh with none logs "somewhat
  surprising" and carries on, producing a partial result. It is what an imported mesh tagged as a
  basemesh looks like, and it should be reported as that rather than half-done.
- **Reachability of what the command needs**, such as a property set read off a service's module
  (see [Reading module-level names MPFB does not publish](architecture.md#reading-module-level-names-mpfb-does-not-publish)).
- **A vocabulary MPFB validates *after* it destroys something.** This is the sharpest case, and it
  is the one exception to
  [validate the shape, never the vocabulary](tool-interface.md#validate-before-crossing-the-socket).
  `HumanService.set_character_skin()` opens with
  `MaterialService.delete_all_materials(..., also_destroy_groups=True)` on the basemesh and the body
  proxy, and only then tests its five skin types — with five separate `if` statements rather than a
  chain with an `else`. An unrecognised value therefore deletes the character's materials, builds
  nothing, and surfaces as a `ValueError` raised from `create_and_assign_material_slots()` about a
  mesh with no materials: a traceback from a function that never saw the bad argument, after damage
  that cannot be undone across the socket. Where a vocabulary is checked late and the check is
  preceded by destruction, check it in the command first — and, where the vocabulary is small,
  closed and MPFB's own enum rather than a scan of the user's disk, check it in the tool module too,
  so a typo never crosses the socket at all. Report `known_*` alongside either way: the local check
  is belt and braces, and the authoritative answer still comes from Blender.

- **A combination MPFB fails on part way.** `ExportService.bake_modifiers_remove_helpers()` bakes
  the basemesh's modifiers in a way that keeps its shape keys and the body proxy's with a bare
  `modifier_apply`, which Blender refuses on a mesh with shape keys - and the Export copy sequence
  interpolates visemes onto the proxy first. MPFB's own panel then fails half way through the copy.
  `mpfb_create_export_copy` predicts it from the options and the proxy's modifiers and refuses
  before copying (`proxy_cannot_be_baked`, naming the modifiers), because the alternative is a
  half-processed copy left in the scene ([FR 039](../feature-requests/done/039-exporting-characters/README.md)).
  A precondition can be a property of the *request* as much as of the world.

Report which precondition blocked (`ready: false` plus a `blocked_by` naming it) rather than only a
sentence, so a caller can branch on it; and make sure the tool changed nothing on the way to
finding out.

## A tool reports an ordering constraint it cannot enforce

MPFB's services have **implicit sequencing**, and violating it produces no error anywhere. The rig
has to be added before the mesh assets, because `HumanService.add_mhclo_asset()` rigs a garment only
if a `Skeleton` relative exists at the moment the garment is attached and nothing re-rigs it
afterwards — `HumanService.refit()` deliberately passes `set_parent=False`. Rigify generation has to
come after the mesh assets, because `RigifyHelpers.adjust_children_for_rigify()` handles exactly
what is on the character when it runs. MPFB's own character builder documents both in comments, and
its randomizer follows them; nothing enforces them. An agent that dresses a character and then rigs
it gets garments that do not follow the armature, and finds out when someone moves a bone.

No single call can validate a sequence. But a tool can often *observe* that the caller is about to
break one, and where it can, **it reports the observation in its response, naming the objects
affected** — rather than either failing or staying silent.

- **Report, do not refuse.** Rigging an already-dressed character is a legitimate thing to do when
  the clothes are decorative. `mpfb_add_rig` adds the rig and returns `mesh_assets_not_rigged`
  listing what it has just failed to rig; it does not second-guess the caller.
- **Name the objects, not the rule.** "Some assets may not be rigged" is advice; `["Shirt",
  "Shoes"]` is something an agent can act on. This is the sequencing counterpart of
  [an empty answer must never be ambiguous](responses.md#how-tools-report-the-asset-behind-an-object).
- **Observe before acting, so the claim is precise.** The assets are enumerated *before* the rig is
  added. Afterwards they are still reachable, but the answer would then be "assets on this
  character" rather than "assets that were attached while there was no rig".
- **A half-finished sequence must look half-finished.** `mpfb_add_rig` on a `rigify.*` identifier
  produces only a meta rig, so it returns `is_metarig: true` and a `next_step` naming
  `mpfb_generate_rigify_rig` and saying that assets come first. "The rig was added" must not read as
  "the character is rigged".
- **Where a step forecloses a later one, say so at the point of decision.**
  `mpfb_generate_rigify_rig`'s `meta_rig_action: "delete"` leaves a character that can never be
  refitted again, which `mpfb_refit_human` can only report after the fact. `refit_will_be_possible`
  is that same fact, knowable in advance.
- **Dress before placing, and say so where it was not done.** A garment's sub-rig equipped on a
  character that stands away from the origin is bound wrong by MPFB and drags its vertices away -
  5.7 m for `ponytail01` in [FR 045](../feature-requests/done/045-placing-a-character/README.md)'s
  live check - and stays wrong wherever the character goes next; one equipped at the origin
  survives every move. `mpfb_add_asset` reports it the moment it happens and
  `mpfb_place_character` and the summary go on reporting it (`subrigs_broken`, measured), each
  naming `mpfb_refit_human`, which re-binds it. Neither refuses: the asset is equipped, and the
  repair is one call.
- **Splitting a tool can be what makes the order expressible.** Rigify generation is a tool of its
  own rather than a flag on `mpfb_add_rig` precisely because the correct order — meta rig, then
  garments, then generate — cannot be written as a single call.

## A tool whose effect is outside the `.blend` owes more

Everything else here changes a `.blend` that the user can undo, revert or simply not save.
`mpfb_save_preset` writes a **file**, and FR 025 is where that difference was first paid for;
`mpfb_save_expression` ([FR 027](../feature-requests/done/027-expression-library/README.md)) is the
second, writing `<name>.json` into the expressions directory of MPFB's user data; and
`mpfb_export_character` ([FR 039](../feature-requests/done/039-exporting-characters/README.md)) is
the third, writing `<export_name>.fbx`, `.glb` or `.usdz` - the first file meant for another
application. Four properties follow, and they are the whole of the extra obligation:

- **Address the artifact by name, never by a path.** A preset is `<name>` within MPFB's user config
  directory, resolving to `human.<name>.json`. A tool that took a caller-supplied path would write
  anywhere the Blender process can; addressing by name confines writing to a directory MPFB owns,
  keeps one namespace rather than two lists that disagree with MPFB's own panels, and makes
  unreachable a third failure that would otherwise be found the hard way —
  `deserialize_from_json_file()` extracts the name with a regex whose match it never checks, so any
  path not of exactly that shape raises `AttributeError: 'NoneType' object has no attribute
  'group'` from inside MPFB, with nothing in the message about what the caller did wrong. Confirmed
  against a running install, not read off the source.

  **The directory may be one the human chose, never one the caller chose.** An export has no
  directory MPFB owns, and a fixed one would leave the user moving files by hand. So the person who
  started the bridge sets it - the add-on's `export_directory` preference, or `--export-dir`
  headless - and otherwise it is `<MPFB user data>/exports`. It is the add-on's setting rather than
  an environment variable on mpfb-mcp's side, because that would be the MCP client's configuration,
  which an agent may be able to edit; and there is no directory argument, so nothing that writes a
  call chooses where a file lands. `path_resolved_by` (`"command_line"`, `"preferences"`,
  `"default"`) says who did, in every answer. **A directory somebody named that does not exist is a
  refusal** (`export_directory_missing`), not created on their behalf: a typo in a preference must
  not become a directory tree. The default is created, as MPFB creates its own.
- **The name is a shape, so it is validated on this side of the socket, and more strictly than MPFB
  does.** This is the filesystem case of
  [validate before crossing the socket](tool-interface.md#validate-before-crossing-the-socket), and
  it is not the vocabulary exception: which characters may appear in a filename is knowable here
  and cannot drift from anything on the user's disk. Strictness runs one way — every name accepted
  must be one MPFB's own panel would also accept, so the two never disagree about what exists.
  Where the rule has to exist on both sides of the socket (the tool module refuses before anything
  is sent; the command is the last statement before `open()`), a test runs the two
  implementations over one table of names, because two copies that disagree would let an artifact
  be written under a name that cannot be read back.
- **Refuse to overwrite by default, and always name the absolute artifact.** There is no undo, no
  confirmation channel across MCP, and the caller cannot see the directory. So an existing file is
  a refusal carrying that file's size and modification time — enough to decide from, without a
  second call — and `path` is in **every** answer, refusals included, because "which file was this
  about" is the first thing a caller needs whatever happened.
- **Refuse to write where the result cannot be found.** FR 027 added this, and it is the one that
  the preset case never needed: a preset has one directory, while an expression lives in a library
  MPFB assembles from several data roots, **first root first**. A file saved into user data while a
  higher-priority root holds one of the same name would be written and then never listed, never
  applied and never restored from a preset - nothing fails, and the file is simply unreachable. So
  `mpfb_save_expression` refuses (`blocked_by: "name_shadowed"`), naming the file that would win.
  This rests on MPFB's *code*, which FR 027's live check confirmed, and not on MPFB's composer panel
  and data README, which both say user files take priority; the discrepancy is filed as item 8 of
  `mpfb2/features/MCP_DISCOVERED_BUGS.md`. If MPFB changes its precedence, this refusal changes
  with it.

The general obligation those four serve is that **a refusal must never be a partial write**: every
precondition is settled before the writing call is made. MPFB's own path happens to be safe here
(`serialize_to_json_string()` runs to completion before the file is opened), but that is an
inherited property rather than a guarantee, so the ordering is the command's own.

The counterpart on the reading side is that a tool addressing an artifact by name must be able to
say **which names exist**: a misspelling is the likeliest way such a tool is called wrongly, so the
refusal names them, per
[how tools name things that can be added](tool-interface.md#how-tools-name-things-that-can-be-added).

## A batched mutating tool resolves before it writes

Where a tool changes many things at once, **every entry is resolved and validated before anything
is written, and if any entry fails, none of them are applied.**

- **A half-applied batch is a state nothing can describe.** Thirty changes with one typo in them
  must apply zero, not twenty-nine: the character is then in a condition neither the agent nor the
  user can name, and the response format cannot usefully say which half landed or which half to
  retry. Failing the whole batch leaves the caller with one action — fix the entry and resend.
- **Resolve the expensive, failure-prone part up front.** For `mpfb_set_targets` that means
  locating the file each change *might* have to load, during resolution, so a missing target is a
  `resolution_errors` entry rather than an `IOError` raised half way through the writes.
- **Report per entry once application starts**, in request order, including what changed as a
  consequence — one sided change with `symmetry` on touches up to four shape keys, and the response
  has to be able to say so.
- **A refusal names the write that would work, when there is one.** `mpfb_set_material_settings`
  ([FR 040](../feature-requests/done/040-procedural-material-settings/README.md)), the third batched
  tool, refuses an entry naming a **linked** socket, since writing one changes nothing. On MPFB's
  layered skin almost every region colour is linked from the `color` group, so the refusal carries
  `write_instead` - the group and socket that drive it - and the caller's one action is to resend
  with that. Where the driver is not something a caller can set, such as a texture, it is `null`.
- **A refusal may name an entry for another tool.** `mpfb_set_pose_bones` refuses an FK bone while
  `IK_FK` hands the limb to IK - writing it would change nothing visible - and its `write_instead`
  is `{"tool": "mpfb_set_pose_switches", "switches": [...]}`, the call that puts the bone in
  charge. A `write_instead` without `tool` names an entry for the same tool, as before.
- **The second form: snapshot, write, check, restore.** Some checks can only be made after
  writing: whether a pose bone's `move_to` touches a locked channel depends on where its parents
  ended up, and `pose_bone.matrix`, the only setter that takes "where the bone should be", ignores
  locks. So `mpfb_set_pose_bones` copies every channel of every bone it will touch, writes, checks,
  and **on any failure puts the copy back exactly** and answers as if resolution had failed. That
  form is allowed **only where what is written can be put back exactly**: pose basis data is plain
  numbers and can be, a rebuilt mesh or a loaded target cannot, and the first form stays the rule
  for those ([FR 042](../feature-requests/done/042-posing-bones-switches-and-reset/README.md)).
- **A range is enforced where it protects something, and not where MPFB contradicts it.** A
  built-in node's factor is clamped by Blender without a word, so a value outside it is refused
  rather than stored as something else. A group node's input range is only an interface hint -
  Blender stores whatever is assigned - and is enforced anyway, as what MPFB's own UI would let a
  user set, **except** on a socket whose current value already lies outside it: MPFB's `MpfbBody`
  declares `NavelWidthMultiplier` as 0.001-0.2 and defaults it to 11.0, and a range MPFB does not
  keep is not one this package holds a caller to. Measured against the installed MPFB, not read.
- **Batch because per-call cost dominates, not on principle**, and the number that argument rests
  on has moved twice. It was originally made against a ~1.0 s round trip, then against the ~250 ms
  [FR 013](../feature-requests/done/013-live-verification/README.md) measured; on the bridge the
  same tool's call is **58 ms** where it was 461 ms
  ([FR 030](../feature-requests/done/030-backend-seam/README.md)), so transport alone would make
  thirty calls under two seconds. **The decision survives the number getting an order of magnitude
  smaller**, because transport was never the larger half: thirty modifier changes were measured at
  3.6 s in one call and 98.4 s in thirty, and most of that 95 s is per-call setup the far side
  redoes each time rather than bytes on a wire. Read it as a settled interface decision that no
  longer needs a number to defend: a whole series of modeling changes is one request, and an entry
  that fails costs the caller one resend. Where the work inside a call is itself expensive —
  loading an MHCLO asset is seconds of mesh import and vertex fitting — the argument does not carry
  over, and one-per-call is the better shape.

## A tool whose effect is known in advance to be transient

Most of what a mutating tool changes lives in the `.blend` until something explicitly saves or
discards it — the same durability a user's own edits have. `mpfb_set_face_units` is the first tool
whose effect is narrower than that on its own terms, independent of anything the caller does: a
composed face survives neither `mpfb_save_preset` (which serializes MPFB's applied-expressions
*stack*, and a composed face has no stack rows) nor anything that rebuilds the face from that stack
— `mpfb_apply_expressions`, `mpfb_create_human_from_preset` — which clears every face unit first.
See [FR 026](../feature-requests/done/026-face-units/README.md#a-composed-face-is-transient) for
why, which is a fact about MPFB's two-level expression model rather than a limitation of the tool.

**Say the fact once, in the tool description, and compute the current state into the response.**
FR 026 put a fixed "this will not survive" sentence in every answer as well as the description,
because nothing could yet say whether it was true of *this* face. [FR 027](../feature-requests/done/027-expression-library/README.md)
replaced it with the computation: `matches_stack` and `unexplained_face_units`, from
[`shared/expression_divergence.py`](../bridge/mpfb_bridge/shared/expression_divergence.py), say
whether the stack explains the face and which units it does not. The difference is the one
[responses.md](responses.md) draws between a warning and a fact: a sentence true on every answer
teaches an agent to ignore it, while `matches_stack: true` on a character with nothing composed is
an answer, and `false` names exactly what is at risk and names `mpfb_save_expression` as what keeps
it. The description keeps the one-paragraph explanation, because it is what an agent reads *before*
calling.

## A tool that destroys state it did not create owes the caller a list

`mpfb_apply_expressions` is the other half of that model, and the first tool here whose own effect
**destroys work another tool made**, silently in MPFB and unrecoverably across the socket: the
library's rebuild clears every face unit before writing the stack's aggregate, so any unit composed
on top with `mpfb_set_face_units` is gone. MPFB's UI survives this because the two panels are in
different tabs and a human sees sliders move. Across MCP there is no such feedback.

- **Name what went, measured on both sides of the write.** The units the stack did not explain are
  read *before* the call, and those the rebuild then actually moved are returned as
  `discarded_face_units`, each with its value before and now. Measuring only the first half
  predicts a loss that may not happen: FR 027's own round-trip test found that the save-then-replace
  sequence — which keeps everything, because the saved file holds the composed units — would
  otherwise be reported as having discarded all of them.
- **Name what would have kept it.** The answer says `mpfb_save_expression`, which is the only way
  a composed face crosses into the library.
- **Do not refuse, unless the destruction is never what a caller means.** Here it usually is what
  a caller means: an agent that composes a face and then applies a library expression has, on the
  most natural reading, changed its mind. A refusal would need an override argument on every call to
  protect the minority case, which is a description cost paid by everyone; a list returned after the
  fact costs nothing when it is empty. FR 027's live check confirmed the loss is real before this
  was settled.
- **Stay quiet when nothing is lost.** An empty `discarded_face_units` and no sentence about it,
  per the rule above: a tool that warns on every call trains an agent to ignore it.
- **Where nothing else records the change, the answer is the undo.** Blender's undo stack does not
  see a bridge command's writes, and MPFB keeps no record of a pose, nor of where a character
  stood. `mpfb_place_character` answers with the call that puts the character back - `position` and
  `facing`, kept to six and four decimals so that every object in the family returns to within
  1e-5, and `position` alone for a tilted root, since a turn would be refused on it
  ([FR 045](../feature-requests/done/045-placing-a-character/README.md)). And `mpfb_reset_pose` answers
  with `restore_with`: the arguments for `mpfb_set_pose_switches` and `mpfb_set_pose_bones`, keyed
  by tool name, that put back exactly what it reset - as `mpfb_save_expression`'s `apply_with` is
  the call that makes a face durable. It is **never capped**, because a capped undo restores
  nothing (its worst case, every control of a generated `human_toes` rig posed, measured 45 KB);
  it is **exact**, read before each bone's own constraints and kept to more digits than a read-back,
  so a live round trip put every channel back to within 1e-6; and **a reset bone the writer would
  refuse is named rather than included** (`not_restorable`), because one refused entry fails the
  writer's whole batch. Each such bone had no visible effect when it was reset - a chain `IK_FK`
  had handed away, an FK bone a helper drives - so the visible pose still comes back whole
  ([FR 042](../feature-requests/done/042-posing-bones-switches-and-reset/README.md)).
- **A write that resets controls the caller did not name owes them in `restore_with` too.**
  `mpfb_set_rigify_hand_shape` puts a written finger's segment controls at rest, because a rotation
  left on one would add to the curl and make the answer's `curl` untrue; a caller who asked for a
  fist did not ask for that, and may have posed those segments by hand. So the answer lists them
  (`segments_reset`, each with its transform before), and `restore_with` holds two calls, sent in
  the order the keys are in: its own entries for each changed finger's `curl` and `spread`, then
  `mpfb_set_pose_bones` entries for the segments and for any master whose channels were not a curl
  and a spread at all (a hook, a twist), which an amount cannot express. Amounts keep seven
  decimals, so a live round trip put every channel back within 1e-5, the bound single-precision
  Euler channels allow ([FR 047](../feature-requests/done/047-rigify-hand-shapes/README.md)).
