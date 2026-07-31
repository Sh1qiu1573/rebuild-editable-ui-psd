#!/usr/bin/env python3
"""Exhaustively rank font/size/tracking/stroke candidates against a glyph mask."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def load_mask(path: Path) -> np.ndarray:
    image = Image.open(path)
    channel = image.getchannel("A") if "A" in image.getbands() else image.convert("L")
    value = np.asarray(channel, dtype=np.uint8) > 0
    ys, xs = np.nonzero(value)
    if not len(xs):
        raise SystemExit("Reference text mask is empty")
    return value[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


def dilate(mask: np.ndarray, radius: int = 1) -> np.ndarray:
    result = np.zeros_like(mask)
    height, width = mask.shape
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            y0, y1 = max(0, dy), min(height, height + dy)
            x0, x1 = max(0, dx), min(width, width + dx)
            sy0, sy1 = max(0, -dy), min(height, height - dy)
            sx0, sx1 = max(0, -dx), min(width, width - dx)
            result[y0:y1, x0:x1] |= mask[sy0:sy1, sx0:sx1]
    return result


def edge(mask: np.ndarray) -> np.ndarray:
    eroded = mask.copy()
    height, width = mask.shape
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        shifted = np.zeros_like(mask)
        y0, y1 = max(0, dy), min(height, height + dy)
        x0, x1 = max(0, dx), min(width, width + dx)
        sy0, sy1 = max(0, -dy), min(height, height - dy)
        sx0, sx1 = max(0, -dx), min(width, width - dx)
        shifted[y0:y1, x0:x1] = mask[sy0:sy1, sx0:sx1]
        eroded &= shifted
    return mask & ~eroded


def render_text(text: str, font_path: Path, size: int, tracking: int, stroke: int) -> np.ndarray:
    font = ImageFont.truetype(str(font_path), size=size)
    boxes = [font.getbbox(character, stroke_width=stroke) for character in text]
    advances = [font.getlength(character) for character in text]
    left = min((box[0] for box in boxes), default=0)
    top = min((box[1] for box in boxes), default=0)
    right = max((sum(advances[:index]) + index * tracking + box[2] for index, box in enumerate(boxes)), default=1)
    bottom = max((box[3] for box in boxes), default=1)
    canvas = Image.new("L", (max(1, int(np.ceil(right - left + stroke * 2 + 4))), max(1, int(np.ceil(bottom - top + stroke * 2 + 4)))), 0)
    draw = ImageDraw.Draw(canvas)
    x = stroke + 2 - left
    y = stroke + 2 - top
    for character, advance in zip(text, advances):
        draw.text((x, y), character, font=font, fill=255, stroke_width=stroke, stroke_fill=255)
        x += advance + tracking
    data = np.asarray(canvas, dtype=np.uint8) > 0
    ys, xs = np.nonzero(data)
    return data[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1] if len(xs) else data


def place_center(candidate: np.ndarray, shape: tuple[int, int], dx: int, dy: int) -> np.ndarray:
    result = np.zeros(shape, dtype=bool)
    top = (shape[0] - candidate.shape[0]) // 2 + dy
    left = (shape[1] - candidate.shape[1]) // 2 + dx
    src_top, src_left = max(0, -top), max(0, -left)
    dst_top, dst_left = max(0, top), max(0, left)
    height = min(candidate.shape[0] - src_top, shape[0] - dst_top)
    width = min(candidate.shape[1] - src_left, shape[1] - dst_left)
    if height > 0 and width > 0:
        result[dst_top : dst_top + height, dst_left : dst_left + width] = candidate[src_top : src_top + height, src_left : src_left + width]
    return result


def score(reference: np.ndarray, candidate: np.ndarray) -> tuple[float, float, float]:
    intersection = np.count_nonzero(reference & candidate)
    union = max(np.count_nonzero(reference | candidate), 1)
    iou = float(intersection / union)
    ref_edge, cand_edge = edge(reference), edge(candidate)
    recall = float(np.count_nonzero(ref_edge & dilate(cand_edge)) / max(np.count_nonzero(ref_edge), 1))
    precision = float(np.count_nonzero(cand_edge & dilate(ref_edge)) / max(np.count_nonzero(cand_edge), 1))
    return iou, recall, precision


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference_mask", type=Path)
    parser.add_argument("--text", required=True)
    parser.add_argument("--font", action="append", type=Path)
    parser.add_argument("--font-root", action="append", type=Path, help="Recursively scan .ttf/.otf/.ttc files")
    parser.add_argument("--font-pattern", help="Case-insensitive regex applied to candidate font paths")
    parser.add_argument("--size-min", type=int)
    parser.add_argument("--size-max", type=int)
    parser.add_argument("--tracking-min", type=int, default=-3)
    parser.add_argument("--tracking-max", type=int, default=6)
    parser.add_argument("--stroke-min", type=int, default=0)
    parser.add_argument("--stroke-max", type=int)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    font_paths = list(args.font or [])
    roots = list(args.font_root or [])
    if not font_paths and not roots and os.name == "nt":
        roots.append(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts")
    for root in roots:
        if not root.is_dir():
            raise SystemExit(f"Font root not found: {root}")
        for suffix in ("*.ttf", "*.otf", "*.ttc"):
            font_paths.extend(root.rglob(suffix))
    pattern = re.compile(args.font_pattern, re.IGNORECASE) if args.font_pattern else None
    font_paths = sorted({path.resolve() for path in font_paths if not pattern or pattern.search(str(path))})
    if not font_paths:
        raise SystemExit("No font files selected; use --font, --font-root, or a broader --font-pattern")
    reference = load_mask(args.reference_mask)
    height = reference.shape[0]
    size_min = args.size_min or max(4, int(height * 0.55))
    size_max = args.size_max or max(size_min, int(height * 1.6))
    stroke_max = args.stroke_max if args.stroke_max is not None else max(1, int(height * 0.18))
    results: list[dict] = []
    rejected_fonts: list[dict[str, str]] = []
    for font_path in font_paths:
        if not font_path.is_file():
            raise SystemExit(f"Font file not found: {font_path}")
        try:
            ImageFont.truetype(str(font_path), size=max(size_min, 8))
        except Exception as error:
            rejected_fonts.append({"font": str(font_path), "error": str(error)})
            continue
        for size in range(size_min, size_max + 1):
            for tracking in range(args.tracking_min, args.tracking_max + 1):
                for stroke in range(args.stroke_min, stroke_max + 1):
                    rendered = render_text(args.text, font_path, size, tracking, stroke)
                    if rendered.shape[0] > reference.shape[0] * 1.4 or rendered.shape[1] > reference.shape[1] * 1.4:
                        continue
                    best = None
                    for dy in range(-2, 3):
                        for dx in range(-2, 3):
                            candidate = place_center(rendered, reference.shape, dx, dy)
                            iou, recall, precision = score(reference, candidate)
                            combined = iou * 0.6 + recall * 0.2 + precision * 0.2
                            if best is None or combined > best[0]:
                                best = (combined, iou, recall, precision, dx, dy)
                    if best:
                        results.append({
                            "score": round(best[0], 6), "iou": round(best[1], 6),
                            "edge_recall": round(best[2], 6), "edge_precision": round(best[3], 6),
                            "font": str(font_path.resolve()), "font_size_px": size,
                            "tracking_px": tracking, "stroke_width_px": stroke,
                            "alignment_dx": best[4], "alignment_dy": best[5],
                        })
    results.sort(key=lambda item: item["score"], reverse=True)
    report = {
        "reference_mask": str(args.reference_mask.resolve()),
        "text": args.text,
        "searched_font_files": len(font_paths) - len(rejected_fonts),
        "rejected_fonts": rejected_fonts,
        "searched_candidates": len(results),
        "best_candidates": results[: args.top],
        "accepted": bool(results and results[0]["iou"] >= 0.90 and results[0]["edge_recall"] >= 0.95),
        "acceptance": {"min_iou": 0.90, "min_edge_recall": 0.95},
        "warning": "Use this only to shortlist. The final Photoshop TypeLayer render must pass visual_regression_gate.py.",
    }
    rendered_json = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered_json)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered_json + "\n", encoding="utf-8")
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
