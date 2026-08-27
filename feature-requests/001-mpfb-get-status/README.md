# mpfb_get_status: MPFB presence, version, and configured paths

**Status:** Accepted

Every tool in the [target catalog](../../specifications/vision.md#target-tool-catalog) beyond
`mpfb_create_human` assumes MPFB is present in the connected Blender instance, at a compatible
version, and pointed at the asset roots the caller expects — but nothing today lets a caller
(human or agent) check any of that before acting. `mpfb_create_human` already fails with a bare
`{"status": "error", ...}` if MPFB isn't loaded, and an agent troubleshooting a failure has no
lower-level tool to ask "is MPFB even there?" before re-trying or giving up.

This is the first "introspection (read-only)" tool from the target catalog, and a natural
starting point for the feature-request process: it establishes the pattern other read-only
tools (`mpfb_get_human_summary`, `mpfb_list_assets`) will follow, and it is itself the tool an
agent should reach for first when any other MPFB tool call fails unexpectedly.

## Goals

Primary: let a caller determine whether MPFB is loaded and usable in the connected Blender
instance — distinguishing "not there", "there but not initialized", and "ready" — and, when it
is, which version and where it is reading its data from (addon install location, configured
data/asset roots, installed asset packs).

Secondary: surface enough asset-pack and data-root detail that "MPFB can't find asset X" or
"why did `mpfb_create_human` fail" can usually be diagnosed from this one call, without a
separate round trip per path.

## Functional requirements

A new tool, `mpfb_get_status`, taking no arguments. It always returns `{"status": "ok", ...}`
from the blender_mcp envelope — including when MPFB is absent, disabled, or failed to
initialize — with a `result` shaped as follows.

### Resolution state

MPFB's module is found by scanning `sys.modules` (see
[architecture.md](../../specifications/architecture.md#resolving-mpfb-from-generated-code)),
but being *found* is not the same as being *usable*. `mpfb/__init__.py` declares
`MPFB_CONTEXTUAL_INFORMATION = None` at module level and only builds it inside `register()` —
with the `"SERVICES"` entry assigned on that function's very last line. `unregister()` never
resets it. Every result therefore carries a `state`:

| `state` | Meaning | Detected by |
|---------|---------|-------------|
| `"absent"` | No loaded module name ends in `mpfb`. MPFB is not installed, or was never imported. | empty candidate list |
| `"not_initialized"` | Module loaded, but `register()` did not complete: `MPFB_CONTEXTUAL_INFORMATION` is `None`, or is a dict with no `"SERVICES"` key. MPFB is installed but broken or half-registered. | the two checks above |
| `"ok"` | Module loaded and `MPFB_CONTEXTUAL_INFORMATION["SERVICES"]` is available. | — |

`"not_initialized"` is a first-class result, not an error. It is arguably the most valuable
thing this tool can report: it is where a user lands when MPFB fails to register (too old a
Blender, an exception inside `ClassManager.register_classes()`, a partially failed upgrade),
and from the caller's side today it is indistinguishable from a healthy install — every other
tool simply fails with a bare `{"status": "error"}`.

`result` also carries `message`: one short human-readable sentence naming the state and, where
applicable, the likely next step. This is what an agent can surface verbatim to a user.

### Always populated

- `state` — as above
- `message` — as above
- `candidate_modules`: **every** loaded module name ending in `mpfb`, in `sys.modules` order
  (empty when `absent`). Normally exactly one. The bootstrap resolves whichever comes *first*,
  which is arbitrary — so two or more entries mean MPFB is installed under two extension
  repositories (or a stale legacy addon lingers beside an extension install). That is itself a
  diagnosis, and explains erratic behavior from other MPFB tools, so all candidates are
  reported rather than only the winner.
- `package`: the resolved module's `__name__` (e.g. `"bl_ext.repo.mpfb"`), `null` when absent.
  Read off the module rather than from `MPFB_CONTEXTUAL_INFORMATION["__package__"]`: the values
  are identical once initialized, but the module attribute is also readable in the
  `not_initialized` state, where the dict may be `None`.
- `enabled`: whether `package` is a key in `bpy.context.preferences.addons` — MPFB's own
  `__init__.py` uses this idiom to find its preferences. Reported because `unregister()` leaves
  `MPFB_CONTEXTUAL_INFORMATION` fully populated in `sys.modules`, so an MPFB the user *disabled*
  still reports `state: "ok"`; `enabled: false` is the only thing that distinguishes it from a
  live install. `null` when absent.
- `blender`: `{"version": "5.1.0"}` from `bpy.app.version_string` — no MPFB dependency, so it is
  available in all three states.

### Populated when `state` is `"not_initialized"` or `"ok"`

Both read directly off the resolved module, needing no services:

- `version`: dotted version string built from MPFB's `VERSION` tuple (e.g. `"2.0.17"`)
- `build_info`: MPFB's `BUILD_INFO` (`"FROM_SOURCE"` for a source checkout, otherwise a build
  date string) — distinguishes a developer's source install from a packaged release

### Populated only when `state` is `"ok"`

- `is_source_dist`: `LocationService.is_source_dist()` — `true` if running from a source
  checkout (the `test/` dir exists next to the addon). Kept alongside `build_info` because the
  two can legitimately disagree (a build rewrites `BUILD_INFO` *and* drops `test/`, so a
  disagreement points at an unusual or partial install).
- `addon_installation_path`: absolute path to the addon's install directory
  (`LocationService.get_mpfb_root()`)
- `paths`: other configured/derived absolute paths, each with a `configured` flag since two of
  them (`second_root`, `mh_user_data`) are optional and often unset:
  - `mpfb_data` — bundled static assets shipped with the addon
  - `user_home`, `user_data`, `user_config`, `user_cache`, `log_dir` — MPFB's per-user
    directories
  - `second_root` — optional additional asset library (`null` path, `configured: false` if unset).
    **Scene-scoped, not global:** `get_second_root()` reads `second_root` off
    `bpy.context.scene` via `ASSET_SETTINGS_PROPERTIES` and only falls back to the preference.
    Its value therefore depends on the currently open `.blend` and changes when another file is
    loaded — so this field, and by extension the whole status result, must not be cached across
    scene loads.
  - `mh_user_data` — optional standalone-MakeHuman user data integration (`null` path,
    `configured: false` if unset/not autodiscovered)
- `asset_roots`: `AssetService.get_available_data_roots()` — the flat, deduplicated list of
  data roots MPFB will actually search (already filtered to directories that exist on disk).
  This is deliberately reported *alongside* `paths` rather than instead of it: `paths` shows
  what's *configured* (even if the directory doesn't exist), `asset_roots` shows what MPFB will
  *actually use*.
