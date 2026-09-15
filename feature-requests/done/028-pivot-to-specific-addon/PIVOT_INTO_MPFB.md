# Where the Blender-side code should live: three options

**Status:** Analysis only. Nothing is decided and nothing in any repository is changed by it.
Written 2026-09-10, building on [PIVOT_ANALYSIS.md](PIVOT_ANALYSIS.md), which concluded that
merging the tools upstream into ahujasid/blender-mcp should not be pursued, and that the
Blender-side logic wants a home inside the MakeHuman ecosystem instead. This document takes that
one step further and asks *which* home.

Facts here were checked against the checkouts of `../mpfb2`, `../blender_mcp`,
`../ahujasid-blender-mcp` and `../makehuman-static-website` as they stood on that date.

## The three options, stated precisely

**Option 1 — continue as is.** mpfb-mcp keeps assembling Python programs and sending them over
somebody else's add-on socket: blender lab's `blender_mcp` today, ahujasid's as well once the
[backend adapter](../../NEXT_STEPS.md#second-backend-the-community-blender-mcp) lands.
MPFB is untouched. The ~7,750 lines of payload and fragment source stay on the client side and
cross the wire on every call.

**Option 2 — merge into MPFB.** The payload logic becomes a real MPFB-side API, and MPFB gains
the ability to serve it: either its own command socket, or handlers plus a socket. mpfb-mcp
becomes a thin client. Ships inside the MPFB extension, on Blender's extension platform, to every
MPFB user.

**Option 3 — a separate companion add-on.** The same logic, in a *second* Blender extension —
call it the bridge — that depends on MPFB at runtime but ships separately. MPFB itself gains
nothing and loses nothing. Two shapes are possible, and they are not equally good:

- **3a, handler-provider.** The bridge holds the MPFB logic; the *transport* stays with
  blender_mcp or ahujasid, and mpfb-mcp sends a one-line program that calls into the bridge.
  Programs shrink from tens of kilobytes to a few hundred bytes with no upstream change required,
  and it works with both backends. But it keeps the dependency on someone else's add-on, and it
  is unclear whether such a call survives ahujasid's safe-mode allowlist (see below) — that would
  need to be established before choosing it.
- **3b, own socket.** The bridge runs its own command server on its own port with a **closed
  command vocabulary** — no `exec()` of caller-supplied code at all — and mpfb-mcp talks to it
  directly. No blender_mcp, no ahujasid, no adapter, no code generation. This is the shape meant
  wherever this document says "option 3" without qualification.

All three keep GPL-3.0, keep the licence question closed, and keep telemetry out. That was
settled in the first analysis; what separates these three is *packaging, consent and blast
radius*, not law.

## The comparison

| | 1 — as is | 2 — into MPFB | 3 — companion add-on (3b) |
|---|---|---|---|
| MPFB code changed | none | substantial, permanent | none |
| Who controls the release cadence | third party for the add-on half | MakeHuman | MakeHuman |
| Blender extension review exposure | none of ours | **MPFB's own listing** | the bridge's listing only |
| Manifest permission string users see | n/a | MPFB's changes to name an inbound socket | the bridge declares it; MPFB's is untouched |
| Reaches a user who never asked for AI | no | **yes — every MPFB user** | no — installation is the consent |
| Install steps to first prompt | ~8, two of them developer-grade | ~5 | ~6 |
| Code on the wire per call | tens of KB (blender lab: ~250 ms/4 KB) | parameters only | parameters only |
| Arbitrary code execution into Blender | yes, inherent to the design | yes, unless the API is closed-vocabulary | **no — closed vocabulary** |
| Broken by ahujasid's safe mode | **yes, entirely** | n/a | n/a |
| Reputational blast radius of a defect | the other add-on's | **MPFB's** | the bridge's |
| Testable in MPFB's own harness | no | yes | yes, with MPFB installed |
| Things Joel maintains | 1 (this repo) | 1 (MPFB, larger) | 2 (MPFB unchanged, plus the bridge) |
| Reversible | fully | **barely** | fully — stop shipping it |

Two rows deserve emphasis because they are where the decision actually is:

- **"Reaches a user who never asked for AI"** is the entire community question, and only option 2
  answers it "yes".
- **"Install steps"** differ between options 2 and 3 by *one click*, provided the bridge is
  listed on extensions.blender.org — where MPFB itself has been since 2.0.8 and where the site
  already tells users to install from. Option 2's community risk buys one click.

## Option 1 — continue as is

**For.** Zero cost today; it already works and is verified against a real Blender. It keeps MPFB
completely clean, which is the strongest possible answer to the alienation question. Blender
lab's add-on is a Blender Foundation lab project (`blender.org/lab/mcp-server`), so "MPFB works
with Blender's own MCP experiment" is a defensible sentence to say in public — considerably more
defensible than "MPFB works with the telemetry-funded one". And the adapter that adds the second
backend is small and already designed.

**Against.** The install path is the worst of the three and it is the part users actually meet:
Blender, MPFB from the platform, a second add-on downloaded from projects.blender.org and
installed by hand, enable it, start its socket server, turn `timer_interval_active` down from
0.25 s or accept calls that are four to five times slower, then clone this repository, make a
venv, `pip install -e .`, and hand-edit an MCP client's JSON config. Eight steps, at least three
of which will lose a hobbyist. MPFB's audience is not developers.

Beyond friction, the design carries three structural liabilities:

- **It is arbitrary code execution by construction.** Every call ships a program that MPFB's host
  add-on `exec()`s. That is fine for a proof of concept and awkward as a recommendation to
  end users.
- **Safe mode kills it outright.** ahujasid's opt-in `BLENDER_MCP_SAFE_MODE=1` allowlist denies
  `os`, `sys` and the name `modules`; `bootstrap.py` opens with `import sys` and a `sys.modules`
  scan, and ten of twenty-one payloads `import os`. Every program this project sends is rejected.
- **The wire cost is permanent.** The session source cache, fragment hashing and re-send-once
  recovery exist only to manage it.

**Consequence if chosen indefinitely:** mpfb-mcp stays a developer's tool. That is a legitimate
choice — but it should be chosen deliberately, not arrived at by default.

## Option 2 — merge into MPFB

**For.** The shortest install path (MPFB, a checkbox or a Start button, a client). One codebase,
one release, one version number, one place to look. The logic sits next to the services it
drives, gets MPFB's own test harness and pylint config, and can use anything MPFB has. A stable
MPFB-side API would benefit every automation client, not just this one. Discoverability is
maximal: the feature exists for anyone who reads the panel.

**Against.**

- **It puts MPFB's listing on the line.** MPFB is distributed through extensions.blender.org and
  the download page tells "most, if not all users" to install it there. An inbound socket that
  drives the add-on is a reviewer question, and the manifest's `[permissions]` block — today
  `network = "(optional) Interact with local instance of MakeHuman"` — would have to say
  something about accepting local connections, which every user reads at install time. MCP
  iteration then runs at the speed of extension review.
- **It cannot be taken back.** Once shipped to the whole user base, removing it is itself a
  breaking change with its own announcement.
- **Every user gets it, including the ones who would object.** See below.
- **The blast radius of any security defect is MPFB's,** not a side project's. A listening socket
  in a character generator installed by tens of thousands of hobbyists is a different risk
  posture from one in an opt-in developer add-on.
- **Scope creep in a project that has resisted it.** MPFB is a character generator; an MCP
  command server is a different kind of software with a different maintenance rhythm.

**Consequence if chosen:** MPFB becomes, in part, an AI-integration project, and is discussed as
one. The engineering is the easy half.

## Option 3 — a separate companion add-on

**For.**

- **Installation is the consent.** A user who does not want AI near their character generator
  simply never installs the bridge, and nothing in MPFB changes, not even a permission string.
  This is the cleanest possible answer to the community question and it is worth more than it
  first appears — it converts an argument about principle into an argument about nothing.
- **MPFB's extension listing, review cycle and reputation are untouched.** The bridge has its own
  listing, its own review, its own permission declaration and its own release cadence, which can
  be fast and frequent without dragging MPFB's release engineering along.
- **The mechanism already exists and is proven twice.** MPFB's `__init__.py` deliberately exports
  `MPFB_CONTEXTUAL_INFORMATION` and documents the `sys.modules`-scan pattern for reaching MPFB
  "without knowing anything about the module structure" — used by MPFB's own test suite, and by
  this project's `bootstrap.py`. A companion add-on is the supported entry point, not a hack.
- **The security posture is the best of the three.** A closed command vocabulary — twenty-two
  named commands with validated parameters — executes no caller-supplied code at all. That is a
  strictly better story than either existing MCP add-on, at review time and in public argument,
  and it is a difference that a sceptical user can verify by reading a list.
- **It collects the technical wins anyway**: no code generation, no session source cache, no
  4 KB-per-tick tax, no dependence on either third-party add-on or on their safe modes, real
  tracebacks, and payload logic that is ordinary tested Python.
- **Fully reversible**, and it can be renamed, transferred, or handed to a co-maintainer without
  touching MPFB.

**Against.**

- **One more thing to install** — the honest cost, and it is one click if the bridge is listed on
  the extension platform, plus a compatibility matrix (MPFB version × bridge version × server
  version) that options 1 and 2 do not both have. Option 1 has a worse version of the same
  problem; option 2 does not have it at all.
- **A second project to maintain**, with its own repository, releases, issue tracker, docs and
  review submissions. For a one-person ecosystem this is the real objection.
- **It must reimplement transport.** Roughly 300–500 lines of socket server plus main-thread
  dispatch — both existing add-ons show exactly how, including the traps (`bpy` is main-thread
  only; dispatch via `bpy.app.timers`; multi-byte UTF-8 splits across `recv()` chunks) — but it
  is code that currently costs nothing because someone else writes it.
- **Separation is real but partial.** A bridge published by the MPFB maintainer, named after
  MPFB, and linked from makehumancommunity.org will be read as endorsement whatever the
  packaging says. It answers "is this forced on me?" completely; it answers "is the project
  going in that direction?" only partly.
- **Discoverability is halved.** Nobody finds a feature that is not in the panel. It needs a
  documentation page and probably a line in the MPFB docs saying the bridge exists — which is,
  notably, exactly the treatment MPFB already gives the third-party Lip Sync add-on.

## The community question

The concern is legitimate and worth taking on its own terms rather than as an obstacle to route
around. Two opposing pressures act on the same decision.

### What would actually be objected to

Anti-AI sentiment in the 3D community is not one position. Sorting it matters, because the three
options answer the parts very differently:

1. **"My tools should not feed AI companies."** Answered fully by all three options here — no
   telemetry, no dataset collection, GPL throughout. It is *not* answered if a user is pointed at
   ahujasid's backend, whose terms permit indefinite retention, model training and dataset
   release with consent on by default; that is a fact about a backend option 1 wants to support,
   and it deserves a plain warning in the documentation whichever option is chosen.
2. **"AI should not be in the software I install."** Answered by 1 and 3 (not installed, not
   present). Not answered by 2 — the code ships to everyone, and "there is a checkbox" does not
   satisfy this objection, because the objection is to the code being there.
3. **"This tool makes human likenesses; automating it is worse."** Not answered by packaging at
   all. It is an argument about the feature existing, and it will be made regardless. The honest
   response is that MPFB is GPL and locally run, that nothing is uploaded, and that the bridge
   drives the same operations a user can already perform by hand.
4. **"This devalues the craft."** Also unanswerable by packaging, and the loudest.

Objection 2 is the one that packaging can actually dispose of, and it is the one most likely to
produce visible fallout — a one-star review on MPFB's extension listing, a forum thread, a fork —
because it lands on people who never opted into the conversation.

### The precedent MPFB has already set

MPFB is not starting from neutral, and this cuts both ways.

`src/mpfb/ui/operations/ai/` exists today: a module whose docstring says it "contains
functionality for working with AI stuff", registering `MPFB_PT_Ai_Panel` labelled "OpenPose",
whose purpose is exporting poses for Stable Diffusion. It is documented on the community site
with a full tutorial including ControlNet screenshots. So MPFB has already shipped an AI-facing
feature to every user and survived it — which weakens the "this would be unprecedented"
objection, and is a useful precedent to cite.

But the two are different in a way critics will notice immediately: OpenPose export is *passive
and outbound* — a user clicks a button and gets a file. An MCP bridge is *inbound and active* —
a language model drives the add-on. The precedent supports "MPFB documents AI interop"; it does
not support "MPFB embeds an AI control surface". Option 3 sits on the supported side of that line.
Option 2 crosses it.

### The other side: cumbersome scares people away too

The reverse risk is just as real and gets discussed less. MPFB's users are largely hobbyists who
found it through a YouTube tutorial and installed it with one click from Blender's extension
platform — the download page exists mostly to tell people *not* to use the other methods. Against
that baseline, option 1's eight steps, two of them involving a terminal and a JSON config file,
are not a rough edge; they are the feature not existing for that audience. Every additional
component multiplies drop-off, and the drop-off falls hardest on exactly the non-technical users
the AI-assisted workflow would help most.

The MCP client configuration step is irreducible — it exists in all three options and is somebody
else's UI. What *is* controllable is the number of Blender-side pieces: two in option 1, zero in
option 2, one in option 3.

### Where the two pressures actually meet

They conflict on exactly one row of the table — whether the code ships to everyone — and the
distance between the best answer to each pressure is one click.

That asymmetry is the argument. Option 2 gains one install step over option 3 and pays for it
with MPFB's extension listing, MPFB's review cycle, MPFB's blast radius, MPFB's reversibility and
the entirety of objection 2. Option 1 avoids the community risk exactly as well as option 3 does
and pays for it with three extra steps, arbitrary code execution, a permanent wire tax and a
dependency on two third parties, one of which can disable it with an environment variable.

A secondary point worth stating plainly: **whichever option is chosen, say so first, in public,
in the project's own words.** The difference between "MPFB is adding AI" as a discovery and as an
announcement that explains what it is, what it is not, that it is local, that it is optional, and
that nothing is uploaded, is most of the difference in how it is received. The MakeHuman
community is small and has a maintainer who is known to talk to it; that is an asset here.

## Recommendation

**Option 3, in its 3b shape: a separate companion add-on with its own closed-vocabulary command
socket** — with option 1 kept alive during the transition and retired only when the bridge is
better.

It takes every technical benefit the first analysis attributed to "moving into MPFB", answers the
community objection that packaging can answer, keeps MPFB's listing and reputation out of the
argument entirely, improves the security posture relative to all existing options, and stays
reversible. The price is one install click and a second small project — and the second project is
one that already exists in all but name, since it is the payload directory of this repository.

Do **not** rule option 2 out permanently. If the bridge proves itself — used, stable, uncontested
for a year or two — folding it into MPFB later is a much easier conversation, because by then it
will be a known quantity rather than a proposal. The reverse move is not available.

A staged path, each stage useful on its own:

1. **Now.** Add the `LICENSE` file. Document the safe-mode limitation. Land the backend adapter
   if the community add-on's users are wanted in the meantime — it is small and it is the
   fallback if the bridge stalls.
2. **Next.** Extract the payload logic into a bridge add-on with a closed command vocabulary and
   its own socket, keeping the MPFB-facing behaviour and the specifications intact. mpfb-mcp
   grows a second backend that is the bridge, so both paths run side by side and can be compared
   on a real Blender.
3. **Then.** Publish the bridge on the extension platform, with a documentation page on
   makehumancommunity.org that states plainly what it does, that it is local, that it is optional,
   that nothing is uploaded, and — if ahujasid's backend is still supported — what that project's
   terms collect.
4. **Later, only if warranted.** Revisit folding it into MPFB.

## What to establish before committing

1. **Does 3a work at all under ahujasid's safe mode?** If a one-line call into a bridge module
   clears the allowlist, 3a becomes a cheap intermediate step; if not, 3b is the only option that
   is safe-mode-proof. Cheap to test.
2. **What does extension-platform review make of a listening socket?** Ask before building, for
   the bridge (option 3) and hypothetically for MPFB (option 2). The answer may decide this on
   its own.
3. **How much does a second extension actually cost to maintain** in release engineering, review
   submissions and support load, honestly estimated against a one-person ecosystem?
4. **What is the real appetite among MPFB users** — both for the feature and against it? A forum
   post describing the bridge before it exists costs nothing and would replace the guesswork in
   the section above with evidence.
5. **Can the bridge's command vocabulary be closed** without losing tools that genuinely need
   open-ended access? Twenty-two named commands suggests yes, but `mpfb_set_asset_material`,
   which had no service function to wrap, is the one to check first.
