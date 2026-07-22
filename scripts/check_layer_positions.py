#!/usr/bin/env python3
"""Compare PSD layer positions with manifest bounds and emit move corrections."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from psd_tools import PSDImage


def walk(parent):
    for layer in parent:
        yield layer
        if layer.is_group():
            yield from walk(layer)


def center(bounds: list[float]) -> tuple[float, float]:
    return ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("psd", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tolerance", type=float, default=1.0)
    args = parser.parse_args()

    psd = PSDImage.open(args.psd)
    by_name: dict[str, list] = defaultdict(list)
    for layer in walk(psd):
        by_name[layer.name].append(layer)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    checks: list[dict] = []
    missing: list[str] = []
    ambiguous: list[str] = []

    for item in manifest.get("layers", []):
        if item.get("kind") == "group" or item.get("position_check") is False:
            continue
        expected = item.get("expected_bounds") or item.get("bounds")
        if not expected or len(expected) != 4:
            continue
        layer_name = item.get("psd_name") or item.get("id") or item.get("name")
        matches = by_name.get(layer_name, [])
        if not matches:
            missing.append(layer_name)
            continue
        if len(matches) > 1:
            ambiguous.append(layer_name)
            continue
        layer = matches[0]
        if not layer.bbox:
            missing.append(layer_name)
            continue
        actual = list(layer.bbox)
        expected_center = center(expected)
        actual_center = center(actual)
        dx = round(expected_center[0] - actual_center[0], 4)
        dy = round(expected_center[1] - actual_center[1], 4)
        dw = round((expected[2] - expected[0]) - (actual[2] - actual[0]), 4)
        dh = round((expected[3] - expected[1]) - (actual[3] - actual[1]), 4)
        position_pass = abs(dx) <= args.tolerance and abs(dy) <= args.tolerance
        size_pass = abs(dw) <= args.tolerance and abs(dh) <= args.tolerance
        checks.append({
            "layer": layer_name,
            "expected_bounds": expected,
            "actual_bounds": actual,
            "move_dx": dx,
            "move_dy": dy,
            "width_delta": dw,
            "height_delta": dh,
            "position_pass": position_pass,
            "size_pass": size_pass,
            "action": "none" if position_pass else "translate_in_photoshop",
        })

    failed = [check for check in checks if not check["position_pass"] or not check["size_pass"]]
    result = {
        "tolerance": args.tolerance,
        "checked": len(checks),
        "failed": len(failed),
        "missing_layers": missing,
        "ambiguous_layer_names": ambiguous,
        "checks": checks,
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if not failed and not missing and not ambiguous else 2


if __name__ == "__main__":
    raise SystemExit(main())
