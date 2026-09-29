# Links to documentation and other online resources

**Status:** Done

An agent driving MPFB through these twenty tools can find out what is installed, what could be
added and what a character is made of. What it cannot do is look anything *up*. When a tool
response is not enough — what an `.mhclo` file actually contains, what a human preset stores, how
MPFB's asset packs are obtained and installed — the agent has no address to go to, and the failure
mode is not an error but a guess presented as fact.

This is the first entry in the one area of [vision.md](../../../specifications/vision.md#target-tool-catalog)
that is still empty. It is deliberately the *small* half of it: two catalogue tools that hand out
addresses. The ranked search over bundled documentation that vision.md calls `mpfb_search_docs`
stays a separate, later effort — this request neither implements it nor forecloses it.

There are two distinct bodies of material, with different audiences and different provenance:

- **The community sites.** MPFB keeps thirteen `URL_*` constants in
  [`src/mpfb/ui/weburls.py`](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/ui/weburls.py) — homepage, documentation, FAQ,
  forum, issue tracker, asset packs, system assets, the getting-started guide and video. These are
  MPFB's own values and change with MPFB. (The NEXT_STEPS entry — since moved to
  [HISTORY.md](../../HISTORY.md) — said they are found via the `start_here` UI module;
  `start_here/startherepanel.py` only *consumes* them, and `weburls.py` is where they live.)
