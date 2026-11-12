# SPDX-License-Identifier: GPL-3.0-or-later

"""
What ``mpfb_*`` results cost across this machine's Claude Code transcripts, and what FR 059 saves.

Run with any Python, before the effort and again after it::

    python3 -I feature-requests/059-what-a-session-pays-for/measure_transcripts.py

It reads ``~/.claude/projects`` and prints sizes, plus the opening of each repeated sentence, which
is this package's own text. It imports nothing from this repository and writes nothing. The numbers
describe the sessions that exist, on whatever version of the tools each one ran, so they rank the
candidates rather than promise a saving.
"""

from __future__ import annotations

__all__ = ()

import collections
import copy
import glob
import json
import os
import statistics

_TIPS = {"left_arm": "left_hand", "right_arm": "right_hand", "left_leg": "left_foot",
         "right_leg": "right_foot", "left_hand": "left_hand", "right_hand": "right_hand",
         "left_foot": "left_foot", "right_foot": "right_foot", "head": "head", "neck": "head"}
_MOVES_EVERYTHING = {"torso", "hips", "spine", "root", "body"}
_MEASURES = ("limb_measures", "achieved_measure", "amounts_measure")


def _results():
    """Every mpfb result, once, as (tool, transcript, text)."""
    names, seen, results = {}, set(), []
    for path in glob.glob(os.path.expanduser("~/.claude/projects/*/**/*.jsonl"), recursive=True):
        with open(path, errors="replace") as handle:
            for line in handle:
                if "tool_" not in line:
                    continue
                try:
                    blocks = (json.loads(line).get("message") or {}).get("content")
                except ValueError:
                    continue
                for block in blocks if isinstance(blocks, list) else ():
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_use" and block.get("name", "").startswith("mcp__mpfb__"):
                        names[block["id"]] = block["name"].replace("mcp__mpfb__", "")
                    use_id = block.get("tool_use_id")
                    if block.get("type") == "tool_result" and use_id in names and use_id not in seen:
                        seen.add(use_id)
                        content = block.get("content")
                        parts = content if isinstance(content, list) else [{"type": "text", "text": content}]
                        text = "".join(part.get("text", "") for part in parts
                                       if isinstance(part, dict) and part.get("type") == "text")
                        results.append((names[use_id], path, text))
    return results


def _size(value):
    return len(json.dumps(value, separators=(",", ":"), ensure_ascii=False))


def _strings(value, counts):
    if isinstance(value, str):
        counts[value] += 1
    elif isinstance(value, dict):
        for item in value.values():
            _strings(item, counts)
    elif isinstance(value, list):
        for item in value:
            _strings(item, counts)


def _rounded(value, digits):
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {key: _rounded(item, digits) for key, item in value.items()}
    return [_rounded(item, digits) for item in value] if isinstance(value, list) else value


def _flat_uniform(value):
    """Characters in arrays a tabular format such as TOON could take."""
    if (isinstance(value, list) and len(value) >= 3 and all(isinstance(item, dict) for item in value)
            and len({tuple(sorted(item)) for item in value}) == 1
            and not any(isinstance(field, (dict, list)) for item in value for field in item.values())):
        return _size(value)
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    return sum(_flat_uniform(child) for child in children)


def _untouched_pose_readings(result):
    """Characters in limbs and landmarks a write could not have moved, by body part."""
    parts = {change.get("body_part") for change in result.get("changes") or []}
    if parts & _MOVES_EVERYTHING or not isinstance(result.get("limbs"), dict):
        return 0
    trimmed = copy.deepcopy(result)
    before = _size(trimmed)
    trimmed["limbs"] = {key: item for key, item in result["limbs"].items() if key in parts}
    if isinstance(result.get("landmarks"), dict):
        keep = {_TIPS.get(part) for part in parts}
        trimmed["landmarks"] = {key: item for key, item in result["landmarks"].items() if key in keep}
    return before - _size(trimmed)


