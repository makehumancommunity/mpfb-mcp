"""
The commands that **change** a .blend, against a real MPFB - thirteen when this
directory was made, sixteen since FR 026 and FR 027 added the face commands,
seventeen since FR 040 added ``set_material_settings``, twenty since FR 042 added
the three pose writers.

**A layer, after the add-on itself and the read-only commands.** A module here
may assume that everything under ``aaa_addon/`` and ``ccc_reading/`` passed, and
``-x`` makes sure it only runs if it did. That is what the ``ddd_`` buys: a
write whose result is read back through a read-only command means nothing if
that command's own module has not passed first. Inside the layer the modules are
unprefixed and their order carries no meaning (see
[testing.md](../../../../specifications/testing.md#two-harnesses-split-at-the-directory-boundary)).
Until [FR 035](../../../../feature-requests/done/035-bridge-test-layers/README.md)
this directory sorted *between* read-only modules, and was a way out of running
short of letters rather than a layer.

**One module per command, and only commands.** ``list_urls`` migrated in the same
effort as these and is *read-only*, so it is in ``ccc_reading/``. A test whose
claim is about several commands at once is in ``eee_composite/``, even when
every command it dispatches is one of these. What this directory holds is the
set FR 032's requirement 3 is about: commands that mutate, and therefore
commands whose tests have an obligation the layers before them do not.

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
[the spike](../../../../feature-requests/done/032-creation-and-modification-migrated/SPIKE.md)
before any of this was written: a fixture asset tree must be a **redirected data
root**, not merely a temporary directory with an MHCLO in it.
``ClothesService.fit_clothes_to_human()`` re-reads a garment's MHCLO through
``AssetService``, which searches the data roots - so a garment equipped from
outside them can be equipped and then never refitted.
``_fixtures.only_these_data_roots()`` is that, spelled once.
"""

__all__ = ()
