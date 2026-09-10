"""
The curated index of mpfb2's developer documentation, and the URL rule over it.

MPFB's ``docs/`` tree holds 105 markdown files - one per service, per file
format, per entity - and it is **not shipped with the extension**: it sits in
the repository, not under ``src/mpfb/``, so no amount of code running inside
Blender can reach it. Hence a table here and an address per entry, rather than
anything read at run time.

**Eighteen of the 105, not all of them.** The inclusion test is *would an agent
working through these tools be better off having read this?* - which keeps the
services it drives, the formats its arguments name, and the property store its
answers come out of, and drops the UI panels and the entities an agent never
addresses. A curated list read as the whole tree is the failure this table has
to avoid, so every answer carries ``curated``, ``tree_document_count`` and
``tree_url``
([the obligation](../../../specifications/tool-interface.md#how-tools-name-things-that-can-be-added)).
Much past twenty-five entries and the curation has stopped being curation.

**One URL per entry, built rather than stored.** Three strings per document
where one plus a rule will do is three places for a typo, and building them is
also what keeps ``tree_url`` consistent with the entries under it.

**Pinned to ``master``.** A document may therefore describe an MPFB newer than
the installed one. Matching the ref to the installed version was considered and
rejected: it would make a purely local tool depend on Blender, and mpfb2's docs
are not tagged per release in a way that makes an older URL reliably resolve.

Every title, description and keyword list here is mpfb-mcp's own text. MPFB
publishes no index of its docs tree, so there is nothing to copy and nothing
that stays right by itself - which is why
``tests/test_reference_drift.py`` checks the paths against a sibling checkout.
"""

from __future__ import annotations

__all__ = (
    "DOCUMENTS",
    "RAW_URL_BASE",
    "REF",
    "REPOSITORY",
    "TOPICS",
    "TREE_DOCUMENT_COUNT",
    "TREE_URL",
    "entries",
    "page_url",
    "raw_url",
)

REPOSITORY = "makehumancommunity/mpfb2"

# The branch every URL below points into. Reported in the response, because a
# document describing a newer MPFB than the installed one is a real and
# unsurprising outcome that a caller should be able to see coming.
REF = "master"

# raw.githubusercontent.com returns the markdown itself; github.com/.../blob/
# returns the rendered page a human would read. A caller that can fetch wants
# the first; a caller handing an address to a user wants the second.
RAW_URL_BASE = "https://raw.githubusercontent.com/{}/{}/".format(REPOSITORY, REF)
PAGE_URL_BASE = "https://github.com/{}/blob/{}/".format(REPOSITORY, REF)
TREE_URL = "https://github.com/{}/tree/{}/docs".format(REPOSITORY, REF)

# How many markdown files the tree held when this table was curated. The point
# of reporting it is the ratio: eighteen of eighteen reads as complete, and
# eighteen of 105 reads as a selection. Checked against a sibling checkout by
# tests/test_reference_drift.py, which is also what notices when it drifts.
TREE_DOCUMENT_COUNT = 105

# The topics, in the order they are worth reading. Not MPFB's vocabulary -
# MPFB's tree has directories, and these follow them, but "general" is ours.
TOPICS = ("general", "services", "fileformats", "entities", "ui")


def _document(path, title, topic, description, keywords):
    return {
        "path": path,
        "title": title,
        "topic": topic,
        "description": description,
        "keywords": list(keywords),
    }


