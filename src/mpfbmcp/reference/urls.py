"""
The community addresses ``mpfb_list_urls`` hands out, and the rule that merges them.

Three tables and one function. ``MPFB_URLS`` is a **copy** of the constants in
MPFB's ``src/mpfb/ui/weburls.py``, kept so that the tool can answer when MPFB is
absent, half-registered or unreachable - which is precisely the state in which
"where do I download MPFB" is the question being asked. ``ECOSYSTEM_URLS`` is
this package's own: MakeHuman and the community sites MPFB's own constants do
not name. ``DESCRIPTIONS`` says what is at each address, for both.

**A copy is a thing that goes stale**, so ``merge()`` never prefers it: when the
live values are readable it reports them, reports that it read them, and reports
every key where the copy disagrees. The copy is a fallback, never a second
source of truth - see
[the standing rule](../../../specifications/responses.md#a-response-says-which-source-answered-it).

**Neither the descriptions nor the keywords are MPFB's.** MPFB stores no prose
beside its URLs at all; every sentence here is mpfb-mcp's own reading of what is
at that address, which is a derived fact and is reported as one
([why that matters](../../../specifications/responses.md#how-tools-report-a-derived-rather-than-recorded-fact)).

The keys are MPFB's constant names, and ``ECOSYSTEM_URLS`` uses the same
``URL_`` namespace deliberately: if MPFB ever publishes a constant under a name
used here, ``merge()`` resolves it the same way it resolves any other
disagreement - the live value wins, and the entry is reported as MPFB's.
"""

from __future__ import annotations

__all__ = (
    "DESCRIPTIONS",
    "ECOSYSTEM_URLS",
    "MPFB_URLS",
    "merge",
)

# Copied from mpfb2's src/mpfb/ui/weburls.py. Eleven constants as of MPFB
# 2.0.17 - the feature request that added this tool said thirteen, which was
# wrong, and the enumerate-by-prefix rule in the payload is what makes the
# number not matter. Checked against a sibling checkout by
# tests/test_reference_drift.py.
MPFB_URLS = {
    "URL_HOMEPAGE": "http://static.makehumancommunity.org/mpfb.html",
    "URL_SOURCE_CODE": "https://github.com/makehumancommunity/mpfb2",
    "URL_DOCUMENTATION": "https://static.makehumancommunity.org/mpfb/docs.html",
    "URL_FAQ": "https://static.makehumancommunity.org/mpfb/faq/index.html",
    "URL_FORUM": "http://www.makehumancommunity.org/forum/",
    "URL_ISSUE_TRACKER": "https://github.com/makehumancommunity/mpfb2/issues",
    "URL_ASSET_PACKS": "http://static.makehumancommunity.org/assets/assetpacks.html",
    "URL_GETTING_STARTED_GUIDE":
        "https://static.makehumancommunity.org/mpfb/docs/getting_started.html",
    "URL_GETTING_STARTED_VIDEO": "https://www.youtube.com/watch?v=FNeiLDH_lnw",
    "URL_VIDEO_CHANNEL": "https://www.youtube.com/@MakeHumanCommunity",
    "URL_SYSTEM_ASSETS":
        "https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html",
}

# mpfb-mcp's own additions: the surrounding ecosystem an agent may be asked
# about and MPFB has no constant for. Every one of these was taken from a
# sibling repository rather than composed here, because an address that is
# almost right is worse than no address - it fails somewhere the caller cannot
# see the mistake. MPFB does not endorse them by their being in this list, which
# is what the entries' `source: "mpfb_mcp"` says.
ECOSYSTEM_URLS = {
    "URL_MAKEHUMAN_COMMUNITY": "http://www.makehumancommunity.org/",
    "URL_MAKEHUMAN_SOURCE_CODE": "https://github.com/makehumancommunity/makehuman",
    "URL_MAKEHUMAN_WIKI": "http://www.makehumancommunity.org/wiki/Main_Page",
    "URL_MAKEHUMAN_ASSET_REPOSITORY":
        "http://www.makehumancommunity.org/content/user_contributed_assets.html",
    "URL_MPFB_DEVELOPER_DOCS": "https://github.com/makehumancommunity/mpfb2/tree/master/docs",
    "URL_STATIC_DOCUMENTATION_SITE": "https://static.makehumancommunity.org/",
}

