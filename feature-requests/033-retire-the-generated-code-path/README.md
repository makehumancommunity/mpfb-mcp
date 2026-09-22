# Retire the generated-code path

**Status:** Accepted

This is [stage 4 of the pivot](../NEXT_STEPS.md#4-retire-the-generated-code-path), and it is the
only stage that deletes rather than adds. [FR 028](../done/028-pivot-to-specific-addon/README.md)
decided that MPFB's Blender-side logic belongs in an add-on of our own,
[FR 029](../done/029-bridge-transport-and-skeleton/README.md) built it,
[FR 030](../done/030-backend-seam/README.md) built the seam and migrated one tool, and
[FR 031](../done/031-introspection-and-catalogues-migrated/README.md) migrated nine more, and
[FR 032](../done/032-creation-and-modification-migrated/README.md) migrated the remaining
fourteen — fourteen rather than fifteen, because `mpfb_list_docs` never crossed the socket to begin
with. **That has landed**, so every tool that crosses the socket has a bridge command, the default
backend is the bridge, and a machine nothing uses is still being maintained: 9,416 lines under
[codegen/](../../src/mpfbmcp/codegen), a wire client duplicating a third party's protocol, a
session source cache, and something on the order of 6,000 lines of tests executing payloads
against stubs — plus a second prerequisite in every install instruction and a second transport in
almost every module docstring in the package.

**The goal is that the generated-code path stops existing anywhere except in the record of why it
did.** After this effort, `feature-requests/` is the only directory in the repository that refers
to it — the finished requests keep their text unchanged, because a historical artifact that has
been edited to describe a system it predates is worth less than one that has not. Everything else
— `src/`, `tests/`, `bridge/`, `verification/`, `specifications/`, `README.md`, `CLAUDE.md`,
`pyproject.toml` — reads as though there had only ever been one way to reach Blender.

**Nothing here is allowed to change what a tool answers.** This is a deletion, and the property
that makes it safe is that the thing being deleted is already unused by the time it starts. FR 032
arranged that deliberately: it flipped the default in its **last** commit, after comparing both
paths field by field and scene by scene, so by the time this effort starts the generated path has
been carrying nothing for a while rather than carrying everything until yesterday.

**Three things FR 032 left that are this effort's to collect**, none of which existed when this
request was written:

- [tests/generated_path.py](../../tests/generated_path.py) and the twenty-five `setUpModule`
  lines that use it. It exists only because those modules had to say they were about a path that
  is no longer the default; with the path gone, so is the reason.
- The measured share of a test module that goes with its payload, now known across all
  twenty-four rather than estimated: 27% for the dullest tool, ~60% over FR 031's nine, **58%**
  over FR 032's fourteen. Two outliers are worth expecting rather than being surprised by —
  `mpfb_list_urls` at 24%, because most of that module tests the client-side merge that stays, and
  `mpfb_create_human`, which has no payload layer at all.
- The transitional two-add-on prerequisite in
  [verification/README.md](../../verification/README.md), which FR 032 made the *default* one
  rather than an alternative. Removing it is this effort's, and the README already says so.

## Goals

**Primary. Delete the generated-code path.** [codegen/](../../src/mpfbmcp/codegen) entire — the
assembler, the bootstrap strings, the source loader, twenty-four payloads and seven shared
fragments — plus [shared_cache.py](../../src/mpfbmcp/shared_cache.py) and
[connection.py](../../src/mpfbmcp/connection.py), the `pyproject.toml` package-data that ships
payloads, and every test that exists to exercise any of it.

**Primary. The seam keeps its name and its callers, and loses its branch.**
[backend.py](../../src/mpfbmcp/backend.py) survives as a single-transport `send()`:
`MIGRATED_COMMANDS`, `MPFB_MCP_BACKEND`, `BACKENDS` and the envelope mapping go, and no tool module
changes as a consequence. This was chosen over deleting the seam and having tools call
`bridge_connection.send_command()` directly: one indirection is a cheaper thing to carry than
twenty-five edited tool modules in an effort whose whole claim is that it changes no behaviour.

**Primary. Sweep the documentation, and treat it as part of the deletion rather than as follow-up.**
The specifications, `CLAUDE.md`, `README.md`, `verification/README.md` and the module docstrings in
`src/` are all written around two transports. The acceptance test is mechanical (requirement 8), so
that "mostly done" is not a state this can finish in.

**Primary. Fold what the path taught into the specifications and HISTORY, rather than losing it
with the code.** Some of what is being deleted is the only place a real finding is written down —
the 4 KB cost model, why the source cache caches source and not answers, why a payload was a real
file. A finding does not become false because the code it was measured on is gone.

**Secondary. `verification/` runs against one add-on, in one configuration.** The transitional
two-add-on prerequisite FR 030 created goes away here, which is what it was always going to do.

**Explicitly not goals.** Migrating anything — [FR 032](../done/032-creation-and-modification-migrated/README.md)
must be complete before this starts (requirement 1). Changing any tool's name, description, arguments or answer. Changing anything in
`bridge/` beyond what the harness rewrite needs. Touching
[bridge_connection.py](../../src/mpfbmcp/bridge_connection.py)'s hand-kept `PROTOCOL_VERSION`
duplicate, which is a different duplication with a different reason and is not part of this.
And **filing the 4 KB chunked read upstream**: NEXT_STEPS currently says to do it here, and that is
being changed rather than honoured (requirement 11) — it is not an engineering task, it does not
gate anything, and attaching it to a deletion effort is how it ends up half-done.

## Functional requirements

1. **The effort refuses to start while any tool still has a payload.** The first thing written is
   the check that says so: every tool `build_server()` registers either has an entry in
   `MIGRATED_COMMANDS` or has no payload at all (`mpfb_list_docs`, and nothing else). If that does
   not hold, [FR 032](../done/032-creation-and-modification-migrated/README.md) is not finished and
   this request is not startable. This is a requirement
   rather than an assumption because the deletion is irreversible in practice — a payload deleted
   while its tool still needs it is not caught by any test that survives the same commit.

2. **The generated path is gone from the installed package.** Deleted:
   `src/mpfbmcp/codegen/` (including `payloads/`, `shared/`, `bootstrap.py`, `shared_loader.py`),
   `src/mpfbmcp/shared_cache.py`, `src/mpfbmcp/connection.py`. In `pyproject.toml`, the
   `[tool.setuptools.package-data]` entry for `mpfbmcp.codegen` goes; `namespaces = false` is
   re-examined rather than reflexively kept, and whichever way it lands, the comment above it —
   which currently explains itself entirely in terms of payloads — is rewritten to say what is
   true afterwards.

3. **`backend.send()` becomes one code path, and its signature stops advertising a second.**
   `MIGRATED_COMMANDS`, `command_for()`, `BACKENDS`, `BACKEND_BLENDER_MCP`, `BACKEND_VARIABLE`,
   `preferred_backend()`, `as_common_envelope()` and `ERROR_COMMAND_FAILED` are removed;
   `shared`, `cached_shared` and `strict_json` are removed from the signature, since all three are
   properties of assembling a program. The module's docstring is rewritten rather than trimmed: it
   is currently an essay about why there are two transports, and what should remain is an
   explanation of why a tool calls a seam at all when there is one.

   Two details that must not be skipped. `as_common_envelope()` exists to give a generated-code
   failure the `error` slug the bridge writes itself — confirm against
   [command_server.py](../../bridge/mpfb_bridge/command_server.py) that every bridge error envelope
   carries `error` before deleting the mapping, rather than inferring it from the docstring. And
   **`MPFB_MCP_BACKEND` becoming meaningless must not be silent**: a value left in somebody's
   MCP client configuration should produce one line through the `mpfbmcp` logger saying the
   variable is no longer read — never on stdout, which is the JSON-RPC channel.

4. **The record has one unit again.** In [observability.py](../../src/mpfbmcp/observability.py):
   `begin()`, `tool_name_from_program()`, the payload-seam marker convention, `_PROGRAM_KEY` and
   `_PROGRAM_EXTENSION` go with the programs they described. What must not change is the record a
   bridge call already writes: same directory layout, same `index.tsv` columns and meanings, same
   bytes in the `.json` and the request file. The renaming that made a request "a program on one
   path and a command on the other" collapses back to one word, and the docstrings that explain the
   distinction lose it.

5. **`verification/` stops using `send_code()`, and says plainly what that costs.**
   [harness.py](../../verification/harness.py)'s `probe()` is the harness's own channel into
   Blender and has no replacement in the bridge's closed vocabulary; the decision taken for this
   request is that **the harness is rewritten on commands that already exist rather than the
   bridge growing instrument-serving ones**. So `snapshot()`, `ensure_scratch_scene()`,
   `cleanup_scratch_scene()`, `rename_object()`, `smoke.py`'s hand-assembled `get_status` program
   and the record's traceback item are each either re-expressed through an existing command or
   dropped.

   **Each one that narrows is named in [verification/README.md](../../verification/README.md)**,
   in the section that already exists for what the smoke run deliberately does not check. The
   snapshot is the significant loss and should be described as one: today it compares twelve
   `bpy.data` collections plus `is_dirty` before and after, which is what turns "the run deleted
   what it made" from a claim into an assertion, and what a command-based replacement can see is
   narrower. Under-reporting that is worse than losing it. If the conclusion during implementation
   is that the scratch-scene discipline cannot survive at all, that is a finding to write down and
   raise, not to route around by adding an `exec` command to the bridge — which would reintroduce
   the property the whole pivot exists to remove.

   The two documented invocations collapse to one: `MPFB_MCP_BACKEND=bridge` disappears, and the
   prerequisite becomes MPFB and the MPFB Bridge in one Blender, with blender_mcp named nowhere.

6. **The tests that exist to exercise the generated path are deleted outright.** Namely: every
   payload-layer test class in the twenty-four tool test modules (the "frozen" third layer FR 030
   and FR 031 created, measured at roughly 60% of a migrated module),
   [test_codegen.py](../../tests/test_codegen.py),
   [test_connection.py](../../tests/test_connection.py),
   [test_shared_cache.py](../../tests/test_shared_cache.py),
   [test_fragment_drift.py](../../tests/test_fragment_drift.py),
   [fake_addon.py](../../tests/fake_addon.py) and
   [blender_stubs.py](../../tests/blender_stubs.py). They are not re-examined for content:
   [FR 032](../done/032-creation-and-modification-migrated/README.md) is the effort that moves a check
   into `bridge/test/`, and doing it again here would be doing it
   late and twice.

   **Two things inside that set are not generated-path machinery and must survive the deletion**,
   which is the one place this requirement needs care rather than a `git rm`:

   - `blender_stubs.py` is 3,544 lines and holds `PresetTestCase`'s real config directory and
     `MeshAssetTestCase`'s real asset library, which wrapper-layer tests use for checks that run
     **before** any transport is chosen — the preset name whitelist is the clearest case. What a
     surviving test needs moves to the module that needs it, or to a much smaller fixtures module;
     what only a payload needed goes.
   - `test_codegen.py` holds the class that runs the preset-name rule as **three** implementations
     over one table of names. The fragment dies, so the rule then lives in two places —
     [preset_names.py](../../src/mpfbmcp/preset_names.py) and
     [bridge/mpfb_bridge/shared/preset_files.py](../../bridge/mpfb_bridge/shared/preset_files.py) —
     and the reason it is checked at all is unchanged: a disagreement lets a preset be written
     under a name that cannot be loaded back. That class moves, as a two-way check, into a module
     that survives.

   `python3 -m unittest discover -s tests` must pass after the deletion, must still find no test
   that imports `bpy`, and [test_verification_smoke.py](../../tests/test_verification_smoke.py)'s
   coverage rule — one smoke item per registered tool — must still hold.

7. **`bridge/` is checked for what it inherited, not assumed clean.** The bridge's own modules and
   tests were written during the migration and refer to payloads and to the generated path in
   docstrings, for the good reason that a command and the payload it replaced had to be findable
   from each other. Those references become dangling here, and `bridge/mpfb_bridge/shared/`'s
   stated reason for mirroring `codegen/shared/` name for name expires with the directory it
   mirrors. Rewrite them; keep the directory and the names, which are fine on their own merits.

8. **The documentation sweep has a mechanical acceptance check.** After the effort,

   ```bash
   grep -rIE "send_code|codegen|generated (code|program)|blender_mcp|payload|shared fragment" \
     --exclude-dir=.git --exclude-dir=feature-requests --exclude-dir=__pycache__ .
   ```

   returns nothing that describes the retired path as current. The check is a grep because the
   alternative is a judgement made thirty times, and the counting in this repository's own
   documentation has drifted before ([FR 020](../done/020-trim-claude-md/README.md) found five
   factual errors surviving in exactly this way). A hit that is genuinely about something else —
   the bridge's own payload-free wire, a URL containing the word — is fine and is left; a hit
   phrased in the present tense about a machine that no longer exists is not.

   The documents this touches, and what each needs, are in
   [Affected specifications](#affected-specifications). `CLAUDE.md` is the largest single edit and
   is a *map* edit, not a narrative one: the Project status section stops being about a pivot in
   flight, Commands loses the backend table and the blender_mcp timer-interval note, Architecture
   loses one of its two diagrams and the codegen/shared_cache/connection rows from its module
   table, the tool table loses twenty-five "**Migrated** (FR 031)" annotations that no longer
   distinguish anything, the test table loses its deleted rows, and the test count is re-measured
   rather than adjusted by arithmetic.

9. **A design argument that rests on the retired cost model is restated, not deleted.** This is
   the requirement most likely to be skipped, because the sentences in question read as background
   rather than as claims. The known cases:

   - **`mpfb_set_targets` is batched "because a round trip costs ~250 ms and a target costs
     milliseconds".** The batching stays — it is a settled interface and a good one — but its
     stated reason is a number measured on a transport that no longer exists. FR 030 measured the
     bridge at 58 ms against blender_mcp's 461 ms for one tool; restate the argument on a number
     that is true, or state it as an interface decision that no longer needs the number.
   - **`mpfb_list_assets`' cap-and-page and the tool-description budget** are about the size of an
     *answer* and of what an MCP client downloads, not about program size. Confirm that, and leave
     them alone — this requirement is about restating what changed, not about rewriting what did
     not.
   - **FR 017's finding that "not sending something beats not doing it"** (the 4 ms category scan
     against 18 KB of code describing it) is a fact about the retired path and becomes something
     HISTORY.md remembers.

   The general rule to apply: any claim in `src/` or `specifications/` whose number came from the
   generated path either gets a bridge number or moves into `feature-requests/`.

10. **What the path taught is folded before it is deleted.**
    [architecture.md](../../specifications/architecture.md#the-generated-code-path-what-runs-today-and-is-being-retired)'s
    generated-code part stops being a section of a standing specification. Its durable content goes
    to [HISTORY.md](../HISTORY.md) — the 4 KB-per-tick cost model and how it was measured, the
    session source cache's central lesson (**cache source, never what a fragment computed**, so
    nothing can go stale and no tool needs a `refresh`), and why a payload was a real file rather
    than a string literal. Three things in that part are **not** historical and must be kept, in
    the specification, reworded so they no longer depend on generated code to state:
    resolving MPFB by scanning `sys.modules` rather than importing a submodule; the rule that MPFB
    submodules are never imported directly; and that both ends validate.

11. **NEXT_STEPS and HISTORY are left correct, including the entries this effort does not
    perform.** Stage 4 moves out of [NEXT_STEPS.md](../NEXT_STEPS.md) into
    [HISTORY.md](../HISTORY.md) per the [lifecycle](../CLAUDE.md#lifecycle); stage 5 (publish and
    document) remains and becomes the only open stage. Two other entries in that file point at
    machinery this effort removes and must be repaired rather than left dangling: **Handle the
    4 KB chunked read** says to file it "in the retirement stage", which is no longer true — it
    becomes a standalone item, and its justification must survive without the architecture.md
    section it cites; and **Finding, downloading and installing asset packs** offers "retrieval on
    the Blender side, in generated code" as one of its two options, which is now only reachable as
    a bridge command. The **Superseded: second backend** entry keeps its text, but its links to
    deleted spec anchors need re-pointing.

12. **No tool's interface or answer changes.** Twenty-five tools, the same names, the same
    descriptions, the same envelopes. The description budget is re-measured before and after and
    must be unchanged, since nothing here is supposed to touch a description.

## Non-functional requirements

**Honesty about what verification loses.** The one place this effort can quietly make the project
worse is requirement 5: a harness that checks less while reporting the same "pass" is a worse
instrument that looks identical. Whatever narrows is written down where somebody reading a passing
run will see it.

**Reversibility while it is in progress.** The work is a sequence of coherent commits — the
harness, then the seam, then the deletion, then the documentation — rather than one. A bisect
across this effort should land on a specific thing, and `git revert` of the deletion commit should
be a usable emergency answer for as long as the release after it is young.

**The documentation must read as finished, not as edited.** The specifications are written as
continuous argument, and deleting the second half of a comparison leaves sentences that are
grammatical and no longer say anything ("on the bridge it is our own protocol and the duplication
problem goes away with it" is a comparison with nothing to compare). Every paragraph that mentions
two transports is rewritten, not cut at the seam.

**No new capability, and no tidying.** A deletion effort that also improves something cannot be
reviewed as a deletion. Anything noticed on the way out that is worth doing is worth a line in
NEXT_STEPS.md instead.

## Architecture

**The order matters, and it is not the order the deletion list suggests.**

1. **The precondition check first** (requirement 1), as a script in this subdir. Everything else
   is unsafe until it passes.
2. **The verification harness second**, while the generated path still works. `harness.py` is the
   only consumer of `connection.py` that is not a tool, and it is the thing that proves the
   deletion did no harm — rewriting it after deleting its channel leaves no way to check the
   claim. Land it, run the smoke in both configurations, and only then continue.
3. **The seam third**, which is one module and touches no tool.
4. **The deletion fourth**, files and tests together.
5. **The documentation last**, when the grep in requirement 8 can actually be run.

**Pitfalls, each of which has bitten this repository or is one line away from doing so:**

- **`tests/blender_stubs.py` is not purely payload machinery** (requirement 6). Deleting it
  wholesale will take wrapper-layer fixtures with it, and the failure will look like a test that
  was always unnecessary.
- **The payload-seam marker convention spans two directories.** `observability.py` finds a tool's
  name from `# --- payload: <name>.py ---`, and `verification/harness.py`'s `probe()` writes that
  marker by hand so its own records are named. They go together or the harness's records silently
  become `unnamed`.
- **`preset_names.py` stays.** It is the rule on this side of the socket and it is the reason a
  preset name cannot become a path; only the fragment goes. Its docstring cites
  `codegen/shared/preset_files.py` and needs to cite the bridge module instead.
- **`reference/` stays and is unrelated.** `urls.py` and `docs.py` are vendored tables that are
  never sent anywhere; `test_reference_drift.py` stays with them. They mention blender_mcp only in
  passing and are the most likely false positive in requirement 8's grep.
- **Do not let this effort absorb FR 032's tail.** If a tool turns out to be unmigrated once the
  work starts, the answer is to finish FR 032, not to migrate it here — the two efforts have
  opposite risk profiles and reviewing them as one commit series loses that.

## Affected specifications

All seven, which is itself a statement of how deep the two-transport assumption goes:

- **[architecture.md](../../specifications/architecture.md)** — the largest edit. *The generated-code
  path* and its four subsections (*What a call costs is the size of its program*, *Code-generation
  layout*, *Generated code may keep its own source inside Blender*, *Shared fragments*) are removed
  per requirement 10. *No direct dependency on MPFB or blender_mcp* keeps its rule and loses its
  second clause everywhere; consider whether its title should still name blender_mcp. *Supporting a
  second backend* keeps its name — FR 028 was explicit that it earned it — but is rewritten as the
  decision it became rather than as a plan in progress. *Resolving MPFB* keeps its substance and
  stops being about generated code. *mpfb-mcp opens no network connection except the one to the
  add-on* keeps its rule and re-points its "the add-on" at the bridge.
- **[testing.md](../../specifications/testing.md)** — *The unit suite is two layers* becomes one
  layer plus the bridge's harness. *A migrated tool is tested where it runs* stops being about
  migration and becomes the standing rule for all tools, including the "frozen third layer"
  paragraphs and the 27%/60% measurements, which move to HISTORY. *Two harnesses, split at the
  directory boundary* is unaffected in substance and keeps its hard constraint. The closed list of
  what stays client-side loses its fragment-drift entry.
- **[observability.md](../../specifications/observability.md)** — *Diagnostics attach at the socket
  boundary, never to the program* keeps its rule and loses "twenty-five tools crossing two
  functions" and the three bullets about what the second transport changes. Its title's "never to
  the program" is worth re-reading: the rule is about not instrumenting inside Blender, which
  survives, but the wording is generated-path wording.
- **[tool-interface.md](../../specifications/tool-interface.md)** — *How generated code addresses
  objects* is a section title naming a machine that is gone; the rules in it (name-based
  addressing, `in_current_scene`, `view_layer.objects.active`) are unchanged and true of bridge
  commands. Rename and reword. *Validate before crossing the socket* is unaffected.
- **[mutating-tools.md](../../specifications/mutating-tools.md)**, **[responses.md](../../specifications/responses.md)**,
  **[mpfb-integration.md](../../specifications/mpfb-integration.md)** — no structural change
  expected; each mentions payloads, generated code or the round-trip cost in passing, and each
  needs requirement 8's grep run over it and requirement 9 applied to any number it quotes.
- **[README.md](../../specifications/README.md)** — *Which machine these documents describe* is
  written explicitly about the transition and is rewritten to describe one machine.

Outside `specifications/`: [CLAUDE.md](../../CLAUDE.md) (requirement 8),
[README.md](../../README.md), [verification/README.md](../../verification/README.md)
(requirement 5), [bridge/test/README.md](../../bridge/test/README.md) and `pyproject.toml`.

## Tests

**No new unit tests, and that is the point.** The suite shrinks; what remains is the wrapper layer,
the two wire/seam modules, the record, the reference tables and the smoke-coverage rule. Two
existing checks *move* rather than die (requirement 6): the preset-name rule as a two-way check,
and whichever `blender_stubs.py` fixtures a surviving wrapper test needs.

**The unit suite cannot establish anything about this effort's central claim**, which is that
twenty-five tools still work when the code half of them used to run through is gone. That is a live
check, and it belongs in this subdir as `check_retirement.py`, run during the effort:

1. Against a Blender with **MPFB and the MPFB Bridge enabled and blender_mcp not installed or
   disabled** — which is the actual proof, and is the first time in the project's life that
   configuration has been exercised.
2. It runs the full smoke (`verification/smoke.py`) in that Blender and asserts all twenty-five
   tools answer, with the same `skipped` set the pre-deletion run reported for the same install.
3. It compares each tool's answer against the last recorded pre-deletion run in
   `verification/results/`, field by field, and names any difference. A difference is not
   automatically a failure — an asset library changes, a cache warms — but an unexplained one is.
4. It asserts the harness rewrite (requirement 5) did not weaken what it still claims: the scratch
   scene is created and removed, and whatever the narrowed snapshot does compare, compares.

**Run the smoke in both configurations before the deletion commit**, so the comparison in step 3
has something honest to compare against. That is the last useful thing the generated path ever
does.

Nothing is added to [verification/](../../verification/): this effort introduces no tool, and the
twenty-five items it already has are exactly what it needs.

## References

- [NEXT_STEPS.md, stage 4](../NEXT_STEPS.md#4-retire-the-generated-code-path) — the entry this
  request implements.
- [FR 028](../done/028-pivot-to-specific-addon/README.md) — the decision, and the analysis
  documents beside it.
- [FR 032](../done/032-creation-and-modification-migrated/README.md) — the effort that must land
  first, and which flips the default backend to the bridge so that this one deletes a path nobody
  has been using.
- [FR 030](../done/030-backend-seam/README.md) — the seam, the first migration, and the
  461 ms/58 ms measurement requirement 9 needs.
- [FR 031](../done/031-introspection-and-catalogues-migrated/README.md) — nine migrations, the
  60% test-layer rate, and the fragment-drift check that dies here.
- [FR 020](../done/020-trim-claude-md/README.md) — why requirement 8's acceptance check is a grep
  rather than a reading.
- [FR 023](../done/023-verification-smoke-test/README.md) — why this effort's live check is a
  script in its own subdir and adds nothing permanent to `verification/`.
