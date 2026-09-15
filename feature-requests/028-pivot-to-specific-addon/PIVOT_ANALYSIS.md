# Pivot analysis: upstreaming MPFB tools into the community "blender mcp"

**Status:** Analysis only. Nothing here is decided, and nothing in the repository is changed by
it. Written 2026-09-10 against the checkouts of `../blender_mcp`, `../ahujasid-blender-mcp` and
`../mpfb2` as they stood on that date.

The question: instead of building mpfb-mcp as a separate MCP server that piggy-backs on a Blender
MCP add-on, should the MPFB tools be **submitted upstream to
[ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp)** — becoming part of that
project's server and add-on, in that project's style, with most of what is now a client-side
payload moved into the Blender-side add-on instead?

## Summary

**Do not pivot to a full upstream merge.** The three things that make the pivot attractive — the
larger user base, the disappearance of the code-generation layer, and the wire cost of shipping
programs — are real, but two of the three are obtainable *without* upstreaming, and the merge
carries four costs that are hard to reverse: a licence conflict between GPL-3.0 MPFB-derived code
and an MIT project, a telemetry regime that would forward character parameters and viewport
screenshots under terms permitting model training and dataset release, a release cadence for MPFB
integration that would no longer be MakeHuman's to set, and the loss of the specification and
review discipline this repository has built.

The strongest option on the table is a different one, and it is available immediately:

> **Move the Blender-side logic into MPFB itself** (where it is GPL, where Joel controls the
> release cadence, and where `HumanService` and friends already live), keep mpfb-mcp as a thin
> client, and add the already-scoped **backend adapter** so it runs against either add-on. Then,
> if upstream interest exists, offer ahujasid a *small* bridge — one or two tools plus a status
> check — rather than twenty-two.

That gets the reach, gets the payloads out of the wire, and gives up none of the four things
above. What it does not get is presence in someone else's tool list, which is the one genuine
advantage of the merge and is worth revisiting separately.

## What the two projects actually are

Measured, not assumed:

| | mpfb-mcp | ahujasid/blender-mcp |
|---|---|---|
| Licence | GPL-3.0-or-later (SPDX headers on all 31 test modules; no `LICENSE` file yet — see gaps) | MIT |
| Size | 12.8k lines `src/`, 14.2k lines tests | 15.9k lines total, 1.6k lines tests |
| Tests | 800, stdlib `unittest`, payloads `exec()`'d against stub Blender + stub MPFB | ~9 pytest modules; add-on cannot be imported, so tests stub `bpy` or lift code with `ast` |
| Tools | 22, returning `dict`, each with `ToolAnnotations` | 28, returning `json.dumps(...)` strings, no annotations |
| Tool descriptions | 51.5 KB + 8.4 KB schemas, held to a ceiling by a test | 16.7 KB of docstrings, unbudgeted |
| Add-on | none of its own — sends assembled Python over the socket | `addon.py`, 4.2k lines, **duplicated** at `src/blender_mcp/bundled/addon.py`, kept in sync by hand |
| History | 55 commits, 2026-08-27 → 2026-09-10 | 199 commits since 2025-03; 135 by the maintainer, the rest across ~10 contributors |
| Process | 24 numbered feature requests, seven specifications, a live smoke run | No `CONTRIBUTING.md`, no `.github/`, no CI |
| Funding / posture | none | GitHub Sponsors, a product website, telemetry-backed dataset collection |

They are not the same kind of project. One is a specification-first proof of concept for one
domain; the other is a broad, popular, single-maintainer product with a data strategy.

## What the pivot would buy

