# Pivot to an MPFB-specific bridge add-on

**Status:** Proposed

Piggybacking on someone else's MCP add-on and shipping the Blender-side logic as generated
Python on every call has proved cumbersome and inefficient. The install path is eight steps,
three of them developer-grade, for an audience of hobbyists; every call is arbitrary code
execution by construction; ahujasid's opt-in safe mode rejects every program this project
sends; and the wire cost — ~250 ms per 4 KB, ~1 s from idle — is permanent, with the session
source cache, fragment hashing and re-send-once recovery existing only to manage it.

Two analyses were written on 2026-09-10. [PIVOT_ANALYSIS.md](PIVOT_ANALYSIS.md) asked whether
the tools should be upstreamed into ahujasid/blender-mcp and concluded no — a GPL/MIT licence
conflict, a telemetry regime, and a release cadence that would stop being MakeHuman's.
[PIVOT_INTO_MPFB.md](PIVOT_INTO_MPFB.md) then asked where the Blender-side logic should live
instead, and recommended **option 3b: a separate companion add-on with its own closed-vocabulary
command socket**, with the current path kept alive during the transition and retired only when
the bridge is better. Merging into MPFB itself was recommended against — it buys one install
click and pays with MPFB's extension listing, review cycle, blast radius and reversibility.

This request adopts that recommendation and **plans the pivot; it does not perform it.** It
delivers a proof-of-concept add-on that proves the one genuinely unproven part (the transport),
answers the one open question that is an engineering question, rewrites the two specifications
that state the old principle outright, and lays out the child requests that do the actual work.
No tool is migrated here and `src/mpfbmcp/` is not touched.

## Goals

**Primary.** Turn a recommendation into a decided, documented direction that a child request can
begin from: a working transport, rewritten specifications, and an ordered sequence of efforts.

**Secondary.** Retire the guesswork. Three things are currently assumed rather than known — that
a socket server inside Blender with main-thread dispatch is unremarkable to write, that the
command vocabulary can actually be closed, and that a second Blender extension is affordable.
The first two are settled here; the third is recorded honestly as a cost, because it is not an
engineering question.

**Secondary.** Make the bridge legible to the people most likely to have to read it. It is
MPFB-adjacent Blender code living in a repository whose conventions grew up around an MCP server
that never touches `bpy`; a MakeHuman contributor opening `bridge/` should recognise the linting,
the typing setup and the test harness as their own, even though the package around it is not.

**Explicitly not a goal.** Deciding whether the bridge is ever folded into MPFB. That door is
left open and is revisited only if the bridge proves itself in use; the reverse move is not
available, which is the entire reason for starting outside.

## Functional requirements

1. **A proof-of-concept bridge add-on exists and runs.** It is a real Blender extension with a
   `blender_manifest.toml`, installable and enablable in Blender 4.2+, that starts and stops a
   TCP command server from its preferences panel.
2. **It answers exactly one command end-to-end**, `get_status`, over its own socket, from a
   throwaway client script — reporting whether MPFB is present, initialized and reachable, in
   the same three-state vocabulary `mpfb_get_status` already uses. One command is enough,
   because what is being proved is the transport and the dispatch, not the answer.
3. **The command vocabulary is closed in the PoC**, not merely intended to be: the server
   dispatches on a name from a fixed table and `exec()`s nothing a caller sent. A PoC that
   evaluates caller-supplied code proves the wrong design works.
4. **The closed-vocabulary question is answered for the hardest case.**
   `mpfb_set_asset_material` has no MPFB service function behind it — it reimplements a UI
   operator from services. The request must state, with the code in front of it, whether its
   behaviour survives as a named command with validated parameters, since it is the tool most
   likely to need open-ended access. If it does not, that is a finding, and the recommendation
   is revisited rather than worked around.