- `asset_packs`: `{"count": N, "names": [...], "system_assets_pack_installed": bool}` — from
  `AssetService.get_pack_names()` and `AssetService.system_assets_pack_is_installed()`. The
  system-assets flag is called out on its own because most other assets and default materials
  depend on that pack being present.
- `blender.platform`: `SystemService.deduce_platform()` (e.g. `"LINUX"`), merged into the
  `blender` object described above.
- `blender.meets_mpfb_minimum` / `blender.mpfb_minimum_version`:
  `SystemService.is_blender_version_at_least()` and the `LOWEST_FUNCTIONAL_BLENDER_VERSION`
  constant it defaults to. This tool should *answer* the "is this Blender new enough for this
  MPFB?" question rather than hand the caller two version strings to compare — MPFB already
  computes the verdict, and an incompatible Blender is a prime cause of the
  `not_initialized` state.
- `rigify_available`: `SystemService.check_for_rigify()` — whether Rigify is enabled and
  functional, relevant to any future `mpfb_add_rig` tool call requesting a `rigify.*` rig.

## Non-functional requirements

- **Read-only / side-effect-free.** Must not create objects, modify the scene, or write files.
  All information above is retrievable via read-only service calls; no `bpy.ops` mutation is
  needed.
- **Never raises on absence *or* partial initialization.** MPFB being missing, disabled, or
  stuck half-registered are all expected, everyday responses for this specific tool, not error
  conditions — each maps to a `state` value. Concretely, the generated code must not let
  `MPFB_CONTEXTUAL_INFORMATION` being `None` (`TypeError`) or lacking `"SERVICES"` (`KeyError`)
  escape, since those are exactly the states a user hits when MPFB is broken and most needs
  diagnosing. Other failure modes (Blender/blender_mcp unreachable, malformed response) still
  surface as blender_mcp's normal `ConnectionError` / `{"status": "error"}`, unchanged.
