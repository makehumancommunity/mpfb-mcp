# Make vision.md about the vision

**Status:** Done

[specifications/vision.md](../../../specifications/vision.md) is 374 lines, and **296 of them are
the "Target tool catalog"** — 79% of a document whose job is to say why the project exists and
what it is trying to become.

The catalog was written when nothing existed, as a list of tools worth building. It has since
been kept up to date, which sounds like diligence and was in fact the problem: **21 of its 23
entries are now marked Implemented**, and each has grown from a one-line intention into a
paragraph describing what the tool returns, field by field. The `mpfb_set_skin` entry is 25
lines and names `material_instances_requested`, `settings_file_created` and `scale_assumption`.
The `mpfb_add_asset` entry is 25 lines and explains `proxy_extras` and Blender's `.001`
uniquifying. This is reference documentation, and it is the **third** copy of it: every field
checked appears in the tool's own module docstring *and* in the feature request that added it,
and every live measurement quoted here is also in
[FR 013's review](../013-live-verification/review.md) and
[HISTORY.md](../../HISTORY.md).

That is the same failure [FR 020](../020-trim-claude-md/README.md) found in CLAUDE.md and
[FR 021](../021-split-architecture-spec/README.md) found in architecture.md, in its third
location: a document that was easiest to append to became the place everything was appended to.
Here it has an extra cost the other two did not have. A *forward-looking* document that is 91%
backward-looking cannot do its job — the two tools that genuinely do not exist yet,
`mpfb_get_human_summary` and `mpfb_search_docs`, are four lines buried at 96 and 332.

## Goals

**Primary:** vision.md states the goal, the approach, what makes something a tool, and what the
intended surface is — in about 130 lines. Someone who wants to know what a tool returns is sent
to the tool.

**Secondary:** rescue the vision-level material currently trapped inside the catalog. Why a tool
exists at all — as opposed to what it returns — is real and is written down nowhere else.

## Functional requirements

- vision.md is under 150 lines.
- The `## Target tool catalog` and `## Resolved: which "blender mcp"? Both` headings survive
  **with their current slugs**: 15 links point at the first and 2 at the second, and 14 of the
  15 are from finished feature requests whose links must keep resolving.
- The catalog states what an agent must be able to do, by capability area, and names the tools
  that do not exist yet. It does not describe the response of a tool that does.
- A new section states the principles that decide what becomes a tool.
- The backend section keeps the decision and the reason it is affordable; the adapter's design
  moves to [architecture.md](../../../specifications/architecture.md), which is where a statement
  about a seam below `send_code()` belongs.
- No fact is lost that does not exist in at least two other places.

## Non-functional requirements

**A vision document must be able to be wrong about the future without being wrong about the
present.** The catalog's problem was that keeping it accurate meant describing the past. A
capability area does not need updating when a tool ships.

**Deletion, not relocation.** Unlike FR 021, this effort *removes* prose rather than re-filing
it. That is only safe because the removed material is verifiably a third copy, so the check that
matters is the one that proves it.

## Architecture

Not code. vision.md gets five sections:

| Section | Lines | Change |
|---|---|---|
| Goal | ~10 | Kept, with a sentence on what "efficiently" means for an agent |
| Approach: piggyback, don't fork | ~23 | Unchanged, diagram included |
| What makes something a tool | ~35 | **New.** Extracted from the catalog's prose |
| Target tool catalog | ~40 | Capability areas and what is still missing, replacing 296 lines |
| Resolved: which "blender mcp"? Both | ~15 | Decision kept; adapter design moves out |

[architecture.md](../../../specifications/architecture.md) gains **Supporting a second backend**:
the adapter sits below `send_code()` rather than beside it, translating transport and result
channel together, because the community add-on returns captured stdout rather than the exec
namespace's `result` dict. Tools, payloads and `codegen/` stay unchanged either way, which is
the architectural claim.

## Tests

**No unit tests change and none are added.** This effort touches two Markdown files. The suite
is run once to confirm nothing under `src/` or `tests/` was edited.

**No live verification is required.** Nothing here reaches Blender.

Two documentation checks apply, and the second is the one that makes deletion safe rather than
merely convenient:

- The repo-wide link checker introduced in [FR 020](../020-trim-claude-md/README.md) and
  extended in [FR 021](../021-split-architecture-spec/README.md) reports no dangling link,
  and both surviving vision.md anchors still resolve.
- **Every response field, argument and measurement named in the removed catalog prose is
  located in at least two other files** — the tool module and its feature request — before the
  prose is deleted. A field that appears only in vision.md is not deleted; it is a fact with no
  home, and it moves to the tool's docstring instead.

## References

- Inbound links: `grep -rno "vision\.md#[a-z0-9_-]*" --include=*.md --include=*.py .`
- [FR 020](../020-trim-claude-md/README.md) and
  [FR 021](../021-split-architecture-spec/README.md) — the same problem in CLAUDE.md and
  architecture.md.
