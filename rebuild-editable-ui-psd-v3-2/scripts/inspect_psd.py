#!/usr/bin/env python3
"""Inspect a PSD's document metadata and complete layer tree."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from psd_tools import PSDImage


def enum_value(value) -> str:
    if hasattr(value, "name"):
        return str(value.name)
    raw = getattr(value, "value", value)
    if isinstance(raw, bytes):
        return raw.decode("ascii", errors="replace")
    return str(raw)


def layer_record(layer, depth: int, index: int) -> dict:
    record = {
        "index": index,
        "depth": depth,
        "name": layer.name,
        "type": type(layer).__name__,
        "bounds": list(layer.bbox) if layer.bbox else None,
        "visible": bool(layer.is_visible()),
        "opacity": int(layer.opacity),
        "blend_mode": enum_value(layer.blend_mode),
        "clipping": bool(getattr(layer, "clipping", False)),
        "has_mask": bool(layer.has_mask()),
    }
    if type(layer).__name__ == "TypeLayer":
        record["text"] = layer.text
    if hasattr(layer, "smart_object") and layer.smart_object:
        record["smart_object"] = {
            "filename": layer.smart_object.filename,
            "filetype": layer.smart_object.filetype,
        }
    try:
        record["effects"] = [type(effect).__name__ for effect in layer.effects]
    except Exception:
        record["effects"] = []
    return record


def walk(parent, depth: int = 0):
    for index, layer in enumerate(parent):
        yield layer_record(layer, depth, index)
        if layer.is_group():
            yield from walk(layer, depth + 1)


def inspect(path: Path) -> dict:
    psd = PSDImage.open(path)
    records = list(walk(psd))
    counts = Counter(record["type"] for record in records)
    canvas_covering = [
        record["name"]
        for record in records
        if record["bounds"]
        and record["bounds"][0] <= 0
        and record["bounds"][1] <= 0
        and record["bounds"][2] >= psd.width
        and record["bounds"][3] >= psd.height
    ]
    return {
        "path": str(path.resolve()),
        "document": {
            "width": psd.width,
            "height": psd.height,
            "color_mode": enum_value(psd.color_mode),
            "depth": psd.depth,
            "top_level_layers": len(psd),
            "total_layers": len(records),
        },
        "counts": dict(sorted(counts.items())),
        "canvas_covering_layers": canvas_covering,
        "layers": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("psd", type=Path)
    parser.add_argument("--json", type=Path, dest="json_path", help="Also write the report to this file")
    args = parser.parse_args()

    report = inspect(args.psd)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
