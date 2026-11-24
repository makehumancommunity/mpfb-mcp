# SPDX-License-Identifier: GPL-3.0-or-later

"""
The preloaded tool surface, measured and capped.

An MCP client downloads every tool's description and parameter schema before
any work happens, so the docstrings in ``src/mpfbmcp/tools/`` are a call-time
cost paid by every session that loads the tool, and by every session on a host
that loads every tool up front. The server instructions are paid by every
session on every host, and since
[FR 059](../feature-requests/done/059-what-a-session-pays-for/README.md) they are
measured here too, beside the two limits a client was seen or reported to cut
them at.
[FR 013](../feature-requests/done/013-live-verification/review.md) measured it
for the first time and found 66.7 KB of descriptions against an estimate of
58.5 KB - it had grown unnoticed across five requests, because nothing counted
it. This module counts it.

The ceiling below is what keeps the number from drifting silently again. It is
deliberately close to the current total rather than generous: a ceiling with
room in it is a ceiling that gets filled. Raising it is a decision, and the
right way to make it is to raise it here in the same commit as the docstring
that needs the space.

What this cannot test is whether a description is any *good*. Nothing on this
side of the socket can, which is why
[FR 016](../feature-requests/done/016-trim-tool-descriptions/README.md) trimmed
one tool at a time rather than in one pass, and why the rule it applied - a
sentence stays only if a caller with no access to this repository would act
differently for having read it - lives in
[tool-interface.md](../specifications/tool-interface.md#a-tool-description-is-call-time-instruction-with-a-budget)
rather than in an assertion here.

Run as a script to print the per-tool table rather than the assertion::

    python3 tests/test_description_budget.py

Run with::

    python -m unittest tests.test_description_budget -v
"""

from __future__ import annotations

__all__ = ()

import asyncio
import json
import unittest

import mpfbmcp

