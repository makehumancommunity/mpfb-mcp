# Basic object finding and identification

**Status:** Done

Every modification tool in the [target catalog](../../../specifications/vision.md#target-tool-catalog)
beyond `mpfb_create_human` operates on *an existing object* — set a target on this basemesh, add
an asset to that human, put a rig on this character. But nothing today lets a caller discover
which objects exist, which of them are MakeHuman objects, or how they hang together. An agent
that did not itself create the character is blind: it can see Blender object names through
blender_mcp's generic tools, but nothing tells it that `Human.003` is a Basemesh while
`Human.004` is a Clothes item parented to it.

That blindness also blocks the two introspection tools already named in the catalog.
`mpfb_get_human_summary` takes "a given/active human" as its subject, and `mpfb_add_asset` /
`mpfb_set_skin` need to say which mesh they act on. Both presuppose a way to name a human and be
confident the name refers to the right kind of object. This request supplies that missing layer.

MPFB already carries the concept: every object it creates gets an `object_type` custom property
(`Basemesh`, `Skeleton`, `Subrig`, `Clothes`, `Eyes`, ...), and `ObjectService` has the reading
and relationship-walking logic built on it. It carries the asset provenance too — `asset_source`
and `material_source` properties, and `AssetService` to turn those fragments back into paths.
Almost nothing needs to be invented here — the work is choosing what to expose, and handling the
places where MPFB's conventions do not map cleanly onto a tool response.

## Goals

Primary: let a caller find MakeHuman objects in the current scene by type, determine what a given
object is — named explicitly, or simply the one that is active — and discover what else belongs
with it — enough to pick a subject for every later tool, without guessing from Blender names.

Also: say what each of those objects was *made from*. Knowing that `Human.004` is a `Clothes` item
identifies its role, but a caller asking "which shirt is this" or "can I re-fit it" needs the asset
behind it — the `.mhclo` it was imported from, the rig definition a skeleton was built to, the kind
of skin material a basemesh carries. MPFB records enough to answer that, in object properties it
sets at import time and in identification helpers that read the object itself, so the answer costs
one more property read per object plus, at most, an asset-root lookup.

Secondary: make the answer safe to act on. A name that does not resolve, a type filter that
matches nothing, and a type filter that was misspelled must be three visibly different answers,
not one empty list.

## Functional requirements

Two tools. The four narrow tools this effort was originally sketched as in
[NEXT_STEPS.md](../../NEXT_STEPS.md) — list basemeshes, list skeletons, identify one object's
type, list one object's relatives — collapse into two parameterized tools rather than four: listing basemeshes and
listing skeletons differ only by a filter value, and "which type is this object" is the cheap
first half of "what is related to this object", so a caller asking the second question always
wants the first anyway.

### `mpfb_list_objects`

Lists MakeHuman objects in the **current scene**, optionally filtered by MPFB object type.

Argument: `object_type` (optional string). Omitted or `null` means every object carrying any MPFB
`object_type`. Given, it filters — with MPFB's own matching semantics, see
[Architecture](#architecture).

`result` carries:

- `objects`: a list, each entry `{"name": ..., "object_type": ..., "blender_type": ...}` where
  `object_type` is MPFB's custom property (`"Basemesh"`, `"Clothes"`, ...) and `blender_type` is
  Blender's own (`"MESH"`, `"ARMATURE"`). Ordered as the scene iterates, which is stable within a
  session.
- `count`: length of `objects`.
- `requested_type`: the filter as given (`null` when omitted), echoed back so a caller reading a
  response out of context knows what it answers.
- `type_recognized`: whether `requested_type` matched a type MPFB actually knows about. This is
  what keeps "no basemeshes in this scene" distinct from "you asked for `Basemseh`" — the two are
  otherwise the same empty list, and an agent that cannot tell them apart will confidently report
  an empty scene.
- `known_types`: MPFB's full type vocabulary, so a caller can correct itself from the same
  response rather than needing a second tool or a hardcoded list.

Per-object output here stays at name and the two types: no `asset_info`. That field can cost an
asset-root directory walk per object (see [Architecture](#architecture)), and paying it for every
object in the scene to answer "what is in here" would make the cheap orienting tool the expensive
one. A caller that wants the asset behind a listed object asks `mpfb_get_object_info` about it.

Only the **current scene** is searched (`bpy.context.scene.objects`), so results match what the
user is looking at. Objects that exist in the `.blend` but are not linked into the scene are not
listed — but see `mpfb_get_object_info` below, which must not pretend they do not exist.

### `mpfb_get_object_info`

Identifies one object and reports what is related to it.

Argument: `name` (optional string) — a Blender object name. **Omitted or `null` means the
currently active object**, which is what a user pointing at something on screen and saying "what
is this" means, and saves an agent a `mpfb_list_objects` round trip in the common case where the
subject is whatever was just created or clicked. MPFB's own UI panels work from the active object
throughout, so this matches how a user already thinks about the scene.

`result` carries:

- `found`: whether a subject resolved. **Failing to resolve one is a successful answer, not an
  error** — an agent guessing at a name should get a usable "no" it can recover from, the same
  way [`mpfb_get_status`](../001-mpfb-get-status/README.md) answers rather than fails when
  MPFB is absent. Two distinct cases produce `found: false`: no object by that name, and no
  active object at all (an empty scene, or everything deselected). `message` names which.
- `resolved_from`: `"name"` or `"active_object"` — how the subject was chosen. Reported on every
  response, including `found: false`. Without it, a result obtained from the active object is
  indistinguishable from one obtained by name once it is out of its original context, and the two
  have very different lifetimes: a name stays valid until the object is renamed or deleted, an
  active-object answer is stale the moment the user clicks elsewhere.
- `name`: the resolved object's name, echoed back. Redundant when the caller passed it, but it is
  the whole point of the active-object form — it is how a caller turns "whatever is selected" into
  a stable address it can pass to later tools.
- `in_current_scene`: whether the object is linked into the current scene. Object names are unique
  across the whole `.blend`, so a name can resolve to an object that exists but is not in the
  scene `mpfb_list_objects` searched. Reporting this explicitly is what stops that from reading as
  a contradiction between the two tools.
- `object_type` / `blender_type`: as in `mpfb_list_objects`. `object_type` is `null` (not an empty
  string) when the object carries no MPFB type — it is a plain Blender object, not a MakeHuman one.
- `is_makehuman_object`: whether `object_type` is set at all. The single question most callers are
  actually asking.
- `asset_info`: what MPFB knows about the asset this object was made from. `null` for an object
  with no MPFB `object_type` — a plain Blender cube was not made from a MakeHuman asset, and an
  empty dict would suggest we looked and found nothing. Otherwise a dict **whose keys depend on the
  object type**, described below.
- `related_objects`: every MPFB-typed object among the object's nearest relatives — parents,
  children, and siblings — each as a
  `{"name", "object_type", "blender_type", "in_current_scene", "asset_info"}` entry,
  **excluding the object itself**. Each entry carries its own `in_current_scene` for the same
  reason the subject does, and that reason turned out to be broader than this request first
  assumed — see [Architecture](#architecture). Deliberately a **flat list, not a tree**: the hierarchy a
  basemesh sits in is real (a subrig can hang off a clothes item rather than off the character),
  but every consumer of this field wants "what belongs with this character", and nesting would make
  the common case pay for the rare one. A caller that needs the structure can walk it by calling
  this tool again on a returned name. Each entry's `asset_info` is the same structure as the
  subject's, populated the same way: the common question is "what is this character wearing", and
  answering it from one call rather than one call per child is the difference between an agent that
  describes a character and one that walks a tree to do it.
- `other_related_objects`: related objects in the same neighbourhood that carry *no* MPFB type,
  each additionally flagged with `rigify_role`: `"generated_rig"`, `"metarig"` or `null`. MPFB
  does not tag Rigify's generated rig with an `object_type`, so a character driven by Rigify would
  otherwise report no rig at all while one is plainly attached. These are kept in a separate list
  from `related_objects` so the distinction between *what MPFB claims* and *what we inferred from
  the object hierarchy* stays visible.
- `message`: one human-readable sentence, as `mpfb_get_status` does — most valuable in the
  `found: false` and "exists but not in this scene" cases, where the next step is not obvious.

`other_related_objects` entries carry `in_current_scene` too, and get **no** `asset_info`: they
carry no MPFB type, so by the rule above the value could only ever be `null`, and a key that is
always `null` is noise. Their `rigify_role` is the analogous field for what little can be said
about them.

#### The shape of `asset_info`

Three shapes, keyed off the object's type family. A union of all keys with the inapplicable ones
set to `null` was considered and rejected: `mhclo_path: null` on a skeleton reads as "we could not
find the mhclo", which is a different and much more alarming claim than "a skeleton does not have
one". The keys present say which question was asked; their values say whether it could be answered.

- **`Skeleton` / `Subrig`** — `{"rig_type": ..., "rig_definition_path": ...}`.
  `rig_type` is what `RigService.identify_rig()` reports. The vocabulary is larger than it first
  appears: `"default"`, `"default_no_toes"`, `"game_engine"`, `"game_engine_with_breast"`,
  `"cmu_mb"`, `"mixamo"`, `"mixamo_unity"`, `"openpose"`, `"rigify.human"`,
  `"rigify.human_toes"`, `"rigify.unknown"`, `"rigify_generated.game_engine"`,
  `"rigify_generated.human"`, `"rigify_generated.human_toes"`,
  `"rigify_generated.unknown"`, `"custom.<name>"`, or `"unknown"`. It never returns `None` —
  `"unknown"` is the miss. Note this is *identified from the bones present*, not read
  back from a property MPFB stored — MPFB does not record which rig was applied, so a
  hand-edited armature can be identified as something it was not built from. `rig_definition_path`
  is the absolute path of the `rig.<name>.json` the type corresponds to, or `null` when there is
  none to point at (`unknown`, `rigify.unknown`, any `rigify_generated.*`, or a file that is not
  on disk).
- **Mesh assets** (`Clothes`, `Eyes`, `Eyebrows`, `Eyelashes`, `Hair`, `Teeth`, `Tongue`,
  `Proxymeshes`) — `{"asset_source": ..., "mhclo_path": ..., "material_type": ...,
  "material_source": ..., "mhmat_path": ...}`.
  `asset_source` is the fragment MPFB stored on import (`"fedora/fedora.mhclo"`) or `null` if the
  object carries none; `mhclo_path` is that fragment resolved to an absolute path, or `null` if it
  could not be. `material_type` is `MaterialService.identify_material()` on the object's first
  material slot (`"makeskin"`, `"gameengine"`, `"procedural_eyes"`, `"enhanced_skin"`,
  `"layered_skin"`, `"empty"`, `"unknown"`). The key is `mhclo_path` for every type in this family,
  proxymeshes included, since MPFB imports them all through the same mhclo format — but note the
  file it points at may carry a `.proxy` extension rather than `.mhclo`, so a caller must not match
  on the suffix to decide what it is holding.

  `material_source` / `mhmat_path` are the same pair as on the basemesh and are reported here for
  the same reason — "which mhmat is this object's material built from" is one question, and a
  caller should not have to know which of two MPFB properties happens to answer it for a given type.
  They do come from different properties, and the **meaning of `null` therefore differs by type**,
  which the tool docstring must say plainly:
  - For an ordinary mesh asset the value is the `alternative_material` fragment, set when a
    material other than the asset's own was applied. `null` is the ordinary case and means the
    object uses **the default material named inside its mhclo** — not that the material is unknown.
    That default is deliberately *not* resolved here; see [Architecture](#filling-in-asset_info).
  - `Proxymeshes` is the exception in this family: a body proxy wears the character's skin, so MPFB
    writes the basemesh's `material_source` onto it as well. It is read there first, exactly as
    `HumanService` reads it, and falls back to `alternative_material`.
- **`Basemesh`** — `{"material_type": ..., "material_source": ..., "mhmat_path": ...}`.
  `material_type` as above, and `material_source` / `mhmat_path` the same pair as for mesh assets,
  here always the skin. **The used skin mhmat *is* deducible, in the cases where there is one**
  — see [Architecture](#architecture): MPFB stores the mhmat as a fragment on the basemesh whenever
  a skin was loaded from one, so `material_source` carries that fragment and `mhmat_path` its
  resolved absolute path. A freshly created human that was never given a skin has neither, and
  reports both as `null` — correctly, because there is no mhmat behind its procedural material.

Two rules across all three shapes:

- **Every `*_path` is absolute or `null`; a fragment is never presented as a path.** The two are
  easy to confuse — `"fedora/fedora.mhclo"` looks path-shaped — and a caller that passes a fragment
  to a file-opening tool gets a confusing failure far from here. Keeping the fragment in its own
  field is what lets both be reported without either being mistaken for the other.
- **Keeping the fragment alongside the path is also how the two failure modes stay
  distinguishable**, without adding a flag for it. This holds for both pairs —
  `asset_source`/`mhclo_path` and `material_source`/`mhmat_path`. A `null` fragment means the object
  records no such asset at all: it was built rather than imported, it is using a default material,
  or it predates the property. A non-null fragment with a `null` path means the asset *is* recorded
  but is not installed under any asset root this Blender can see — the user moved or uninstalled the
  pack. The first is normal; the second is something a caller may want to tell the user about, and
  an undifferentiated `null` path would hide it.

## Non-functional requirements

- **Read-only / side-effect-free.** Both tools only read custom properties, walk the object
  hierarchy, inspect bone names and material node trees, and look up files on disk. `ObjectService`
  also carries destructive methods (`delete_object`, `extract_vertex_group_to_new_object`) and
  selection-mutating ones (`activate_blender_object`, `select_object`,
  `deselect_and_deactivate_all`) — the payloads must touch none of them. In particular, resist any
  temptation to select or activate an object in order to inspect it; that changes state the user
  can see. The asset lookups are read-only in the same sense: they open no `.blend`, import
  nothing, and must never fall back on an MPFB call that would *load* the asset in order to find
  out where it is.
- **Cheap enough to call before anything else.** `mpfb_list_objects` is a scene iteration and
  property reads — nothing that touches geometry, loads files, or scans asset directories — and
  that is why its per-object output stays at name and the two types.
  `mpfb_get_object_info` is where `asset_info` relaxes this, deliberately and in a bounded way:
  resolving a fragment to an absolute path is an `os.walk` of the configured asset roots
  (`AssetService.find_asset_absolute_path()`), which on a large asset library is not free, and one
  `mpfb_get_object_info` call can do it once per related object. The bound is that the walk happens
  **only when there is a fragment to resolve** — a scene of hand-made Blender objects, or a
  freshly created human with no assets and no skin, pays nothing — and that the tool is asked about
  one object at a time. If live testing shows this is too slow with many asset roots, the fallback
  is an opt-out argument on `mpfb_get_object_info`, not moving `asset_info` out of it; do not add
  that argument pre-emptively.
- **A field that says "the asset is missing" must not be confusable with one that says "there is no
  asset".** The fragment/path pairing in [`asset_info`](#the-shape-of-asset_info) exists for this,
  and it is the same quality attribute as the `type_recognized` and `found` cases below: an agent
  reading a bare `null` will conclude, not investigate.
- **An empty answer must never be ambiguous.** Covered functionally by `type_recognized` and
  `found` above, but it is the quality attribute driving both: an agent acting on a wrong empty
  answer does not retry, it concludes and moves on.
- **Not cacheable.** Results describe one scene at one moment. Loading another `.blend`, or the
  user deleting an object, invalidates them entirely — and unlike `mpfb_get_status` these results
  are *addresses* that later mutating tools will act on, so a stale one is worse than a missing one.
  The active-object form of `mpfb_get_object_info` is the sharpest case: its subject depends on
  session state no caller can see, and changes when the user clicks in the viewport. This is the
  cost of the convenience, and the reason the resolved `name` and `resolved_from` are both in the
  response — a caller that intends to act on the object should carry the name forward rather than
  re-deriving it from the active object on each later call.

## Architecture

- Two tool modules, `src/mpfbmcp/tools/list_objects.py` and
  `src/mpfbmcp/tools/get_object_info.py`, plus two payload files under
  [`codegen/payloads/`](../../../src/mpfbmcp/codegen/payloads) and two `register()` calls in
  `__init__.py` — the shape [architecture.md](../../../specifications/architecture.md#code-generation-layout)
  requires. No shared code-generation module should need editing; if it does, that is a signal
  worth recording.
- **Use the raising bootstrap** (`bootstrap="raising"`). Unlike `mpfb_get_status`, these tools
  cannot answer anything meaningful without `ObjectService`, and its `RuntimeError` already points
  the caller at `mpfb_get_status`.
- `ObjectService` is in the `SERVICES` dict, so it resolves through the standard bootstrap with no
  special handling. So are the four services `asset_info` needs — `AssetService`, `ClothesService`,
  `MaterialService`, `RigService` — and `LocationService`. None of them needs the private-constant
  trick; pull them out of `SERVICES` the same way.
- **Pitfall — `object_is()` matches by substring, not equality.** `ObjectService.object_is()`
  lowercases both sides and tests `requested in actual`, so `"mesh"` matches both `Basemesh` and
  `Proxymeshes`, and `"rig"` matches `Subrig`. This is deliberate on MPFB's side — it absorbs
  the `Proxymesh`/`Proxymeshes` naming variance visible in MPFB's own docs. Use `object_is()` rather than comparing
  `get_object_type()` strings, so mpfb-mcp inherits MPFB's semantics instead of inventing
  stricter ones that reject a type MPFB itself accepts. But **document the behavior in the tool
  docstring**, because an agent filtering on `"rig"` and receiving subrigs will otherwise read it
  as a bug.
- **The type vocabulary lives in private module-level constants.** `_ALL_TYPES`, `_MESH_TYPES`,
  `_SKELETON_TYPES` and friends are module-level names in `objectservice.py`, not members of
  `ObjectService` and not in `SERVICES`. Read them the way FR 001 reads
  `LOWEST_FUNCTIONAL_BLENDER_VERSION` — `sys.modules[ObjectService.__module__]` — since the module
  is necessarily imported once `ObjectService` resolved. They are underscore-private and may be
  renamed by MPFB without notice, so read them with `getattr(..., default)` and fall back to a
  literal list in the payload rather than raising. Populating `known_types` from MPFB rather than
  from a hardcoded list in mpfb-mcp is deliberate: a list duplicated here drifts silently, and this
  one is user-facing guidance an agent will act on.
- **Pitfall — `find_all_objects_of_type_amongst_nearest_relatives()` yields the object itself.**
  Its first action is `if ObjectService.object_is(blender_object, mpfb_type_name): yield
  blender_object`. `find_related_objects()` is a thin wrapper over it with `_ALL_TYPES`, so the
  subject appears in its own relatives list. Filter it out, and dedupe the rest by object name —
  the traversal excludes the branch it arrived from, but defensive dedup is cheap and the
  alternative is a duplicate that reads as two distinct objects.
- `other_related_objects` has no `ObjectService` equivalent and needs its own walk:
  `find_related_objects()` only yields objects carrying an MPFB type. Walk the same neighbourhood
  (the object, its children recursively via `get_list_of_children()`, then the parent chain and
  their children) and keep whatever `object_is_any_makehuman_object()` reports falsy for. Classify
  each with `object_is_generated_rigify_rig()` and `object_is_rigify_metarig()`.
- **Pitfall — the relationship walk itself leaves the current scene.** This request originally
  expected only the Rigify pairing helpers to do so. `find_rigify_metarig_by_rig()` does iterate
  `bpy.data.objects` rather than the scene; `find_rigify_rig_by_metarig()` turned out to iterate
  nothing at all, being a single `rigify_target_rig` property lookup. But
  `ObjectService.get_list_of_children()` walks `bpy.data.objects` as well, and *every* relative is
  found through it — so `find_related_objects()` can return an object that is not in the scene
  `mpfb_list_objects` searched. Filtering those out would silently drop a real relationship, so
  the resolution is the one this request already named for the Rigify case, applied to every
  entry: mark it with the same `in_current_scene` flag the subject gets, and do not let it in
  unlabelled.
- **Pitfall — `get_object_type()` returns `""`, never `None`,** for an object carrying no MPFB
  type, and `object_is_any_makehuman_object()` returns that *string* rather than a bool (as does
  `object_is_generated_rigify_rig()`, which hands back Rigify's `rig_id`). Coerce where a value
  enters the response: `object_type` must be a type name or `null` and never `""`, and
  `is_makehuman_object` must be a real bool.
- `mpfb_get_object_info` resolves its name against `bpy.data.objects` (unique across the file) and
  then reports `in_current_scene` from `bpy.context.scene.objects`, rather than looking up in the
  scene and reporting a bare "not found". Distinguishing "no such object" from "exists, elsewhere"
  is the whole value of that field.
- **Pitfall — resolve the active object via the view layer, and expect `None`.** Read it as
  `bpy.context.view_layer.objects.active` rather than `bpy.context.active_object`: the generated
  code runs inside the blender_mcp add-on's execution context, not from a viewport operator, and
  the view-layer form is the one that does not depend on which UI area happens to be current. It
  is `None` whenever nothing is active — an empty scene, or the user deselecting everything — and
  that must produce `found: false` with an explanatory `message`, never an `AttributeError` on
  `None.name`. Note the asymmetry this creates with the rest of the tool: an active object is
  always in the current scene, so `in_current_scene` can only be `false` in the by-name form.
- Input validation, per
  [Validate before crossing the socket](../../../specifications/architecture.md#validate-before-crossing-the-socket):
  reject a non-string or empty/whitespace-only `name` locally — but only when one was *given*, since
  omitting it now means "use the active object". An explicitly empty string is still a caller error
  and must not be silently treated as omission: the two arise from different mistakes, and quietly
  answering about the active object when the caller believed it named something is worse than
  failing. Do **not** validate `object_type`
  against a locally hardcoded vocabulary — that would put the drifting list back in mpfb-mcp;
  `type_recognized` answers it authoritatively from inside Blender instead. Rejecting an empty
  string for `object_type` is still worthwhile, since it would otherwise substring-match every type.
- Response envelope unchanged: return `send_code(...)` as-is with `strict_json=True`. Note that
  every field above must be a plain `str`/`bool`/`None` — see
  [References](#references) for a case where an MPFB getter returned a `pathlib.Path` despite its
  annotation and took a whole response down.

### Filling in `asset_info`

- **The properties are not services.** `asset_source`, `alternative_material` and
  `material_source` live on the object as Blender custom properties managed by `BlenderConfigSet`
  instances — the first two on `GeneralObjectProperties` (prefix `MPFB_GEN_`), the last on
  `HumanObjectProperties` (prefix `MPFB_HUM_`) — which are *entities*, not members of `SERVICES`. Two ways in, in order of preference: reach them off the module of a
  service that already imported them, `sys.modules[ObjectService.__module__].GeneralObjectProperties`
  and `sys.modules[HumanService.__module__].HumanObjectProperties` (the same
  `sys.modules[Service.__module__]` pattern the type vocabulary uses above), or read the raw
  properties `blender_object["MPFB_GEN_asset_source"]` / `["MPFB_HUM_material_source"]`. Prefer the
  first: the raw key hardcodes a prefix assembled in two places (`_PREFIX = "MPFB_"` in
  `blenderconfigset.py` plus the per-set prefix in `objectproperties/__init__.py`) and skips the
  config set's default handling. Whichever is used, guard it — these are private-ish entities and
  an absent property must yield `null`, not an exception.
- **Mesh assets already have a resolver: `ClothesService.find_clothes_absolute_path(obj)`.** It
  reads `asset_source`, lowercases `object_type` to use as the asset subdir, and calls
  `AssetService.find_asset_absolute_path()` — which is exactly the derivation `mhclo_path` needs,
  for every mesh asset type and not only `Clothes` (the subdir convention is `Eyes` → `eyes`,
  `Hair` → `hair`, and so on). Use it rather than reassembling the same three steps; if it turns
  out to mishandle a type, fixing it in MPFB is better than forking it here. It returns `None` when
  either input is missing, which maps straight onto `mhclo_path: null`.
- **Skin mhmat: yes, it is deducible — when a skin was actually loaded from one.** This resolves
  the open question in the request. `HumanService.set_character_skin()` — there is no `set_skin()`, and the private
  `_set_skin()` is the deserializer that calls it — writes the mhmat as a fragment into
  `material_source` (`os.path.basename(dirname) + "/" + basename`) on the basemesh, and on the body
  proxy too when there is one; `HumanService._populate_human_info_with_skin_info()` reads it back
  as `human_info["skin_mhmat"]`, so this is MPFB's own answer to the same question. Resolve it with
  `AssetService.find_asset_absolute_path(fragment, "skins")` — see the precedence rule below, which
  is where a `Proxymeshes` object carrying this property as well is handled. The limits are worth
  stating in the tool docstring: the property is only written when a skin came from an mhmat, so a
  default procedural skin leaves it empty; nothing rewrites it if the material is later edited or
  replaced by hand, so it records *what was loaded*, not necessarily what is on the mesh now. The
  same caveat applies to `alternative_material`, and to `material_type`, which is the one field in
  `asset_info` derived from the material actually present rather than from a record of what was
  loaded — where the two disagree, `material_type` is the one describing reality.
- **`material_source` comes from two different properties, and each resolves against a different
  asset subdir.** This is the one place where a single response key is filled from more than one
  source, so the rule needs to be explicit. In order:
  1. `material_source` (`MPFB_HUM_material_source`), if set. Resolve it with
     `AssetService.find_asset_absolute_path(fragment, "skins")`. Only a `Basemesh` or a
     `Proxymeshes` object ever carries it — MPFB writes it in
     `HumanService.set_character_skin()` to the basemesh and, when there is one, the body proxy, and nowhere else. Reading it first on a
     proxy mirrors `HumanService._populate_human_info_with_skin_info()`, which prefers the proxy
     over the basemesh precisely because the proxy is what the skin is on.
  2. Otherwise `alternative_material` (`MPFB_GEN_alternative_material`), if set. Resolve it against
     **the object type's own subdir**, not `"skins"` —
     `AssetService.find_asset_absolute_path(fragment, object_type.lower())`, the same subdir
     convention `find_clothes_absolute_path()` uses. Getting this wrong does not raise; it silently
     returns `null` for an asset that is installed, which is the failure the fragment/path pairing
     was meant to make visible and would instead make misleading.
  3. Otherwise both keys are `null`.
  The fragments are produced by `AssetService.path_to_fragment()` (or the same two-basename
  expression inlined), so they are always `"<dirname>/<filename>.mhmat"` and never absolute.
- **Do not resolve an asset's *default* material.** When `alternative_material` is unset, the mesh
  asset is using the material named on the `material` line inside its mhclo, which is knowable —
  `MPFB_OT_Load_Library_Material_Operator._find_default_material()` does it by locating the mhclo
  and loading it with `Mhclo(...).load(path, only_metadata=True)`. That is a file parse per asset on
  top of the asset-root walk, for a value the caller can derive itself from `mhclo_path`, and it
  would make the ordinary case (no alternative material) the expensive one. Report `null` and let
  the docstring say what `null` means here. If a later effort wants the default material, it
  belongs behind an explicit argument, and `AssetService.alternative_materials_for_asset()` — which
  already caches per asset — is the better starting point than the operator's private helper.
- **`rig_type` is identified, not recorded.** There is no property holding it:
  `RigService.identify_rig(armature_object)` matches bone names against a table and falls back to
  `ObjectService.object_is_generated_rigify_rig()` / `object_is_rigify_metarig()`, to a `mixamo`
  bone-name scan, and finally to `AssetService.get_custom_rigs()`. It always returns a string, never
  `None` — `"unknown"` is the miss. Call it only on an `ARMATURE`: it dereferences
  `armature_object.data.bones`, which a mesh does not have. The custom-rig fallback reads JSON files
  off disk (cached in a module global), so this is another lookup that is cheap on a second call and
  not on the first.
- **Deriving `rig_definition_path` from `rig_type`.** MPFB builds the path in
  `HumanService.add_builtin_rig()`: `LocationService.get_mpfb_data("rigs")`, then subdir `rigify` if
  the type starts with `rigify.` else `standard`, then `rig.<name>.json` where `<name>` is the type
  with any `rigify.` prefix stripped. Mirror that, `os.path.isfile()` it, and report `null` rather
  than a path that does not exist. Three cases have no file to point at and must be `null`, not a
  guess: `"unknown"`, anything starting with `rigify_generated.` (a generated rig was built by
  Rigify from a metarig, not loaded from a definition — `RigService.infer_metarig_type_from_generated()`
  can name the metarig it likely came from, but that is an inference about a *different* object and
  does not belong in this field), and a rig whose file is simply absent. For a `"custom.<name>"`
  type the path is not derived at all — take it from the matching entry's `path` key in
  `AssetService.get_custom_rigs()`.
- **`material_type` needs a material.** `MaterialService.get_material(obj, 0)` returns `None` for an
  object with no slots, and `MaterialService.identify_material(None)` answers `"empty"`, so the pair
  composes without a guard — but `identify_material()` walks the material's node tree, so it is not
  a property read. It is still local to the object and touches no files, which is why it is in
  `asset_info` for both mesh families. It is a heuristic, and its own comments say so ("This might
  give a false positive if someone added a material with a principled node to a MH object"); the
  tool docstring should not present its answer as authoritative. Only meshes have material slots —
  do not call it on an armature.
- **Dispatch on the type family, not on the type string.** Which of the three shapes to build
  follows `_SKELETON_TYPES` / `_MESH_ASSET_TYPES` / `Basemesh` — reuse the vocabulary read described
  above rather than writing a second list of type names in the payload. A type MPFB knows about but
  this list does not (MPFB adds one) should fall through to an empty dict `{}` with the object still
  reported normally: an unrecognized MakeHuman object is not an error, and `{}` says "no asset
  questions apply to this type" without claiming any specific answer.
- **Every value in `asset_info` must survive `strict_json`.** `find_asset_absolute_path()` returns
  `str` (it goes through `os.path.abspath`), but `AssetService`'s `list_*_assets()` helpers return
  `pathlib.Path`, and `LocationService.get_mpfb_root()` has already been caught returning `Path`
  despite a `-> str` annotation when called with no sub-path (commit `631989c`, below;
  `get_mpfb_data()` is unaffected and does return `str`). Coerce every path with `str()` at the
  point it enters the response dict rather than trusting an annotation.

## Affected specifications

- [vision.md](../../../specifications/vision.md#target-tool-catalog) — the "Introspection (read-only)"
  list has no entry for object finding at all; it jumps from `mpfb_get_status` to
  `mpfb_get_human_summary`, which silently assumes the subject is already known. Add
  `mpfb_list_objects` and `mpfb_get_object_info`, mark them **Implemented** when this lands, and
  note that `mpfb_get_human_summary` and the modification tools take their subject from them.
- [architecture.md](../../../specifications/architecture.md) — three candidate additions, all worth
  deciding on at implementation time rather than up front:
  - **How generated code addresses objects.** This effort establishes that tools name objects by
    Blender object name, scoped to the current scene, with "exists elsewhere in the file" as a
    distinct answer. Every later mutating tool will follow it, so it belongs in the standing spec
    rather than in one request.
  - **Reading private module-level constants from MPFB.** FR 001 did this once
    (`LOWEST_FUNCTIONAL_BLENDER_VERSION`); this effort does it again for the type vocabulary, and a
    third time for the property entities `asset_info` needs. That makes it a pattern: allowed, via
    `sys.modules[Service.__module__]`, never via a fresh import, and always with a fallback because
    the names are private — and it now covers reaching non-`SERVICES` *entities* through a service's
    module, not only constants.
  - **How tools report the asset behind an object.** The fragment-plus-absolute-path pairing, the
    rule that a `*_path` field is absolute or `null`, and the type-varying rather than unioned
    `asset_info` shape are conventions every later tool that mentions an asset should follow —
    `mpfb_get_human_summary` and `mpfb_add_asset` most immediately. Worth writing down once the
    shape has survived contact with a real scene.

## Tests

Unit tests follow [tests/test_get_status.py](../../../tests/test_get_status.py)'s two-layer approach,
which fits this effort better than `test_create_human.py`'s source-substring assertions, since
both payloads carry real branching:

- Tool-level, with `send_code` mocked: argument validation (empty/whitespace/non-string `name`,
  empty `object_type`), that an *omitted* `name` is accepted while an *empty* one is rejected,
  that `strict_json=True` is passed, and that the blender_mcp envelope comes back unchanged.
- Generated-code-level, `exec()`-ing the assembled source against a stubbed `bpy` and stubbed
  services injected into `sys.modules` — `ObjectService` for the relationship walk, plus
  `AssetService`, `ClothesService`, `MaterialService`, `RigService` and `LocationService` for
  `asset_info`. The stub scene should include, at minimum: a basemesh with a skeleton and two
  clothes children; an untyped Rigify-looking armature in the same hierarchy; a typed object
  present in `bpy.data.objects` but absent from the scene; and a plain Blender cube. That covers
  self-exclusion from `related_objects`, the `related`/`other_related` split, `in_current_scene`,
  and the untyped-object branch. The stub `bpy.context.view_layer.objects.active` should be
  exercised both set and `None`, covering `resolved_from: "active_object"` and the
  no-active-object branch — the latter is the one that crashes on `None.name` if it is missed.
- A test that an unrecognized `object_type` yields `type_recognized: false` with an empty
  `objects` list, since that pairing is the requirement's whole point and is easy to regress into
  a bare empty list.
- `asset_info` shape tests, driven off the same stub scene: that a skeleton gets the rig keys and
  no mesh keys and vice versa, that an untyped object gets `null` and an
  `other_related_objects` entry gets no such key at all, and that a type outside the three families
  falls through to `{}` rather than raising.
- `asset_info` resolution tests, which are the ones with real branching. For each of the three
  shapes, exercise all three outcomes with the stub resolver: fragment present and resolving to a
  path; fragment present and the resolver returning `None` (asset not installed) — asserting the
  fragment survives in the response while the path is `null`, since that distinction is the reason
  both fields exist; and no fragment at all.
- `material_source` precedence and subdir tests, since that key is filled from two properties: a
  clothes object with only `alternative_material` set, a basemesh with only `material_source` set,
  and a `Proxymeshes` object carrying **both** — asserting the `MPFB_HUM_` one wins there. Have the
  stub `find_asset_absolute_path` record the `asset_subdir` it was called with and assert on it:
  `"skins"` for the `material_source` route and the lowercased object type for the
  `alternative_material` route. A swap between those two is invisible in the response shape and
  would only show up as an unresolvable path against a real asset library. Add one asserting a `pathlib.Path` returned by a stub
  resolver comes out of the payload as a `str`, per commit `631989c`.
- A test that no resolver is called at all when there is no fragment — a stub whose
  `find_asset_absolute_path` raises if invoked. The bounded cost claimed in the non-functional
  requirements is otherwise unverifiable from this side of the socket, and an accidental
  unconditional walk would be invisible until someone with a large asset library complains.
- **Live verification against a real Blender is required for this effort**, more than for the
  relationship walk: every `asset_info` value comes from an MPFB property or helper whose real
  return type and content the stubs assert nothing about. At minimum, on a character with a skin
  loaded from an mhmat, at least one mhclo asset, and both a standard and a Rigify rig: check that
  each path is absolute and exists on disk, that `rig_type` matches the rig actually applied, and
  that the whole response survives `strict_json`.

## References

- `../../../../mpfb2/src/mpfb/services/objectservice.py` and
  `../../../../mpfb2/docs/services/objectservice.md` — the source of every capability above.
  The docs' "Object Type Constants" table is the human-readable version of `_ALL_TYPES`.
- `../../../../mpfb2/src/mpfb/entities/objectproperties/` — where `object_type`, `asset_source`,
  `alternative_material` and `uuid` actually live (`generalproperties/`, exposed as
  `GeneralObjectProperties`, full prefix `MPFB_GEN_`), along with `material_source`
  (`humanproperties/`, exposed as `HumanObjectProperties`, prefix `MPFB_HUM_`). All four are
  string properties defaulting to `""`, so an unset one reads back as the empty string rather
  than as `None`. One JSON file per property, each
  documenting what the property is for; `blenderconfigset.py` is where the `MPFB_` half of the
  prefix is prepended.
- `../../../../mpfb2/src/mpfb/services/assetservice.py` — `find_asset_absolute_path()` (the
  fragment → absolute path walk, and its multiple-match tie-breaking), `path_to_fragment()` for the
  inverse, and `get_custom_rigs()` for `custom.<name>` rig paths.
- `../../../../mpfb2/src/mpfb/services/clothesservice.py` — `find_clothes_absolute_path()`, the
  ready-made `asset_source` + `object_type` → mhclo path resolver, and `refit_to_basemesh()` for
  the same derivation done inline.
- `../../../../mpfb2/src/mpfb/services/materialservice.py` — `get_material()` and
  `identify_material()`, including the comments on where the heuristic can give a false positive.
- `../../../../mpfb2/src/mpfb/ui/apply_assets/assetlibrary/operators/loadlibrarymaterial.py` — the
  only place `alternative_material` is written outside `HumanService`, and therefore the definition
  of what that fragment means: `path_to_fragment()` of the chosen mhmat, cleared to `""` when the
  asset's default material is restored. Its `_find_default_material()` is the mhclo-parsing lookup
  this request deliberately does not do.
- `../../../../mpfb2/src/mpfb/services/rigservice.py` — `identify_rig()`'s bone-name table and
  fallbacks, and `infer_metarig_type_from_generated()`.
- `../../../../mpfb2/src/mpfb/services/humanservice.py` — the reference implementation of the same
  questions: `_populate_human_info_with_skin_info()` and `_populate_human_info_with_bodyparts_info()`
  read exactly these properties to build a serialized human, `set_character_skin()` is where
  `material_source` is written, and `add_builtin_rig()` is where the `rig.<name>.json` path is
  assembled. Where this request and that code disagree about how a value is derived, that code is
  right.
- [FR 001](../001-mpfb-get-status/README.md) — the `sys.modules[Service.__module__]` constant
  read, the "absence is an answer, not an error" stance, and the `message` field convention all
  come from there.
- Commit `631989c` — `mpfb_get_status`'s first live run returned an error envelope because
  `LocationService.get_mpfb_root()` hands back a `pathlib.Path` despite being annotated `-> str`.
  Cited twice above: as the reason `strict_json` output needs checking against real MPFB, and as
  the reason this request insists on live verification.

## Verification status

Added when this request was marked `Done`. The implementation landed with its unit tests
passing, but **the live verification described under [Tests](#tests) was deliberately left out
of scope and has not been run**. Nothing here has been exercised against a real Blender + MPFB +
blender_mcp instance, so every documented `asset_info` value rests on reading MPFB's source
rather than on observation — which this request itself argued is the weakest part of the
effort, since the stubs assert nothing about MPFB's real return types.

Covered locally instead: `tests/test_list_objects.py` and `tests/test_get_object_info.py`
execute the generated source against the stubs in `tests/blender_stubs.py`, which reproduce the
MPFB behaviors the payloads are written around — `""` rather than `None` for an untyped object,
a non-bool `object_is_any_makehuman_object()`, a `find_related_objects()` that yields the
subject itself, and a `get_list_of_children()` that walks the whole file. They cover subject
resolution by name and by active object (including the no-active-object branch), the
related/other-related split, `in_current_scene` on subject and relative, all three `asset_info`
shapes and their fall-through, all three resolution outcomes per shape, the `material_source`
precedence and both asset subdirs, `pathlib.Path` coercion, and that no asset-root walk happens
without a fragment. That validates the branching, not MPFB's actual return values.

Still outstanding:

- [ ] `mpfb_list_objects` with no filter, on a scene holding a rigged, dressed character —
      every MakeHuman object listed, `known_types` populated from MPFB itself, and
      `type_recognized` true.
- [ ] `mpfb_list_objects` with `"rig"` — confirm MPFB's substring matching really does return
      `Subrig` alongside `Skeleton`, since the tool docstring promises exactly that.
- [ ] `mpfb_get_object_info` with no `name` while an object is selected — `resolved_from:
      "active_object"` and the right subject. This confirms
      `bpy.context.view_layer.objects.active` resolves inside the blender_mcp add-on's execution
      context, which is the one assumption the unit tests cannot approximate at all.
- [ ] The same with nothing selected — `found: false` with an explanatory `message`, not a
      traceback.
- [ ] `mpfb_get_object_info` on a basemesh whose skin was loaded from an mhmat — `material_source`
      populated and `mhmat_path` an absolute path that exists on disk.
- [ ] The same on at least one mhclo asset, and on a body proxy if one is fitted — `asset_source`
      and `mhclo_path` likewise, noting whether the proxy's path really ends `.proxy`, and that a
      proxy carrying both properties reports the skin rather than the alternative material.
- [ ] A standard rig and a Rigify-generated rig on the same character — `rig_type` matches the rig
      actually applied; the standard one resolves a `rig_definition_path` that exists on disk; the
      generated one reports `null` for it and appears in `other_related_objects` with
      `rigify_role: "generated_rig"`.
- [ ] An object present in the `.blend` but not linked into the current scene —
      `in_current_scene: false`, both as the subject and as somebody's relative.
- [ ] Every response above survives `strict_json`: nothing MPFB returns leaks a `pathlib.Path`
      or a Blender object into `result` (the failure mode of commit `631989c`).
- [ ] A timing check on a large asset library: whether one `mpfb_get_object_info` call, resolving
      a fragment per relative, is tolerably fast. If it is not, the fallback this request names is
      an opt-out argument, not moving `asset_info` out of the tool.
