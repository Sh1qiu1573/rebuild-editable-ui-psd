#!/usr/bin/env python3
"""Estimate glyph ink thickness and text outline parameters from masks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError as exc:  # pragma: no cover - environment gate
    raise SystemExit("OpenCV is required: python -m pip install opencv-python-headless") from exc


def load_mask(path: Path, size: tuple[int, int]) -> np.ndarray:
    image = Image.open(path)
    alpha = image.getchannel("A") if "A" in image.getbands() else None
    channel = alpha if alpha is not None and alpha.getextrema()[0] < 255 else image.convert("L")
    if channel.size != size:
        raise SystemExit(f"Mask size {channel.size} does not match source size {size}")
    return np.asarray(channel, dtype=np.uint8) >= 128


def median_color(image: np.ndarray, mask: np.ndarray) -> str | None:
    pixels = image[mask]
    if not len(pixels):
        return None
    color = np.median(pixels, axis=0)
    return "#" + "".join(f"{int(round(value)):02X}" for value in color)


def weight_label(ratio: float) -> str:
    if ratio < 0.07:
        return "light"
    if ratio < 0.105:
        return "regular"
    if ratio < 0.145:
        return "medium"
    if ratio < 0.20:
        return "bold"
    return "heavy"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("fill_mask", type=Path, help="Glyph fill only, excluding outline")
    parser.add_argument("--total-mask", type=Path, help="Glyph fill plus outline")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source_image = Image.open(args.image).convert("RGB")
    source = np.asarray(source_image, dtype=np.uint8)
    fill = load_mask(args.fill_mask, source_image.size)
    if not np.any(fill):
        raise SystemExit("Fill mask is empty")
    total = load_mask(args.total_mask, source_image.size) if args.total_mask else fill.copy()
    if np.any(fill & ~total):
        raise SystemExit("Total mask must contain the full fill mask")

    ys, xs = np.nonzero(fill)
    bounds = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
    glyph_height = max(1, bounds[3] - bounds[1])
    distance = cv2.distanceTransform(fill.astype(np.uint8), cv2.DIST_L2, 5)
    local_max = (distance > 0) & (distance >= cv2.dilate(distance, np.ones((3, 3), np.uint8)) - 1e-4)
    diameters = 2.0 * distance[local_max]
    ink_thickness = float(np.median(diameters)) if len(diameters) else 0.0
    thickness_ratio = ink_thickness / glyph_height
    fill_sample = fill & (distance >= max(1.0, min(3.0, ink_thickness * 0.4)))
    if not np.any(fill_sample):
        fill_sample = fill

    outline = total & ~fill
    outline_status = "unknown" if args.total_mask is None else ("present" if np.any(outline) else "absent")
    if np.any(outline):
        distance_to_fill = cv2.distanceTransform((~fill).astype(np.uint8), cv2.DIST_L2, 5)
        outline_width = float(np.percentile(distance_to_fill[outline], 95))
    else:
        outline_width = 0.0

    result = {
        "source": str(args.image.resolve()),
        "fill_mask": str(args.fill_mask.resolve()),
        "total_mask": str(args.total_mask.resolve()) if args.total_mask else None,
        "bounds": bounds,
        "glyph_height_px": glyph_height,
        "ink_thickness_px": round(ink_thickness, 4),
        "ink_thickness_to_height": round(thickness_ratio, 6),
        "font_weight_estimate": weight_label(thickness_ratio),
        "font_weight_confidence": "low",
        "fill_color": median_color(source, fill_sample),
        "outline": {
            "status": outline_status,
            "width_px": round(outline_width, 4) if outline_status != "unknown" else None,
            "color": median_color(source, outline),
            "pixel_count": int(np.count_nonzero(outline)),
        },
        "warnings": [
            "Weight classification is visual evidence, not a font-family identification; compare candidate fonts in the final render."
        ],
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
