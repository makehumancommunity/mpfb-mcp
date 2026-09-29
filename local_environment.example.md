# Local environment

A template. Copy it to `local_environment.md` (gitignored) and fill it in for this machine, so that
Claude Code and anyone else working in the checkout knows where things are. Nothing in the
repository reads this file programmatically; scripts take their paths from environment variables
such as `BLENDER_EXE`.

## Blender

The Blender executable to use for the bridge's tests and for live checks, and whether it is
suitable for running headless:

    /path/to/blender

## MPFB

MPFB's user data directory (its preferences panel shows it). Beneath it:

- Installed assets are in `<user data>/data`
- Saved config (such as human presets) is in `<user data>/config`
- Information about installed asset packs is in `<user data>/data/packs`

Where the MPFB extension enabled in that Blender resolves to, and so where the running MPFB source
is (a checkout of https://github.com/makehumancommunity/mpfb2, if it is symlinked into an
extension repository).

## Version control

Leave this section out unless this is the maintainer's checkout. If it is, say so here — for
example "This is the maintainer's checkout." — and [CLAUDE.md](CLAUDE.md#version-control) applies
the maintainer's workflow instead of the contributor's.
