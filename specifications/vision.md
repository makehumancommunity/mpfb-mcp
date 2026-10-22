# Vision

> **Visionary specification.** This describes the *intended end state* of the system, not
> necessarily the current implementation; where the code diverges, the intent stated here
> governs. See [Status of these documents](README.md#status-of-these-documents).
>
> **This document was rewritten by [FR 028](../feature-requests/done/028-pivot-to-specific-addon/README.md)
> to describe the bridge, and since
> [FR 032](../feature-requests/done/032-creation-and-modification-migrated/README.md) the bridge is
> what an unconfigured install runs.** The generated-code path is kept working one variable away
> until [FR 033](../feature-requests/done/033-retire-the-generated-code-path/README.md) deletes it; see
> [What runs today](#what-runs-today).

This document says why mpfb-mcp exists, how it gets there, and what decides whether something
becomes a tool. It deliberately does **not** describe what any tool returns: that lives in the
tool's own module docstring, one line each in [README.md](../README.md), and in the feature
request that added it.

## Goal

MPFB (MakeHuman Plugin For Blender) exposes a rich Python service layer
(`HumanService`, `TargetService`, `AssetService`, etc. — see [mpfb2](https://github.com/makehumancommunity/mpfb2)) for creating and
editing MakeHuman characters, but that layer is only reachable from *inside* a running
Blender process. mpfb-mcp's goal is to make MPFB's capabilities available to LLM agents (and
other MCP clients) as a normal set of MCP tools, **without requiring any change to MPFB itself**.

**"Available" is a low bar; the goal is *efficiently* available.** An agent driving MPFB through
a generic code-execution tool can already do anything — it would have to read MPFB's source to
know what to call, guess which of two similarly named functions is the right one, and discover
by failure that a rig must be added before the garments. Every tool here exists to remove one of
those, so that a correct MakeHuman character is the *cheap* outcome rather than the lucky one.
The measure of the project is not how much of MPFB is reachable but how few round trips, and how
little source-reading, a competent agent needs to get a character right.

**A second measure was added by [FR 028](../feature-requests/done/028-pivot-to-specific-addon/README.md):
install friction.** MPFB's users are largely hobbyists who found it through a tutorial and
installed it with one click from Blender's extension platform. A capability that costs them a
terminal, a virtual environment and a hand-edited JSON file is, for that audience, a capability
that does not exist. The number the project is judged by is Blender-side pieces to install, and
the target is one.

## Approach: a bridge add-on of our own

MPFB's Blender-side logic lives in a **companion Blender extension, the MPFB Bridge**, which
runs a command server on a port of its own and dispatches a **closed vocabulary** of named
commands. mpfb-mcp is a thin client: it validates arguments, sends a command name and its
parameters, and shapes the answer into an MCP response.

```
Claude / other MCP client
   |
   |-- stdio --> mpfb-mcp   (MPFB-specific tools; validates, then sends a command)
                    |
                    |  {"command": "...", "params": {...}} + NUL, over TCP 127.0.0.1:9877
                    v
            MPFB Bridge add-on   -- looks the name up in a fixed table, and runs nothing else
                    |
                    v
            MPFB services (bl_ext.*.mpfb), reached by the sys.modules scan MPFB documents
```

Four properties follow, and they are the whole argument for this shape:

- **No caller-supplied code is executed, ever.** A request names a command; a name that is not
  in the table is refused with an error listing the ones that are. This is a claim a sceptical
  user can check by reading one short file, which is why the vocabulary is a literal table in a
  module of its own. Both general-purpose Blender MCP add-ons are, by construction, arbitrary
  code execution into Blender; that is defensible for a proof of concept and awkward as a
  recommendation to a hobbyist.
- **The wire carries parameters, not programs**, so what a call costs stops being a function of
  how much source describes it. A whole mechanism existed to manage that tax — a per-session cache
  of fragment *source* inside Blender, keyed by a hash of itself, with a re-send-once recovery when
  Blender turned out not to hold it — and this shape does not levy the tax, so the mechanism went
  with it.
- **MPFB is not modified, and does not know the bridge exists.** The bridge reaches it through
  `MPFB_CONTEXTUAL_INFORMATION` and the `sys.modules` scan MPFB documents and uses in its own
  test suite — the supported entry point for exactly this, not a trick. MPFB's manifest, its
  extension listing, its review cycle and its release cadence are untouched.
- **Installation is the consent.** A user who does not want an AI control surface near their
  character generator simply never installs the bridge. That is the cleanest available answer to
  the community question, and it is worth more than it looks: it converts an argument about
  principle into an argument about nothing.

The honest costs, stated here because they are real and will be raised. It is **one more thing
to install** — one click if the bridge is listed on the extension platform, against zero for
folding the logic into MPFB. It creates a **compatibility matrix** (MPFB × bridge × mpfb-mcp)
that a single package would not have, which is why the bridge reports a protocol version from
its very first command. And **separation is real but partial**: a bridge published by MPFB's
maintainer, named after MPFB and linked from makehumancommunity.org will be read as endorsement
whatever the packaging says.

Folding the bridge into MPFB later is deliberately **not** ruled out. If it proves itself — used,
stable, uncontested — that is a much easier conversation than it would be today, because by then
it is a known quantity rather than a proposal. The reverse move is not available, which is the
entire reason for starting outside. The three options and the argument between them are in
[PIVOT_INTO_MPFB.md](../feature-requests/done/028-pivot-to-specific-addon/PIVOT_INTO_MPFB.md).

## What runs today

**Everything above describes the machine that runs, and it is the only one.** All forty tools
that cross the socket send a command name and its parameters to the bridge; the forty-first,
`mpfb_list_docs`, answers from a local table and reaches no Blender at all.

**The machine it replaced is gone.** Until
[FR 033](../feature-requests/done/033-retire-the-generated-code-path/README.md), a tool assembled a
Python program and sent it to a third party's add-on, which `exec()`-ed it inside Blender. The
staging was the point: each child effort of FR 028 landed with **both paths still working**, so
they could be compared side by side on a real Blender rather than swapped on faith — which is what
FR 032's check did for all twenty-four, answer by answer and scene by scene, before the default
moved, and the deletion then removed a path that had been carrying nothing for a while rather than
everything until the commit before.

What the change bought, measured on one machine in one session:

| | Bridge | The path it replaced |
|---|---|---|
| Blender-side add-on | `bridge/mpfb_bridge`, ours | blender lab's `blender_mcp`, unmodified |
| What crosses the wire | a command name and its parameters | an assembled Python program |
| Executes caller-supplied code | no | yes, by construction |
| Port | 9877 | 9876 |
| The smoke run, twenty-five tools | **4.9 s** | 48.5 s |
| Blender-side logic testable against a real MPFB | yes | no |

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
  rather than a flag, because "meta rig, then garments, then generate" cannot be written as one
  call. See
  [A tool reports an ordering constraint it cannot enforce](mutating-tools.md#a-tool-reports-an-ordering-constraint-it-cannot-enforce).

**One tool is one bridge command, and the unit stays the intent.** This is the rule the bridge
inherits rather than a new one, and it is stated here because a closed vocabulary invites exactly
the wrong simplification: a command set that mirrors MPFB's service layer, leaving the agent to
sequence it. Two consequences are load-bearing. A **batched** tool stays one command —
`mpfb_set_targets` takes lists because a round trip costs orders of magnitude more than a target
does, and splitting it would reintroduce the cost the pivot removes. And a tool that does
**multi-step reasoning** before acting stays one command: the refit blocker decides whether a
refit would silently leave the rig behind, and an agent asked to make that decision across three
round trips will get it wrong.

## Target tool catalog

The surface is four capability areas. What matters is that an agent can get through all of them
without reading MPFB's source; which tools that takes is an implementation question, and the
answer changes.

| Area | An agent must be able to | Today |
|---|---|---|
| **Introspection** | ask what is already there, and what state it is in, before acting — always cheaply, and always getting an answer rather than an error — and, since FR 041, what a character's rig can move and what its pose is now, and since FR 047 the shape of a Rigify character's hands | 12 tools |
| **Catalogues** | learn what *could* be added, each entry named exactly as the acting tool will want it | 5 tools |
| **Creation and modification** | build a character and change it: phenotype, modeling targets, rig, garments, materials, face, since FR 042 its pose, since FR 045 where it stands in the scene and since FR 047 a Rigify character's hands by a named shape or a curl per finger — and undo a mistake, for which `mpfb_reset_pose` and its `restore_with` are the first tool built; and **keep** it, as a preset that outlives the session and a face as an expression the library can apply, and since FR 039 **take it elsewhere**, as a processed copy written to a file a game engine or another application opens | 25 tools |
| **Documentation** | answer "how does MPFB do X" without the client shipping its own copy of the manual | 2 tools |

[README.md](../README.md) lists the forty-four that exist, grouped this way;
[CLAUDE.md](../CLAUDE.md#the-forty-four-tools) gives one line each and points at the module
docstring that explains it. **Forty-four tools are forty-three bridge commands**, one for one
except `mpfb_list_docs`, which needs no Blender at all. Exporting is part of keeping a character
rather than a fifth area: it is the same act, a character outliving the scene, aimed at another
application rather than at MPFB.

**What is still missing**, and why each is worth having:

- `mpfb_search_docs` — ranked search over MPFB documentation *bundled with the client*, mirroring
  how blmcp exposes Blender's RST reference. Likely sourced from
  [makehuman-static-website](https://github.com/makehumancommunity/makehuman-static-website).
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

<a id="resolved-which-blender-mcp-both"></a>

## Superseded: which "blender mcp"? Neither, in the end

There are two unrelated projects called "blender mcp": blender lab's
[implementation](https://projects.blender.org/lab/blender_mcp), which this project's Blender-side
logic used to be executed by, and a separate, more feature-rich
[community implementation](https://github.com/ahujasid/blender-mcp). Some users have the latter
installed instead of the former.

**Supporting both used to be a goal. It is not any more.** The bridge removes the dependency
that an adapter between them existed to abstract: once no program crosses the socket, there is no
third-party add-on in the path to choose between. Comparing the two remains a useful piece of
work — it is what established that the difference which matters is the *result channel* rather
than the framing — but the adapter it was pointing at is not going to be built.

Two things that comparison produced outlive it. The seam it designed, **below the transport and
invisible to tools**, is what the bridge is now built behind; see
[Supporting a second backend](architecture.md#supporting-a-second-backend). And its finding that
**backend selection must be explicit configuration, never autodetection** carries over unchanged
and matters more than before: both existing add-ons answer on 9876, the bridge answers on 9877,
and no single probe distinguishes any of them.

A user who runs the community add-on is not left out — they are pointed at the bridge, which is
one extension rather than two and does not execute what it is sent. That is a better answer than
the adapter would have been. The superseded entry is recorded in
[NEXT_STEPS.md](../feature-requests/NEXT_STEPS.md#superseded-second-backend-the-community-blender-mcp).