# The total of every tool's description, in bytes of UTF-8. FR 016 brought the
# measured total from 70,352 to 47,759 - a third of it - by moving rationale into
# specifications/, by shipping the docstrings dedented, and by giving the server
# instructions the conventions every tool was repeating. It stopped there rather
# than at the ~45,000 that request aimed for, because what was left was
# instruction: see FR 016 for what came out, and what was left in on purpose.
# The ceiling leaves about 700 bytes, which is a paragraph - enough that a real
# addition fits and a habit of adding does not.
#
# Raised from 48,500 to 52,200 by
# [FR 024](../feature-requests/done/024-documentation-urls/README.md), which
# added `mpfb_list_urls` and `mpfb_list_docs`. Two new tools cannot be made to
# fit inside a ceiling with 740 B of headroom and a 400 B floor per tool, so the
# request raised it deliberately rather than trimming twenty descriptions to pay
# for two. What keeps that from being a licence: both newcomers came in at 1,981
# and 1,806 B against a 2,387 B per-tool average, because a lookup tool
# instructs about a small static vocabulary and most of what a caller needs is
# visible in the response - and the headroom left over is the same paragraph it
# was before.
#
# Raised from 52,200 to 59,200 by
# [FR 025](../feature-requests/done/025-character-presets/README.md), which added
# `mpfb_list_presets`, `mpfb_save_preset` and `mpfb_create_human_from_preset` -
# 1,885, 2,404 and 2,723 B against a 2,341 B per-tool average. The catalogue one
# came in well under, as a catalogue tool should. The other two did not, and each
# has a reason that is instruction rather than rationale:
# `mpfb_create_human_from_preset` is the only tool in the package with seven
# optional arguments, each of which changes what gets built and none of which a
# caller can discover from a response (the two vocabularies it shares with
# existing tools - rig identifiers, skin models - are named by pointing at those
# tools rather than restated); and `mpfb_save_preset` is the only tool here that
# writes a file nothing can undo. The ceiling moves by roughly what the three
# cost, and the paragraph of headroom stays a paragraph.
#
# Raised from 59,200 to 62,400 by
# [FR 026](../feature-requests/done/026-face-units/README.md), which added
# `mpfb_get_face_units` and `mpfb_set_face_units` - 1,283 and 2,149 B against a
# 2,302 B per-tool average. The read tool came in well under, as a catalogue-ish
# tool should; the write tool spends its bytes on what a caller cannot discover
# from a response - the asset-pack precondition, the additive-by-default
# semantics, and the warning that a composed face is transient. The ceiling
# moves by roughly what the two cost, and the paragraph of headroom stays a
# paragraph.
#
# Raised from 62,400 to 68,300 by
# [FR 027](../feature-requests/done/027-expression-library/README.md), which
# added `mpfb_list_expressions`, `mpfb_get_expression`,
# `mpfb_apply_expressions` and `mpfb_save_expression` - 921, 1,067, 1,451 and
# 1,660 B against a 2,300 B per-tool average - and grew
# `mpfb_set_face_units` by about 300 B. All four came in under the average
# because the request required the composer/library conflict to be explained
# **once**, in `mpfb_set_face_units` (which is what its 300 B bought), and
# pointed at from the others; `mpfb_save_expression` is the largest because it
# is the second tool here to write a file nothing can undo. The ceiling moves by
# what the five cost, and the paragraph of headroom stays a paragraph.
#
# Raised from 68,300 to 69,600 by
# [FR 034](../feature-requests/done/034-character-summary/README.md), which added
# `mpfb_get_character_summary` - 1,315 B against a 2,160 B per-tool average -
# and grew `mpfb_get_macro_details` by one line for `macro_drift`. The summary
# is under the average because it restates no field: its description names the
# detailed tool behind each section, which the request required since the
# response carries no such map, and leaves each field's meaning to that tool's
# description. The ceiling moves by what the two cost, and the paragraph of
# headroom stays a paragraph.
#
# Raised from 69,600 to 72,900 by
# [FR 040](../feature-requests/done/040-procedural-material-settings/README.md),
# which added `mpfb_get_material_settings` and `mpfb_set_material_settings` -
# 1,619 and 1,730 B, both under the per-tool average, after a trim that took
# 680 B out of the first drafts. Neither names a socket or group: MPFB's node
# trees are read live and the vocabulary is in the read's answer. The read
# explains the answer's per-node keys once; the write spends its extra on the
# four things the request required it to say - the colour space, the
# linked-socket refusal, what makes a flat skin colour visible, and what
# discards the settings. The ceiling moves by what the two cost, and the
# paragraph of headroom stays a paragraph.
#
# Raised from 72,900 to 76,450 by
# [FR 041](../feature-requests/done/041-pose-controls-and-read-back/README.md), which
# added `mpfb_get_pose_controls` and `mpfb_get_pose` - 2,105 and 1,433 B. The
# first is at the per-tool average because it carries the posing vocabulary
# every later posing tool shares - the character frame, the ten body parts and
# the roles - once, as FR 027 did for the face; the read-back, which an agent
# calls after every pose change, points there and is well under. The ceiling
# moves by what the two cost, and the paragraph of headroom stays a paragraph.
#
# Raised from 76,450 to 80,450 by
# [FR 042](../feature-requests/done/042-posing-bones-switches-and-reset/README.md),
# which added `mpfb_set_pose_bones`, `mpfb_set_pose_switches` and
# `mpfb_reset_pose` - 1,672, 1,356 and 955 B, all under the per-tool average.
# None restates the posing vocabulary: the frame, the body parts and the roles
# stay in `mpfb_get_pose_controls`, and the writers spend their bytes on what a
# caller cannot discover from an answer - what each change kind means, which
# switches snap, and that `restore_with` is the undo. The ceiling moves by what
# the three cost, and the paragraph of headroom stays a paragraph.
#
# Raised from 80,450 to 80,800 by
# [FR 043](../feature-requests/done/043-narrower-pose-controls/README.md), which
# gave `mpfb_get_pose_controls` three arguments - `roles`, `include_hidden`,
# `compact` - and the three counts that explain what they leave out: 2,105 B to
# 2,438 B. It lost the "~60 KB" warning the default answer no longer earns, and
# names seven of the fifteen roles rather than all of them, since
# `counts_by_role` names every role on every classified answer. A compact entry
# drops keys rather than nulling them, so the description has to list the keys
# it keeps, which is most of the rest. The ceiling moves by what that cost.
#
# Raised from 80,800 to 84,050 by
# [FR 039](../feature-requests/done/039-exporting-characters/README.md), for two
# tools, both trimmed first and both under the average:
# `mpfb_create_export_copy` (1,988 B; 2,077 before trimming) carries MPFB's
# panel's eleven options and the swap it lacks, one clause each - what
# `bake_shapekeys` freezes, which pack each set needs, that the copy shares
# materials unless swapped - since none of that is discoverable from an answer
# before the call, plus the one refusal MPFB's own sequence makes necessary
# and how long the call can take, measured; `mpfb_export_character` (1,312 B;
# 1,552) spends most of its bytes on the one thing a caller must not guess at,
# that the directory is not theirs to choose. The readiness facts are named and
# not explained: they are in every answer.
#
# Raised from 84,050 to 85,500 by
# [FR 045](../feature-requests/done/045-placing-a-character/README.md), for one
# tool and three lines elsewhere: `mpfb_place_character` (1,320 B, well under
# the average) says what `facing` 0 means and which way is positive, since
# neither is discoverable from an answer before the call, and - because the
# live check found it - that a garment must be equipped before the character is
# placed, which is the one ordering mistake a sub-rig does not survive; the
# frame is left to the specification. `mpfb_get_character_summary` grew 126 B
# for the `placement` section's line, `mpfb_add_asset` 51 B for
# `subrigs_broken`, and `mpfb_add_rig` shrank 27 B where a false claim
# - that adding a rig moves a placed character - became the true one. The
# ceiling moves by what that cost.
#
# Raised from 85,500 to 86,350 by
# [FR 046](../feature-requests/done/046-license-in-the-catalogues/README.md), for
# three existing tools and no new one: 825 B, of which `mpfb_list_assets` is
# 451 B (773 B before trimming) for the `license` argument and the five answer
# keys a caller filters or counts by, `mpfb_list_asset_materials` 203 B and
# `mpfb_get_object_info` 171 B for naming the attribution fields they now carry.
# What a license means is one sentence - `null` is unknown, never permissive -
# and the derivation's caveats stay in the bridge docstrings.
#
# Raised from 86,350 to 88,400 by
# [FR 047](../feature-requests/done/047-rigify-hand-shapes/README.md), for two
# tools, both under the average: `mpfb_set_rigify_hand_shape` (1,236 B) names
# the six shapes, the finger names and both ranges, and what each sign of
# `spread` does on which finger, since a caller must send them before any answer
# could tell it; `mpfb_get_rigify_hand_shape` (840 B) points at the writer for
# the vocabulary and spends its bytes on what is measured beside the amounts.
# The shapes' amounts are in every reader answer (`known_shapes`), not here.
#
# Raised from 88,400 to 94,100 by
# [FR 048](../feature-requests/done/048-measuring-mesh-assets/README.md):
# `mpfb_check_intersections` at 2,040 B and `mpfb_check_mesh_asset` at 2,600 B,
# against a 2,050 B per-tool average, and 260 B on `mpfb_add_asset` for the field.
# The second is over the average because it is six sections, each of which a caller
# has to be told how to read, and because `outward_fraction` near 0.5 reads as a
# defect in a closed shell unless the description says otherwise.
#
# Raised from 94,100 to 99,400 by
# [FR 049](../feature-requests/done/049-makeskin-materials/README.md): the reader at
# 1,659 B and the writer at 2,077 B, about the 2,050 B average, and the store at 2,206 B,
# over it because `values_not_restored` is a surprise a caller cannot discover until a
# material comes back different, and a surprise stays in full.
#
# Raised from 99,400 to 102,000 by FR 050: `mpfb_write_mesh_asset` at about 2,530 B, over the
# average for its refusals, two of which a caller cannot foresee.
#
# Raised from 102,000 to 104,700 by FR 051: `mpfb_generate_delete_group` at about 2,800 B, over the
# average because two counts on a mesh nobody can see into need saying what each one counts, and
# nonzero being normal is not something a caller could guess.
#
# Raised from 104,700 to 106,600 by
# [FR 054](../feature-requests/done/054-refits-keep-the-pose/README.md), which adds no tool: an argument
# and an answer key on six, explained once in `mpfb_refit_human` at about 650 B and pointed at from the
# other five in a sentence each, because a refit that keeps a pose changes what a caller should expect
# from each of them. The ceiling keeps its paragraph of headroom.
#
# Raised from 106,600 to 108,250 by
# [FR 059](../feature-requests/done/059-what-a-session-pays-for/README.md), which adds no tool and
# moves 1,630 B into seven descriptions out of the answers, where the same text cost about 52 KB
# across the nine sessions that request measured. Most of it is requirement 12: `limb_measures`,
# `achieved_measure` and `amounts_measure` left every answer, so each tool that reports a limb,
# an `achieved` or a finger's amounts now says what it measures - `mpfb_get_pose` (+261),
# `mpfb_set_pose_switches` (+212) and `mpfb_reset_pose` (+202) the limbs, `mpfb_get_rigify_hand_shape`
# (+164) the amounts. `mpfb_set_pose_bones` (+498) and `mpfb_set_rigify_hand_shape` (+199) carry
# their definitions and also say that they now report only what the call moved or wrote and where
# the rest is named; `mpfb_add_asset` (+94) names `weights_from`, the field its weights warning
# became. Requirement 4 moved nothing: every sentence the instructions lost was already in the
# description of the tool it named. The ceiling keeps its headroom.
#
# Raised from 108,250 to 115,750 by
# [FR 060](../feature-requests/done/060-authoring-rigs/README.md), by what its four rig authoring tools
# measure: `mpfb_create_rig` 1,977 B, `mpfb_weight_rig` 1,931 B, `mpfb_store_rig` 1,859 B and
# `mpfb_get_rig_definition` 1,835 B, 7,602 B in all, less what the instructions' trims took off. Each is a table, three methods or four refusals
# about identification that a caller cannot foresee, and the order across the four is said once,
# in `mpfb_create_rig`. The instructions gained one clause, paid for by trimming four others.
#
# Raised from 115,750 to 119,250 by
# [FR 061](../feature-requests/done/061-rig-weights-that-hold-up/README.md), by what it measures:
# `mpfb_check_rig_weights` 2,326 B, new, its six sections and the bend's four measurements, and
# `mpfb_weight_rig` +676 B to 2,607 B, for the helper rules, `helper_bones` and the clean, which a
# caller cannot foresee and which change what a weighting writes. The instructions gained one tool
# name, paid for by shortening two clauses.
DESCRIPTION_CEILING = 119250

