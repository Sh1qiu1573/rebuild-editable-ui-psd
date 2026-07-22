#!/usr/bin/env python3
"""Compare two same-size images and optionally write an amplified difference image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--diff", type=Path, help="Write an amplified RGB difference image")
    parser.add_argument("--amplify", type=float, default=4.0)
    parser.add_argument("--threshold", type=float, default=5.0, help="Per-channel tolerance")
    args = parser.parse_args()

    reference = load_rgb(args.reference)
    candidate = load_rgb(args.candidate)
    if reference.shape != candidate.shape:
        raise SystemExit(
            f"Image size mismatch: reference={reference.shape[1]}x{reference.shape[0]}, "
            f"candidate={candidate.shape[1]}x{candidate.shape[0]}"
        )

    delta = np.abs(reference - candidate)
    per_pixel_max = delta.max(axis=2)
    report = {
        "width": int(reference.shape[1]),
        "height": int(reference.shape[0]),
        "mae": round(float(delta.mean()), 4),
        "rmse": round(float(np.sqrt(np.mean(np.square(delta)))), 4),
        "max_error": int(delta.max()),
        "identical_pixels_percent": round(float((per_pixel_max == 0).mean() * 100), 4),
        "pixels_within_threshold_percent": round(
            float((per_pixel_max <= args.threshold).mean() * 100), 4
        ),
        "threshold": args.threshold,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.diff:
        args.diff.parent.mkdir(parents=True, exist_ok=True)
        amplified = np.clip(delta * args.amplify, 0, 255).astype(np.uint8)
        Image.fromarray(amplified, mode="RGB").save(args.diff)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