def _unwritten_fingers(result):
    trimmed = copy.deepcopy(result)
    before = _size(trimmed)
    for hand in trimmed.get("hands") or []:
        for key in ("fingers_before", "fingers_after"):
            if isinstance(hand.get(key), dict):
                hand[key] = {name: item for name, item in hand[key].items()
                             if name in (hand.get("fingers_written") or ())}
    return before - _size(trimmed)


def main():
    results = _results()
    total = sum(len(text) for _, _, text in results)
    per_session = collections.Counter()
    per_session_calls = collections.Counter()
    per_tool = collections.defaultdict(list)
    for tool, path, text in results:
        per_session[path] += len(text)
        per_session_calls[path] += 1
        per_tool[tool].append(len(text))
    print("{:d} results, {:d} characters, {:d} sessions".format(len(results), total, len(per_session)))
    print("per session: median {:.0f} characters, max {:d}, median {:.0f} calls".format(
        statistics.median(per_session.values()), max(per_session.values()),
        statistics.median(per_session_calls.values())))
    print("over 10,000: {:d}, over 25,000: {:d}".format(
        sum(len(text) > 10000 for *_, text in results), sum(len(text) > 25000 for *_, text in results)))
    for tool, sizes in sorted(per_tool.items(), key=lambda item: -sum(item[1]))[:6]:
        print("  {:<30s} {:4d} calls, mean {:5d}, {:4.1f} %".format(
            tool, len(sizes), sum(sizes) // len(sizes), 100 * sum(sizes) / total))

    parsed = []
    for tool, _, text in results:
        try:
            parsed.append((tool, json.loads(text)))
        except ValueError:
            pass
    base = sum(_size(answer) for _, answer in parsed)
    share = lambda saved: "{:7d}  {:4.1f} %".format(saved, 100 * saved / base)

    counts = collections.Counter()
    for _, answer in parsed:
        _strings(answer, counts)
    prose = [(text, count) for text, count in counts.items()
             if len(text) >= 40 and count >= 5 and " " in text and not text.startswith("/")]
    print("\nRepeated prose, 40 characters or more, seen 5 times or more:")
    print("  all", share(sum(len(text) * (count - 1) for text, count in prose)))
    for text, count in sorted(prose, key=lambda item: -len(item[0]) * (item[1] - 1))[:5]:
        print("  x{:<4d} {!r}".format(count, text[:70]))

    def of(tool):
        return [answer["result"] for name, answer in parsed
                if name == tool and isinstance(answer.get("result"), dict)]

    adds = of("mpfb_add_asset")
    print("\nCandidates, as characters and a share of everything:")
    print("  *_measure(s) keys       ", share(sum(
        _size(result[key]) + len(key) + 3
        for _, answer in parsed if isinstance(answer.get("result"), dict)
        for result in [answer["result"]] for key in _MEASURES if key in result)))
    print("  weights warning         ", share(sum(
        len(text) for result in adds for text in result.get("warnings") or ()
        if text.startswith("import_weights was"))))
    print("  on {:d} of {:d} mpfb_add_asset calls".format(sum(
        any(text.startswith("import_weights was") for text in result.get("warnings") or ())
        for result in adds), len(adds)))
    print("  untouched limbs, landmarks", share(sum(_untouched_pose_readings(r) for r in of("mpfb_set_pose_bones"))))
    print("  unwritten fingers       ", share(sum(_unwritten_fingers(r) for r in of("mpfb_set_rigify_hand_shape"))))

    print("\nRejected, for comparison:")
    print("  floats rounded to 3     ", share(base - sum(_size(_rounded(answer, 3)) for _, answer in parsed)))
    print("  flat uniform arrays     ", share(sum(_flat_uniform(answer) for _, answer in parsed)))
    print("  message                 ", share(sum(
        _size(answer["result"]["message"]) + 10 for _, answer in parsed
        if isinstance(answer.get("result"), dict) and answer["result"].get("message"))))
    print("  envelope                ", share(sum(
        _size({key: item for key, item in answer.items() if key != "result"}) for _, answer in parsed)))


if __name__ == "__main__":
    main()
