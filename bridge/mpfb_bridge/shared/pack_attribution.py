"""
Which installed packs claim a file, and what their metadata says about it.

**One implementation, imported by every command that reports a license.** See
[`__init__.py`](__init__.py) for why this directory exists beside
``commands/``. ``list_assets`` and ``list_asset_materials`` report it per row,
``get_object_info`` per equipped asset through
[`asset_info.py`](asset_info.py), and ``get_character_summary`` carries a subset
of that. Two of them reporting different licenses for one file is the
disagreement a shared module exists to make impossible, and the answer may end
up in somebody's licensing decision
([FR 046](../../../feature-requests/done/046-license-in-the-catalogues/README.md)).

**The attribution is derived, not recorded.** MPFB stores no link from an
installed file back to the pack that installed it. A pack's JSON names the
*directories* it installs under, one entry per asset, each with a ``license``,
an ``author`` and a ``source`` page. So a file is attributed by joining:

1. **its containing directory's name** against the asset names the packs claim,
   which is how ``pack`` was always derived. A file lying **directly in an asset
   root** is not attributed at all: its directory is named for the subdir
   (``skins/default.mhmat`` sits in ``skins``), and the join would hand it to
   whichever pack happened to ship an asset called that. No directory name means
   no attribution, and no fallback either.
2. **its file stem**, only when the directory claims nothing. Eye materials need
   it: ``eyes/materials/brown.mhmat`` sits in a directory called ``materials``,
   and ``makehuman_system_assets`` claims it as ``brown``. **This rests on a
   condition measured rather than guaranteed**: on the maintainer's install,
   with 1,606 pack entries, the fallback attributes exactly the nine files under
   ``eyes/materials/`` and nothing else. Stems repeat (``teeth`` seven times),
   but every repeat sits in a directory that is already claimed, so the fallback
   never reaches it. A pack that one day claims ``materials`` would turn this
   off for eye materials silently; one that ships a directory nothing claims,
   full of files named like another pack's assets, would mis-attribute them.

What follows from the join, and is said here rather than tidied up:

- **A material in its asset's own directory takes the asset's attribution.**
  That is right when the garment's author shipped it, and cannot be told apart
  from a material someone dropped into that directory by hand.
- **A field is reported only when every claimant agrees on it.** Two packs may
  claim one directory (``hats01`` and ``hats01_cc0``); none disagree on this
  install, but the next one may, and a disagreement is answered with ``None``
  and ``claims_disagree``, every claim kept for the caller to report.
- **No claim is an ordinary answer**: ``license`` ``None``, ``packs`` ``[]``.
  It is never filled in from a pack's name, the asset's subdir, or a ``license``
  line in the file itself. MHCLO files carry one only as free text, most often
  MakeClothes' boilerplate about the *tool*, and MPFB's ``MHMAT_KEYS`` defaults
  a missing MHMAT ``license`` to ``CC0`` - reading that would report an unknown
  license as CC0, the worst wrong answer there is.
- **Pack metadata is read only from the user data root's** ``packs/``. A file
  under another data root is joined against it all the same, by name: right
  when a pack's files were copied there, wrong when an unrelated asset shares
  the name, and ``None`` when its pack's metadata was never installed here,
  even if the file did come from a pack.

**How the entries are read.** MPFB publishes the pack names and each pack's
asset names (``get_pack_names()``, ``get_asset_names_in_pack()``), not the
entries. So the entries are read off ``assetservice.py``'s module global
``_PACKS`` after ``get_pack_names()`` has populated it, through
[`mpfb_surface.py`](mpfb_surface.py): one scan, MPFB's cached one, so ``pack``
and ``license`` cannot describe two different reads, and ``refresh`` on either
catalogue keeps its meaning. A public ``AssetService.get_pack_metadata()`` is
used first if MPFB ever grows one (proposed in ``MCP_DISCOVERED_BUGS.md``). If
neither is there, the names still come from the published getters and every
license is ``None``; :attr:`PackIndex.entries_read` says so, for the message.

**Built once per call** (:func:`read_index`) and passed down, never per row:
the catalogue already read this metadata for ``pack``, and attribution must not
add a second read per asset or per material.
"""

__all__ = (
    "FIELDS",
    "PackIndex",
    "attribute",
    "read_index",
    "unattributed",
)

import os

from . import mpfb_surface

# What each attribution reports, in the order a row carries them. ``source_url``
# rather than the metadata's own ``source``, because several answers already
# report ``asset_source``, a fragment, and the two would read as one concept.
FIELDS = ("license", "author", "source_url", "packs")

