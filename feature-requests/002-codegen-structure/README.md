# Restructure code generation for readability and growth

**Status:** Accepted

With only two tools implemented, [`src/mpfbmcp/mpfb_codegen.py`](../../src/mpfbmcp/mpfb_codegen.py)
is already 233 lines and holds every tool's payload. Two distinct problems follow from that, and
both get worse with each tool in the
[target catalog](../../specifications/vision.md#target-tool-catalog):

**Structure.** All build logic is central, so adding a tool means editing a shared module that
every other tool also depends on. The module's `__all__` grows one entry per tool, unrelated
payloads sit next to each other, and the one genuinely shared thing — the MPFB bootstrap — is
buried among them. Only the bootstrap is actually common; everything else is tool-private and
belongs with its tool.

**Readability.** The generated Python is a string, and today it is written two different ways:
`_MPFB_STATUS_BODY` is a readable triple-quoted block, while `build_create_human_code()` is a
single 500-character line of escaped newlines and doubled braces. Nothing enforces the readable
form, and the unreadable form is what a developer copies when adding the next tool. Neither form
gets syntax highlighting, linting, or editor indentation help, and neither can be run or
inspected as Python on its own — yet this string *is* the code that does the work.

This request restructures both, and records readability and developer experience in the standing
specifications as prioritized non-functional requirements, so later work does not quietly
regress them. It changes no tool behavior: the code that reaches Blender should do the same
thing before and after.

## Goals

Primary: make the Python that runs inside Blender something a developer edits as ordinary,
highlighted, lintable Python in its own file, and make adding a tool a matter of adding files
rather than editing shared ones.

Secondary: state readability/developer experience as an explicit, prioritized non-functional
requirement in [specifications/architecture.md](../../specifications/architecture.md), so it is a
standing rule rather than a one-off cleanup.

Explicit non-goal: changing what any tool does, what it accepts, or what it returns. This is a
refactor. `mpfb_create_human` and `mpfb_get_status` keep their signatures, docstrings,
annotations and response envelopes.

## Functional requirements

1. Each tool's generated-code payload lives in its **own file**, written as ordinary Python —
   no escaped newlines, no `.format()` placeholders inside the payload, no brace doubling.
2. The MPFB bootstraps (raising and non-raising) remain **shared**, defined once, and are
   composed into a tool's payload rather than copied into it.
3. Adding a new tool requires **no edit to any shared code-generation module** — only a new tool
   module, a new payload file, and the `register()` call in
   [`__init__.py`](../../src/mpfbmcp/__init__.py). This is the objective test of the structural
   goal.
4. Parameters reach the payload as **data, not string interpolation**. A payload file must not
   contain a placeholder that a builder substitutes into; it reads values from a name the
   assembler binds.
5. The assembled source is **unchanged in effect**: for the same inputs, the code sent over the
   socket does what the current code does. Formatting and variable-name differences are
   acceptable; behavioral differences are not.
6. Payload files are **installed with the package** and load correctly from a non-editable
   install (`pip install .`), not only from a source checkout.
7. No new runtime dependency. Assembly uses the standard library only.
8. Readability and developer experience are documented as prioritized non-functional
   requirements in the standing specifications (see [Affected specifications](#affected-specifications)).

## Non-functional requirements

- **Developer experience is the point of this change**, so it is also the acceptance criterion:
  if a developer cannot open a payload file and edit it like normal Python — with highlighting,
  indentation, and a linter that mostly works — the change has not achieved its goal, regardless
  of how clean the module graph looks.
- **Discoverability.** Reading a tool module should reveal the whole tool: its parameters, its
  validation, and where its payload lives. Nothing tool-specific should require knowing about a
  central registry.
- **Safety of parameter injection.** Values must not be able to alter the structure of the
  generated program. Data-based injection (requirement 4) is what guarantees this; a future tool
  taking string input (an asset name, a target name) would otherwise be an injection hole in a
  system whose entire job is to `exec()` generated code.
- **No behavior regression.** See requirement 5. The existing test suite must pass, adjusted only
  where it names moved symbols.
- **Traceability of failures.** Errors from the payload surface as text from inside Blender.
  Assembly must not make it materially harder to map a reported line back to a payload file.

## Architecture

### Target layout

```
src/mpfbmcp/
    codegen/
        __init__.py        # assemble(): bootstrap + params prelude + payload
        bootstrap.py       # _MPFB_MODULE_SCAN and the two bootstrap variants (moved as-is)
        payloads/
            create_human.py
            get_status.py
    tools/
        create_human.py    # unchanged tool surface; calls codegen.assemble(...)
        get_status.py
```

[`mpfb_codegen.py`](../../src/mpfbmcp/mpfb_codegen.py) goes away rather than becoming a shim —
this is a proof of concept with no external consumers, and a compatibility shim would preserve
exactly the central module this request exists to remove. Its two `build_*_code()` functions
disappear: with parameters injected as data, assembly is a single call at the point of use, so
there is nothing tool-specific left for them to hold. Where a tool genuinely needs assembly logic
of its own, that logic lives in its tool module.

### Assembling

One shared entry point, roughly:

```python
def assemble(payload: str, *, bootstrap: str = "raising", params: dict | None = None) -> str
```

returning `bootstrap source + params prelude + payload source`. `bootstrap` selects between the
two variants documented in
[architecture.md](../../specifications/architecture.md#two-bootstrap-variants); `payload` names a
file under `codegen/payloads/`.

The prelude binds one name — `PARAMS` — from a JSON literal:

```python
import json
PARAMS = json.loads('{"scale": 0.1, "macro_detail_dict": {...}}')
```

Build the literal as `repr(json.dumps(params))`: `json.dumps` produces the data, `repr` produces
a valid Python string literal for it. This is what satisfies requirement 4 — no caller-supplied
value is ever parsed as code, only as JSON — and it is also what removes the escaping problem,
since the payload file itself contains no substitution points at all.

Payload files then read `PARAMS["scale"]` and leave `result` bound, the existing convention.
Each payload should open with a docstring naming the assembler-bound names it relies on
(`PARAMS`, and `_MPFB_SERVICES` or `_mpfb_state`/`_mpfb_services` depending on the bootstrap),
since a linter will flag those as undefined — that is the one readability cost of this approach,
and it is worth stating in the file rather than leaving a developer to work it out.

### Pitfalls

- **Payload files must never be imported.** They are `.py` files inside the package tree but they
  are not modules of this package: they reference `bpy` and MPFB services, and importing one on
  the mpfb-mcp side would fail. Keep `codegen/payloads/` **without** an `__init__.py` so it is
  not importable, and load payloads as *resources*
  (`importlib.resources.files("mpfbmcp.codegen").joinpath("payloads/x.py").read_text()`).
- **Packaging.** Because `payloads/` is deliberately not a package,
  `[tool.setuptools.packages.find]` will not pick it up. Add explicit package data to
  [pyproject.toml](../../pyproject.toml):
  `[tool.setuptools.package-data] "mpfbmcp.codegen" = ["payloads/*.py"]`. Requirement 6 exists
  because this is easy to miss — an editable install keeps working while a real install ships a
  package with no payloads.
- **Keep the `.py` extension.** `.py.txt` or `.tmpl` would sidestep the import and packaging
  concerns, but loses exactly the editor support this request is for. The import problem is
  solved by the missing `__init__.py`; the packaging problem is solved by one config line.
- **Line numbers.** Concatenation means a traceback line number refers to the assembled string,
  not the payload file. Keep assembly order fixed (bootstrap, prelude, payload) and emit a
  comment line naming the payload file at the seam, so the offset can be read off the generated
  source when debugging.
- **Move the bootstraps verbatim.** `_MPFB_MODULE_SCAN`, `_MPFB_BOOTSTRAP` and
  `_MPFB_STATUS_BOOTSTRAP` encode decisions made in [FR 001](../done/001-mpfb-get-status/README.md)
  — all candidates rather than the first, `None` and missing-`"SERVICES"` handled separately,
  never importing MPFB submodules. Move them, do not rewrite them; the module docstring
  explaining *why* moves with them to `codegen/bootstrap.py`.
- **`get_status`'s payload is a three-tier build-up**, not a linear script: `bpy`-only fields,
  then module-readable fields, then service-backed fields. That structure is load-bearing (it is
  what makes absence a successful answer) and the existing comments explaining each tier must
  survive the move.

## Affected specifications

- [architecture.md](../../specifications/architecture.md) — two additions:
  - A new standing section on **readability and developer experience as prioritized
    non-functional requirements**, stating that generated code is code and is held to the same
    readability standard as the rest of the repo; that a payload must be editable as ordinary
    Python in its own file; and that where readability and brevity/cleverness conflict,
    readability wins. This is the durable rule NEXT_STEPS asks for, and it applies beyond
    codegen.
  - A statement of the **code-generation layout** as a convention new tools follow: shared
    bootstrap, per-tool payload file, data-based parameter injection, and the rule that adding a
    tool must not require editing shared code-generation modules. This sits naturally beside the
    existing [One module per tool](../../specifications/architecture.md#one-module-per-tool) and
    [Validate before crossing the socket](../../specifications/architecture.md#validate-before-crossing-the-socket)
    sections.
- [vision.md](../../specifications/vision.md) — no change. No tool is added, removed or altered.

Outside the specifications, the repo's [CLAUDE.md](../../CLAUDE.md) describes
`mpfb_codegen.py` by name in its Architecture section, including the two bootstraps and the rule
about resolving services. That section must be updated in the same change, or it will point at a
file that no longer exists.

## Tests

The existing suite is the safety net for requirement 5, and needs adjusting where it names moved
symbols: [tests/test_get_status.py](../../tests/test_get_status.py) imports
`build_get_status_code` from `mpfbmcp.mpfb_codegen`, and both tool tests assert on substrings of
the generated source.

Add or adapt:

- **Characterization check (do this first).** Before refactoring, capture the current output of
  `build_create_human_code(...)` and `build_get_status_code()` to files. After refactoring, diff
  the newly assembled source against them. Differences should be confined to whitespace, the
  parameter prelude, and the seam comment; anything else is a behavior change and should be
  justified or reverted. This is a temporary development aid, not a committed test.
- **Every payload file compiles.** Enumerate `codegen/payloads/*.py` and `compile()` each one on
  its own. This catches a syntax error in a file nothing imports — the obvious new failure mode
  this layout introduces. [test_get_status.py](../../tests/test_get_status.py) already compiles
  assembled source; this extends the idea to the files themselves.
- **Assembly.** `assemble()` selects the right bootstrap, emits a `PARAMS` prelude that round
  trips (exec the prelude, compare `PARAMS` to the input dict), and produces compilable output.
- **Injection safety.** A parameter value containing quotes, a newline, a backslash and a
  `"""` sequence survives assembly as *data*: exec the assembled prelude and assert `PARAMS`
  equals the input, rather than asserting on the source text.
- **Exec-based branch tests keep working.** The `absent` / `not_initialized` / `ok` tests in
  [test_get_status.py](../../tests/test_get_status.py) execute the generated source against a
  stubbed `bpy` and stubbed `sys.modules` entries. They should need no change beyond the import,
  and are the strongest evidence the `get_status` payload survived the move intact.
- **Installed-package load.** Requirement 6 is not covered by a source-tree test run. Verify it
  manually once: build the package and install it into a throwaway venv, then import `mpfbmcp`
  and assemble both payloads. Worth an explicit note in the commit, since the failure only
  appears for someone installing normally.

**Real-Blender verification.** Unit tests cannot show that the assembled code still works inside
Blender (see
[architecture.md](../../specifications/architecture.md#no-direct-dependency-on-mpfb-or-blender_mcp)).
Because this refactor is behavior-preserving by design, one smoke pass is enough: with Blender +
MPFB + blender_mcp running, call `mpfb_create_human` once and `mpfb_get_status` once and confirm
both still return `status: "ok"` with the same shape as before. This is a *separate*, much
smaller check than the manual verification [FR 001](../done/001-mpfb-get-status/README.md#verification-status)
still owes — that debt is not settled by this request and should not be folded into it.

## References

- [NEXT_STEPS.md](../NEXT_STEPS.md) — originating entry, "Code structure and readability".
- [FR 001](../done/001-mpfb-get-status/README.md) — introduced the second bootstrap and the
  three-tier status payload; its decisions must survive this move unchanged.
- [architecture.md](../../specifications/architecture.md#resolving-mpfb-from-generated-code) —
  the bootstrap rules being relocated, not rewritten.
