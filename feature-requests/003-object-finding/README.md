# Basic object finding and identification

**Status:** Accepted

Every modification tool in the [target catalog](../../specifications/vision.md#target-tool-catalog)
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
and relationship-walking logic built on it. Almost nothing needs to be invented here — the work
is choosing what to expose, and handling the places where `ObjectService`'s conventions do not
map cleanly onto a tool response.

## Goals

Primary: let a caller find MakeHuman objects in the current scene by type, determine what a given
object is — named explicitly, or simply the one that is active — and discover what else belongs
with it — enough to pick a subject for every later
tool, without guessing from Blender names.

Secondary: make the answer safe to act on. A name that does not resolve, a type filter that
matches nothing, and a type filter that was misspelled must be three visibly different answers,
not one empty list.

## Functional requirements

Two tools. The four bullets in [NEXT_STEPS.md](../NEXT_STEPS.md#basic-object-finding-and-identification)
collapse into two parameterized tools rather than four narrow ones: listing basemeshes and
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
  way [`mpfb_get_status`](../done/001-mpfb-get-status/README.md) answers rather than fails when
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
- `related_objects`: every MPFB-typed object among the object's nearest relatives — parents,
  children, and siblings — each as a `{"name", "object_type", "blender_type"}` entry, **excluding
  the object itself**. Deliberately a **flat list, not a tree**: the hierarchy a basemesh sits in
  is real (a subrig can hang off a clothes item rather than off the character), but every consumer
  of this field wants "what belongs with this character", and nesting would make the common case
  pay for the rare one. A caller that needs the structure can walk it by calling this tool again
  on a returned name.
- `other_related_objects`: related objects in the same neighbourhood that carry *no* MPFB type,
  each additionally flagged with `rigify_role`: `"generated_rig"`, `"metarig"` or `null`. MPFB
  does not tag Rigify's generated rig with an `object_type`, so a character driven by Rigify would
  otherwise report no rig at all while one is plainly attached. These are kept in a separate list
  from `related_objects` so the distinction between *what MPFB claims* and *what we inferred from
  the object hierarchy* stays visible.
- `message`: one human-readable sentence, as `mpfb_get_status` does — most valuable in the
  `found: false` and "exists but not in this scene" cases, where the next step is not obvious.

## Non-functional requirements

- **Read-only / side-effect-free.** Both tools only read custom properties and walk the object
  hierarchy. `ObjectService` also carries destructive methods (`delete_object`,
  `extract_vertex_group_to_new_object`) and selection-mutating ones (`activate_blender_object`,
  `select_object`, `deselect_and_deactivate_all`) — the payloads must touch none of them. In
  particular, resist any temptation to select or activate an object in order to inspect it; that
  changes state the user can see.
- **Cheap enough to call before anything else.** These are the tools an agent runs to orient
  itself, so they should be a scene iteration and property reads — nothing that touches geometry,
  loads files, or scans asset directories. This is why per-object output stays at name and the two
  types.
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
  [`codegen/payloads/`](../../src/mpfbmcp/codegen/payloads) and two `register()` calls in
  `__init__.py` — the shape [architecture.md](../../specifications/architecture.md#code-generation-layout)
  requires. No shared code-generation module should need editing; if it does, that is a signal
  worth recording.
- **Use the raising bootstrap** (`bootstrap="raising"`). Unlike `mpfb_get_status`, these tools
  cannot answer anything meaningful without `ObjectService`, and its `RuntimeError` already points
  the caller at `mpfb_get_status`.
- `ObjectService` is in the `SERVICES` dict, so it resolves through the standard bootstrap with no
  special handling.
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
- **Pitfall — the Rigify pairing helpers scan the whole file.**
  `find_rigify_metarig_by_rig()` and `find_rigify_rig_by_metarig()` iterate `bpy.data.objects`, not
  the scene. If they are used to enrich `rigify_role`, an object outside the current scene can
  surface in a scene-scoped answer. Either restrict results to the neighbourhood walk above, or
  mark such an entry with the same `in_current_scene` flag the subject gets — do not let it in
  unlabelled.
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
  [Validate before crossing the socket](../../specifications/architecture.md#validate-before-crossing-the-socket):
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

## Affected specifications

- [vision.md](../../specifications/vision.md#target-tool-catalog) — the "Introspection (read-only)"
  list has no entry for object finding at all; it jumps from `mpfb_get_status` to
  `mpfb_get_human_summary`, which silently assumes the subject is already known. Add
  `mpfb_list_objects` and `mpfb_get_object_info`, mark them **Implemented** when this lands, and
  note that `mpfb_get_human_summary` and the modification tools take their subject from them.
- [architecture.md](../../specifications/architecture.md) — two candidate additions, both worth
  deciding on at implementation time rather than up front:
  - **How generated code addresses objects.** This effort establishes that tools name objects by
    Blender object name, scoped to the current scene, with "exists elsewhere in the file" as a
    distinct answer. Every later mutating tool will follow it, so it belongs in the standing spec
    rather than in one request.
  - **Reading private module-level constants from MPFB.** FR 001 did this once
    (`LOWEST_FUNCTIONAL_BLENDER_VERSION`); this effort does it again for the type vocabulary. A
    second instance makes it a pattern: allowed, via `sys.modules[Service.__module__]`, never via a
    fresh import, and always with a fallback because the names are private.

## Tests

Unit tests follow [tests/test_get_status.py](../../tests/test_get_status.py)'s two-layer approach,
which fits this effort better than `test_create_human.py`'s source-substring assertions, since
both payloads carry real branching:

- Tool-level, with `send_code` mocked: argument validation (empty/whitespace/non-string `name`,
  empty `object_type`), that an *omitted* `name` is accepted while an *empty* one is rejected,
  that `strict_json=True` is passed, and that the blender_mcp envelope comes back unchanged.
- Generated-code-level, `exec()`-ing the assembled source against a stubbed `bpy` and a stubbed
  `ObjectService` injected into `sys.modules`. The stub scene should include, at minimum: a
  basemesh with a skeleton and two clothes children; an untyped Rigify-looking armature in the
  same hierarchy; a typed object present in `bpy.data.objects` but absent from the scene; and a
  plain Blender cube. That covers self-exclusion from `related_objects`, the
  `related`/`other_related` split, `in_current_scene`, and the untyped-object branch. The stub
  `bpy.context.view_layer.objects.active` should be exercised both set and `None`, covering
  `resolved_from: "active_object"` and the no-active-object branch — the latter is the one that
  crashes on `None.name` if it is missed.
- A test that an unrecognized `object_type` yields `type_recognized: false` with an empty
  `objects` list, since that pairing is the requirement's whole point and is easy to regress into
  a bare empty list.

**This request must not be marked `Done` before a manual verification pass against a running
Blender.** FR 001 and FR 002 both landed with their verification outstanding, and the first live
run of `mpfb_get_status` afterwards failed outright on a `pathlib.Path` that no unit test could
have caught (see [References](#references)). The stubs above assert what we *believe* MPFB
returns; only a live run shows what it does. At minimum:

1. A scene with one MPFB human: `mpfb_list_objects()` unfiltered lists basemesh, skeleton and any
   assets; `object_type="Basemesh"` narrows to one.
2. `mpfb_get_object_info` on that basemesh: skeleton and clothes appear in `related_objects`, the
   basemesh itself does not, and nothing appears twice.
3. `mpfb_get_object_info` on a name that does not exist, and on an object outside the current
   scene — confirming `found: false` versus `found: true, in_current_scene: false`.
4. `mpfb_get_object_info` with no argument, having clicked the basemesh in the viewport: the same
   answer as calling it by name, with `resolved_from: "active_object"` and the resolved `name`.
   Then with everything deselected — `found: false`, `resolved_from: "active_object"`, and a
   message saying so. This is the check the unit tests can least stand in for, since it depends on
   whether the add-on's execution context sees the same active object the user does.
5. A Rigify-rigged character, confirming the generated rig lands in `other_related_objects` with a
   `rigify_role` rather than vanishing.
6. An empty scene, and a scene with only non-MPFB objects — both should answer, not fail.

## References

- `../../../mpfb2/src/mpfb/services/objectservice.py` and
  `../../../mpfb2/docs/services/objectservice.md` — the source of every capability above.
  The docs' "Object Type Constants" table is the human-readable version of `_ALL_TYPES`.
- `../../../mpfb2/src/mpfb/entities/objectproperties/` — where `object_type` actually lives, as a
  `BlenderConfigSet` with the full prefix `MPFB_GEN_`. Not needed if everything goes through
  `ObjectService`, but worth knowing when a value looks wrong.
- [FR 001](../done/001-mpfb-get-status/README.md) — the `sys.modules[Service.__module__]` constant
  read, the "absence is an answer, not an error" stance, and the `message` field convention all
  come from there.
- Commit `631989c` — `mpfb_get_status`'s first live run returned an error envelope because
  `LocationService.get_mpfb_root()` hands back a `pathlib.Path` despite being annotated `-> str`.
  Cited twice above: as the reason `strict_json` output needs checking against real MPFB, and as
  the reason this request insists on live verification.