# Pack metadata key -> attribution key, for the three a claim carries.
_CLAIM_KEYS = (("license", "license"), ("author", "author"), ("source", "source_url"))


class PackIndex:
    """Every installed pack's claims, keyed by the asset name a pack claims.

    ``pack_names`` is every installed pack, sorted, whether or not it has
    anything on disk. ``claims`` maps an asset name to one dict per claiming
    pack, sorted by pack. ``known_licenses`` is every license the metadata
    records, sorted. ``entries_read`` is ``False`` when only the names could be
    read, in which case every claim's fields are ``None``.
    """

    __slots__ = ("pack_names", "claims", "known_licenses", "entries_read")

    def __init__(self, pack_names, claims, entries_read):
        self.pack_names = pack_names
        self.claims = claims
        self.entries_read = entries_read
        licenses = set()
        for asset_claims in claims.values():
            for claim in asset_claims:
                if claim["license"] is not None:
                    licenses.add(claim["license"])
        self.known_licenses = sorted(licenses)


def _text(value):
    """A metadata value as reported: a non-empty string, or ``None``."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _entries_of(services, pack_names):
    """pack name -> {asset name: entry}, or ``None`` when MPFB does not let them be read.

    After ``get_pack_names()``, which populated ``_PACKS`` if it was ``None``.
    """
    asset_service = services["AssetService"]
    getter = getattr(asset_service, "get_pack_metadata", None)
    if callable(getter):
        entries = dict()
        try:
            for pack_name in pack_names:
                entries[pack_name] = getter(pack_name) or dict()
        except Exception:  # pylint: disable=broad-except
            entries = None
        if entries is not None:
            return entries
    packs = mpfb_surface.module_level(services, "AssetService", "_PACKS", fallback=None)
    if not isinstance(packs, dict):
        return None
    return packs


def read_index(services):
    """Every installed pack's claims, read once for this call."""
    asset_service = services["AssetService"]
    try:
        pack_names = sorted(str(name) for name in (asset_service.get_pack_names() or []))
    except Exception:  # pylint: disable=broad-except
        pack_names = []

    entries = _entries_of(services, pack_names)
    claims = dict()
    for pack_name in pack_names:
        pack_entries = None if entries is None else entries.get(pack_name)
        if isinstance(pack_entries, dict):
            asset_names = list(pack_entries.keys())
        else:
            pack_entries = dict()
            try:
                asset_names = asset_service.get_asset_names_in_pack(pack_name) or []
            except Exception:  # pylint: disable=broad-except
                asset_names = []
        for asset_name in asset_names:
            entry = pack_entries.get(asset_name)
            entry = entry if isinstance(entry, dict) else dict()
            claim = {"pack": pack_name}
            for metadata_key, attribution_key in _CLAIM_KEYS:
                claim[attribution_key] = _text(entry.get(metadata_key))
            claims.setdefault(str(asset_name), []).append(claim)
    for asset_claims in claims.values():
        asset_claims.sort(key=lambda claim: claim["pack"])
    return PackIndex(pack_names, claims, entries is not None)


def unattributed():
    """What :func:`attribute` answers for a file no pack claims, or no file at all."""
    return {"license": None, "author": None, "source_url": None, "packs": [],
            "claims_disagree": False, "claims": []}


def _claims_for(index, path, normalized_roots):
    directory = os.path.normpath(os.path.dirname(path))
    if directory in normalized_roots:
        # Directly in an asset root: see the module docstring. No fallback.
        return []
    claims = index.claims.get(os.path.basename(directory))
    if claims:
        return claims
    stem = os.path.splitext(os.path.basename(path))[0]
    return index.claims.get(stem) or []


def attribute(index, path, roots):
    """Who claims ``path``, and what they agree it is.

    ``roots`` are the asset roots ``path`` is to be judged against, as the
    caller searched them - this module does not decide a subdir, because
    ``list_assets`` and ``list_asset_materials`` derive theirs differently.
    The answer carries :data:`FIELDS`, plus ``claims_disagree`` and every claim
    under ``claims``, for a command that reports the disagreement.
    """
    if not path:
        return unattributed()
    normalized_roots = [os.path.normpath(str(root)) for root in roots or []]
    claims = _claims_for(index, str(path), normalized_roots)
    answer = unattributed()
    if not claims:
        return answer
    answer["packs"] = [claim["pack"] for claim in claims]
    answer["claims"] = [dict(claim) for claim in claims]
    for _metadata_key, key in _CLAIM_KEYS:
        values = set(claim[key] for claim in claims)
        if len(values) == 1:
            answer[key] = values.pop()
        else:
            answer["claims_disagree"] = True
    return answer