# The parameter schemas FastMCP derives from the signatures and annotations.
# Not docstring text, not written by hand, and not what FR 016 was about - but
# it is downloaded with the descriptions, so it is measured beside them and
# capped so that a signature cannot grow the preload unnoticed either. Raised
# from 9,000 to 10,400 by FR 025: `mpfb_create_human_from_preset` alone declares
# eight parameters, seven of them nullable, which is 881 B of `anyOf` - the
# largest schema in the package and the price of the "omitted means use what the
# preset says" idiom it shares with `mpfb_set_macro_details`.
#
# Raised from 10,400 to 10,600 by FR 026: `mpfb_set_face_units`'s batched
# `face_units` list is 431 B of array-of-object schema, the same shape
# `mpfb_set_targets` pays for twice over.
#
# Raised from 10,600 to 12,100 by FR 027: 1,482 B across four tools, of which
# 706 B is `mpfb_save_expression` - six optional metadata arguments, one schema
# line each, which the request named in advance as the largest new cost - and
# 423 B is `mpfb_apply_expressions`' batched `expressions` list, the same
# array-of-object shape as `mpfb_set_face_units`.
#
# Raised from 12,100 to 12,300 by FR 034: `mpfb_get_character_summary`'s one
# nullable `name` is 161 B, the smallest schema a tool acting on a character can
# have.
#
# Raised from 12,300 to 13,150 by FR 040: 845 B across two tools, of which
# 595 B is `mpfb_set_material_settings`' three batched lists - the
# array-of-object shape `mpfb_set_targets` pays for twice - and 250 B is the
# read's two nullable strings.
#
# Raised from 13,150 to 13,700 by FR 041: 545 B across two tools, each a
# nullable `name` and a nullable list of strings, `body_parts`.
#
# Raised from 13,700 to 14,650 by FR 042: 944 B across three tools - two
# batched lists of objects, the array-of-object shape `mpfb_set_targets` pays
# for, and `mpfb_reset_pose`'s `body_parts` and `include_switches`.
#
# Raised from 14,650 to 14,900 by FR 043: 250 B for `mpfb_get_pose_controls`'
# nullable `roles` list and its two bools.
#
# Raised from 14,900 to 15,000 by
# [FR 044](../feature-requests/done/044-switches-filter/README.md): 124 B for
# `mpfb_get_pose_controls`' nullable `switch_names` list, the same shape as
# `roles`.
#
# Raised from 15,000 to 16,600 by FR 039: 1,612 B across two tools, of which
# 1,143 B is `mpfb_create_export_copy`'s thirteen flat optional arguments - the
# panel's options, flat as the tool interface requires rather than nested.
#
# Raised from 16,600 to 17,100 by FR 045: 486 B for `mpfb_place_character`'s
# four nullable arguments, two of them objects.
#
# Raised from 17,100 to 17,200 by FR 046: 89 B for `mpfb_list_assets`'
# nullable `license`.
#
# Raised from 17,200 to 17,800 by FR 047: 580 B across two tools, a nullable
# `name` each, the reader's `body_parts` list and the writer's batched `hands`.
#
# Raised from 17,800 to 18,800 by FR 048: 868 B across three tools, most of it
# `mpfb_check_intersections`' four nullable arguments and `mpfb_check_mesh_asset`'s
# three, and one bool on `mpfb_add_asset`.
#
# Raised from 18,800 to 20,200 by FR 049: 1,390 B across three tools, most of it the
# setter's three nullable objects of objects and the store's seven arguments.
#
# Raised from 20,200 to 21,400 by FR 050: 1,190 B for `mpfb_write_mesh_asset`'s thirteen arguments.
#
# Raised from 21,400 to 22,000 by FR 051: 600 B for `mpfb_generate_delete_group`'s six.
#
# Raised from 22,500 to 22,650 by FR 056: 150 B, for `mpfb_list_assets`' `summary` and for `limit`
# and `offset` becoming nullable, since an unnamed one has to be told from a named one.
#
# Lowered from 22,650 to 11,700 by
# [FR 059](../feature-requests/done/059-what-a-session-pays-for/README.md): `build_server()` publishes
# the schemas without pydantic's `title` on every property and with an optional argument as its own
# type rather than `anyOf` with `null` and a null default, which was 11.5 KB of 22.5 KB. Both rules
# apply to whatever is registered, so the nullable arguments the raises above paid `anyOf` for now
# cost a type each, and every later one will. The ceiling is the 11,008 B measured plus a paragraph.
#
# Raised from 11,700 to 12,850 by FR 060: 1,136 B across four tools, most of it
# `mpfb_weight_rig`'s seven arguments and `mpfb_store_rig`'s seven.
SCHEMA_CEILING = 12850

