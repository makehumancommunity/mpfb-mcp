"""
The thirteen commands that **change** a .blend, against a real MPFB.

**A directory rather than fourteen more prefixed files, and that is the whole
reason this package exists.** ``bridge/test/tests/`` forces module order with an
``aaa_``…``ooo_`` prefix, MPFB's arrangement; fifteen of those are taken, and
[FR 032](../../../../feature-requests/032-creation-and-modification-migrated/README.md)
adds fourteen modules against the eleven letters left before ``zzz_``. MPFB
prefixes *directories* as well as files - ``bbb_services/``, ``ccc_data/``,
``ddd_entities/``, ``eee_ui/`` - and that is the way out, taken here once rather
than discovered at the twelfth module. Inside a prefixed directory the modules
need no prefix of their own: they are ordered among themselves alphabetically
and the directory is ordered among its siblings.

**Thirteen, not fourteen.** ``list_urls`` migrated in the same effort and is
*read-only*, so it stays a flat sibling module out here with the other read-only
commands. What this directory holds is the set FR 032's requirement 3 is about:
commands that mutate, and therefore commands whose tests have an obligation the
fifteen before them did not.

**Cleanup is this suite's own risk now.** A read-only command could not leave
anything behind. These add rigs, equip assets, create materials and write preset
files, and a *failing* test is exactly the one most likely to leave something.
Two rules follow, and every module here keeps both:

- **What a test made, the fixture removes**, however the test ends.
  [`_fixtures.Character`](../_fixtures.py) already does that for objects, by
  snapshotting names on the way in and deleting what is new on the way out -
  which is why a test that adds a rig or equips a garment needs no cleanup code
  of its own, since both are new objects on a character inside that block.
- **A test that writes outside the .blend writes somewhere redirected.**
  ``redirected_locations()`` points MPFB's ``LocationService`` at a
  ``tmp_path``; nothing here may touch the developer's real config directory,
  and the two preset commands are the ones that would.

**And one rule that is not about cleanup**, found by
[the spike](../../../../feature-requests/032-creation-and-modification-migrated/SPIKE.md)
before any of this was written: a fixture asset tree must be a **redirected data
root**, not merely a temporary directory with an MHCLO in it.
``ClothesService.fit_clothes_to_human()`` re-reads a garment's MHCLO through
``AssetService``, which searches the data roots - so a garment equipped from
outside them can be equipped and then never refitted.
``_fixtures.only_these_data_roots()`` is that, spelled once.
"""

__all__ = ()