# One sentence each, written to answer "which question is this address the
# answer to". A key with no entry here is reported with a null description
# rather than dropped, so a constant MPFB adds tomorrow still appears.
DESCRIPTIONS = {
    "URL_HOMEPAGE": {
        "title": "MPFB home page",
        "description": "The project's front page: what MPFB is, and where to download it.",
        "keywords": ["mpfb", "download", "install", "home"],
    },
    "URL_SOURCE_CODE": {
        "title": "MPFB source code",
        "description": "The mpfb2 GitHub repository - the addon's source, and its docs/ tree.",
        "keywords": ["source", "code", "github", "repository", "mpfb2"],
    },
    "URL_DOCUMENTATION": {
        "title": "MPFB documentation",
        "description": "The user-facing documentation hierarchy, written for people using the "
                       "addon rather than reading its source.",
        "keywords": ["documentation", "docs", "manual", "help"],
    },
    "URL_FAQ": {
        "title": "MPFB FAQ",
        "description": "Frequently asked questions, including how MPFB differs from the "
                       "standalone MakeHuman application.",
        "keywords": ["faq", "questions", "differences", "makehuman"],
    },
    "URL_FORUM": {
        "title": "MakeHuman community forum",
        "description": "Where to ask for help with MPFB or MakeHuman, and where releases are "
                       "announced.",
        "keywords": ["forum", "help", "support", "community", "ask"],
    },
    "URL_ISSUE_TRACKER": {
        "title": "MPFB issue tracker",
        "description": "Where to report an MPFB bug or request a feature. Bugs in MPFB itself "
                       "go here, not to whoever wrote the tool that hit them.",
        "keywords": ["issue", "bug", "tracker", "report", "feature request"],
    },
    "URL_ASSET_PACKS": {
        "title": "MPFB asset packs",
        "description": "The asset packs available for download - clothes, hair, skins, eyes and "
                       "poses. Install one of these when mpfb_list_assets reports little or "
                       "nothing.",
        "keywords": ["assets", "asset packs", "download", "clothes", "hair", "skins"],
    },
    "URL_GETTING_STARTED_GUIDE": {
        "title": "Getting started with MPFB",
        "description": "The written walkthrough for a first character, in MPFB's own UI terms.",
        "keywords": ["getting started", "tutorial", "guide", "beginner"],
    },
    "URL_GETTING_STARTED_VIDEO": {
        "title": "Getting started video",
        "description": "The same walkthrough as a video, on YouTube.",
        "keywords": ["video", "tutorial", "youtube", "getting started"],
    },
    "URL_VIDEO_CHANNEL": {
        "title": "MakeHuman Community video channel",
        "description": "The project's YouTube channel, where the tutorial videos live.",
        "keywords": ["video", "youtube", "channel", "tutorials"],
    },
    "URL_SYSTEM_ASSETS": {
        "title": "MakeHuman system assets pack",
        "description": "The system assets pack, which MPFB needs for the standard skins and "
                       "eyes. mpfb_get_status reports whether it is installed.",
        "keywords": ["system assets", "download", "skins", "eyes", "required"],
    },
    "URL_MAKEHUMAN_COMMUNITY": {
        "title": "MakeHuman Community",
        "description": "The community site behind both MakeHuman and MPFB.",
        "keywords": ["makehuman", "community", "home"],
    },
    "URL_MAKEHUMAN_SOURCE_CODE": {
        "title": "MakeHuman source code",
        "description": "The standalone MakeHuman application, which shares MPFB's asset formats "
                       "and base mesh and can act as an asset server for it.",
        "keywords": ["makehuman", "source", "github", "standalone"],
    },
    "URL_MAKEHUMAN_WIKI": {
        "title": "MakeHuman wiki",
        "description": "The community wiki: background on the base mesh, the file formats and "
                       "the project's history.",
        "keywords": ["wiki", "makehuman", "background", "reference"],
    },
    "URL_MAKEHUMAN_ASSET_REPOSITORY": {
        "title": "User-contributed assets",
        "description": "The community's asset repository - individual user-contributed assets, "
                       "as opposed to the curated packs at URL_ASSET_PACKS.",
        "keywords": ["assets", "user contributed", "download", "repository", "community"],
    },
    "URL_MPFB_DEVELOPER_DOCS": {
        "title": "MPFB developer documentation",
        "description": "The mpfb2 repository's docs/ tree: one document per service, file "
                       "format and entity. mpfb_list_docs indexes the useful part of it.",
        "keywords": ["developer", "docs", "services", "file formats", "api"],
    },
    "URL_STATIC_DOCUMENTATION_SITE": {
        "title": "MakeHuman documentation site",
        "description": "The static site hosting the documentation for every project in the "
                       "MakeHuman ecosystem.",
        "keywords": ["documentation", "site", "makehuman", "mpfb"],
    },
}


