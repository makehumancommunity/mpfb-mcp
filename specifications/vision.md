# Vision

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).

This document says why mpfb-mcp exists, how it gets there, and what decides whether something
becomes a tool. It deliberately does **not** describe what any tool returns: that lives in the
tool's own module docstring, one line each in [README.md](../README.md), and in the feature
request that added it.

## Goal

MPFB (MakeHuman Plugin For Blender) exposes a rich Python service layer
(`HumanService`, `TargetService`, `AssetService`, etc. — see `../mpfb2/`) for creating and
editing MakeHuman characters, but that layer is only reachable from *inside* a running
Blender process. mpfb-mcp's goal is to make MPFB's capabilities available to LLM agents (and
other MCP clients) as a normal set of MCP tools, without requiring any change to MPFB or to
the Blender MCP tooling it relies on.

**"Available" is a low bar; the goal is *efficiently* available.** An agent driving MPFB through
a generic code-execution tool can already do anything — it would have to read MPFB's source to
know what to call, guess which of two similarly named functions is the right one, and discover
by failure that a rig must be added before the clothes. Every tool here exists to remove one of
those, so that a correct MakeHuman character is the *cheap* outcome rather than the lucky one.
The measure of the project is not how much of MPFB is reachable but how few round trips, and how
little source-reading, a competent agent needs to get a character right.

## Approach: piggyback, don't fork

mpfb-mcp is a normal Python package, installed like any other MCP server, that runs as its
own MCP server process. It talks to the *existing, unmodified*
[blender_mcp](../../blender_mcp) add-on over the same TCP socket blender_mcp itself uses,
sending it generated Python code to execute inside Blender:

```
Claude / other MCP client
   |
   |-- stdio --> blender_mcp  (generic Blender tools)   --\
   |                                                       >-- TCP :9876 --> blender_mcp add-on --> exec() in Blender
   |-- stdio --> mpfb-mcp     (MPFB-specific tools)     --/                                            |
                                                                                                        v
                                                                                             MPFB services (bl_ext.*.mpfb)
```

The user enables MPFB and the blender_mcp add-on in Blender as usual, starts blender_mcp's
socket server from its preferences, and configures **two** MCP servers in their client. No new
Blender extension, no fork of blender_mcp, and no coordination of install order between MPFB
and blender_mcp is required. See [architecture.md](architecture.md) for how this is
implemented.

## What makes something a tool

MPFB has hundreds of callable service functions. Wrapping them one for one would produce an API
that is complete and useless — the agent would still have to know which to call, in what order,
with which of MPFB's several defaults. These are the tests a candidate tool has to pass.

- **A tool is named for something a user wants, not for a service function.** Several exist with
  no single MPFB function behind them, because the *intent* is the unit:
  `mpfb_symmetrize_targets` repairs an asymmetric face, which MPFB's own symmetry setting cannot
  do after the fact; `mpfb_remove_asset` exists because deleting the object is the obvious wrong
  way and leaves a mask modifier behind. Conversely, one MPFB function may be reached by two
  tools, or none.
