#!/usr/bin/env python3
"""Split OCR tokens into independent text units using spatial gaps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import median


def overlap_ratio(a: list[float], b: list[float], axis: str) -> float:
    if axis == "horizontal":
        start, end = max(a[1], b[1]), min(a[3], b[3])
        base = min(a[3] - a[1], b[3] - b[1])
    else:
        start, end = max(a[0], b[0]), min(a[2], b[2])
        base = min(a[2] - a[0], b[2] - b[0])
    return max(0.0, end - start) / max(base, 1.0)


def union_bounds(items: list[dict]) -> list[float]:
    return [
        min(item["bounds"][0] for item in items),
        min(item["bounds"][1] for item in items),
        max(item["bounds"][2] for item in items),
        max(item["bounds"][3] for item in items),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="JSON list or object with an items list")
    parser.add_argument("output", type=Path)
    parser.add_argument("--orientation", choices=("horizontal", "vertical"), default="horizontal")
    parser.add_argument("--gap-ratio", type=float, default=1.25)
    parser.add_argument("--minimum-gap", type=float, default=8.0)
    parser.add_argument("--line-overlap", type=float, default=0.5)
    parser.add_argument("--joiner", default="")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    items = payload["items"] if isinstance(payload, dict) else payload
    if not items:
        raise SystemExit("No OCR items found")
    for item in items:
        if "text" not in item or "bounds" not in item or len(item["bounds"]) != 4:
            raise SystemExit("Every OCR item requires text and four-value bounds")

    cross_sizes = [
        (item["bounds"][3] - item["bounds"][1])
        if args.orientation == "horizontal"
        else (item["bounds"][2] - item["bounds"][0])
        for item in items
    ]
    gap_limit = max(args.minimum_gap, median(cross_sizes) * args.gap_ratio)

    cross_key = (lambda x: (x["bounds"][1] + x["bounds"][3]) / 2) if args.orientation == "horizontal" else (lambda x: (x["bounds"][0] + x["bounds"][2]) / 2)
    main_key = (lambda x: x["bounds"][0]) if args.orientation == "horizontal" else (lambda x: x["bounds"][1])

    lines: list[list[dict]] = []
    for item in sorted(items, key=cross_key):
        placed = False
        for line in lines:
            if max(overlap_ratio(item["bounds"], other["bounds"], args.orientation) for other in line) >= args.line_overlap:
                line.append(item)
                placed = True
                break
        if not placed:
            lines.append([item])

    units: list[dict] = []
    warnings: list[str] = []
    for line in lines:
        ordered = sorted(line, key=main_key)
        current = [ordered[0]]
        for item in ordered[1:]:
            previous = current[-1]
            gap = (
                item["bounds"][0] - previous["bounds"][2]
                if args.orientation == "horizontal"
                else item["bounds"][1] - previous["bounds"][3]
            )
            if gap > gap_limit:
                units.append({"text": args.joiner.join(x["text"] for x in current), "bounds": union_bounds(current), "tokens": current})
                current = [item]
            else:
                current.append(item)
        units.append({"text": args.joiner.join(x["text"] for x in current), "bounds": union_bounds(current), "tokens": current})

    for item in items:
        if "  " in item["text"] and "characters" not in item:
            warnings.append(f"Token {item['text']!r} contains distant spaces but has no character boxes; verify manually")

    result = {"orientation": args.orientation, "gap_limit": gap_limit, "units": units, "warnings": warnings}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