def _entry(key: str, url: str, source: str) -> dict[str, object]:
    """One reported link. An undescribed key keeps null fields rather than vanishing."""
    described = DESCRIPTIONS.get(key)
    return {
        "key": key,
        "url": url,
        # null, not "": MPFB adds a constant without telling anyone, and a
        # missing description is "we have not written one" rather than "there
        # is nothing at this address".
        "title": described["title"] if described else None,
        "description": described["description"] if described else None,
        "keywords": list(described["keywords"]) if described else None,
        "source": source,
    }


def merge(live_urls: dict[str, str] | None) -> dict[str, object]:
    """Every link to report, plus what the vendored copy got wrong.

    ``live_urls`` is what the payload read out of MPFB's ``weburls`` module, or
    None when it could not be read at all - MPFB absent, half-registered, or
    Blender unreachable. Returns the ``urls`` list together with the three
    staleness fields, which are ``null`` rather than ``false``/``[]`` when there
    was nothing live to compare against: "the copy agrees with MPFB" and "we
    could not ask MPFB" are different claims, and only the caller can tell which
    one matters ([why](../../../specifications/responses.md#response-shape)).
    """
    if live_urls is None:
        mpfb_entries = [_entry(key, MPFB_URLS[key], "mpfb") for key in sorted(MPFB_URLS)]
        stale = None
        differences = None
    else:
        mpfb_entries = [_entry(key, live_urls[key], "mpfb") for key in sorted(live_urls)]
        differences = _differences(live_urls)
        stale = bool(differences)

    # After MPFB's, and only where MPFB does not already use the key: the live
    # value wins every disagreement, this one included.
    claimed = {entry["key"] for entry in mpfb_entries}
    ecosystem_entries = [_entry(key, ECOSYSTEM_URLS[key], "mpfb_mcp")
                         for key in sorted(ECOSYSTEM_URLS) if key not in claimed]

    return {
        "urls": mpfb_entries + ecosystem_entries,
        "count": len(mpfb_entries) + len(ecosystem_entries),
        "fallback_stale": stale,
        "fallback_differences": differences,
        "vendored_mpfb_key_count": len(MPFB_URLS),
    }


def _differences(live_urls: dict[str, str]) -> list[dict[str, object]]:
    """Every key where the vendored copy and the live module disagree.

    Three ways to disagree, and they are kept apart because they call for
    different things: a changed URL means this file is wrong, a key MPFB has
    added means it is incomplete, and a key MPFB has removed means it is
    carrying an address that may no longer resolve.
    """
    differences = []
    for key in sorted(set(MPFB_URLS) | set(live_urls)):
        vendored = MPFB_URLS.get(key)
        live = live_urls.get(key)
        if vendored == live:
            continue
        if vendored is None:
            difference = "added_by_mpfb"
        elif live is None:
            difference = "missing_from_mpfb"
        else:
            difference = "changed"
        differences.append({
            "key": key,
            "difference": difference,
            "mpfb_url": live,
            "vendored_url": vendored,
        })
    return differences