- **The mpfb2 repository's developer documentation.** 105 markdown files under
  [`docs/`](https://github.com/makehumancommunity/mpfb2/tree/master/docs) — one per service, per
  file format, per entity. This is the material that actually answers "how does MPFB do X", and it
  is **not shipped with the extension**: `docs/` sits in the repo, not under `src/mpfb/`, so no
  amount of code running inside Blender can reach it.

A second effort depends on this one:
[Finding, downloading and installing asset packs](../../NEXT_STEPS.md#finding-downloading-and-installing-asset-packs)
needs the asset-packs URL, and says so.

## Goals

**Primary:** an agent can obtain the address of the authoritative document for a question it
cannot answer from a tool response, without assembling a URL and without a local checkout of
anything.

**Secondary:**

- Unblock the asset-pack effort, which needs `URL_ASSET_PACKS`.
- Settle, as a standing constraint rather than an accident, that mpfb-mcp opens no network
  connection except the one to the blender_mcp add-on.
- Answer usefully in the state where the question is most likely asked: MPFB not installed, or
  Blender not running. Both tools must work there.

## Functional requirements

### `mpfb_list_urls` — the community sites

1. Returns one entry per link, each carrying: `key` (MPFB's constant name, e.g.
   `URL_ASSET_PACKS`), `url`, `title`, `description` (one sentence on what is at that address and
   which question it answers), `keywords`, and `source` — `"mpfb"` for a value read from
   `weburls.py`, `"mpfb_mcp"` for an ecosystem link this package maintains.
2. **Enumerates by prefix, not by a list kept here.** Every module-level name beginning `URL_` is
   reported, so a constant MPFB adds later appears without a change in this repository. A key with
   no description of ours is reported with `description: null` rather than omitted.
3. **Reports where the answer came from**: `source_of_truth` is `"mpfb"` or `"builtin_fallback"`,
   with `mpfb_version` when read live. A caller must never have to infer which it got. Where the
   two disagree — a constant MPFB has changed, or one it has added or removed — the live value
   wins and the response says the fallback is stale.
4. **Answers in all three states**: MPFB read live; MPFB absent or not initialized (fallback,
   `source_of_truth: "builtin_fallback"`, `mpfb_status` carrying the reason); Blender unreachable
   (fallback, same field, reason naming the socket failure). None of the three is an error
   envelope. This is the [absence-is-an-answer](../../../specifications/responses.md) shape
   `mpfb_get_status` already has, extended to a socket failure — see [Architecture](#architecture),
   since that part is genuinely new.
5. Carries the **ecosystem links** MPFB's constants do not: MakeHuman itself, the community asset
   repository, the sibling projects an agent may be asked about. These are `source: "mpfb_mcp"`
   and are honest about it — MPFB does not endorse them by having them in this list.
6. **Not capped, not paged.** Roughly twenty entries. The docstring says so explicitly, so a
   caller does not go looking for `truncated` or `total_count` — the
   [bounding convention](../../../specifications/responses.md#how-tools-bound-a-large-answer) applies
   to answers that do not fit, and this one does.

### `mpfb_list_docs` — the developer documentation

7. Returns a **curated subset** of the mpfb2 repository's `docs/` tree — the documents that answer
   questions an agent driving *these* tools will actually hit, not all 105. Each entry carries:
   `path` (repo-relative, e.g. `docs/services/humanservice.md`), `raw_url`
   (`raw.githubusercontent.com/.../master/...`, which returns markdown), `page_url` (the
   `github.com/.../blob/master/...` page, for a human), `title`, `description`, `keywords` and
   `topic` (`services` / `fileformats` / `entities` / `ui` / `general`).
8. **The response must not read as the whole tree.** It carries `curated: true`, the count of
   documents in the tree it was curated from, and `tree_url` pointing at the full listing. This is
   the [an absent entry must be explainable](../../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added)
   obligation: an agent that reads a short list as the whole truth concludes rather than
   investigates.
9. **Filterable** by `topic` and by a free-text `keyword` matched against title, description and
   keywords. With no argument it returns everything it has.
10. **Pinned to `master`, and says so.** `ref: "master"` in the response, and the docstring states
    that a document may therefore describe MPFB newer than the installed one. Matching the URL to
    the installed MPFB version was considered and rejected for this effort: it would make a purely
    local tool depend on Blender, and mpfb2's docs are not tagged per release in a way that makes
    the older URL reliably resolve.
11. **Never crosses the socket and never touches the network.** It is a local table. It works with
    no Blender, no MPFB and no connectivity.

### Both

12. **Neither tool fetches anything.** They return addresses; the MCP client retrieves them if it
    can. This is a standing constraint on the package, recorded as such — see
    [Affected specifications](#affected-specifications).
13. Descriptions and keywords are **mpfb-mcp's own text**, not MPFB's — MPFB stores none. Both
    docstrings say so, per the
    [derived-fact convention](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact).

### Candidate curated set

A starting point, to be settled during the effort. The inclusion criterion is the test to apply to
each: *would an agent working through the existing twenty tools be better off having read this?*

`docs/index.md`, `docs/code-structure.md`; `docs/services/` — `humanservice`, `targetservice`,
`assetservice`, `objectservice`, `materialservice`, `rigservice`, `clothesservice`,
`locationservice`; `docs/fileformats/` — `mhclo`, `mhmat`, `target`, `human_preset`, `rig`,
`weights`, `pose`, `expression`; `docs/entities/objectproperties.md`.

That is eighteen. The last four file formats are there because the queued efforts (presets,
expressions, poses) will want them; if the set grows much past twenty-five, the curation has
stopped being curation and requirement 7 should be revisited.

## Non-functional requirements

**The description budget is the binding constraint on this effort.** The twenty existing tools
measure 47,730 B against a ceiling of 48,500 — about 770 B of headroom, and
[`MINIMUM_DESCRIPTION`](../../../tests/test_description_budget.py) is 400 B per tool. Two new tools do
not fit, and cannot be made to fit by trimming them. The effort therefore **raises
`DESCRIPTION_CEILING` deliberately**, records the reason in the test's own comment and in the
commit message, and holds both descriptions to well under the current 2,387 B average: these two
instruct about a small, static vocabulary, and most of what a caller needs is visible in the
response itself. If either description approaches the average, it is carrying rationale that
belongs in the module docstring.

**Robustness over authority.** A links tool that fails when MPFB is missing is useless in the one
situation where the download link is the answer. Every degradation is a successful response that
names what degraded.

**Drift is the standing risk, on both halves.** The vendored URL copy drifts when MPFB edits
`weburls.py`; the curated doc list drifts when a document is renamed or removed. Neither can be
checked at runtime without the network, so both get a **test that runs only when a sibling
`../mpfb2` checkout is present and skips otherwise** (see [Tests](#tests)). This costs nothing on
a machine without the checkout and catches the drift on the machine where the work happens.

**Cost.** `mpfb_list_urls` is one small program — a few hundred bytes, so well under one 4 KB
chunk and one timer tick. `mpfb_list_docs` costs nothing at all.

## Architecture

**Two tool modules, one payload.** `tools/list_urls.py` with
`codegen/payloads/list_urls.py`; `tools/list_docs.py` with **no payload at all** — the first tool
in the package that never generates code. That is a real exception to
[CLAUDE.md](../../../CLAUDE.md#the-twenty-two-tools)'s "tool module, payload and test module all share a
name", and it should be stated there rather than left to be noticed.
`tests/test_codegen.py`'s payload list is hand-maintained, so it simply does not gain an entry for
`list_docs`; nothing breaks, but the omission needs a comment or the next reader will read it as a
mistake.

**Reading `weburls.py` from generated code.** Resolve MPFB's root package with the existing
`_MPFB_MODULE_SCAN`, then read `sys.modules.get(root_name + ".ui.weburls")` — **never**
`importlib.import_module`. MPFB imports its UI during `register()`, so on an initialized install
the module is already in `sys.modules` and reading it re-executes nothing.

This extends
[Reading module-level names MPFB does not publish](../../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish),
which today says such a name is reached *through a service's module*. `weburls` is a **UI** module
with no service behind it; the rule's three conditions still hold (through `sys.modules` rather
than a fresh import, always with a fallback, never as a substitute for a service), but the spec as
written does not cover the case and should. Note the difference from
[`_modelsubpanels`](../../../specifications/mpfb-integration.md#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not),
which `mpfb_set_targets` deliberately does *not* read: that module builds a table at import time
and would be a stale snapshot. `weburls` is thirteen string literals with no computation, so
reading it has none of that problem — and saying why the two are treated differently is part of the
fold-back.

**Use `MPFB_STATUS_BOOTSTRAP`, not `MPFB_BOOTSTRAP`.** This is a tool that must answer when MPFB is
absent, so it becomes the second consumer of the non-raising bootstrap — which is what that
bootstrap exists for.

**The socket failure is the genuinely new part.** Today a connection error becomes an error
envelope from `connection.py`, uniformly, for every tool. `mpfb_list_urls` must instead catch it
and answer from the vendored copy. Two pitfalls:

- Catch **only** the connection/transport failure, not every exception. A payload that raised
  inside Blender is a defect and must still surface as an error; swallowing it into a
  "fallback" answer would hide it permanently.
- Do it in the tool module, not in `connection.py` or `shared_cache.py`. Nineteen tools depend on
  a connection failure being an error, and this is one tool's exception, not a change to the wire
  layer.

**Where the vendored data lives.** An ordinary sub-package — `src/mpfbmcp/reference/` with
`urls.py` and `docs.py`, each a plain module with `__init__.py`. Deliberately *not* under
`codegen/payloads/` or a new data directory: these are imported by this package and never sent to
Blender, which is the exact opposite of what a payload is, and the
[package-data globs](../../../pyproject.toml) are shallow and fussy enough that a real sub-package is
the lower-risk choice.

**`mpfb_list_docs` builds URLs from `path`, it does not store them.** One repo constant, one raw
constant, `path` appended. Storing three strings per entry where one plus a rule will do is three
places for a typo, and the rule is what makes requirement 8's `tree_url` consistent with the
entries.

## Affected specifications

- [architecture.md](../../../specifications/architecture.md) — extend
  [Reading module-level names MPFB does not publish](../../../specifications/architecture.md#reading-module-level-names-mpfb-does-not-publish)
  to cover a UI module with no service behind it, and why `weburls` qualifies where
  `_modelsubpanels` does not. Add the standing constraint that **mpfb-mcp opens no network
  connection except to the blender_mcp add-on**, and note that a tool may legitimately answer
  without crossing the socket at all.
- [responses.md](../../../specifications/responses.md) — a response that reports **which source
  answered it** when a tool has more than one; and the curated-list obligation (a deliberately
  partial answer must carry the size of what it was drawn from and the address of the whole).
- [tool-interface.md](../../../specifications/tool-interface.md) — the description budget section
  gains the ceiling change and its reason.
- [mpfb-integration.md](../../../specifications/mpfb-integration.md) — `weburls.py` is a concept MPFB's
  UI has and its services do not, which is exactly what
  [that section](../../../specifications/mpfb-integration.md#when-mpfb-mcp-models-a-concept-mpfbs-ui-has-but-its-services-do-not)
  is about; this is the second instance and the first one where reading the UI module is the right
  answer.
- [vision.md](../../../specifications/vision.md#target-tool-catalog) — the **Documentation** row moves
  from "none yet" to two tools; the `mpfb_search_docs` bullet stays, narrowed to what remains.
- [testing.md](../../../specifications/testing.md) — a test that skips on the absence of a sibling
  checkout is a new kind here, and the reason it is worth having anyway.

## Tests

- **`tests/test_list_urls.py`** — the wrapper with `send_code` mocked: live read, fallback on MPFB
  absent, fallback on a connection failure, and that a payload error is *not* swallowed into a
  fallback. Then the payload `exec()`'d against a stub `sys.modules` carrying a fake `ui.weburls`
  module — including one carrying an **extra** `URL_` constant and one **missing** a known key, so
  requirement 2's enumeration and requirement 3's staleness reporting are both under test rather
  than assumed.
- **`tests/test_list_docs.py`** — entirely local: URL construction from `path`, `topic` and
  `keyword` filtering, and that `curated`, `tree_url` and the tree count are always present.
- **Two drift tests, skipped without a sibling checkout.** With `../mpfb2` present: every `URL_*`
  constant in `weburls.py` appears in the vendored copy with the same value, and every curated
  `path` is a file that exists. `skipUnless` on the checkout, so the suite still passes anywhere.
- **`tests/test_description_budget.py`** — ceiling raised, with the reason in the comment beside
  it, as that comment's own history does for FR 016.
- **`tests/test_verification_smoke.py` and `verification/smoke.py`** — one item each. Note that
  `mpfb_list_docs`' item needs no MPFB and no Blender; the item table's coverage rule is derived
  from the registry, so it still needs an entry, and the effort should decide whether a tool that
  cannot fail against Blender is a per-tool item or belongs with the run-level ones.

**This effort needs a real Blender, once, for one claim.** That `<root>.ui.weburls` is present in
`sys.modules` on a normally installed and initialized MPFB is precisely what a stub cannot
establish — the stub is built from the assumption under test. A script in this subdir asserts it,
reports the thirteen keys and values actually read, and compares them against the vendored copy.
It runs during the effort and moves to `done/` with it; what stays behind is the two smoke items.

## References

- [`mpfb2/src/mpfb/ui/weburls.py`](https://github.com/makehumancommunity/mpfb2/blob/master/src/mpfb/ui/weburls.py) — the thirteen constants,
  and their docstring's reason for existing ("so that the same link does not have to be maintained
  in several panels"), which is the same reason this tool should read them rather than copy them.
- [`mpfb2/docs/`](https://github.com/makehumancommunity/mpfb2/tree/master/docs) — 105 markdown
  files; at [`mpfb2/docs`](https://github.com/makehumancommunity/mpfb2/tree/master/docs).
- NEXT_STEPS: *Getting URLs to documentation etc* — the entry this request scoped. It has since
  moved to [HISTORY.md](../../HISTORY.md), so there is no section left in NEXT_STEPS.md to link.
- [NEXT_STEPS: Finding, downloading and installing asset packs](../../NEXT_STEPS.md#finding-downloading-and-installing-asset-packs)
  — the dependent effort.
- [vision.md: target tool catalog](../../../specifications/vision.md#target-tool-catalog) — the
  Documentation row and the `mpfb_search_docs` bullet this request deliberately does not close.
- [FR 016](../016-trim-tool-descriptions/README.md) — what the description budget is, and what
  was already taken out to make room.


## Outcome

**Done**, and verified two ways: [`check_weburls.py`](check_weburls.py) in this subdir (14 checks,
all passing, against Blender 5.1.0 with MPFB 2.0.17), and one smoke item per tool in
[verification/](../../../verification/) — 25 items, 0 failed, 0 skipped, 43.4 s. What landed and
what it decided is in [HISTORY.md](../../HISTORY.md#fr-024--links-to-documentation-and-other-online-resources);
the durable decisions are folded into the documents named under
[Affected specifications](#affected-specifications). What follows is only where this request was
**wrong**, since that is the part a reader of a finished request cannot get from the specs.

- **Eleven `URL_*` constants, not thirteen.** The background section says thirteen; the installed
  MPFB 2.0.17 publishes eleven, and so does the checkout. Harmless, because FR-2 enumerates by
  prefix rather than from a list — which is precisely the property that made the miscount not
  matter, and the reason to keep it that way.
- **Nineteen candidate documents, not eighteen.** The candidate set under
  [Candidate curated set](#candidate-curated-set) lists nineteen paths and calls it eighteen. All
  nineteen were kept; the response computes `curated_document_count` rather than carrying a
  written-down number, so again nothing depended on the arithmetic.
- **"A few hundred bytes" was the wrong unit for the program.** True of the logic, false of the
  program: at 6.8 KB assembled `list_urls.py` is dominated by its own docstring, as every payload
  here is, and only two of the twenty-one fit in one 4 KB chunk at all. The cost claim that
  actually mattered survived intact and is what the test asserts — the vendored table is **not**
  in the program, because sending it in as `PARAMS` would have put ~3 KB on every call to compute
  what a local function already computes.
- **The "which is a per-tool item?" question under [Tests](#tests) resolved to "a per-tool item".**
  `mpfb_list_docs` reaches no Blender, so there is nothing live for its item to establish — but
  coverage is derived from the registry and the run-level set is closed at three, so a per-tool
  item is what it gets, with the comment saying why.

One thing the request did not anticipate and the implementation added: `check_weburls.py` provokes
the fallback by pointing `BLENDER_MCP_PORT` at a **really refused socket** rather than by mocking
`ConnectionError`. The Tests section scoped the live check to the `sys.modules` claim alone, but
catching a transport failure and answering anyway is the one genuinely new mechanism here, and a
mechanism only ever exercised through a mock has not been exercised.