DOCUMENTS = (
    _document(
        "docs/index.md", "Docs index", "general",
        "The entry point to mpfb2's developer documentation, and the pointer to the "
        "user-facing documentation hierarchy on the website.",
        ["index", "overview", "documentation", "start"]),
    _document(
        "docs/code-structure.md", "Code structure", "general",
        "How MPFB's source is laid out and what the layers are - services, entities, UI - "
        "which is the context every other document assumes.",
        ["structure", "layout", "architecture", "services", "entities", "overview"]),
    _document(
        "docs/services/humanservice.md", "HumanService", "services",
        "The highest-level orchestrator: creating a basemesh, applying macro and detail "
        "targets, adding rigs, equipping assets, setting skins, and serializing a whole "
        "character. Most mutating tools here wrap one of its functions.",
        ["human", "create", "character", "orchestrator", "mhm", "preset", "refit"]),
    _document(
        "docs/services/targetservice.md", "TargetService", "services",
        "How MPFB models morph targets as shape keys: the macro sliders, the detail targets, "
        "the target stack, and the naming rules that make a shape key's name differ from its "
        "filename.",
        ["target", "shape key", "morph", "macro", "modifier", "stack"]),
    _document(
        "docs/services/assetservice.md", "AssetService", "services",
        "Asset discovery across the data roots: what an asset root is, how a fragment "
        "resolves to a file, what the asset list caches, and how asset packs are tracked.",
        ["asset", "library", "roots", "fragment", "pack", "cache", "discovery"]),
    _document(
        "docs/services/objectservice.md", "ObjectService", "services",
        "The object layer: the MakeHuman object types, how objects in one character are "
        "related to each other, and how a basemesh is found from anything fitted to it.",
        ["object", "type", "basemesh", "relationships", "parent", "children"]),
    _document(
        "docs/services/materialservice.md", "MaterialService", "services",
        "The five material models - MakeSkin, enhanced skin, layered skin, procedural eyes "
        "and game engine - and how each builds a different node tree.",
        ["material", "skin", "makeskin", "enhanced", "layered", "node tree", "shader"]),
    _document(
        "docs/services/rigservice.md", "RigService", "services",
        "Armatures, bones, constraints, poses and vertex weights, including how a rig is "
        "identified from an existing armature and how weights are loaded.",
        ["rig", "armature", "bone", "weights", "pose", "rigify", "skeleton"]),
    _document(
        "docs/services/clothesservice.md", "ClothesService", "services",
        "How a garment is fitted to the basemesh through an MHCLO's vertex mapping, and what "
        "refitting actually recomputes when the body changes.",
        ["clothes", "fit", "refit", "mhclo", "mask", "vertex mapping", "proxy"]),
    _document(
        "docs/services/locationservice.md", "LocationService", "services",
        "Every path MPFB uses: the addon root, the user data, config and cache directories, "
        "and the second root. What mpfb_get_status reports comes from here.",
        ["path", "directory", "user data", "config", "cache", "second root", "location"]),
    _document(
        "docs/fileformats/mhclo.md", "MHCLO file format", "fileformats",
        "The format describing a mesh fitted to the basemesh - clothes, but also hair, eyes "
        "and full-body proxies. What mpfb_add_asset equips and mpfb_list_assets lists.",
        ["mhclo", "clothes", "proxy", "asset", "fitting", "format"]),
    _document(
        "docs/fileformats/mhmat.md", "MHMAT file format", "fileformats",
        "The material format: colors, textures, transparency, sub-surface scattering and "
        "shader parameters, referenced from an MHCLO's material key.",
        ["mhmat", "material", "texture", "shader", "skin", "format"]),
    _document(
        "docs/fileformats/target.md", "Target file format", "fileformats",
        "The morph target format (.target and .ptarget): the vertex displacements behind "
        "every modeling slider.",
        ["target", "ptarget", "morph", "shape key", "vertex", "format"]),
    _document(
        "docs/fileformats/human_preset.md", "Human preset format", "fileformats",
        "The saved-character JSON: body shape, rig, body parts, clothes, materials and color "
        "adjustments, stored as human.<name>.json in the user config directory.",
        ["preset", "save", "load", "human", "json", "character", "format"]),
    _document(
        "docs/fileformats/rig.md", "Rig definition format", "fileformats",
        "The rig JSON: the bone hierarchy, how each bone endpoint is positioned against the "
        "mesh, and the Rigify metadata. What mpfb_list_rigs enumerates.",
        ["rig", "armature", "bone", "rigify", "json", "format"]),
    _document(
        "docs/fileformats/weights.md", "Vertex weights format", "fileformats",
        "The weights JSON that skins the basemesh to an armature, stored beside the rig "
        "files. Why a rig can load weights belonging to a different rig.",
        ["weights", "vertex group", "skinning", "rig", "json", "format"]),
    _document(
        "docs/fileformats/pose.md", "Pose file format", "fileformats",
        "The pose JSON: bone rotations and translations, for the system poses MPFB ships and "
        "the ones a user saves.",
        ["pose", "bone", "rotation", "json", "format"]),
    _document(
        "docs/fileformats/expression.md", "Expression file format", "fileformats",
        "The expression JSON: a named, weighted combination of ARKit face unit shape keys.",
        ["expression", "face", "arkit", "face unit", "shape key", "json", "format"]),
    _document(
        "docs/entities/objectproperties.md", "Object properties", "entities",
        "The three BlenderConfigSet singletons behind MPFB's custom properties - object_type, "
        "asset_source, material_source and the macro sliders - which is where every tool "
        "here reads what an object is.",
        ["properties", "custom property", "object_type", "asset_source", "macro",
         "blenderconfigset"]),
)


def raw_url(path: str) -> str:
    """The address that returns the document's markdown."""
    return RAW_URL_BASE + path


def page_url(path: str) -> str:
    """The address that returns the rendered page a person would read."""
    return PAGE_URL_BASE + path


def entries(topic: str | None = None, keyword: str | None = None) -> list[dict[str, object]]:
    """The curated documents, filtered, each with its two addresses attached.

    ``topic`` matches exactly and case-insensitively; a topic this table does
    not have matches nothing rather than raising, which is what lets the tool
    report ``topic_recognized`` and ``known_topics`` instead of failing. A
    ``keyword`` is a case-insensitive substring, matched against the title, the
    description, the keywords **and the path** - the path is what a caller who
    has seen one of these addresses before will search with.
    """
    wanted_topic = topic.strip().lower() if topic else None
    wanted_keyword = keyword.strip().lower() if keyword else None

    found = []
    for document in DOCUMENTS:
        if wanted_topic is not None and document["topic"].lower() != wanted_topic:
            continue
        if wanted_keyword is not None and wanted_keyword not in _searchable(document):
            continue
        entry = dict(document)
        entry["keywords"] = list(document["keywords"])
        entry["raw_url"] = raw_url(document["path"])
        entry["page_url"] = page_url(document["path"])
        found.append(entry)
    return found


def _searchable(document: dict[str, object]) -> str:
    return " ".join([
        document["path"],
        document["title"],
        document["description"],
        " ".join(document["keywords"]),
    ]).lower()