- **Not cacheable.** The result reflects the state of one Blender process at one moment, and
  parts of it (`second_root`, and anything derived from it) are scene-scoped and change when a
  different `.blend` is loaded. Callers should re-call rather than remember.
- **Fast.** No asset-list scanning beyond what `AssetService.get_available_data_roots()` and
  `get_pack_names()` already do cheaply (path-exists checks and cached pack metadata) — this
  tool is meant to be cheap enough to call proactively before every other MPFB tool call.

## Architecture

- New tool module `src/mpfbmcp/tools/get_status.py`, `register(mcp)`-based like
  `create_human.py`.
- `mpfb_codegen.py` needs a **second, non-raising bootstrap** alongside the existing
  `_MPFB_BOOTSTRAP` (which `raise RuntimeError(...)` on absence — correct for
  `mpfb_create_human`, wrong here). Factor the `sys.modules` scan itself out of
  `_MPFB_BOOTSTRAP` into a shared helper both bootstraps call, so the resolution logic isn't
  duplicated between "raise on absence" and "report a `state` on absence" variants. Two changes
  to that shared helper fall out of the requirements above:
  - It must return **all** matching module names, not the first match. The raising bootstrap
    keeps using the first (unchanged behavior); `mpfb_get_status` reports the full list as
    `candidate_modules`.
  - Resolution has to be split into "found a module" and "that module is initialized". The
    raising variant collapses both into its existing `RuntimeError`; the status variant maps
    them to `absent` / `not_initialized` / `ok`.

  This is the concrete follow-up [architecture.md](../../specifications/architecture.md#resolving-mpfb-from-generated-code)
  should fold back in once this lands (see Affected specifications below).
- **Pitfall — do not import MPFB submodules to work around a missing `SERVICES` dict.** When
  `state` is `not_initialized` it is tempting to reach the services directly (e.g.
  `importlib.import_module(package + ".services")`) to fill in more fields. Don't:
  `locationservice.py` ends with `LocationService = _LocationService()` followed by
  `LocationService.ensure_relevant_directories_exist()`, so importing it **creates directories
  on disk** — violating the read-only requirement, in the one state where MPFB is already
  broken. In `not_initialized`, report only what is readable off the module object itself
  (`VERSION`, `BUILD_INFO`, `__name__`) plus `bpy`-derived fields.
- `enabled` comes from `bpy.context.preferences.addons`, not from MPFB: check whether the
  resolved package name is a key in it, the same idiom `mpfb/__init__.py` uses to locate its own
  preferences.
- `LOWEST_FUNCTIONAL_BLENDER_VERSION` is a module-level constant in `systemservice.py`, not a
  member of `SystemService`, and is not in the `SERVICES` dict. Read it without a fresh import
  via `sys.modules[SystemService.__module__].LOWEST_FUNCTIONAL_BLENDER_VERSION` — the module is
  necessarily already imported if `SystemService` resolved.
- Field sources, all static/class methods — no instantiation needed:
  - `mpfb.VERSION`, `mpfb.BUILD_INFO`, `mpfb.__name__` — read directly off the resolved `mpfb`
    module, same as `_MPFB_BOOTSTRAP` already reads `MPFB_CONTEXTUAL_INFORMATION["SERVICES"]`,
    but without needing that dict to exist. Use `mpfb.__name__` for `package` rather than
    `MPFB_CONTEXTUAL_INFORMATION["__package__"]`: same value, one fewer precondition.
  - `LocationService.get_mpfb_root()`, `.get_mpfb_data()`, `.get_user_home()`,
    `.get_user_data()`, `.get_user_config()`, `.get_user_cache()`, `.get_log_dir()`,
    `.get_second_root()`, `.get_mh_user_data()`, `.is_source_dist()` — all in
    `mpfb2/src/mpfb/services/locationservice.py` (docs:
    `mpfb2/docs/services/locationservice.md`). `LocationService` is a module-level singleton,
    not a static class like the others — resolve it via the same `SERVICES` dict entry
    (`MPFB_CONTEXTUAL_INFORMATION["SERVICES"]["LocationService"]`).
  - `AssetService.get_available_data_roots()`, `.get_pack_names()`,
    `.system_assets_pack_is_installed()` — `mpfb2/src/mpfb/services/assetservice.py` (docs:
    `mpfb2/docs/services/assetservice.md`). `get_pack_names()` triggers a metadata rescan if not
    yet cached, so the first call after Blender starts may be slightly slower than subsequent
    ones — still fine for a status tool.
  - `SystemService.deduce_platform()`, `.check_for_rigify()` — static, cheap.
    `check_for_rigify()` logs warnings for each missing Rigify component when Rigify isn't
    available; that's expected and not an error for this tool.
  - `bpy.app.version_string` — Blender's own version, no MPFB dependency.
- Response envelope: same as `mpfb_create_human` — return blender_mcp's `send_code(...)` result
  as-is (`strict_json=True`; every field above is plain JSON-safe data).

## Affected specifications

- [architecture.md](../../specifications/architecture.md#resolving-mpfb-from-generated-code) —
  currently documents only the raising bootstrap ("Every tool that needs an MPFB service class
  should reuse this same bootstrap"), and describes resolution as a single step. Once this lands,
  fold in:
  - the non-raising variant and when each should be used (raising: the tool cannot proceed
    without MPFB anyway; non-raising: the tool's job is partly *to answer* whether MPFB is
    present);
  - that resolution is **two** steps, not one — finding a module whose name ends in `mpfb`, and
    that module having completed `register()` — because `MPFB_CONTEXTUAL_INFORMATION` is `None`
    until then, gets its `"SERVICES"` entry only on `register()`'s last line, and is never reset
    by `unregister()`;
  - that the scan can match more than one module, and which one the raising bootstrap picks is
    arbitrary;
  - the standing rule that generated code must resolve services **only** through the
    `SERVICES` dict and never by importing MPFB submodules directly, since several of them have
    import-time side effects (`locationservice.py` creates directories).
- [vision.md](../../specifications/vision.md#target-tool-catalog) — move `mpfb_get_status` from
  the planned list to "Implemented", matching how `mpfb_create_human` is marked today.

## Tests

Unit tests (stdlib `unittest`, mocking `send_code` — see
[architecture.md](../../specifications/architecture.md#no-direct-dependency-on-mpfb-or-blender_mcp))
can cover:

- The generated code compiles (`compile(code, "<generated>", "exec")`). Note this is a *new*
  pattern — `tests/test_create_human.py` asserts on substrings of the generated source, not on
  compilability — and is worth adding here because this tool's generated code carries real
  branching logic rather than a single service call.
- The generated code contains the three-state classification: an explicit `None` check on
  `MPFB_CONTEXTUAL_INFORMATION` and a membership check for `"SERVICES"`, so a regression that
  reintroduces the raising behavior is caught locally.
- `mpfb_get_status()` takes no arguments and passes `strict_json=True`.
- The tool passes blender_mcp's response through unchanged (it does no local
  interpretation/branching on the result — the graceful-absence behavior lives in the generated
  code, not in Python on the mpfb-mcp side).

What unit tests **cannot** cover (per
[architecture.md](../../specifications/architecture.md#no-direct-dependency-on-mpfb-or-blender_mcp)):
whether the generated code actually produces the documented field values. This needs a manual
verification pass against a real Blender + MPFB + blender_mcp instance before marking this
`Done`, the same kind of end-to-end check already done for `mpfb_create_human`. At minimum:

1. **MPFB enabled** — `state: "ok"`, `enabled: true`, every field populated, and every non-null
   path an existing absolute path.
2. **MPFB never enabled in this session** — `state: "absent"`, empty `candidate_modules`, and a
   populated `blender.version` (proving the `bpy`-only fields survive the absent branch).
3. **MPFB enabled, then disabled from Blender's preferences** — the stale-state case. Expect
   `enabled: false`; note in the verification whether `state` comes back `"ok"` (module and
   dict still in `sys.modules`, as the code suggests) so the documented meaning of `enabled`
   matches reality.

State `"not_initialized"` cannot easily be produced on demand. It can be approximated by
setting `MPFB_CONTEXTUAL_INFORMATION = None` on the resolved module from a Blender Python
console before calling the tool; do that at least once to confirm the branch reports rather
than raises.

## References

- `mpfb2/docs/services/locationservice.md`, `mpfb2/docs/services/assetservice.md`,
  `mpfb2/docs/services/systemservice.md` — source docs for every field above.
- [specifications/vision.md](../../specifications/vision.md#target-tool-catalog) — originating
  entry: "`mpfb_get_status` — MPFB present? version? data roots configured? asset packs
  installed?".
