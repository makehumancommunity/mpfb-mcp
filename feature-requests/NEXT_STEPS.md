# Next steps

This file contains remaining, not-yet-finished development efforts, in no particular order.
Each would become a numbered subdir under `feature-requests/` (see [CLAUDE.md](CLAUDE.md))
when started.

Completed efforts are no longer listed here — they move to [HISTORY.md](HISTORY.md), which
records what has already landed and why. When an effort below is finished, move it there
(see the [lifecycle in CLAUDE.md](CLAUDE.md#lifecycle)).

`mpfb_get_status`, the first introspection tool, has landed —
see [FR 001](done/001-mpfb-get-status/README.md) and its
[entry in HISTORY.md](HISTORY.md#fr-001--mpfb_get_status). Its manual verification against a
running Blender is still outstanding and is tracked in the request itself, under
[Verification status](done/001-mpfb-get-status/README.md#verification-status), rather than as
an effort here.

See [specifications/vision.md](../specifications/vision.md#target-tool-catalog) for the rest of
the target tool catalog — `mpfb_get_human_summary` and `mpfb_list_assets` are the natural next
introspection tools, but no tool beyond FR 001 has been scoped into a feature request yet.
The one scoped effort in flight is [FR 002](002-codegen-structure/README.md), a refactor rather
than a new tool.

## Code structure and readability

Scoped as [FR 002](002-codegen-structure/README.md) (status: Accepted).

With only two tools implemented, `src/mpfbmcp/mpfb_codegen.py` already looks like it is 
going to grow very large. All in all, the code structure should take into account that the 
number of tools might grow significantly. Thus keeping all the code build logic in one file 
seems like it is going to become a problem. Maybe the "build_..." functions specific to each 
tool could live in the tool python files rather than centrally and import the bootstrap logic 
from the codegen file? 

Further, the "build_..." functions are hard to read, since all specific code ends up on a single 
line with escaped newlines. A way need to be found to turn this code into something which 
is convenient for developers to work with and modify.

It should be noted in the specifications that code readability and developer experience
are proritized non-functional requirements.
 
## Observability

Logging should be added so that it is possible to see the exact python code sent to blender,
and the reponses that came back.

## Get available detail targets

In order to model, the LLM needs to know which targets are available. These come from two
distinct sources: `targets.json` in the system data directory and the targets installed 
in the user data directory.

A new tool should be added for getting information about available targets. It should return:

- The absolute path to target.json (which the LLM can then parse outside the MCP pipeline)
- A list of targets available in the user data directory.

Note that macrodetails/phenotype is a separate question, as that is handled via attributes
on the basemesh rather than by loading target files specifically.


