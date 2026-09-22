# What the headless spike found

**Run** `spike_headless_operators.py` in a Blender with MPFB enabled:

```bash
/path/to/blender -b -noaudio -P spike_headless_operators.py
```

[FR 032's Architecture section](README.md#architecture) asks for this before any migration,
because three of the fourteen commands drive `bpy.ops` somewhere below them and operators in
`blender --background` fail for context reasons that have nothing to do with this project's code.
It named the answer as the single largest schedule risk in the effort.

## The answer: everything works headless, Rigify included

Blender 5.1.0, `bpy.app.background == True`, MPFB 2.x from a source-clone extension repository.

| Probe | Outcome |
|-------|---------|
| `bpy.context.mode` | `'OBJECT'` — readable, and the mode every `bpy.ops` path below polls for |
| `HumanService.create_human()` | 19,158 vertices |
| `SystemService.check_for_rigify()` | `True` — Rigify is a bundled extension and is enabled |
| `HumanService.add_builtin_rig(..., "default")` | rig added, weights imported |
| `HumanService.add_builtin_rig(..., "rigify.human")` | meta rig added, `identify_rig() == 'rigify.human'` |
| `RigService.generate_rigify_rig()` | **generated `Human.rigify`**, `identify_rig() == 'rigify_generated.human'` |
| `HumanService.add_mhclo_asset()` | imported and fitted a garment |
| `MaterialService.create_empty_material()` | created, one material slot |
| `HumanService.refit()` | returned without raising |
| `HumanService.serialize_to_json_file()` | 851 bytes written |
| `HumanService.deserialize_from_json_file()` | character rebuilt |

So **requirement 6 needs no exception**. Fourteen bridge test modules can exist, the three
operator-driven ones included, and nothing has to be deferred to the effort's own live check for
want of a window. `generate_rigify_rig()` even leaves the generated rig active, which is the
behaviour `mpfb_generate_rigify_rig` reports as `active_object_after` — so the one mutating tool
that cannot restore the caller's selection is directly assertable here.

## The one thing that is not about headless mode, and matters for fixtures

`HumanService.refit()` raised `IOError` on a character wearing a garment that had been equipped
from a path outside every data root:

```
OSError: mpfb-spike-ntvozhzv/spike.mhclo does not exist
```

`ClothesService.fit_clothes_to_human()` re-reads the garment's MHCLO through `AssetService`, which
searches the **data roots** rather than remembering where the file came from. A garment equipped
from a temporary directory therefore cannot be refitted afterwards.

This is MPFB's behaviour rather than a defect, and it is not a headless finding at all — but it
sets a rule for requirement 6's fixtures: **a fixture asset tree must be a redirected data root**
(`_fixtures.only_these_data_roots()`), not merely a temporary directory a test wrote an MHCLO
into. The read-only commands FR 031 migrated never re-read an asset, so nothing before now could
have discovered it.

## What the spike does not establish

That the *timer-driven* server answers the same as the blocking dispatch, which is the standing
limit of this suite and belongs to the effort's own live check; and anything about a Blender with
Rigify **disabled**, which this machine's is not. `mpfb_generate_rigify_rig`'s `rigify_unavailable`
refusal is therefore a skip-with-a-reason in the bridge suite, exactly as an install without MPFB
is.