**Reach, which is the whole point.** blender-mcp is the one most users already have installed
(PyPI downloads badge, Trendshift listing, an active Discord). Every MPFB tool shipped there is a
tool that needs no second install, no second add-on, no second port. mpfb-mcp today asks a user to
install blender lab's add-on *specifically*, which is the less common one — the friction is real
and is exactly what [vision.md](specifications/vision.md#resolved-which-blender-mcp-both) already
flags.

**The code-generation layer would mostly disappear.** `codegen/` (bootstrap, payload assembly,
shared fragments, `shared_loader.py`, `shared_cache.py`) exists only because the Blender-side code
has to be shipped as text on every call. Add-on-side handlers would be ordinary Python in an
ordinary module, importing nothing they cannot import, debugged with a real traceback and a real
`stderr` instead of a `result` dict and a captured stream. Roughly **7,750 lines** of payload and
fragment source stop being generated code and become just code.

**The wire cost model changes shape.** [architecture.md](specifications/architecture.md#what-a-call-costs-is-the-size-of-its-program)
records that a call costs ~250 ms per 4 KB because blender lab's add-on reads one 4 KB chunk per
timer tick. Add-on-side handlers send parameters, not programs — a few hundred bytes regardless of
what the tool does. The session source cache, the fragment hashing and the re-send-once recovery
all become unnecessary machinery.

**Safe mode stops being a hazard.** ahujasid's `safe_mode.py` (opt-in, `BLENDER_MCP_SAFE_MODE=1`)
is an AST allowlist over `execute_blender_code`. It permits `bpy`, `bmesh`, `mathutils` and pure
stdlib, and denies `os`, `sys`, and the name `modules` outright. **Every mpfb-mcp program would be
rejected under it** — `bootstrap.py` opens with `import sys` and a `sys.modules` scan, and ten of
the twenty-one payloads `import os`. First-class add-on handlers are not validated by safe mode at
all, because they are not user-authored code. This is a genuine argument for the pivot and a
caveat that the adapter path must document.

**There is an established slot for it.** Poly Haven, Sketchfab, Hyper3D and Hunyuan3D are already
optional integrations there, each with a paired `get_*_status` tool the model is told to check
first, and each gated add-on-side by a preference toggle. `mpfb_get_status` is that pattern
already. An MPFB integration would not be architecturally foreign.

## What the pivot would cost

### 1. Licence: GPL code cannot be relicensed into an MIT repository

MPFB is **GPL-3.0** (`../mpfb2/LICENSE.CODE.md`). This repository's tests carry
`SPDX-License-Identifier: GPL-3.0-or-later`. blender-mcp is **MIT**, including its `addon.py`.

MIT is one-way compatible with GPL: MIT code can be absorbed into a GPL work, not the reverse.
Contributing to blender-mcp means offering the code under MIT, which requires holding the
copyright to everything offered. Parts of what would move are not merely *written against* MPFB;
they are **derived from it**:

- `src/mpfbmcp/reference/urls.py` is a copy of MPFB's `ui/weburls.py`.
- `codegen/shared/target_categories.py` reproduces MPFB's modeling-category table.
- `codegen/shared/asset_sections.py` reproduces `ASSET_LIBRARY_SECTIONS`.
- `tools/set_asset_material.py`'s payload is a reimplementation of an MPFB UI operator, "with
  three of its quirks reproduced rather than tidied up".

Joel holds copyright over most of MPFB, so relicensing much of this is legally available to him —
but MPFB has other contributors, and the question is not only whether it is permitted. Moving
MakeHuman-ecosystem work under MIT donates it to a project whose terms allow indefinite retention
and dataset release, and the ecosystem's GPL choice was a deliberate one. There is also the
narrower question of an MIT-licensed `addon.py` that at runtime resolves and drives GPL MPFB
services in-process; users combining the two is unproblematic, but distributing an add-on built to
do it invites the plugin-linkage argument.

**This needs a deliberate decision (and probably a second opinion) before any code is offered, not
after.** It is the single item most likely to make the pivot un-doable after work has been spent.

### 2. Telemetry: MPFB tool calls would become training data by default

`TERMS_AND_CONDITIONS.md` in that repository states that prompts, generated code, scene metadata,
viewport screenshots and trajectory rows (goal, action, before/after state, accept/reject
feedback) are collected, may be stored indefinitely, may be used to **train AI models**, and may
be **released as an open dataset**. Consent is a checkbox in add-on preferences that is **on by
default**; without it a minimal anonymous record still goes out. `telemetry_decorator.py` wraps
`@mcp.tool()` functions so new tools are instrumented automatically — a contributed MPFB tool
would pick this up whether or not its author thought about it. Every tool there also carries a
`user_prompt` parameter whose description instructs the model to pass the user's words *verbatim*,
which exists to feed this.

For MPFB the payload is not neutral. A character's macro details are body proportions; MakeHuman
is routinely used to build likenesses of real people, and viewport screenshots of that character
are collected too. Routing MakeHuman users into that regime, from a project maintained in the EU,
is a decision with GDPR and community-trust dimensions that has nothing to do with code quality.
Note the contrast: this repository's own diagnostics are **off by default**, write locally only,
and CLAUDE.md tells the reader to review a record before sharing it.

### 3. Release cadence for MPFB integration stops being MakeHuman's

Today a payload defect is fixed here and shipped the same day; the add-on side is generic and
never changes. After the pivot, MPFB-facing code lives in `addon.py` — **duplicated** in
`src/blender_mcp/bundled/addon.py`, kept in sync by hand, versioned by `ADDON_PROTOCOL_VERSION`,
delivered through blender-mcp's PyPI release and re-installed into Blender by the user via
`uvx blender-mcp install-addon`.

So: MPFB changes a service signature → mpfb-mcp cannot fix it → a PR waits for a single maintainer
with no CI and no contribution guide → a blender-mcp release → users re-install the add-on. The
MakeHuman ecosystem's own compatibility fixes would be gated on a third party's cadence. That
cadence is currently healthy (7–24 commits/month) but it is one person's, and there is no
governance document promising anything.

### 4. Tool-list weight, and why upstream may reasonably decline

mpfb-mcp preloads **51.5 KB of descriptions plus 8.4 KB of schemas** into every client session
(`tests/test_description_budget.py`, which enforces a ceiling). blender-mcp's 28 tools total
**16.7 KB** of docstrings. Adding twenty-two MPFB tools would roughly **quadruple** what every
blender-mcp user downloads and holds in context — including the overwhelming majority who have
never installed MPFB — and take the tool count to fifty.

There is no precedent there for conditional tool registration: the Poly Haven and Sketchfab tools
are registered unconditionally at import and gated only add-on-side. So an MPFB integration cannot
currently hide itself when MPFB is absent. A maintainer weighing a large domain-specific block
against context cost for everyone else has a sound reason to say no, or to ask for it to be cut
down to three or four tools — which would mean discarding most of the interface design, not
porting it.

**This risk is asymmetric and should be tested before the work, not after**: the refactor is large
and the decision is someone else's.

### 5. The discipline does not survive the move

The specifications are what make this codebase what it is, and most of them have no upstream
counterpart to land in:

- `responses.md`'s `null`-vs-`[]` rule — meaningless where tools return `json.dumps(...)` strings.
- `mutating-tools.md`'s subject resolution, borrowed-selection restoration, the uniform
  `performed` flag across eleven tools, all-or-nothing batches.
- `tool-interface.md`'s validate-the-shape-never-the-vocabulary rule and the local checks that
  exist because `isinstance(True, int)` is `True`.
- `ToolAnnotations` on every tool (`readOnlyHint`, `destructiveHint`, `idempotentHint`) — used
  nowhere upstream.
- 800 tests, two layers per tool, against stubs that reproduce MPFB's real misbehaviour; upstream
  has no equivalent harness and no CI to run one in.
- The feature-request lifecycle, `HISTORY.md`, the live smoke run.

Some of this could be contributed as an improvement to the host project. Most of it would simply
be dropped in review as unlike the surrounding code, and CLAUDE.md there says plainly: "no
configured linter/formatter — match existing style". The likely outcome is twenty-two tools
rewritten to a lower standard, and the reasoning — which currently lives in module docstrings and
`HISTORY.md` — deleted along the way.

### 6. The refactor itself

Not a port; a rewrite of the boundary. `codegen/` deleted, ~7,750 lines of payload and fragment
source re-homed into a 4.2k-line `addon.py` **and its duplicate**, 800 tests rewritten against a
harness that cannot import the module under test, 22 tool modules restyled to `async def ... ->
str` with `ctx`, `user_prompt` and telemetry decorators, and the seven specifications either
rewritten or abandoned. Optimistically weeks; and the merge could still be declined at the end,
having produced a fork of someone else's add-on rather than a working product of one's own.

## Consequences if it proceeds anyway

- This repository becomes a staging area for patches, or is archived. There is no half-state where
  both exist: two servers exposing `mpfb_*` tools against one Blender is the interleaving failure
  CLAUDE.md already warns about.
- The GPL/MIT decision is made once and is effectively irreversible for the code that crosses.
- MPFB gains a supported path into the most-used Blender MCP — genuinely valuable — at the cost of
  being a guest in it.
- MakeHuman users acquire a telemetry default they did not choose, and the maintainer acquires the
  duty to explain it.
- The four tools that depend on MPFB internals most tightly (`set_asset_material`, `set_skin`,
  `symmetrize_targets`, `refit_human`) become the ones whose fixes are slowest to reach users,
  because they are the ones MPFB changes underneath.

## The alternatives, ranked

**A. Backend adapter only** — already scoped in
[NEXT_STEPS.md](feature-requests/NEXT_STEPS.md#second-backend-the-community-blender-mcp) and
[architecture.md](specifications/architecture.md#supporting-a-second-backend). An adapter below
`send_code()` translating transport and result channel; tools, payloads and `codegen/` untouched.

Gets: reach for users who already run the community add-on, at a fraction of the cost, with no
licence question, no telemetry question and no dependence on anyone's review.
Does not get: presence in that project's tool list, freedom from safe mode (document it: safe mode
rejects every program this project sends), or relief from the wire cost — though note that
ahujasid's add-on reads on a background thread in 8 KB chunks until the JSON parses, so the
4 KB-per-tick tax is a property of *blender lab's* add-on and **largely vanishes on that backend
anyway**. Two of the pivot's three technical arguments are collected here for a fraction of the
price.

**B. Move the Blender-side logic into MPFB** — the strongest structural answer. Payload logic
becomes a real, tested, documented MPFB-side API (MPFB already carries `socketservice.py` and
`jsoncall.py`, so a command surface is not foreign to it), and mpfb-mcp becomes a thin client
calling it. Then: it stays GPL, its release cadence is MakeHuman's, it is testable in MPFB's own
harness, it benefits *every* MPFB automation client rather than one, and the code sent over the
socket shrinks to a call and its parameters regardless of which add-on is on the other end.

Cost: MPFB gains a public API surface it must keep stable, and the work is comparable in size to
the pivot — but it is spent on something the ecosystem owns. Combined with A, this is the
recommended direction.

**C. A small upstream bridge, later.** If, after A and B, presence in blender-mcp's tool list is
still wanted, offer a *deliberately minimal* integration: `mpfb_status`, one or two high-value
tools, and a passthrough to MPFB's own API — a few KB of descriptions, not sixty. This is a
plausible ask for a maintainer to accept, does not carry MPFB-derived tables across the licence
boundary, and can be withdrawn without losing anything. Open the conversation (an issue or a
Discord message asking whether a domain integration of that size is welcome, and whether
conditional registration could be added) **before** writing anything.

**D. Full pivot** — as analysed above. Highest cost, largest irreversible decisions, outcome
controlled by someone else.

## Before deciding, find out

Cheap to establish, and each could change the ranking:

1. **Does the upstream maintainer want it at all**, and at what size? One issue answers this and
   costs nothing.
2. **Would upstream accept conditional tool registration** (register the MPFB block only when the
   add-on reports MPFB present)? If yes, objection 4 mostly dissolves. If no, twenty-two tools are
   almost certainly declined.
3. **Can MPFB-derived material be offered under MIT** — who holds copyright on `weburls.py` and
   the category tables, and is the ecosystem willing? Get this settled independently of the
   engineering.
4. **Could MPFB tools be exempted from trajectory capture**, or is instrumentation automatic and
   non-negotiable for a contributed tool?
5. **What is the actual installed-base gap** between the two add-ons among *MPFB* users — as
   opposed to Blender MCP users at large? The reach argument is the pivot's whole case, and it has
   not been measured.

## Gaps in this repository this analysis surfaced

Neither is caused by the pivot question; both are worth fixing regardless.

- **There is no `LICENSE` file.** The test modules declare GPL-3.0-or-later and `pyproject.toml`
  declares no licence at all. Any conversation about relicensing starts by being able to say what
  the licence *is*.
- **Safe mode is unaccounted for.** If a user runs either add-on's MCP server with
  `BLENDER_MCP_SAFE_MODE=1`, every program this project sends is rejected at the AST allowlist
  (`import sys`, `sys.modules`, `import os`). That belongs in the second-backend entry as a known
  limitation, and in `mpfb_get_status`'s failure vocabulary if it can be detected.
