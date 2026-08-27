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

Primary: let a caller determine whether MPFB is loaded/enabled in the connected Blender
instance, and if so, which version, and where it is reading its data from (addon install
location, configured data/asset roots, installed asset packs).

Secondary: surface enough asset-pack and data-root detail that "MPFB can't find asset X" or
"why did `mpfb_create_human` fail" can usually be diagnosed from this one call, without a
separate round trip per path.

## Functional requirements

A new tool, `mpfb_get_status`, taking no arguments. It always returns `{"status": "ok", ...}`
from the blender_mcp envelope — including when MPFB is absent — with a `result` shaped as
follows.

**When MPFB is not present** (nothing in `sys.modules` resolves per
[architecture.md](../../specifications/architecture.md#resolving-mpfb-from-generated-code)):

```
{"mpfb_present": false}
```

No other keys are populated; a caller checks `mpfb_present` first.

**When MPFB is present:**

- `mpfb_present`: `true`
- `version`: dotted version string built from MPFB's `VERSION` tuple (e.g. `"2.0.17"`)
- `build_info`: MPFB's `BUILD_INFO` (`"FROM_SOURCE"` for a source checkout, otherwise a build
  date string) — distinguishes a developer's source install from a packaged release
- `is_source_dist`: `LocationService.is_source_dist()` — `true` if running from a source
  checkout (the `test/` dir exists next to the addon)
- `package`: the resolved module dotted name (e.g. `"bl_ext.repo.mpfb"`) — which extension
  repository MPFB was installed under; useful when a machine could plausibly have more than one
- `addon_installation_path`: absolute path to the addon's install directory
  (`LocationService.get_mpfb_root()`)
- `paths`: other configured/derived absolute paths, each with a `configured` flag since two of
  them (`second_root`, `mh_user_data`) are optional and often unset:
  - `mpfb_data` — bundled static assets shipped with the addon
  - `user_home`, `user_data`, `user_config`, `user_cache`, `log_dir` — MPFB's per-user
    directories
  - `second_root` — optional additional asset library (`null` path, `configured: false` if unset)
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
- `blender`: `{"version": "5.1.0", "platform": "LINUX"}` — from `bpy.app.version_string` and
  `SystemService.deduce_platform()`. Not MPFB-specific, but relevant context for the same
  "why did this fail" triage this tool exists for (e.g. an MPFB version requiring a newer
  Blender than is actually running).
- `rigify_available`: `SystemService.check_for_rigify()` — whether Rigify is enabled and
  functional, relevant to any future `mpfb_add_rig` tool call requesting a `rigify.*` rig.

## Non-functional requirements

- **Read-only / side-effect-free.** Must not create objects, modify the scene, or write files.
  All information above is retrievable via read-only service calls; no `bpy.ops` mutation is
  needed.
- **Never raises on absence.** As above — MPFB not being installed/enabled is an expected,
  everyday response for this specific tool, not an error condition. Other failure modes
  (Blender/blender_mcp unreachable, malformed response) still surface as blender_mcp's normal
  `ConnectionError` / `{"status": "error"}`, unchanged.
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
  duplicated between "raise on absence" and "report `mpfb_present: false` on absence" variants.
  This is the concrete follow-up [architecture.md](../../specifications/architecture.md#resolving-mpfb-from-generated-code)
  should fold back in once this lands (see Affected specifications below).
- Field sources, all static/class methods — no instantiation needed:
  - `mpfb.VERSION`, `mpfb.BUILD_INFO`, `mpfb.MPFB_CONTEXTUAL_INFORMATION["__package__"]` — read
    directly off the resolved `mpfb` module, same as `_MPFB_BOOTSTRAP` already reads
    `MPFB_CONTEXTUAL_INFORMATION["SERVICES"]`.
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
  should reuse this same bootstrap"). Once this lands, fold in the non-raising variant and when
  each should be used (raising: the tool cannot proceed without MPFB anyway; non-raising: the
  tool's job is partly *to answer* whether MPFB is present).
- [vision.md](../../specifications/vision.md#target-tool-catalog) — move `mpfb_get_status` from
  the planned list to "Implemented", matching how `mpfb_create_human` is marked today.

## Tests

Unit tests (stdlib `unittest`, mocking `send_code` — see
[architecture.md](../../specifications/architecture.md#no-direct-dependency-on-mpfb-or-blender_mcp))
can cover:

- The generated code for both the "present" and "absent" branches compiles (`compile(code, ...,
  "exec")`), mirroring `tests/test_create_human.py`'s codegen check.
- `mpfb_get_status()` takes no arguments and passes `strict_json=True`.
- The tool passes blender_mcp's response through unchanged (it does no local
  interpretation/branching on the result — the graceful-absence behavior lives in the generated
  code, not in Python on the mpfb-mcp side).

What unit tests **cannot** cover (per
[architecture.md](../../specifications/architecture.md#no-direct-dependency-on-mpfb-or-blender_mcp)):
whether the generated code actually produces the documented field values. This needs a manual
verification pass against a real Blender + MPFB + blender_mcp instance before marking this
`Done` — at minimum once with MPFB enabled (checking every field is populated and paths are
real, existing absolute paths) and once with MPFB disabled (checking the graceful
`{"mpfb_present": false}` shape), the same kind of end-to-end check already done for
`mpfb_create_human`.

## References

- `mpfb2/docs/services/locationservice.md`, `mpfb2/docs/services/assetservice.md`,
  `mpfb2/docs/services/systemservice.md` — source docs for every field above.
- [specifications/vision.md](../../specifications/vision.md#target-tool-catalog) — originating
  entry: "`mpfb_get_status` — MPFB present? version? data roots configured? asset packs
  installed?".
