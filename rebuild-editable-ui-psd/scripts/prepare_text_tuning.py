#!/usr/bin/env python3
"""Convert Pillow font shortlists into Photoshop candidate-set tuning jobs."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import ImageFont


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def font_identity(path: Path) -> tuple[str, str]:
    font = ImageFont.truetype(str(path), size=24)
    family, style = font.getname()
    return str(family), str(style)


def font_match(path: Path, photoshop_fonts: list[dict[str, str]]) -> dict[str, str] | None:
    family, style = font_identity(path)
    family_key, style_key = normalized(family), normalized(style)
    exact = [
        item for item in photoshop_fonts
        if normalized(item["family"]) == family_key and normalized(item["style"]) == style_key
    ]
    if exact:
        return exact[0]
    family_matches = [item for item in photoshop_fonts if normalized(item["family"]) == family_key]
    if len(family_matches) == 1:
        return family_matches[0]
    filename_key = normalized(path.stem)
    filename_matches = [
        item for item in photoshop_fonts
        if normalized(item["postscript_name"]) in filename_key or filename_key in normalized(item["postscript_name"])
    ]
    return filename_matches[0] if len(filename_matches) == 1 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shortlist", type=Path, help="JSON from search_text_style.py")
    parser.add_argument("photoshop_fonts", type=Path, help="JSON from scan_photoshop_fonts.py")
    parser.add_argument("base_job", type=Path)
    parser.add_argument("--layer-id", required=True)
    parser.add_argument("--reference-render", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top", type=int, default=12)
    args = parser.parse_args()

    shortlist = json.loads(args.shortlist.read_text(encoding="utf-8"))
    font_inventory = json.loads(args.photoshop_fonts.read_text(encoding="utf-8"))
    candidates: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for index, item in enumerate(shortlist.get("best_candidates", [])[: args.top]):
        font_path = Path(item["font"])
        match = font_match(font_path, font_inventory["fonts"])
        if not match:
            unmapped.append({"font": str(font_path), "reason": "No unique Photoshop family/style/PostScript match"})
            continue
        size = int(item["font_size_px"])
        tracking = round(float(item["tracking_px"]) / max(size, 1) * 1000)
        values = {
            "font": match["postscript_name"],
            "size_px": size,
            "tracking": tracking,
            "effects.stroke.size": int(item["stroke_width_px"]),
        }
        signature = tuple(values.values())
        if signature in seen:
            continue
        seen.add(signature)
        candidates.append({
            "label": f"photoshop-font-{index + 1:02d}",
            "representation": "native-text",
            "values": values,
            "source_shortlist": item,
            "photoshop_font": match,
        })
    if not candidates:
        raise SystemExit("No shortlist candidates mapped to fonts exposed by Photoshop")

    config = {
        "component_id": args.layer_id,
        "layer_id": args.layer_id,
        "reference": str(args.reference_render.resolve()),
        "base_job": str(args.base_job.resolve()),
        "output_dir": str(args.output_dir.resolve()),
        "candidate_sets": candidates,
        "parameter_families": [],
        "fallback_jobs": [],
        "photoshop_timeout_seconds": 120,
        "photoshop_retries": 1,
        "max_sweeps": 1,
        "thresholds": {
            "min_structure_score": 0.985,
            "min_edge_recall": 0.985,
            "min_edge_precision": 0.985,
            "min_color_histogram_intersection": 0.97,
            "min_detail_ratio": 0.95,
            "max_detail_ratio": 1.05,
        },
        "font_mapping_audit": {"mapped": len(candidates), "unmapped": unmapped},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(config, ensure_ascii=False, indent=2)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