# The server instructions, in characters, since that is what the one observed limit counted.
# A Claude Code session on 2026-11-05 received them cut off at exactly 4,096 characters, with the
# conventions - which came last and which no tool description repeats - among what was lost
# ([FR 059](../feature-requests/done/059-what-a-session-pays-for/README.md)). Nothing had measured
# them. The ceiling keeps a paragraph of headroom below that limit.
INSTRUCTIONS_CEILING = 4000

# The conventions end within this many characters of the start, since a secondary source puts the
# limit at 2 KB, and they are the part that has to survive whatever the limit turns out to be.
CONVENTIONS_END_CEILING = 2048

# The last words of the conventions, which is where CONVENTIONS_END_CEILING is measured to.
CONVENTIONS_END = "named in `temporarily_included`."

# A single description, in characters. The same secondary sources give this as the limit on one
# tool's description where a host loads every tool up front. `mpfb_list_assets` was at 4,094 when
# FR 059 set it, and arrived whole through tool search, so this is the only warning a later
# addition would get rather than a constraint today.
SINGLE_DESCRIPTION_CEILING = 4096

# Every tool the server registers is expected to describe itself. A zero-byte
# description would otherwise pass every assertion here.
MINIMUM_DESCRIPTION = 400


def instructions() -> str:
    """The instructions the server that ships sends on initialization."""
    return mpfbmcp.build_server().instructions or ""