5. **[vision.md](../../specifications/vision.md) and
   [architecture.md](../../specifications/architecture.md) are rewritten** to describe the bridge
   as the intended end state. `vision.md`'s "Approach: piggyback, don't fork" section and
   `architecture.md`'s code-generation, wire-cost and second-backend material state the old
   principle outright and cannot survive the decision. The specifications are visionary by
   charter, so they describe the bridge before it exists; they must also say plainly that the
   generated-code path is what runs today and is being retired, so a reader is not misled about
   which machine they are standing in front of.
6. **The child requests are laid out in [NEXT_STEPS.md](../NEXT_STEPS.md)**, in the order below,
   each stated well enough that it could be started without re-deriving this analysis. Numbers
   are assigned when a request is started, not here.
7. **Nothing that works today stops working.** `src/mpfbmcp/` is unmodified, all 799 tests pass
   unchanged, and [verification/](../../verification/)'s smoke run is untouched. This request
   adds a directory and rewrites prose.
8. **Two NEXT_STEPS entries are re-pointed rather than left to rot.**
   [Second backend: the community "blender mcp"](../NEXT_STEPS.md#second-backend-the-community-blender-mcp)
   is superseded — the bridge removes the dependency the adapter existed to abstract — and
   [Handle the 4 KB chunked read](../NEXT_STEPS.md#handle-the-4-kb-chunked-read-against-blender_mcp)
   stops being this project's problem once no program crosses the socket, though filing it
   upstream remains worth doing for everyone else.
9. **The bridge's code style and tooling are aligned with MPFB's, and the alignment is written
   down.** The PoC lands with the configuration files that enforce it — a `.pylintrc` and a
   pyright/`fake-bpy-module` setup derived from MPFB's — and the request records, per convention,
   what was adopted, what was not, and why. An exact match is explicitly not required; the bar is
   that someone who works on MPFB can read `bridge/` without relearning how a file is laid out.
   The decisions are in [Architecture](#architecture) below and are what the child requests
   inherit.

### Out of scope, deliberately

- Migrating any tool. That is the child requests' work.
- Any change to MPFB. The bridge reaches MPFB through the documented `sys.modules` scan and the
  exported `MPFB_CONTEXTUAL_INFORMATION`, which is the supported entry point, used by MPFB's own
  test suite and by this project's `bootstrap.py` already. If the pivot turns out to need an MPFB
  change, that is a separate request against a separate repository and a separate release.
- Publishing the bridge on extensions.blender.org, and the documentation page on
  makehumancommunity.org that would accompany it. Both belong to the stage where the bridge is
  worth installing.
- The three questions in [PIVOT_INTO_MPFB.md](PIVOT_INTO_MPFB.md#what-to-establish-before-committing)
  that are not engineering questions: what extension review makes of a listening socket, what a
  second extension really costs to maintain, and what MPFB users actually want. They are recorded
  as open, and the answers can change the plan; none of them blocks the PoC.

## Non-functional requirements

- **Reversibility.** Everything this request produces can be deleted without affecting a working
  system. That is the property the whole staged path is built on and it should survive the first
  stage intact.
- **Security posture is the bridge's main argument and must be real.** The server binds
  `127.0.0.1` only, is off until started from preferences, and executes no caller-supplied code.
  The honest limitation — while it is running, any local process can drive it, exactly as with
  both existing add-ons — is documented rather than papered over. A shared-secret token was
  considered and rejected for now: it adds a configuration step to every client setup, which is
  the friction this pivot exists to remove. The closed vocabulary is the defence, and it is one
  a sceptical user can verify by reading a list.
- **Install friction is the metric the pivot is judged by**, not lines of code. The target is
  MPFB, the bridge, and an MCP client config — with the bridge's socket started from a panel,
  not an environment variable.
- **Honesty about what the PoC does not prove.** It proves transport, dispatch and MPFB
  resolution. It proves nothing about twenty-one commands' behaviour, about performance under
  real payloads, or about whether the migration is affordable. The request says so.
- **Readability of the bridge's code is held to this repository's standard**, since it will be
  read by reviewers at an extension platform and by users deciding whether to trust it — which
  is a stronger reason than the one that already applies here.
- **Familiarity, specifically to MPFB's developers.** Readability and familiarity are not the
  same property: code can be perfectly clear and still feel foreign, and foreign is what stops a
  contributor from touching it. The bridge is the piece of this project most likely to attract a
  patch from someone who has worked on MPFB and never on an MCP server, and the pool of such
  people is small enough that losing one matters. The test is subjective and stated as such — a
  person familiar with MPFB should feel at home — but the tooling that produces it is not, and
  that part is checkable.

## Architecture

**Where it lives.** A new top-level subdirectory of this repository, `bridge/`, holding the
extension as `bridge/mpfb_bridge/` with its own `blender_manifest.toml`. It is *not* part of the
pip package: `pyproject.toml` packages `src/mpfbmcp` and must keep doing so, so the bridge needs
neither a package-data glob nor a `namespaces` setting. The PoC **is** that subdirectory's first
commit rather than a throwaway in this request's own subdir — there is nothing to be gained by
writing the transport twice, and a reference implementation buried in `done/` is one nobody
opens. The request's subdir keeps the analysis documents and the check script that drove the PoC.

**Identity.** `id = "mpfb_bridge"`, `name = "MPFB Bridge"`, `license = ["SPDX:GPL-3.0-or-later"]`,
`blender_version_min` matching MPFB's `4.2.0`. The `[permissions]` block needs a `network` string;
blender lab's add-on already declares `network = "Runs a local TCP socket server for MCP client
communication"` and survived review with it, which is a usable precedent. MPFB's own manifest is
untouched — that is the point of the whole packaging choice.

**Port.** Both existing add-ons default to 9876, so the bridge must not. Propose 9877, settable
in preferences, with the server off by default.

**Transport, and what to copy.** `../blender_mcp/addon/blender_mcp_addon/mcp_to_blender_server.py`
(615 lines) is the reference: a non-blocking listening socket accepted and drained from a
`bpy.app.timers` callback, so every command runs on Blender's main thread and `bpy` is never
touched from elsewhere. Copy the model; **do not copy the one 4096-byte `recv()` per tick**
(`_RECV_BUFFER_SIZE`, one chunk per callback) — that is the origin of the tax this pivot removes,
and with parameter-sized requests instead of programs the bridge should drain the socket within a
tick. The known traps are in
[PIVOT_INTO_MPFB.md](PIVOT_INTO_MPFB.md#option-3--a-separate-companion-add-on): main-thread-only
`bpy`, timer dispatch, and multi-byte UTF-8 splitting across `recv()` boundaries.

**Vocabulary and validation.** One command per tool, roughly twenty-one of them — the unit stays
the *intent*, as [vision.md](../../specifications/vision.md#what-makes-something-a-tool) requires,
so batching (`mpfb_set_targets`) and multi-step reasoning (the refit blocker) stay inside one
command rather than becoming several round trips. **Both ends validate, deliberately.** The
server keeps its local shape checks so a malformed call fails before the wire with a message
naming the argument — the bool-strictness and range rules in
[CLAUDE.md](../../CLAUDE.md#what-is-validated-on-this-side-of-the-socket) exist because each
alternative fails silently — and the bridge validates again because a listening socket is
reachable by anything on the machine, not only by mpfb-mcp. The duplication is the cost of the
socket being public, and should be stated as such wherever it is documented, or it will be
mistaken for an oversight and removed.

**Versioning.** The bridge reports a protocol version in its `get_status` answer and the server
checks it. The compatibility matrix (MPFB × bridge × server) is a real cost of this packaging
choice and the only cheap defence is a handshake that exists from the first command. Nothing in
the system carries a version today.

**Code style and tooling.** Two sets of conventions meet in `bridge/`. This repository's are
documented in [CLAUDE.md](../../CLAUDE.md#code-conventions-in-this-repo) and grew up around a
package that never imports `bpy`; MPFB's are in `../mpfb2/.pylintrc`, `../mpfb2/pyrightconfig.json`
and `../mpfb2/CLAUDE.md`, and grew up around 40k lines of add-on code. **Where they disagree about
add-on code, MPFB's win** — the bridge is a Blender extension before it is part of this package,
and its likeliest outside contributor is a MakeHuman developer.

| Aspect | MPFB today | mpfb-mcp today | The bridge |
|---|---|---|---|
| Linting | `.pylintrc`, 160 columns, 4-space indent, `bpy`/`mathutils`/`addon_utils` both C-extension-allowed and in `ignored-modules` | nothing configured | MPFB's `.pylintrc`, copied and scoped to `bridge/` |
| Static typing | pyright, `typeCheckingMode = "basic"`, `fake-bpy-module` pinned in `requirements-dev.txt`, with the standing rule that dev dependencies never reach `blender_manifest.toml` or a runtime import | nothing configured | the same, wholesale — the bridge is `bpy` code and the recipe already exists and is documented |
| Test harness | pytest **inside headless Blender**, `<name>_test.py`, alphabetically ordered directories to force order, bare `assert` with a message, a docstring naming the function under test, coverage started before the add-on loads | stdlib `unittest`, `tests/test_<name>.py`, `TestCase` classes, no Blender anywhere | MPFB's, for `bridge/` only — see below |
| `from __future__ import annotations` | nowhere; Blender's Python is new enough to write `str \| None` directly | every module | dropped in `bridge/`, matching MPFB |
| `__all__` | present in 91 modules | every module | kept; the two agree already |
| String formatting | `.format()` predominant, a few f-strings | `.format()` throughout | `.format()`; the two agree already |
| Line length | 160 | prose wraps at 99, code reaches 173 | 160 |
| Logging | `_LOG = LogService.get_logger("services.objectservice")` at module top | `observability.get_logger` | the same shape and naming, its own logger — see below |
| Blender class registration | `ClassManager.add_class()` during import, registered from `register()`; **nothing imported at module level in `__init__.py` outside `register()`** | not applicable | the import rule is followed exactly; a `ClassManager` of our own is overkill for a handful of classes |
| Operator `bl_idname` | every operator starts `mpfb.` | not applicable | **`mpfb_bridge.`**, never `mpfb.` — that namespace is MPFB's, and a collision between two installed extensions fails silently |
| Trailing whitespace | stripped by `fixfiles.bash` | not enforced | mirrored |
| SPDX headers | essentially absent from `src/`, licence stated in `LICENSE.CODE.md` and the manifest | on all 31 test modules | manifest and a `LICENSE` file; no per-file headers in `bridge/`, matching MPFB |

Three of these need more than a table row.

**Two test harnesses in one repository, deliberately.** This is the sharpest divergence and also
the one alignment that pays for itself immediately: the bridge's tests need a real Blender, which
is precisely what MPFB's harness provides and what `tests/` structurally cannot. So `bridge/`
gets MPFB's pytest-in-headless-Blender arrangement and `tests/` keeps stdlib `unittest`, split at
the directory boundary and explained wherever either is documented, or the split will read as
drift. **One hard constraint falls out of it:** `python3 -m unittest discover -s tests` must keep
discovering exactly what it discovers today. Bridge tests import `bpy` and would fail at import,
not at assertion — so they must live under `bridge/`, never under `tests/`, and the command in
[CLAUDE.md](../../CLAUDE.md#commands) must keep working untouched on a machine with no Blender.

**Logging cannot go through MPFB's `LogService`.** The bridge's first command answers whether
MPFB is present at all, so it cannot depend on MPFB's logger to report that MPFB is missing. It
keeps a module-level `_LOG` in MPFB's shape and with MPFB's dotted naming, backed by a logger of
its own. This is the clearest case of "as far as possible": the idiom is copied, the dependency
is not.

**One MPFB habit not to copy.** MPFB writes `import bpy, os, json, random, gzip` on one line, and
its `.pylintrc` disables `multiple-imports` so the checker permits it. Adopt the configuration —
a familiar-looking config is part of the point — but write one import per line anyway. The check
is disabled, not required, and this is the level of divergence "not an exact match" is meant to
cover.

**What the server side becomes**, for the child requests to build on: the bridge is a *backend*
behind the same seam
[architecture.md](../../specifications/architecture.md#supporting-a-second-backend) already
describes for the community add-on — below `send_code()`, invisible to tools. That seam was
designed for a different second backend and is being spent on this one instead; a tool sends a
command and arguments rather than a program, and `codegen/` is bypassed for a migrated tool and
deleted when the last one is. Observability keeps its attachment point, but records a command and
its parameters rather than a program.

**The proposed sequence of child requests**, each landing with both paths still working:

1. **Bridge transport and skeleton** — the PoC grown into a real add-on: preferences, start/stop,
   error envelope, protocol version, and the command table with `get_status` in it.
2. **The server-side backend seam** — mpfb-mcp learns to talk to the bridge, with explicit
   configuration and no autodetection (both existing add-ons answer on 9876, and no single probe
   distinguishes them). One tool migrated, both paths runnable side by side on a real Blender for
   comparison.
3. **Introspection and catalogues migrated**, then **creation and modification migrated** — in
   batches by capability area, because a catalogue and the tool acting on it are designed as a
   pair and should move together.
4. **Retire the generated-code path** — delete `codegen/`, the session source cache and the
   shared fragments; fold what they taught into the specifications; drop the blender_mcp
   dependency from the install instructions.
5. **Publish and document** — extension platform listing, a page on makehumancommunity.org
   stating plainly that it is local, optional, and uploads nothing.

**The pitfall to name up front:** stage 3 is where the 14.2k lines of tests are decided. Payload
logic that becomes add-on code stops being "source `exec()`'d against stub Blender and stub MPFB"
and becomes ordinary Python in a Blender add-on, testable against a real install. That is an
improvement and a large rewrite at the same time, and it is the part of the pivot most likely to
be under-estimated. [testing.md](../../specifications/testing.md) is rewritten by the request
that first migrates a tool, not by this one — but a plan that does not admit the cost now will
meet it anyway.

## Affected specifications

Rewritten by **this** request, because both state the superseded principle outright:

- [specifications/vision.md](../../specifications/vision.md) — "Approach: piggyback, don't fork"
  is reversed; "Resolved: which blender mcp? Both" is superseded, since supporting either
  third-party add-on stops being a goal once neither is in the path.
- [specifications/architecture.md](../../specifications/architecture.md) — "What a call costs is
  the size of its program", "Supporting a second backend", "Resolving MPFB from generated code"
  and everything under it describe a machine being replaced. "No direct dependency on MPFB or
  blender_mcp" and "mpfb-mcp opens no network connection except the one to the add-on" survive in
  substance and change in detail.

Rewritten **later**, by the child request that invalidates each — listed here so the debt is
visible from the start:

- [specifications/testing.md](../../specifications/testing.md) — by the first tool migration. It
  also has to absorb the two-harness split this request introduces (stdlib `unittest` under
  `tests/`, MPFB's pytest-in-headless-Blender under `bridge/`), and that is deliberately *not*
  written here: with one trivial test in the bridge, anything said about how the bridge is tested
  would be a prediction. The constraint that matters now — `unittest discover -s tests` keeps
  working on a machine with no Blender — is a requirement of this request rather than a
  specification.
- [specifications/observability.md](../../specifications/observability.md) — by the backend seam:
  the record's unit stops being a program.
- [specifications/responses.md](../../specifications/responses.md) and
  [specifications/tool-interface.md](../../specifications/tool-interface.md) — by the backend
  seam: "returns blender_mcp's envelope as-is" needs a new referent.
- [specifications/mpfb-integration.md](../../specifications/mpfb-integration.md) — survives
  almost entirely. What MPFB does wrong, and what to do about it, does not depend on how the call
  arrives.

## Tests

**The PoC cannot be verified without a real Blender**, and that is the whole point of it: it
exists to prove socket, timer dispatch and MPFB resolution inside a running process, none of
which a stub can establish. The check is a script in this request's subdir — a client that
connects to the bridge, issues `get_status` against a Blender with MPFB enabled and against one
without, and asserts the three-state classification and the protocol version — run during the
effort and moved into `done/` with it.

**No smoke item is added** to [verification/](../../verification/). That directory has one item
per registered MCP tool and this request registers none; `tests/test_verification_smoke.py`
enforces exactly that correspondence and must keep passing untouched.

**No unit tests change.** If any test under `tests/` needs editing, this request has exceeded its
scope — requirement 7 says `src/mpfbmcp/` is not touched, and the suite tests that package.

**The bridge's harness is proved, not populated.** Its real suite arrives with its real code in
child request 1, but the arrangement MPFB uses — pytest installed into Blender's bundled Python,
tests run headless against a source checkout, coverage started before the add-on loads — has
enough moving parts that discovering it does not work here would be worse later than now. So the
PoC lands with the harness wired up and **one** trivial test in it, which is also what
demonstrates requirement 9's claim that a MakeHuman developer would recognise the setup. What it
must not do is disturb the existing command: `python3 -m unittest discover -s tests` still has to
find exactly the tests it finds today, on a machine with no Blender installed.

## References

- [PIVOT_ANALYSIS.md](PIVOT_ANALYSIS.md) — why not to upstream into ahujasid/blender-mcp.
- [PIVOT_INTO_MPFB.md](PIVOT_INTO_MPFB.md) — the three options, the community question, and the
  recommendation this request adopts. Its "What to establish before committing" list is the
  source of requirement 4 and of the out-of-scope items.
- `../blender_mcp/addon/blender_mcp_addon/mcp_to_blender_server.py` — the transport model to
  copy, and `_RECV_BUFFER_SIZE` the thing not to.
- `../blender_mcp/addon/blender_mcp_addon/blender_manifest.toml` — the `network` permission
  string that has already passed review for a listening socket.
- `../mpfb2/src/mpfb/blender_manifest.toml` — MPFB's own manifest, `id = "mpfb"`, version 2.0.17,
  `blender_version_min = "4.2.0"`; untouched by this pivot.
- `../mpfb2/src/mpfb/__init__.py` — `MPFB_CONTEXTUAL_INFORMATION` and the documented
  `sys.modules` scan, the supported way for a companion add-on to reach MPFB.

The style and tooling to align with, all in `../mpfb2`:

- `.pylintrc` — 160 columns, the C-extension allow list, and the disabled checks (including
  `multiple-imports`, which the bridge declines to use even though it is permitted).
- `pyrightconfig.json` and `requirements-dev.txt` — `typeCheckingMode = "basic"`,
  `fake-bpy-module` pinned to a build matching the supported Blender, and the rule written at the
  top of that file: never add these to `blender_manifest.toml`, never import them at runtime.
- `docs/type-checking.md` — why that setup exists and how it is used.
- `test/README.md`, `test/execute_tests_headless.bash` and `test/run_to_install_pytest.py` — the
  harness the bridge adopts, including the prerequisite that the add-on must resolve to a source
  checkout and that pytest is installed into Blender's own Python.
- `test/tests/bbb_services/objectservice_test.py` — a representative test in MPFB's style: module
  functions, a docstring naming the function under test, bare `assert` with a message.
- `src/mpfb/services/objectservice.py` — a representative module: `_LOG` at the top, a class
  docstring listing responsibilities, `str | None` without `from __future__`.
- `CLAUDE.md` — the registration flow, the `ClassManager`, the `bl_idname` prefix rule and the
  critical import rule for `__init__.py`.
- `fixfiles.bash` — trailing-whitespace hygiene.
