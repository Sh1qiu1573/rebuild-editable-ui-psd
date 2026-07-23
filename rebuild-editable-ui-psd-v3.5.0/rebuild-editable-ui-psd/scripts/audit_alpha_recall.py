#!/usr/bin/env python3
"""Audit extraction masks for over-erasure and component loss."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

try:
    import cv2
except ImportError as exc:  # pragma: no cover
    raise SystemExit("OpenCV is required: python -m pip install opencv-python-headless") from exc


def load_mask(path: Path, size: tuple[int, int] | None = None) -> np.ndarray:
    image = Image.open(path)
    channel = image.getchannel("A") if "A" in image.getbands() else image.convert("L")
    if size and image.size != size:
        raise SystemExit(f"Mask size {image.size} does not match reference size {size}")
    return np.asarray(channel, dtype=np.uint8)


def edge(mask: np.ndarray) -> np.ndarray:
    binary = mask > 0
    eroded = cv2.erode(binary.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    return binary & ~eroded


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    size = radius * 2 + 1
    return cv2.dilate(mask.astype(np.uint8), np.ones((size, size), np.uint8)).astype(bool)


def component_count(mask: np.ndarray, min_area: int) -> int:
    count, _, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    return int(sum(int(stats[index, cv2.CC_STAT_AREA]) >= min_area for index in range(1, count)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reference_visible_mask", type=Path)
    parser.add_argument("candidate_alpha_or_mask", type=Path)
    parser.add_argument("--min-visible-recall", type=float, default=0.998)
    parser.add_argument("--min-edge-recall", type=float, default=0.99)
    parser.add_argument("--edge-tolerance", type=int, default=1)
    parser.add_argument("--min-component-area", type=int, default=2)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    reference_image = Image.open(args.reference_visible_mask)
    reference = load_mask(args.reference_visible_mask) > 0
    candidate = load_mask(args.candidate_alpha_or_mask, reference_image.size) > 0
    ref_edge = edge(reference.astype(np.uint8) * 255)
    cand_edge = edge(candidate.astype(np.uint8) * 255)
    visible_recall = float(np.count_nonzero(reference & candidate) / max(np.count_nonzero(reference), 1))
    edge_recall = float(np.count_nonzero(ref_edge & dilate(cand_edge, args.edge_tolerance)) / max(np.count_nonzero(ref_edge), 1))
    reference_components = component_count(reference, args.min_component_area)
    candidate_components = component_count(candidate, args.min_component_area)
    failures: list[str] = []
    if visible_recall < args.min_visible_recall:
        failures.append(f"visible_recall={visible_recall:.6f} < {args.min_visible_recall}")
    if edge_recall < args.min_edge_recall:
        failures.append(f"edge_recall={edge_recall:.6f} < {args.min_edge_recall}")
    if candidate_components < reference_components:
        failures.append(f"component_count={candidate_components} < reference_components={reference_components}")
    report = {
        "passed": not failures,
        "visible_pixel_recall": round(visible_recall, 6),
        "edge_recall": round(edge_recall, 6),
        "reference_components": reference_components,
        "candidate_components": candidate_components,
        "thresholds": {
            "min_visible_recall": args.min_visible_recall,
            "min_edge_recall": args.min_edge_recall,
            "edge_tolerance_px": args.edge_tolerance,
        },
        "failures": failures,
        "rule": "Never fix halos by eroding source-visible pixels; expand/refine the matte and restore source pixels instead.",
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