def _schema_keys(schema: object, path: tuple = ()):
    """Every ``(path, key, value)`` of a schema that is a keyword, not a property's name or data.

    A key of ``properties`` names an argument, and an argument named ``title`` is not the
    generated keyword; a ``default`` or an ``enum`` is data, and a dict inside one is not a schema.
    """
    if isinstance(schema, list):
        for index, item in enumerate(schema):
            yield from _schema_keys(item, path + (index,))
        return
    if not isinstance(schema, dict):
        return
    for key, value in schema.items():
        yield (path, key, value)
        if key in ("properties", "$defs", "definitions", "patternProperties") \
                and isinstance(value, dict):
            for name, sub in value.items():
                yield from _schema_keys(sub, path + (key, name))
        elif key in ("anyOf", "allOf", "oneOf", "prefixItems", "items", "additionalProperties",
                     "not"):
            yield from _schema_keys(value, path + (key,))


def measure() -> list[dict[str, object]]:
    """One entry per registered tool, largest description first.

    Measures the server ``mpfbmcp.build_server()`` actually builds rather than a
    list of tools kept here, so a tool registered without being thought about is
    inside the budget rather than outside it.
    """
    tools = asyncio.run(mpfbmcp.build_server().list_tools())
    measured = [
        {
            "name": tool.name,
            "description": tool.description or "",
            "description_bytes": len((tool.description or "").encode("utf-8")),
            "description_characters": len(tool.description or ""),
            "schema_bytes": len(
                json.dumps(tool.inputSchema, separators=(",", ":")).encode("utf-8")),
            "input_schema": tool.inputSchema,
        }
        for tool in tools
    ]
    measured.sort(key=lambda entry: entry["description_bytes"], reverse=True)
    return measured


