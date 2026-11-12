# Instructions that arrive, and schemas and answers without what is generated or repeated

**Status:** Proposed

A Claude Code session on 2026-11-05 received this server's instructions cut off at exactly character
4,096, in the middle of "To know whether meshes pass throu". The Blender server's instructions were
cut off in the same session, which points at a limit in the client rather than anything here. The
text is 7,134 characters, so 3,038 of them did not arrive, and **they are the part this package can
least afford to lose**: the conventions block comes last, and
[tool-interface.md](../../specifications/tool-interface.md#a-tool-description-is-call-time-instruction-with-a-budget)
tells every tool description to leave those conventions out because the instructions carry them. So
in that client, `status` and `result`, the `error` slug, what `name` accepts, `found`/`ready`/`blocked_by`,
`performed` and `truncated` may reach a model nowhere at all. Nothing noticed, because
[test_description_budget.py](../../tests/test_description_budget.py) has never measured the instructions.

Checking this started from [an article on MCP schema bloat](https://layered.dev/mcp-tool-schema-bloat-the-hidden-token-tax-and-how-to-fix-it/)
and went on to the wider advice. Most of it is already done here or does not fit
([Weighed and left out](#weighed-and-left-out)). What survived is below, and **"significant" means at
least 5 % of what a session's results or preload cost, or an actual fault**. Costs are estimated at the
article's 3.8 B per token.

| What a session pays for | Bytes or characters | Approx. tokens |
|---|---:|---:|
| Descriptions, all 51 tools, on a host loading every tool up front | 106,487 | 28,000 |
| Input schemas, on the same host | 22,528 | 5,900 |
| Server instructions, on every host | 7,134 | 1,900 |
| Tool results, median session ([transcripts](#how-the-results-were-measured)) | 120,524 | 32,000 |

A host with tool search pays for only the tools a session loads, and the four real building sessions
loaded 19 to 23 of them, so perhaps 50 KB of descriptions and schemas. **There, the results cost more
than twice what the tools do**, and they are paid on hosts of every kind. This request therefore
covers three things: the instructions, the schemas and the answers.

## Goals

**Primary:** every client that delivers only the first 4,096 characters of a server's instructions
delivers all of this server's, and the conventions come first in any case.

**Secondary:**

- Take the generated noise out of the input schemas, in one place, so that it stays out as tools are
  added: 11.5 KB, or about half of them.
- Stop answers repeating fixed text, and stop writers reporting what the call did not change: about
  151,000 of the 1,196,830 result characters measured, or 12.6 %, which is about 4,000 tokens in a median session.

## Functional requirements

### The instructions

1. **The instructions are at most 4,000 characters**, and a test fails if they grow past that.
   4,096 is one client's limit as observed once, so the ceiling keeps a paragraph of headroom below it.
2. **The conventions come immediately after the opening sentence and end within the first 2,048
   characters.** Secondary sources disagree on the limit, and [one puts it at 2 KB](https://wmedia.es/en/tips/claude-code-mcp-tool-search),
   so the part no tool description repeats has to survive that as well. A test holds this.
3. **A sentence stays only if it does one of three things**:
   - states a convention;
   - routes, by saying which tool does which job, since this may be all a model reads before loading one;
   - states an order across tools that no single tool's description can own.

   A fact about one tool goes.
4. **Nothing a caller needs is lost.** Each sentence removed is listed in this request with where its
   content now lives. Most are already in the description of the tool they name, and that has to be
   checked per sentence rather than assumed. One that is not moves there.
5. **The surprises stay reachable before a mistake is made.** "Add the rig before attaching garments"
   and "a `rigify.*` rig must be finished after them" are orders across tools and stay. A surprise
   that belongs to one tool, such as what a skin deletes, moves only if that tool's description
   states it in full.

### The schemas and the descriptions

6. **No input schema carries a generated `title`.** A property that is itself named `title` is kept,
   so the removal must not match on the key alone.
7. **An optional argument appears as its own type**: `anyOf: [X, null]` with `default: null` becomes X,
   with no `default`. A union of two real types stays a union, a non-null default stays, and `required`
   is unchanged.
8. **Every argument accepted today is still accepted**, an explicit `null` included. Recipes depend on
   this: `mpfb_write_mesh_asset`'s `try_with` carries `name: null` for the caller to fill, and a
   caller may send one as it stands.
9. **An unnamed argument still behaves as it does today.** In particular `mpfb_list_assets`' unnamed
   `limit` and `offset` still cross the socket as null.
10. **No output schema changes**, and every tool keeps its `outputSchema`. See
    [Why the output schemas stay](#why-the-output-schemas-stay).
11. **No description is longer than 4,096 characters**, and a test fails if one grows past that. The
    same secondary sources give that limit for a tool loaded up front. `mpfb_list_assets` is at 4,094
    and arrived whole through tool search in the session above, so this costs nothing today and is
    the only warning a later addition would get.

### Answers do not repeat fixed text

12. **A definition that never changes is in the description, not in the answer.** `limb_measures`,
    `achieved_measure` and `amounts_measure` leave every answer they appear in, and each tool that
    reports those fields says what they measure in its own description. A caller has read a tool's
    description before it can call that tool, including under tool search, so the definition still
    reaches every caller. Measured: 52,371 characters, 4.4 %. The tolerances stay in their modules.
13. **`mpfb_add_asset`'s weights warning fires only when the caller named `import_weights`.** It says
    "was requested" on 127 of 134 calls in the transcripts, and not one of those calls named the
    argument, so it is a false statement as well as 24,257 characters, 2.0 %. Whether an asset's weights came
    from a file or from interpolation is still a fact worth having, as a short field on every answer
    rather than a sentence.
14. **`mpfb_add_asset`'s generated-Rigify warning says what to do and drops how MPFB comes to need it.**
    It is a real surprise and it stays a warning, but `RigifyHelpers.adjust_children_for_rigify()` means
    nothing to a caller. About two thirds of its 12,852 characters can go, 0.7 %.

### A writer reports what the call changed

15. **`mpfb_set_pose_bones` reports the limbs and landmarks the call moved.** Whether one moved is
    measured, comparing before and after with the tolerances the writers already use, and not inferred
    from body parts: a change to the spine moves everything, and then everything is reported. Estimated at up to
    48,479 characters, 4.1 %. That estimate works from body parts because the transcripts cannot say what moved.
16. **`mpfb_set_rigify_hand_shape` reports the fingers it wrote.** 17,332 characters, 1.4 %.
    `restore_with` still restores everything the call changed.
17. **What is left out is named**, per
    [a deliberately partial answer](../../specifications/responses.md#a-deliberately-partial-answer-carries-the-size-of-the-whole):
    the limbs and landmarks that did not move and the fingers not written, by name and without their values,
    so a short answer cannot be read as a character with only those parts.
18. **`limbs_made_stretched` and `limbs_made_unreachable` are unchanged**, and `mpfb_get_pose` stays the
    whole reading, with its description saying so where a writer's answer now points at it.

### The budget

19. **`tests/test_description_budget.py` measures the instructions**, and its report's "preloaded"
    total includes them. `SCHEMA_CEILING` falls to the new measured total plus the usual paragraph.
    `DESCRIPTION_CEILING` rises by exactly what requirements 4 and 12 move into descriptions, saying so
    in its comment. Expect about 1 to 2 KB, against 52 KB in answers across these nine sessions alone.

## Non-functional requirements

- **Robustness against the next tool.** Both schema rules apply to whatever is registered, with no
  per-tool work. "Adding a tool touches exactly four things" stays true.
- **Honesty over size.** No trim may make an answer readable as more complete than it is, and
  [`null` and `[]` stay different answers](../../specifications/responses.md#response-shape). That rule is
  why dropping null and empty keys is not in this request, though it measures at 7 %.
- **No new arguments.** A shorter answer behind an opt-in flag is one that agents do not ask for, which is
  [FR 048's own observation](../NEXT_STEPS.md#add-asset-intersections-by-default). These are default changes.
- **Readability.** Keep the instructions as one string, grouped by purpose in the source, since that is what
  crosses the wire.

## Architecture

- **The instructions and the schemas are in `build_server()`** in
  [`src/mpfbmcp/__init__.py`](../../src/mpfbmcp/__init__.py). The schema step goes beside
  `_shipped_without_source_indentation()` and goes through `_registered_tools()`, the one place this package
  reaches into FastMCP. It rewrites `tool.parameters` only.
- **Why an explicit null survives.** A prototype of requirements 6 and 7, applied in memory, reached
  11,023 B through a real in-memory client. `mpfb_list_docs` then accepted `{"topic": null}` and still
  refused `{"topic": 5}`. FastMCP validates through `fn_metadata.arg_model`, which this step does not
  touch, and it registers its handler with `validate_input=False`, so the published schema is not
  enforced on the server.
- **That second fact belongs to the library, and is the pitfall.** If an `mcp` release turned
  `validate_input` on, an explicit null would start being refused. Requirement 8's test is what would
  catch it. A client that validates arguments against the published schema before sending could also
  refuse a null, which is one more reason a recipe's null is "the caller's to fill".
- **`tests/test_vocabulary.py`'s `_json_type()` already reads both shapes**, so it should pass unchanged.
- **No argument today is both required and nullable, and none is itself named `title`**, both checked
  against the built server. A later tool could be either, so requirements 6 and 7 still have to handle
  them: a required nullable argument would otherwise gain a schema forbidding what it accepts.
- **Nearly half of the instructions have to go, and that is the real work of the first part.** At least
  3,134 characters must come out. The conventions (1,232) stay. The lookup-tool paragraph (562) is the
  obvious first saving, since both tools' descriptions carry it. The rest is sentence by sentence.
- **The answers change in the bridge**, in `commands/set_pose_bones.py`, `commands/set_rigify_hand_shape.py`,
  `commands/get_pose.py`, `commands/get_rigify_hand_shape.py`, `commands/add_asset.py` and
  `shared/pose_writing.py`. Nothing crosses to the tool side but the keys, so `PROTOCOL_VERSION` does not move.
- **Requirement 15 could cost more than it saves if it sends callers back to read.** It saves about 770
  characters a call, and `mpfb_get_pose` costs about 2,655, so a follow-up read after more than about 29 %
  of writes would cancel it. The transcripts show 5 reads against 66 writes today. The live check repeats a
  real posing task and looks at this, and if the ratio climbs, the rule should go rather than the reads.

### Why the output schemas stay

An earlier reading of this problem suggested dropping them: every answer is produced twice, as
`content` and `structuredContent`, and the text copy is pretty-printed (`mpfb_list_docs`: 13,590 B
against 10,385 B compact, 24 % whitespace). The transcripts say otherwise: results are recorded as a single text
block with **0.1 % whitespace**, so in that client the doubling and the whitespace do not reach the model.

The likeliest explanation is that the client reads `structuredContent` when it is present, though that is
inferred from the compact form rather than confirmed. If so, **removing `outputSchema` would make that
client's answers about a quarter larger on every call**. Whether other hosts read `content` is unknown, and
compacting `content` for them is left out until someone is using one.

### How the results were measured

[measure_transcripts.py](measure_transcripts.py) reads this machine's Claude Code transcripts and prints every
number above: 503 `mpfb_*` results, 1,196,830 characters, 9 sessions, a median of 31 calls and a maximum of
309,443 characters in one session. `mpfb_set_pose_bones`, `mpfb_add_asset` and `mpfb_set_rigify_hand_shape` are
54 % of it. **These sessions were heavy on posing and dressing, ran on older versions of the tools, and come from
one maintainer**, so the figures rank the candidates rather than promise a saving. Re-run it after the effort.

### Weighed and left out

| Strategy | Why not here |
|---|---|
| Code execution or Code Mode ([Anthropic](https://www.anthropic.com/engineering/code-execution-with-mcp), [Cloudflare](https://blog.cloudflare.com/code-mode/)) | The bridge "executes nothing a caller sends", and [FR 033](../done/033-retire-the-generated-code-path/README.md) deleted the path that did. Reported gains also depend on a [large API](https://www.getmaxim.ai/articles/code-execution-with-mcp-how-code-mode-cuts-agent-token-costs-by-90/) or big intermediate data, and 0 of 503 results passed 25,000 characters. |
| Fewer tools with an action parameter | One author reports [60-70 %](https://d365hub.com/Posts/Details/2fcf0a27-1ad0-46dd-b48e-b2fa162ecf1a/how-to-build-better-ai-agent-tools-cut-costs-by-70-mcp-server-case-study), as a single anecdote. It would move the tool's vocabulary out of its schema and into prose, while tool search already removes most of the preload it would save. |
| `$ref`/`$defs` | Only two `description` keys exist in all the schemas, a `$ref` is longer than the 40 shared `name` definitions, and the rest save a few hundred bytes. |
| TOON or another tabular format | Only 8.5 % of result characters are in arrays it suits, so at [its own 40 %](https://github.com/toon-format/toon) that is 3.4 %. It would also break the envelope, `restore_with` and "a read-back is a write". |
| Rounding floats | 1.2 %. They are already rounded. |
| Dropping null and empty keys | 7 %, but [`null` and `[]` are load-bearing here](../../specifications/responses.md#response-shape). |
| Removing `protocol_version` and `command` | 3.0 %, under the line, and the envelope is returned exactly as it arrived on purpose. |
| Shortening every `message` | 7.8 % is the most any trim could take, the sentences carry facts a human reads, and it means rewriting about fifty commands by judgement. Worth revisiting, not here. |
| Field selection, `fields` arguments | Catalogues are a small share of these sessions, the largest being 2.3 %, and agents rarely ask for what they do not know they need. See [Response bulk](../NEXT_STEPS.md#response-bulk-on-the-read-only-tools). |
| Resource links for large results | 0 results over 25,000 characters, and FR 056 already answered the worst case with a summary. |
| `anthropic/alwaysLoad` per tool | It [opts a tool out of deferral](https://startdebugging.net/2026/05/how-to-reduce-the-number-of-mcp-tools-claude-loads/), which raises this cost. No tool here is needed by every session. |
| Tool groups or `list_changed` | They help only a host without tool search, and changing the tool list between calls works against prompt caching. The seven asset-authoring tools are about 15 % of the preload if someone needs this later. |
| Compressing proxies such as [mcp-compressor](https://pypi.org/project/mcp-compressor/0.3.0/) | A choice for a host's user, not a change to this server. |
| Another pass over the descriptions | 78 % of the up-front cost, and exact repeats come to only 242 B. It is a judgement effort of its own, and tool search reduces what it would buy. |
| Batching `mpfb_add_asset` | It saves round trips, and tokens only if per-entry answers shrink, which this request's warning changes do anyway. It stays [in NEXT_STEPS](../NEXT_STEPS.md#response-bulk-on-the-read-only-tools). |

## Affected specifications

- [tool-interface.md](../../specifications/tool-interface.md#a-tool-description-is-call-time-instruction-with-a-budget):
  the bullet sending conventions to the instructions gains the limit and the order, and a new bullet
  covers the generated schema keys. Its "all twenty-five" and "twenty-five times" are stale and get fixed while
  there. The glossary's `achieved_measure` row changes.
- [responses.md](../../specifications/responses.md): "carries its definition with it" and "`achieved_measure`
  carries the definition in every answer" are decisions this request reverses, and the rule that replaces them has
  to say why: a caller has already read the description. The `fingers_before`/`fingers_after` and landmark rows
  gain what a writer leaves out.
- [mutating-tools.md](../../specifications/mutating-tools.md), for the rule that a writer reports what the call
  changed and names what it left out.
- [testing.md](../../specifications/testing.md), whose two mentions of the budget test should be checked
  against what it now measures.
- The root [CLAUDE.md](../../CLAUDE.md): the `__init__.py`, `test_description_budget.py`, `mpfb_set_pose_bones` and
  `mpfb_add_asset` rows, as map entries only.

## Tests

In [tests/test_description_budget.py](../../tests/test_description_budget.py), on the server
`build_server()` builds:

- the instructions' length against the ceiling, and the conventions ending within 2,048 characters;
- no description over 4,096 characters;
- no generated `title` in any input schema, and no `anyOf` with a `null` option beside a null default.

In [tests/test_vocabulary.py](../../tests/test_vocabulary.py), which already drives a real in-memory client:

- an explicit `null` accepted for an optional argument and a wrong type still refused, on every tool
  that has an optional argument, since this is what fails if `validate_input` is ever turned on;
- every tool still declares an `outputSchema`.

The existing wire tests hold requirement 9, and `test_list_assets.py` already pins `limit` reaching the
wire as null.

**The answers are the bridge's, so they are tested in `bridge/test/`**, in a real headless Blender:

- `ddd_mutating/set_pose_bones_test.py`: an arm write reports that arm and names the others as not moved; a
  spine write reports every limb and landmark; and the `limbs_made_*` lists are unchanged.
- `ddd_mutating/set_rigify_hand_shape_test.py`: only written fingers report values, the rest are named, and
  `restore_with` still restores exactly.
- `ddd_mutating/add_asset_test.py`: the weights warning appears only when `import_weights` is named, and the new
  field is right with and without a `.mhw` beside the asset.
- `ccc_reading/get_pose_test.py` and `get_rigify_hand_shape_test.py` stop expecting the `*_measure` keys.

**Three things have to be run for real**, since none of this can be established from this side of the socket:

- The [smoke run](../../verification/README.md#running), once, against a real Blender.
- A script in this subdir, `check_preload.py`, that starts `mpfb-mcp` over stdio as a real client and
  prints the instructions' length, the schema total and whether an explicit null is accepted. Then a
  **fresh Claude Code session** with this server registered, which is the only way to confirm the
  delivered text now ends where the source does. Record the client's version here, since the first
  observation did not capture one.
- **One real posing and dressing task in that session**, followed by [measure_transcripts.py](measure_transcripts.py):
  the share of `mpfb_get_pose` calls against writes, for requirement 15, and whether a caller misread a short answer.

## References

- [MCP Tool Schema Bloat: The Hidden Token Tax (and How to Fix It)](https://layered.dev/mcp-tool-schema-bloat-the-hidden-token-tax-and-how-to-fix-it/), Kevin Swiber, 2026-01-16
- [MCP context bloat: the 2026 fixes that actually work](https://mcp.directory/blog/mcp-context-bloat-fix-2026-tool-search-code-mode-progressive-disclosure)
- [Claude Code MCP tool search tips](https://wmedia.es/en/tips/claude-code-mcp-tool-search), the 2 KB figure, and an [issue reporting description cuts near 2,048](https://claudeissues.com/issue/41141-bug) on 2.1.87. A description of 4,094 characters arrived whole on 2026-11-05, so both may be out of date. These are secondary sources, and this request relies on what was observed.
- [FR 016](../done/016-trim-tool-descriptions/README.md), which moved the conventions into the instructions
- [FR 013](../done/013-live-verification/review.md#does-the-tool-surface-fit-its-consumer), which first measured the descriptions
