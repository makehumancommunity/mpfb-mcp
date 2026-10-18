# MPFB integration

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

**What to do when MPFB is inconsistent, undocumented, or wrong.** mpfb-mcp wraps a large addon
that was not written to be wrapped, and the recurring problem is not that MPFB is hard to call —
it is that there is often more than one answer to "what does MPFB do here", and the differences
are invisible from the response unless a tool says so.

The standing bar throughout is the one [FR 007](../feature-requests/done/007-macro-details/README.md)
set: **a character mpfb-mcp produces must be reproducible through MPFB's own UI**, and where it
cannot be, the tool says which path it took and why.

How a command *reaches* MPFB at all — the `sys.modules` scan, and the rule against importing its
submodules — is [architecture.md](architecture.md#resolving-mpfb).

## Where MPFB's UI coerces or re-defaults a service argument, mpfb-mcp does the same and reports both

A service signature's default is not always the product's default, and a service's argument is not
always the one the product would have passed. `HumanService.set_character_skin()` defaults
`skin_type` to `ENHANCED_SSS`, while the settings panel every user actually sees defaults it to
`MAKESKIN`; and it accepts `material_instances=True` for a `MAKESKIN` skin, while
`loadlibraryskin.py` forces that flag to `False` for `MAKESKIN`, `LAYERED` and `GAMEENGINE` alike —
a coercion the service's own guard makes for only two of the three.

A third instance says the pattern is not peculiar to skins. `get_default_deserialization_settings()`
gives `material_instances` as `NEVER`, while `ui/new_human/newhuman/properties/material_instances.json`
— the panel behind MPFB's "create human from save file" button — defaults it to `ENHANCED`. So
`mpfb_create_human_from_preset` takes `ENHANCED` as the meaning of an omitted
`material_instances_policy`, and reports `material_instances_policy_used` beside
`material_instances_policy_service_default`. Both figures were read off
the running install rather than the source.

A fourth is not about a character at all. `FaceService.save_expression()` writes an empty `license`
when none is given, while the composer panel behind MPFB's own "save expression" button pre-fills
`CC0` ([`properties/license.json`](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/ui/create_assets/makeexpression/properties/license.json)).
`mpfb_save_expression` defaults `license` to `CC0` and reports the metadata it wrote, read back from
the file. [FR 027](../feature-requests/done/027-expression-library/README.md) asked whether a licence
- a statement made on the user's behalf - was a default an agent should apply silently, and kept it:
the tool description names the default, so an agent applying it has read it, and a user saving
through MPFB's own panel gets the same value unless they change it.

**Where a tool departs from the panel's default, it says why, and the reason has to be true.**
`mpfb_set_face_units` defaults `refit` to `true`. FR 026 wrote that this matched the composer
panel's `auto_refit`; it does not - the composer's defaults to `false`, and it is the *library*
panel's (`ExpressionsLibraryProperties`) that defaults to `true`. FR 027 found the error, kept the
default on its merits - a human drags a composer slider through dozens of values and each would
refit, while composing across MCP is one batched call, and garments do not follow the face without
a refit - and corrected every place that gave the wrong reason. `mpfb_apply_expressions` follows
the library panel's `true` directly. A default whose stated reason is wrong is harder to revisit
than one that never gave a reason, which is why the correction was worth an effort's time.

Passing the signature's value in either case would produce a character that **cannot be reproduced
through MPFB's own UI**, which is the same quality bar
[FR 007](../feature-requests/done/007-macro-details/README.md) sets for macro details: the goal is
that the value reads back on MPFB's own slider.

- **Follow the UI, not the signature.** The panel is what the user saw and what a character loaded
  from a `.mhm` was made with. A signature default is an implementation detail of one function.
- **Say so in the docstring, naming both values.** "Defaults to `MAKESKIN`, which is MPFB's settings
  panel's default rather than the function's `ENHANCED_SSS`" is checkable; a bare default is not.
- **Report `*_requested` beside `*_used`, with a sentence when they differ.** A silent coercion is
  indistinguishable from a bug: a caller who asks for material instances, gets none, and is told
  nothing will conclude the tool is broken. `mpfb_set_skin` returns
  `material_instances_requested` and `material_instances_used` on every call, not only when they
  disagree — for the same reason
  [A mutating tool reports before and after](mutating-tools.md#a-mutating-tool-reports-before-and-after) reports a
  field the caller named even when it was already so.
- **The coercion belongs on the far side of the socket, not in the stub.** The test has to be
  testing mpfb-mcp. A stub service that coerced would let the code under test do nothing and still
  pass. Each of these rules was checked across the move to the add-on rather than assumed to
  survive it, by [FR 032](../feature-requests/done/032-creation-and-modification-migrated/README.md),
  which had both implementations running side by side to compare. All three held:
  `mpfb_set_skin`'s three-type coercion, `mpfb_create_human_from_preset`'s panel default of
  `ENHANCED` over the service's `NEVER`, and `mpfb_add_asset`'s per-type material default. The
  check is that effort's own
  [live comparison](../feature-requests/done/032-creation-and-modification-migrated/check_creation_migration.py),
  which compares the two answers field by field — so `material_instances_used` (as it was spelled
  then) disagreeing between
  the transports would have been a failure rather than something to notice later.
- **This is not the same as picking between code paths.**
  [Where MPFB's own code paths disagree](#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it)
  is about two implementations of an operation; this is about one implementation whose *arguments*
  the UI fills in differently from its signature. The remedy is different too: there, name the path
  you took; here, apply the coercion and report both values.

## Where MPFB's spelling disagrees with the glossary, the glossary wins

The tools spell one concept one way across the whole surface
([the glossary](tool-interface.md#the-glossary)), and where MPFB names that concept differently the
tool uses the glossary's word. **MPFB is not consistent with itself**, so mirroring it would import
its inconsistencies: it calls a boolean `material_instances` in `set_character_skin()` and a
three-value policy `material_instances` in its deserialization settings, and calls the material
model `material_type` in one function and `skin_type` or `*_model` in others. A caller that learned
`material_instances` from `mpfb_set_skin` and passed `true` to the preset tool would be refused only
if the second tool happened to validate the type.

So `mpfb_create_human_from_preset` takes `material_instances_policy` and `override_skin_type` /
`override_clothes_material_type` / `override_eyes_material_type`, and `mpfb_add_asset` takes
`object_type` where `add_mhclo_asset()` says `asset_type`. The tool's description names MPFB's
spelling once, where a reader comparing the tool with MPFB's source would otherwise lose their
bearings, and the command maps one to the other in a single visible table rather than at each use.

Two things keep MPFB's spelling on purpose, because they *are* MPFB's rather than the tool's: a dict
MPFB itself reads or wrote, reported as it is (`mpfb_create_human_from_preset`'s `settings_used`,
`mpfb_save_preset`'s `contents`), and MPFB's own vocabularies, such as its object types and skin
types. Renaming either would make a value impossible to look up in MPFB.
[FR 037](../feature-requests/done/037-one-word-per-concept/README.md) established this.

## Where MPFB's own code paths disagree, mpfb-mcp picks one and names it

Sometimes there is no single MPFB implementation to wrap. Adding a body proxy has three:
`HumanService.add_mhclo_asset()` imports and fits it and stops there;
`HumanService._check_add_proxy()` calls that and then hides the basemesh, copies the scale factor,
creates the proxy's extra vertex groups and runs a corrective pass; and the asset library's proxy
operator does not call `add_mhclo_asset()` at all and carries a third implementation gated on its
own scene settings. Nothing documents which is canonical.

**Measured** (FR 013's live run), the picture is sharper than "the three disagree", and the
sharper version is the better argument. `add_mhclo_asset()` alone and `_check_add_proxy()` really
do produce visibly different characters: no `Hide base mesh` modifier, 124 vertex groups against
130, and `scale_factor` left at `1.0` rather than copied from the character's `0.1`. But
`_check_add_proxy()` and the library operator produced **identical** state on every field compared.
So the operator is a duplicated implementation rather than a divergent one — and what makes the
choice load-bearing is not that three paths disagree but that the *obvious* implementation, the
service function whose name matches the operation, is the one that differs. A rule that only fired
when three implementations visibly disagreed would not have fired here, and would have been wrong
not to.

**The sharpest instance is two paths that write the same thing, one destroying the other's work.**
MPFB's expression composer writes the 52 `!ex-` shape keys directly (`FaceService.set_expression`,
wrapped by `mpfb_set_face_units`); its expression library keeps a stack of `{asset, weight}` rows on
the basemesh and re-derives the face from it on every change, clearing first
(`mpfb_apply_expressions`, and every preset load). Neither is wrong, and a user in MPFB's UI copes
because the panels are in different tabs and sliders visibly move. Across MCP nothing moves. So
mpfb-mcp does not pick one here - it exposes both - and instead **computes the comparison MPFB never
makes**: whether the stack explains the face
([`shared/expression_divergence.py`](../bridge/mpfb_bridge/shared/expression_divergence.py)),
reported by every tool on either side, with the one bridge between them - saving a composed face as
an expression file - named whenever there is something to lose. See
[a tool that destroys state it did not create](mutating-tools.md#a-tool-that-destroys-state-it-did-not-create-owes-the-caller-a-list).

The same pair produced a smaller instance of the rule below. MPFB's composer save operator builds
the file from the composer panel's scene properties (`MPFB_EX_<unit>`), which the composer's own
UI keeps in step with the face but `set_expression()` does not touch. `mpfb_save_expression` saves
the **shape keys** (`read_current_expression()`), because the panel's sliders are stale for a face
composed across MCP, and its command docstring says so.

This is the sharper, more general form of
[When mpfb-mcp models a concept MPFB's UI has but its services do not](#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not),
whose last clause — document the divergence rather than normalizing it away — extends here from "UI
versus services" to *any* two MPFB code paths.

- **Follow the service-layer path.** It is what `deserialize_from_mhm()` uses, so it is what a
  caller comparing against a loaded `.mhm` will expect, and it is what other services are written
  against. A UI operator's variant is the behavior of one panel, not of MPFB.
- **Say which one in the docstring, and name the one you did not take.** "This matches `.mhm`
  loading rather than the proxy library panel" is something a caller can check; silence is not.
- **Report the parts that differ, individually.** `proxy_extras` names each of the four things
  `_check_add_proxy()` does beyond the plain add, so a caller who sees a difference against MPFB's
  panel can see exactly where it comes from.
- **Record the divergence as a candidate mpfb2 issue — and then confirm it before filing.** Three
  implementations of one operation is a problem in MPFB that mpfb-mcp is working around, not a fact
  about mpfb-mcp. But a candidate defect read from source is a hypothesis: of the seven FR 008
  through FR 011 recorded, the live run confirmed four, refuted two outright
  (`RigService.identify_rig()` cannot return `None`; the alternative-material cache *does* have an
  invalidator) and found the fifth to be worse and quieter than described. Each is provoked by
  [`check_mpfb_issues.py`](../feature-requests/done/019-file-mpfb-defects/check_mpfb_issues.py),
  which lives beside the report it backs, so a claim about MPFB is re-checkable against a future
  MPFB rather than frozen as an opinion. It is deliberately not in `verification/`: it provokes
  defects in MPFB rather than checking mpfb-mcp's tools, and it writes into MPFB's user data
  directory. FR 025's [`check_presets.py`](../feature-requests/done/025-character-presets/check_presets.py)
  is the second of these and confirmed the `save_clothes` defect the same way — by serializing one
  dressed character twice, with the argument as the only difference, rather than by reading the
  function. FR 039 refuted one read from source: the Export copy operator removes modifiers from the
  collection it is iterating, which looks like it skips each removed modifier's neighbour, and on
  Blender 5.1 does not. The smoke run writes outside the `.blend` too now, but exactly one file, always the
  same one, and [verification/README.md](../verification/README.md) names it.
- **Filing it changes nothing here.** A confirmed defect is written up in a defect list kept for
  MPFB's maintainers, `MCP_DISCOVERED_BUGS.md`, one section each; it lives beside a local mpfb2
  checkout and is not published. That is where the reporting ends: MPFB has its own priorities, so a reported
  defect may stand for a long time. The workaround, the coercion or the defensive check that copes
  with it stays exactly as it is, and it is removed when a **running** MPFB no longer needs it —
  which is what the script detects, since it is written to fail once a defect is gone.
- **Two readings of one material follow the serializer, and report the other one.**
  `MaterialService.identify_material()` recognizes procedural eyes by an `IrisSection4Color` input
  and a layered skin by `NavelCenterOverride`; `HumanService`'s serializer recognizes procedural
  eyes by `IrisMinorColor` and a layered skin by its group node names. They agree on every material
  MPFB builds today. `mpfb_get_material_settings` decides what counts as a setting by the
  **serializer's** test, since the promise is that its answer is what a preset holds, and reports
  `identify_material()`'s verdict beside it as `material_identified_as`, the discriminator the other
  tools already report ([FR 040](../feature-requests/done/040-procedural-material-settings/README.md)).
- **The serializer's exclusions are followed, not extended.** It records no colour adjustment for
  the eyes even when they carry a MakeSkin material, none for a MakeSkin body (the body is in
  neither of its lists), only **one** object of each body-part type, and on an asset whose MHMAT
  names an AO map it records the `aoMix` node - the AO strength - rather than the diffuse tint
  behind it (MCP_DISCOVERED_BUGS item 12). `mpfb_get_material_settings` lists every mesh asset
  anyway, each one the serializer skips with the `reason` it does, so an agent can see why a tint
  will not survive a preset rather than finding the asset missing. A tidier rule would make the
  read disagree with the file it describes.
- **`identify_material()` calls an untextured MakeSkin material `gameengine`.** MakeSkin creates
  its `diffuseIntensity` node only for a diffuse texture, and that node is how MakeSkin is
  recognized, so a MakeSkin material whose MHMAT names none is identified by its Principled BSDF
  instead. Observed in FR 040's bridge tests. Every real MHMAT names a texture, which is why it is
  recorded here as a trap for fixtures rather than filed; `material_identified_as` reports MPFB's
  verdict as it is.
- **Do not merge them.** Picking one and naming it is the rule; synthesizing a fourth behavior that
  matches none of MPFB's own would make the result unreproducible from inside Blender.
- **Not reproducing something MPFB's UI does is the same decision and carries the same burden**, so
  it is justified in the module docstring rather than merely noted. Two of them are in the preset
  tools. MPFB's two saving operators emit a `WARNING` whenever `identify_rig()` contains
  `"generated"`; `mpfb_save_preset` does not, because the warning overstates what happens —
  `_populate_human_info_with_rig_info()` is built for the case, infers the meta rig, falls back to
  `rigify.human_toes`, and records that. Nothing fails. What is true is that a generated rig does
  not round-trip, which the *description* says once and the response shows on the call where it
  happened, as `rig_identified_as` beside `rig_saved_as`. A warning emitted on every save of a
  Rigify character is noise an agent learns to ignore. And `mpfb.human_from_presets` ends by
  entering **edit mode** twice to preselect a vertex group, setting an active material index from
  it, and optionally running Rigify generation; `mpfb_create_human_from_preset` reproduces none of
  the three. Entering edit mode across the socket is a hazard rather than a nicety — every later
  `bpy.ops` call polls on the context mode, and a program that fails between the two `mode_set`
  calls leaves Blender in edit mode — and Rigify generation is a tool of its own precisely because
  it cannot be undone.
- **The inverse also happens: MPFB's message can be wrong, and then it must not reach the agent.**
  `_populate_human_info_with_rig_info()` raises `ValueError("Could not identify rig type. Custom
  rigs cannot be serialized.")`, which is false — a custom rig still present in user data
  serializes as `custom.<name>`. `mpfb_save_preset` checks the condition itself, before anything is
  written, and refuses with the real cause: the armature is not one MPFB recognises, which for a
  custom rig means its definition is no longer in user data. Passing MPFB's text through would send
  a caller looking for a limitation that does not exist.
- **The limiting case is no service path at all.** Setting an alternative material on an equipped
  asset exists only in `ui/apply_assets/assetlibrary/operators/loadlibrarymaterial.py`, as two
  module-level helpers. There is nothing to prefer, so the panel's behavior *is* the specification,
  and it is reimplemented from services rather than imported — quirks included, because every quirk
  is a way the result would otherwise differ from what the user gets from the panel. Three of them
  are reproduced deliberately in `mpfb_set_asset_material`: the replacement is always a MakeSkin
  material under the fixed name `makeskinmaterial`, whatever the asset had before; the slots are
  *popped* rather than deleted, so the previous material's node groups survive (unlike the skin
  path, which destroys them); and the viewport colour is keyed on the object's recorded
  `object_type`, so an asset mislabelled at equip time gets the wrong colour here too. Reproduce
  them, and say in the command's docstring that they are reproductions rather than choices.
- **What is "posed" is MPFB's test, plus scale.** `RigService.get_pose_as_dict()` decides whether a
  bone is off rest with a 0.0001 threshold on each channel in the bone's own rotation mode, and
  records rotation and translation only. A Rigify fist is made by scaling the finger masters on Y,
  so following MPFB here would read a clenched hand as at rest, and saving that pose through MPFB
  loses the fist. `mpfb_get_pose` uses MPFB's threshold, so the two agree on everything MPFB can
  see, and adds scale; `shared/pose_reading.py` is where the choice is made, and its bridge test
  asserts that MPFB's dict misses a scale-only fist
  ([FR 041](../feature-requests/done/041-pose-controls-and-read-back/README.md)). A future
  pose-saving tool inherits the same gap and has to decide it again.

## Names inside MPFB's node trees are read live, never tabulated

A socket on one of MPFB's procedural node groups - `IrisMajorColor`, `SkinOverride`, the colour
adjustment's `Factor` - is MPFB's data in the same way a shape key name is, and it changes with
MPFB: the procedural eye tree is being reshaped by mpfb2's bug 306 work as this is written. So
**no socket, group or node name specific to these materials is written down on either side of the
socket**, beyond what MPFB's own code uses to *find* the node.
[FR 040](../feature-requests/done/040-procedural-material-settings/README.md) is the first case.

- **The vocabulary is in the read's answer.** `mpfb_get_material_settings` reports each node's
  settings keyed by the live socket names, and the write resolves every entry against the same live
  node. A socket MPFB renames shows up as a different key in the read and an `unknown_socket`
  refusal with `closest` in the write, never as a silent no-op. The tool descriptions name no
  socket; the unit tests pin none.
- **Which sockets count is MPFB's decision.** A node's settings are
  `NodeService.get_socket_default_values(node)`, the call the serializer makes, so the answer's keys
  are a preset's keys by construction.
- **What MPFB writes inline to find a node may be copied, and says so.** The nine layered-skin
  group keys and the six body-part types the serializer walks are local variables in
  `HumanService`, not names MPFB publishes, so
  [`shared/material_settings.py`](../bridge/mpfb_bridge/shared/material_settings.py) carries a copy
  of each, commented as one. A group MPFB adds shows up as `groups_not_serialized` until the copy is
  updated, and the bridge test comparing the read with the serializer fails.
- **The one exception is the summary**, which names three sockets - the two iris colours and the
  skin colour - because they are what that section is for. A renamed one is reported as `null`
  rather than dropped.
- **Ranges and links are read from the live node too**: a group input's range from its node group's
  interface item, a built-in node's from its RNA property's hard limits, and a link as the node and
  socket it comes from. A range can be contradicted by MPFB's own value (MCP_DISCOVERED_BUGS
  item 11), and the write does not enforce a range MPFB itself does not keep.

## A generated Rigify rig is read live, by Rigify's conventions

[FR 041](../feature-requests/done/041-pose-controls-and-read-back/README.md) is the first time this
package depends on **Rigify's** conventions and not only MPFB's. MPFB has no list of a generated
rig's controls: `RigifyHelpers.get_list_of_*_bones` names *meta-rig* bones and exists to convert a
standard rig into one. So the posing tools read the generated rig itself, in the spirit of
[names inside MPFB's node trees](#names-inside-mpfbs-node-trees-are-read-live-never-tabulated):

- **Body part and chain from the bone collections**, which MPFB's meta-rig defines
  (`data/rigs/rigify/rig.human_toes.json`) and Rigify carries through: `Arm.L (IK)` is the left
  arm's IK chain, and the parenthesised qualifiers Rigify hides - `(Tweak)`, `(Detail)`,
  `(Primary)`, `(Secondary)` - are `hidden_by_default`. Three refinements by name, because the
  collections lump them where an agent would not look: `neck` and `head` are the head, `shoulder.L`
  is the left arm, and the eyes and their common target are the head's `look_target`.
- **Role from Rigify's naming** - `_fk`, `_tweak`, `_master`, `_parent`, `_ik_target` - and the
  limb's IK control and pole from the switches themselves, whose descriptions Rigify writes as
  `"Switch parent of hand_ik.L"`.
- **Switches from the custom properties**, with range, default and description from
  `id_properties_ui()`. A parent switch's **parent names are on the property too**: Rigify's
  `SwitchParentBuilder` passes `items=` to `make_property()`, in Blender's core Rigify since it
  moved there, so the names are read live and the generated `rig_ui.py` is never read at runtime.
  The bridge test checks the live names against that script, searched as data. A property with no
  `items` reports `parent_names: null` with a reason rather than a guess from Rigify's usual order.
  What each end of a switch *means* is not on the property, so a short table of meanings
  (`SWITCH_ENDS`) is this package's, read from Rigify's source: note that `FK_limb_follow` and the
  spine's `neck_follow`/`head_follow` run in opposite directions, because Rigify drives one
  constraint at `value` and the other at `1 - value`.
- **Where the convention does not hold, a table stands in, and is checked.** A
  `rigify_generated.game_engine` rig - which MPFB makes only through its legacy convert-to-Rigify
  operator - has **every control in one collection**, `Bones`, and `_l`/`_r` sides; collections and
  suffixes are not enough there (established live during FR 041). Its body parts come from a token
  table keyed on the meta-rig bone each control is named for. With no qualifiers to read,
  **`hidden_by_default` is derived by role** there
  ([FR 043](../feature-requests/done/043-narrower-pose-controls/README.md)): `tweak`,
  `finger_segment`, `toe_segment`, and the torso's `_fk` controls - the FK spine, which MPFB's
  meta-rig puts in `Torso (Tweak)` while the breasts, also torso `fk`, are shown. The rule is the
  set the qualifiers hide on `human_toes` outside the face; FR 043 found the roles alone missed the
  FK spine, and the bridge test asserts the two agree control for control on a generated
  `human_toes` rig, which keeps reading its collections so that there is something to check the
  rule against. The default rig hides nothing: MPFB shows every bone there. The default rig has one collection
  too, and is classified from a table of the chains MPFB's `Default*Helpers` name; the bridge test
  reads those classes out of `sys.modules` and fails if MPFB renames a bone. Which helpers a default
  rig carries is MPFB's own record (`RigHelpersProperties`, read off its UI package as
  [a UI module with no service behind it](architecture.md#a-ui-module-with-no-service-behind-it)),
  compared with the bones present; what a helper drives is read off the constraints.
- **Any other rig is answered unclassified**, its bones as a hierarchy with no body part or role.
  A wrong `left_hand` is worse than none.

## A third-party add-on's UI operators are reimplemented, never called

Rigify gives every generated rig snap operators of its own - `pose.rigify_limb_ik2fk_<rig_id>`,
`pose.rigify_limb_toggle_pole_<rig_id>`, `pose.rigify_switch_parent_<rig_id>` - and they cannot be
relied on from a bridge command. They are registered by the `rig_ui.py` text block generation
writes into the `.blend`, which runs after a reload only if Python auto-run is allowed and at all
only in a Blender with a UI; and the bone chains each one works on are baked into that script as
operator properties rather than stored on the rig. So `mpfb_set_pose_switches`
([FR 042](../feature-requests/done/042-posing-bones-switches-and-reset/README.md)) **ports** the
snaps into its command module, crediting Rigify (GPL-2.0-or-later, compatible with the bridge's
licence) - the same rule as for MPFB's own UI operators
([when mpfb-mcp models a concept MPFB's UI has but its services do not](#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not)),
applied for the first time to another add-on.

- **A port drops what only a UI wants.** No keyframe is ever inserted; a quaternion IK base is
  twisted through its quaternion rather than switched to `ZXY` for good, as Rigify's
  `correct_rotation` does; and the twist search stops at a tenth of a degree rather than one, since
  a degree at the shoulder is several millimetres at the elbow.
- **The chains come from Rigify's naming, checked against the script, never read from it at
  runtime** - FR 041's answer for parent names, given again for the chains. A limb's FK controls
  give the rest by Rigify's `make_derived_name`: `upper_arm_fk.L` -> `upper_arm_ik.L` and
  `MCH-upper_arm_ik_target.L`, `forearm_fk.L` -> `MCH-forearm_ik.L`, `toe_fk.L` -> `toe_ik.L`, and the
  heel and spin controls are the extras an IK->FK snap returns to rest. The bridge test reads each
  generated `rig_ui.py` as data and requires every chain to match, on `human_toes` (`.L`) and on
  `game_engine` (`_l`); a pole's parent switch keeps only its location, as the script's `locks`
  says. A rig whose bones the rule names but the rig lacks is a resolution error naming them, with
  `raw: true` as the way to write the bare value.

## Reading MPFB's data files directly

Not everything a tool needs is behind a service. `mpfb_list_targets` reports `target.json`, the
bundled index of modeling targets, which MPFB has no accessor for at all — its own consumers build
the path and `json.load()` it. Where a tool has to read a bundled data file, three rules:

- **Locate it through `LocationService`, never by assembling a path from a module's location.**
  `get_mpfb_data("targets")` is the only thing that knows where an extension install put its data;
  a path derived from `__file__` or from the package name is a guess that breaks on the next
  install method.
- **Guard the read, and treat a missing or unparsable file as an answer.** A broken install is one
  of the things a tool is for reporting, so it comes back as `target_json_exists: false` plus an
  explanatory message and whatever else the tool could still gather — not as a failed call. This is
  the same rule as `mpfb_get_status`' three-state classification, applied to a file.
- **Report where it is rather than what is in it, when it is large.** `target.json` is ~140 KB, far
  more than a response should carry, and a client sharing a filesystem with Blender can parse it
  itself. Reporting the path, an overview, and a way to page through the contents is strictly more
  useful than truncating the file.

## MPFB caches what it scans, and a tool says what that costs and what it hides

Three of MPFB's own caches sit under this package's catalogue tools, and each one changes what an
answer means rather than merely how fast it arrives.

- **The asset list.** The first scan of a subdir loads a Blender preview image for every
  thumbnailed asset — the slow, memory-hungry part of `mpfb_list_assets`, paid once per subdir per
  Blender session, and shared with MPFB's own asset panels, so a session where those were opened
  has already paid it. Worse, the cache is keyed by a *label* derived from the filename alone, so
  two assets whose filenames differ only in case or underscores collapse into one entry: a count
  from here can under-report, and one of the two is missing entirely rather than merely
  mislabelled. That is a limitation of MPFB's cache and not of the filters, and it is why a
  listing count may disagree with a count of files on disk.
- **The custom rig list**, cached for the lifetime of the Blender session, so a rig installed after
  Blender started does not appear until something rescans.
- **The alternative materials of one asset**, cached per `(asset_source, asset_subdir)` — the case
  where [the tool is the stale one](responses.md#a-tool-may-report-a-fact-mpfbs-own-ui-does-not-show).
  `mpfb_list_asset_materials`' `refresh` clears it via
  `AssetService.invalidate_alternative_materials_cache()`, which is global — it drops every asset's
  cached scan, not only the one named in the call — reported through `cache_invalidated` rather
  than left implicit ([FR 018](../feature-requests/done/018-alternative-material-refresh/README.md)).
- **The list of saved character presets**, in the module global `_EXISTING_PRESETS`, which exactly
  one thing invalidates: a save through `serialize_to_json_file()`. A preset written by MPFB's panel
  in another Blender, by hand, or by an earlier session is invisible until something rescans.
- **Whether the `faceunits01` asset pack is installed**, in `FaceService`'s module global
  `_FACEUNITS01_INSTALLED` — the third instance of the pattern, and the first one gating a whole
  capability rather than one listing's freshness (see
  [below](#a-capability-that-depends-on-an-optional-asset-pack)). `mpfb_get_face_units`' `refresh`
  busts it via `force_recheck=True`, as do `mpfb_list_expressions`' and `mpfb_get_expression`'s;
  the two writing tools (`mpfb_set_face_units`, `mpfb_apply_expressions`) read the cached answer,
  since a caller who wants a fresh probe before writing reads one through a read tool first.
  Nothing in MPFB invalidates it on a pack install, which is filed as item 10 of
  `mpfb2/features/MCP_DISCOVERED_BUGS.md`. `list_available_expressions()`, by contrast, is **not**
  cached - it walks the disk on every call - so `mpfb_list_expressions`' `refresh` is about the pack
  probe only, and its description says which.

What follows for a tool:

- **A rescan is opt-in, never the default.** `refresh` writes MPFB's caches — the asset one
  rescans the *whole* library and invalidates the alternative-material and pack metadata along the
  way — and those are the same caches MPFB's own panels read. A default that rescanned would make
  a catalogue call a side effect on the user's UI.
- **Say in the docstring what the first call costs and what a rescan does**, since neither is
  visible from the response and both are surprising for a tool that changes nothing in the scene.
- **mpfb-mcp adds no cache of MPFB's data, and that was a decision.** The obvious place for one is
  the modeling category table four commands rebuild on every dispatch, and
  [FR 017](../feature-requests/done/017-category-table-cost/README.md) set out to build it. What it
  found on measuring was that the rebuild costs **4 ms**, which is not worth a cache of any kind —
  and what a cache would cost is the property that makes these tools better than MPFB's own panels:
  a target installed since Blender started is visible here and is not there. So every cache under
  these tools is MPFB's own, and a tool answering from MPFB's data is answering from a scan it just
  did.
- **Where the tool can see past the cache cheaply, it does, rather than handing the caller a flag
  instead of an answer.** `refresh` is opt-in for the reason above, but a caller who has to pass it
  in order to find out whether it would change anything has not been told much.
  `mpfb_list_presets` answers from MPFB's cached list — that is the list MPFB's own dropdown is
  built from, so a name in it is a name the user sees there — and *also* lists the directory, which
  is one `os.listdir` of some tens of files, reporting the difference as `missing_from_mpfb_list`.
  This is affordable precisely because the collection is small; it is not a general licence to
  second-guess a cache whose rescan is the expensive thing being avoided.
- **Where a cache cannot be refreshed at all, say that too.** A caller who cannot tell staleness
  from absence will read a missing asset as a missing file. FR 013 found that
  `AssetService.invalidate_alternative_materials_cache()` *does* exist and clears both dicts —
  nothing called it until
  [FR 018](../feature-requests/done/018-alternative-material-refresh/README.md) wired it up as
  `mpfb_list_asset_materials`' `refresh`, which is why that tool no longer says so.

## A capability that depends on an optional asset pack

[FR 026](../feature-requests/done/026-face-units/README.md) is the first tool pair whose whole
capability depends on an asset pack that may not be installed — the 52 ARKit face units, every one
of which needs a target file from `faceunits01` — and it is not the last: poses, further asset
packs and the extra-target packs all have the same shape. The generalisation is the durable part of
that effort:

- **MPFB reports the absence of an optional pack to nobody.** Without `faceunits01`,
  `FaceService.set_expression()` logs a warning per unit ("Target file not found for face unit,
  skipping") and returns normally, having moved nothing. MPFB's own panels handle this by not
  drawing themselves — `poll()` returns `False`, the operators are unreachable — which is a UI-layer
  guard an MCP tool inherits nothing from. **Probe the pack's own installed-check, and report it in
  every response that depends on it**, not only in a refusal: `mpfb_get_face_units` carries
  `faceunits01_installed` whether or not a subject even resolves, because a caller reading an
  all-zero answer needs to know whether that means "neutral" or "not installed" before it means
  anything at all.
- **Refuse a write outright when the probe fails, rather than succeeding emptily.** MPFB's own
  behaviour — warn and continue — turns a pack-absent call into what looks like a successful no-op.
  `mpfb_set_face_units` checks the probe before writing anything and answers `blocked_by:
  "faceunits01_not_installed"`, per [preconditions are
  answers](mutating-tools.md#preconditions-are-answers).
- **The probe is not a verification, and a per-item resolution failure stays separately
  reportable even after the probe passed.** `is_faceunits01_installed()` tests exactly one target
  (`cheekPuff`); a pack installed halfway — a partial download, a manual copy that missed a file —
  passes that probe and still has individual targets missing. `mpfb_set_face_units`'
  `could_not_load` is what a caller reads when the probe said yes and one specific unit said no
  anyway: checked per requested unit, at write time, never folded into the up-front refusal.
- **Where the write outlives the missing pack, the refusal matters more, and it covers only what
  would claim something.** `mpfb_apply_expressions` writes a stack that *persists* on the basemesh:
  without the pack, the character would go on claiming an expression it has never displayed, and a
  preset would carry the claim to another machine. So it refuses any call that adds or raises a row
  - FR 027 applied this rule rather than extending it - but lets a call that only removes rows
  through, since taking an expression off claims nothing and is how a stack from another machine
  is cleaned up. A catalogue of things that depend on the pack (`mpfb_list_expressions`) reports
  the probe on every answer for the same reason the read tool does: its list is a list of things
  that cannot be applied when the answer is `false`.
- **Use MPFB's own install-check rather than inventing a second definition.** `faceunits01` has no
  service function whose name says "is this pack here" other than the one `FaceService` already
  exposes; a tool inventing its own (checking for a specific file, say) risks disagreeing with what
  MPFB itself will and will not do.
- **Where MPFB has no install-check, take the narrowest definition MPFB's own code implies, and
  probe it the way MPFB resolves the files.** The viseme packs `visemes01` (Microsoft) and
  `visemes02` (Meta) have none ([FR 039](../feature-requests/done/039-exporting-characters/README.md)).
  `mpfb_create_export_copy` probes each with one target resolved through
  `TargetService.target_full_path()`, exactly as `is_faceunits01_installed()` probes `cheekPuff`:
  the silence viseme, `sil_00` and `viseme_sil`, which is what MPFB's `configure_lip_sync()` tests
  for. One target rather than the set because resolving all 37 was measured at 291 ms, a cost every
  answer reporting `visemes01_installed` would pay. The clause above still holds: the probe is not a
  verification, so a requested set is resolved in full before anything is written and its misses
  are `could_not_load`. A probe of MPFB's own is a request to MPFB, recorded in
  [NEXT_STEPS](../feature-requests/NEXT_STEPS.md#viseme-pack-probes), and would replace this one.
- **Check what a service does with a missing file, not what its docstring says.**
  `FaceService.load_targets()` says it raises when a pack is absent; `bulk_load_targets()` underneath
  warns and skips each target that does not resolve, so a load with nothing installed succeeds and
  loads nothing. The per-target resolution before writing is what makes that visible.

## When mpfb-mcp models a concept MPFB's UI has but its services do not

Not every concept a tool needs is a service concept. A modeling *modifier* — a slider from -1.0 to
+1.0, built from a pair of opposing targets, optionally with left and right variants — is not a
`TargetService` idea at all: it lives in `target.json` and in `mpfb/ui/model/_modelsubpanels.py`.
`mpfb_set_targets` lifts it out of the UI into the tool layer, because without it a caller could
address individual shape keys but could not express anything MPFB's own sliders express.

- **Reproduce the mechanics from MPFB's UI code rather than reinventing them**, statement for
  statement where the order matters. `_set_opposed_modifier_value()` zeroes the opposing target
  *first* and only then sets or loads the selected one; doing it the other way leaves both halves
  of a pair briefly non-zero and, with pruning on, deletes the wrong one.
- **Still never import the UI module**, for the reason in
  [Never import MPFB submodules directly](architecture.md#never-import-mpfb-submodules-directly)
  — and here for a second reason: `_modelsubpanels` builds its table at *module import time*, so
  it is a snapshot from when Blender started, and a tool built on it would be blind to a target that
  `mpfb_list_targets` — which scans per call — can see.
- **Document the divergences rather than silently normalizing them.** MPFB's two setter functions
  disagree about the file extension, one trying `.target.gz` then `.target` and the other only the
  first; and MPFB's category name for a gzipped custom target does not strip `.gz`, so its shape key
  is not called what `mpfb_list_targets` reports. Both are reproduced or repaired deliberately, and
  said out loud in the command's docstring and in the response, because a caller who meets one will
  otherwise read it as a bug here.
- **The goal is that the value reads back on MPFB's own slider.** Where reproducing a quirk and
  tidying it up would give different answers in MPFB's panel, reproduce the quirk.

**The export copy is the second case**, and the larger one
([FR 039](../feature-requests/done/039-exporting-characters/README.md)). MPFB's Export copy panel
has an operator, `MPFB_OT_Create_Export_Copy_Operator`, whose `hardened_execute()` composes
`ExportService`, `TargetService` and `FaceService` calls, and no service that does the same.
`mpfb_create_export_copy`'s command reproduces that sequence, step for step and with the panel's
eleven options and defaults, rather than calling `bpy.ops.mpfb.export_copy`, which reads its options
from the user's `EXPO_*` scene properties. Where it departs, the command docstring and the answer say
so: the caller's selection is put back rather than the copy left active, the copy is repaired where
MPFB's own copy falls short (below), one combination MPFB fails on is refused, and a GameEngine
material swap the panel lacks is offered beside it.

### Where a service falls short of what its own code says it does, follow the stated intent

`ExportService.create_character_copy()` comments that "any armature modifier on the child is
pointed to the new root", and then retargets the one modifier named `Armature`. FR 039's live check
found three consequences on a running install, each filed: a garment with a sub-rig, which is the
sub-rig's child and so a grandchild of the root, is not copied at all, because
`get_list_of_children()` returns direct children only; the `Armature PV` modifier MPFB adds for
preserve-volume weights still follows the **original** rig; and on a generated Rigify rig the copied
armature *data* keeps 84 B-bone drivers targeting the original rig, since `Object.copy()` remaps an
object's own drivers and `ID.copy()` of its data does not. A copy driven by its original is not a
copy.

- **Repair to the stated intent, and report each repair.** The command copies the descendants the
  service missed and points every reference on a copy - modifier, constraint, driver - that names an
  original in the family at that original's copy. `copy_repairs` lists every object copied and every
  reference retargeted. One rule covers all three, which is why the Rigify drivers are repaired
  rather than only reported, as the request had planned.
- **Call the service first, then repair.** Reimplementing the copy would hide the defect; calling
  MPFB's function and repairing after it means `copy_repairs` is empty on an MPFB that no longer
  needs it, which is how this package notices a fix upstream.
- **This is not picking between two code paths**, which is
  [a rule of its own](#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it): there
  is one implementation, and its comment and its code disagree. Where the stated intent is not
  clear, report rather than repair.

The general case of the section above — two MPFB *code paths* that disagree, rather than a UI
concept the services lack — is
[Where MPFB's own code paths disagree, mpfb-mcp picks one and names it](#where-mpfbs-own-code-paths-disagree-mpfb-mcp-picks-one-and-names-it).

### Sometimes reading the UI module is the right answer

The modifier case above ends in "never import the UI module", and that reads as a rule about UI
modules. It is not — it is a rule about *snapshots*. `_modelsubpanels` builds its table when
Blender starts, so anything built on it is blind to a target installed since, and mpfb-mcp
reimplements the concept from `target.json` instead.

`mpfb/ui/weburls.py` is the second instance of the same situation and comes out the other way. It
is again a concept MPFB's UI has and its services do not — the community addresses, which MPFB
gathers there "so that the same link does not have to be maintained in several panels" — but it
holds eleven string literals and computes nothing. There is no snapshot in it, so `mpfb_list_urls`
reads it out of `sys.modules` rather than keeping a second copy that MPFB's own edits would not
reach. The mechanics and the two conditions that make a UI module readable are in
[architecture.md](architecture.md#a-ui-module-with-no-service-behind-it).

The distinction worth carrying: **reimplement a UI concept that is computed, read a UI table that
is constant.** Both keep the rule the two cases actually share — MPFB's value is the authority,
and a copy of it is a fallback that must say it is one
([and say so in the response](responses.md#a-response-says-which-source-answered-it)).