def report() -> str:
    """The table a human reads: per tool, then the totals against the ceilings."""
    measured = measure()
    lines = ["{:>8s} {:>8s}  {:s}".format("desc", "schema", "tool")]
    for entry in measured:
        lines.append("{:8d} {:8d}  {:s}".format(
            entry["description_bytes"], entry["schema_bytes"], entry["name"]))
    descriptions = sum(entry["description_bytes"] for entry in measured)
    schemas = sum(entry["schema_bytes"] for entry in measured)
    text = instructions()
    instruction_bytes = len(text.encode("utf-8"))
    lines.append("")
    lines.append("{:d} B of server instructions ({:d} characters, ceiling {:d}; the conventions "
                 "end at {:d}, ceiling {:d})".format(
                     instruction_bytes, len(text), INSTRUCTIONS_CEILING,
                     text.find(CONVENTIONS_END) + len(CONVENTIONS_END), CONVENTIONS_END_CEILING))
    lines.append("{:d} tools, {:d} B of descriptions (ceiling {:d}) plus {:d} B of "
                 "parameter schemas (ceiling {:d}) plus the instructions = {:d} B preloaded".format(
                     len(measured), descriptions, DESCRIPTION_CEILING,
                     schemas, SCHEMA_CEILING, descriptions + schemas + instruction_bytes))
    return "\n".join(lines)