- **A catalogue and the tool that acts on it are designed as a pair.** Every identifier a
  catalogue reports feeds a *named argument* of a specific acting tool, and that pairing is
  decided when the catalogue is designed, not afterwards — otherwise the caller is left
  assembling a string, which is the guesswork a catalogue exists to remove. The obligations on
  both halves are in
  [How tools name things that can be added](tool-interface.md#how-tools-name-things-that-can-be-added)
  and [An acting tool accepts every identifier its catalogue reports](tool-interface.md#an-acting-tool-accepts-every-identifier-its-catalogue-reports).
- **MPFB's own UI is the fidelity bar.** A character mpfb-mcp produces must be reproducible
  through MPFB's panels — same shape keys, same node tree, same weights. Where a service default
  and the panel's default disagree, the panel wins; where MPFB's own code paths disagree, one is
  chosen and named. See [mpfb-integration.md](mpfb-integration.md).
- **A concept MPFB's UI has but its services do not can still be a tool.** A modeling *modifier*
  — a slider from -1.0 to +1.0 built from a pair of opposing targets — is not a `TargetService`
  idea at all, and a tool that could only set individual shape keys would produce characters
  MPFB's own interface cannot represent.
- **A tool may report something MPFB shows nowhere.** An agent cannot look at the viewport, so
  facts a human reads off the screen have to be in the response — which sides of a face disagree,
  which garments were attached while there was no rig, what a refit has just invalidated.
- **Splitting a tool can be what makes an order expressible.** Rigify generation is its own tool
  rather than a flag, because "meta rig, then clothes, then generate" cannot be written as one
  call. See
  [A tool reports an ordering constraint it cannot enforce](mutating-tools.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce).

## Target tool catalog

The surface is four capability areas. What matters is that an agent can get through all of them
without reading MPFB's source; which tools that takes is an implementation question, and the
answer changes.

| Area | An agent must be able to | Today |
|---|---|---|
| **Introspection** | ask what is already there, and what state it is in, before acting — always cheaply, and always getting an answer rather than an error | 5 tools |
| **Catalogues** | learn what *could* be added, each entry named exactly as the acting tool will want it | 4 tools |
| **Creation and modification** | build a character and change it: phenotype, detail morphs, rig, garments, materials — and undo a mistake; and **keep** it, as a preset that outlives the session | 14 tools |
| **Documentation** | answer "how does MPFB do X" without the client shipping its own copy of the manual | 2 tools |

[README.md](../README.md) lists the twenty-five that exist, grouped this way;
[CLAUDE.md](../CLAUDE.md#the-twenty-five-tools) gives one line each and points at the module
docstring that explains it.

**What is still missing**, and why each is worth having:

- `mpfb_get_human_summary` — macro details, equipped assets, rig, skin and active targets for one
  character in a single answer. Today that is five calls, which is five round trips to establish
  what an agent needs before almost any modification. Its macro half must be produced by calling
  the same read `mpfb_get_macro_details` uses, not by a second implementation that can diverge.
- `mpfb_search_docs` — ranked search over MPFB documentation *bundled with the client*, mirroring
  how blmcp exposes Blender's RST reference. Likely sourced from `../../makehuman-static-website`.
  [FR 024](../feature-requests/done/024-documentation-urls/README.md) took the small half of this
  area — `mpfb_list_urls` and `mpfb_list_docs` hand out addresses, so an agent can be pointed at
  the authoritative document instead of guessing. What is left is the half that needs the text
  itself: ranking a query against content nobody has fetched is not something an address can do,
  and it is the part that would let an agent answer rather than delegate. Note that
  [no network connection](architecture.md#mpfb-mcp-opens-no-network-connection-except-the-one-to-the-add-on)
  is now a standing constraint, so the documentation such a tool searches has to be shipped or
  vendored rather than retrieved.

Scoped and queued work is in
[NEXT_STEPS.md](../feature-requests/NEXT_STEPS.md); what has landed, and what each effort
decided, is in [HISTORY.md](../feature-requests/HISTORY.md). A new tool gets its own feature
request when it is scoped.

## Resolved: which "blender mcp"? Both

There are two unrelated projects called "blender mcp": blender lab's implementation (the
primary backend, at `../../blender_mcp`, which this project piggybacks on) and a separate,
more feature-rich [community implementation](https://github.com/ahujasid/blender-mcp), a local
clone of which is available at `../../ahujasid-blender-mcp`. Some users have the latter
installed instead of the former.

**Supporting both as backends is a goal.** blender lab's stays the reference one — it is what
the tools are written and live-verified against — but a user who already runs the community
add-on should be able to point mpfb-mcp at it rather than install a second one.

Comparing the two add-ons showed this to be a contained change rather than a second
implementation: they differ in framing, in the envelope they answer with, and in how a result
gets back, but nothing about that reaches a tool. The seam and what it costs are in
[Supporting a second backend](architecture.md#supporting-a-second-backend). The work is not
scoped into a feature request yet; see
[NEXT_STEPS.md](../feature-requests/NEXT_STEPS.md#second-backend-the-community-blender-mcp).
