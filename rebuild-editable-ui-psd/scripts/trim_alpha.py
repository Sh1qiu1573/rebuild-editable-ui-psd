#!/usr/bin/env python3
"""Crop an RGBA asset to its alpha silhouette's minimal bounding rectangle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def byte_value(value: str) -> int:
    parsed = int(value)
    if not 0 <= parsed <= 255:
        raise argparse.ArgumentTypeError("must be between 0 and 255")
    return parsed


def calculate_crop(alpha: np.ndarray, threshold: int, padding: int) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(alpha > threshold)
    if len(xs) == 0:
        raise ValueError("No alpha pixels exceed the threshold")

    left = max(0, int(xs.min()) - padding)
    top = max(0, int(ys.min()) - padding)
    right = min(alpha.shape[1], int(xs.max()) + 1 + padding)
    bottom = min(alpha.shape[0], int(ys.max()) + 1 + padding)
    return left, top, right, bottom


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--padding", type=int, default=1, choices=(0, 1, 2))
    parser.add_argument("--alpha-threshold", type=byte_value, default=0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    image = Image.open(args.input).convert("RGBA")
    alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)
    crop_box = calculate_crop(alpha, args.alpha_threshold, args.padding)
    cropped = image.crop(crop_box)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(args.output)

    cropped_alpha = np.asarray(cropped.getchannel("A"), dtype=np.uint8)
    report = {
        "input": str(args.input.resolve()),
        "output": str(args.output.resolve()),
        "original_size": list(image.size),
        "alpha_threshold": args.alpha_threshold,
        "padding": args.padding,
        "crop_box": list(crop_box),
        "crop_origin": [crop_box[0], crop_box[1]],
        "cropped_size": list(cropped.size),
        "nonzero_alpha_pixels": int(np.count_nonzero(cropped_alpha > args.alpha_threshold)),
        "transparent_pixels_percent": round(
            float((cropped_alpha <= args.alpha_threshold).mean() * 100), 4
        ),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