class DescriptionBudgetTests(unittest.TestCase):

    def setUp(self) -> None:
        self.measured = measure()

    def test_every_registered_tool_is_measured(self) -> None:
        self.assertEqual(56, len(self.measured))

    def test_total_description_size_is_under_the_ceiling(self) -> None:
        total = sum(entry["description_bytes"] for entry in self.measured)
        self.assertLessEqual(
            total, DESCRIPTION_CEILING,
            "tool descriptions total {:d} B, over the {:d} B ceiling. Move rationale into "
            "specifications/ rather than raising this, or raise it deliberately and say "
            "why in the commit.".format(total, DESCRIPTION_CEILING))

    def test_total_parameter_schema_size_is_under_the_ceiling(self) -> None:
        total = sum(entry["schema_bytes"] for entry in self.measured)
        self.assertLessEqual(total, SCHEMA_CEILING)

    def test_no_single_description_is_over_the_limit_one_host_cuts_at(self) -> None:
        for entry in self.measured:
            self.assertLessEqual(
                entry["description_characters"], SINGLE_DESCRIPTION_CEILING, entry["name"])

    def test_no_input_schema_carries_a_generated_title(self) -> None:
        for entry in self.measured:
            for path, key, _value in _schema_keys(entry["input_schema"]):
                self.assertNotEqual(key, "title", "{:s} at {!r}".format(entry["name"], path))

    def test_no_optional_argument_is_published_as_a_union_with_null(self) -> None:
        # The shape `str | None = None` would publish: an `anyOf` with a `null` option beside a
        # null default. A required nullable argument has no default and keeps its null.
        for entry in self.measured:
            for path, key, value in _schema_keys(entry["input_schema"]):
                if key != "anyOf" or not isinstance(value, list):
                    continue
                with self.subTest(tool=entry["name"], path=path):
                    owner = entry["input_schema"]
                    for step in path:
                        owner = owner[step]
                    self.assertFalse(
                        {"type": "null"} in value and "default" in owner
                        and owner["default"] is None)

    def test_a_property_named_title_would_keep_its_name(self) -> None:
        # No tool declares one today, so this asks the rewrite directly.
        schema = {"title": "xArguments", "type": "object", "required": ["title"],
                  "properties": {
                      "title": {"title": "Title", "type": "string"},
                      "tags": {"anyOf": [{"type": "array", "items": {"type": "string",
                                                                      "title": "Tag"}},
                                         {"type": "null"}],
                               "default": None, "title": "Tags"},
                      "either": {"anyOf": [{"type": "string"}, {"type": "integer"}],
                                 "default": None, "title": "Either"},
                      "kept": {"anyOf": [{"type": "string"}, {"type": "null"}],
                               "default": "x", "title": "Kept"},
                      "needed": {"anyOf": [{"type": "string"}, {"type": "null"}],
                                 "title": "Needed"},
                      "data": {"default": {"title": "not a keyword"}, "type": "object",
                               "title": "Data"}}}
        self.assertEqual(
            mpfbmcp._without_generated_keys(schema),  # pylint: disable=protected-access
            {"type": "object", "required": ["title"],
             "properties": {
                 "title": {"type": "string"},
                 "tags": {"type": "array", "items": {"type": "string"}},
                 "either": {"anyOf": [{"type": "string"}, {"type": "integer"}], "default": None},
                 "kept": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": "x"},
                 "needed": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                 "data": {"default": {"title": "not a keyword"}, "type": "object"}}})

    def test_every_tool_describes_itself(self) -> None:
        for entry in self.measured:
            self.assertGreaterEqual(
                entry["description_bytes"], MINIMUM_DESCRIPTION, entry["name"])

    def test_every_description_names_the_response_field_carrying_the_answer(self) -> None:
        """FR-2: a caller must be able to see what to read, not only what to send.

        The check is deliberately weak - it asserts that a description mentions
        ``result`` and at least one backtick-quoted field name - because the
        strong version is a judgement no assertion can make. It fails on the one
        regression it can see: a trim that removes the response section.
        """
        for entry in self.measured:
            self.assertIn("result", entry["description"], entry["name"])
            self.assertIn("`", entry["description"], entry["name"])


class InstructionsBudgetTests(unittest.TestCase):

    def setUp(self) -> None:
        self.instructions = instructions()

    def test_the_instructions_are_under_the_ceiling(self) -> None:
        self.assertLessEqual(
            len(self.instructions), INSTRUCTIONS_CEILING,
            "the server instructions are {:d} characters, over the {:d} ceiling. A fact about one "
            "tool belongs in its description; see INSTRUCTIONS in src/mpfbmcp/__init__.py.".format(
                len(self.instructions), INSTRUCTIONS_CEILING))

    def test_the_conventions_come_right_after_the_opening_sentence(self) -> None:
        opening_ends = self.instructions.index(". ") + 2
        self.assertTrue(self.instructions[opening_ends:].startswith("Conventions every tool"))

    def test_the_conventions_end_within_the_shorter_limit(self) -> None:
        self.assertIn(CONVENTIONS_END, self.instructions)
        self.assertLessEqual(
            self.instructions.index(CONVENTIONS_END) + len(CONVENTIONS_END),
            CONVENTIONS_END_CEILING)

    def test_every_convention_is_stated(self) -> None:
        # What the tool descriptions leave out because the instructions carry it.
        conventions = self.instructions[:self.instructions.index(CONVENTIONS_END)]
        for key in ("`status`", "`result`", "`error`", "`message`", "`name`", "`found`",
                    "`ready`", "`blocked_by`", "`performed`", "`changes`", "`truncated`",
                    "`total_count`", "`offset`", "`limit`"):
            self.assertIn(key, conventions)


if __name__ == "__main__":
    print(report())
