"""
The ``mpfb_list_docs`` tool: addresses for MPFB's developer documentation.

The mpfb2 repository carries 105 markdown files under ``docs/`` - one per
service, per file format, per entity - and that is the material which actually
answers "how does MPFB do X". It is **not shipped with the extension**:
``docs/`` sits in the repository, not under ``src/mpfb/``, so no amount of code
running inside Blender can reach it. Hence a table of addresses rather than
anything read at run time.

**The one tool in this package that reaches no Blender at all.** It never
crosses the socket and never touches the network: it filters
``mpfbmcp.reference.docs``'s table and attaches two URLs per entry. That is a
real exception to the rule that a tool module, a bridge command and a test
module share a name - there is no ``mpfb_list_docs`` command, because there is
nothing for one to do - and it is stated in
[CLAUDE.md](../../../CLAUDE.md#the-twenty-five-tools) rather than left to be
noticed. It works with no Blender, no MPFB and no connectivity, which is
also why it has no ``mpfb_get_status`` precondition and cannot return an error
envelope from Blender.

**It hands out addresses; it does not fetch them.** Retrieving one is the MCP
client's job. See
[the network boundary](../../../specifications/architecture.md#mpfb-mcp-opens-no-network-connection-except-the-one-to-the-add-on).

Why the list is curated rather than complete, why it is pinned to ``master``,
and what the inclusion test is are all in ``mpfbmcp.reference.docs``, which is
where the table itself lives.
"""

from __future__ import annotations

__all__ = (
    "register",
)

from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

from mpfbmcp import arguments
from mpfbmcp.reference import docs


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="List MPFB Developer Documents",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        )
    )
    def mpfb_list_docs(topic: str | None = None,
                       keyword: str | None = None) -> dict[str, object]:
        """
        Addresses for MPFB's developer documentation - one document per service
        (`HumanService`, `TargetService`, ...), per file format (`.mhclo`,
        `.mhmat`, `.target`, the preset and rig JSON) and for its object
        property store. Use it to answer "how does MPFB actually do X" rather
        than inferring it from a tool response.

        Changes nothing, needs no Blender and no MPFB, and **fetches nothing**:
        it returns URLs for the client to retrieve. `raw_url` returns the
        markdown; `page_url` is the rendered page for a person.

        Arguments, both optional: `topic` (`general`, `services`,
        `fileformats`, `entities`, `ui`; exact, case-insensitive) and `keyword`
        (case-insensitive substring over path, title, description and
        keywords). With neither, returns everything it has.

        **A curated subset, not the tree.** `curated` is always `true`,
        `tree_document_count` says how large the tree it was drawn from is, and
        `tree_url` is the full listing - go there when what you need is not
        here, rather than concluding it does not exist. Pinned to `master`
        (`ref`), so a document may describe a newer MPFB than the installed one.

        `result` carries:

          - `documents`: each `{path, raw_url, page_url, title, description,
            keywords, topic}`, `path` being repo-relative
            (`docs/services/humanservice.md`). Titles, descriptions and
            keywords are mpfb-mcp's own text; MPFB publishes no index.
          - `count`, `curated`, `curated_document_count`, `tree_document_count`,
            `tree_url`, `ref`, `repository`.
          - `requested_topic`, `topic_recognized`, `known_topics`,
            `requested_keyword`. An unknown topic matches nothing rather than
            failing, so check `topic_recognized` before reading an empty
            `documents` as "no such documentation".

        Not capped and not paged: under twenty entries, so no `truncated` or
        `total_count` to check.
        """
        requested_topic = arguments.validated_text(
            topic, "topic", "omit it to search every topic")
        requested_keyword = arguments.validated_text(
            keyword, "keyword", "omit it to match every document")

        recognized = (requested_topic is None
                      or requested_topic.strip().lower() in docs.TOPICS)
        found = docs.entries(topic=requested_topic, keyword=requested_keyword)

        return {
            "status": "ok",
            "result": {
                "documents": found,
                "count": len(found),
                # Always true, and always present, so that a caller never has to
                # infer partiality from the size of the list.
                "curated": True,
                "curated_document_count": len(docs.DOCUMENTS),
                "tree_document_count": docs.TREE_DOCUMENT_COUNT,
                "tree_url": docs.TREE_URL,
                "ref": docs.REF,
                "repository": docs.REPOSITORY,
                "requested_topic": requested_topic,
                "topic_recognized": recognized,
                "known_topics": list(docs.TOPICS),
                "requested_keyword": requested_keyword,
            },
        }
