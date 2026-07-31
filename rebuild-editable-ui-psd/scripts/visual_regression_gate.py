#!/usr/bin/env python3
"""Fail closed when reconstructed component crops lose visible source structure.

The gate is intentionally image-only so an agent can run it before a PSD exists.
Use tightly cropped reference/candidate pairs. A candidate that is merely plausible,
but does not reproduce the source component, must fail.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image


def load_rgb(path: Path, size: tuple[int, int] | None = None) -> np.ndarray:
    image = Image.open(path).convert("RGB")
    if size and image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    return np.asarray(image, dtype=np.float32)


def luminance(rgb: np.ndarray) -> np.ndarray:
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


def edge_map(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    gx = np.zeros_like(gray)
    gy = np.zeros_like(gray)
    gx[:, 1:-1] = gray[:, 2:] - gray[:, :-2]
    gy[1:-1, :] = gray[2:, :] - gray[:-2, :]
    magnitude = np.hypot(gx, gy)
    nonzero = magnitude[magnitude > 0]
    threshold = max(12.0, float(np.percentile(nonzero, 72))) if nonzero.size else 12.0
    return magnitude >= threshold, magnitude


def dilate(mask: np.ndarray, radius: int = 2) -> np.ndarray:
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


def histogram_intersection(reference: np.ndarray, candidate: np.ndarray) -> float:
    values: list[float] = []
    for channel in range(3):
        ref_hist, _ = np.histogram(reference[..., channel], bins=32, range=(0, 256))
        cand_hist, _ = np.histogram(candidate[..., channel], bins=32, range=(0, 256))
        ref_hist = ref_hist / max(float(ref_hist.sum()), 1.0)
        cand_hist = cand_hist / max(float(cand_hist.sum()), 1.0)
        values.append(float(np.minimum(ref_hist, cand_hist).sum()))
    return float(np.mean(values))


def measure(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    ref_gray = luminance(reference)
    cand_gray = luminance(candidate)
    ref_edges, ref_energy = edge_map(ref_gray)
    cand_edges, cand_energy = edge_map(cand_gray)
    ref_count = max(int(ref_edges.sum()), 1)
    cand_count = max(int(cand_edges.sum()), 1)
    edge_recall = float((ref_edges & dilate(cand_edges)).sum() / ref_count)
    edge_precision = float((cand_edges & dilate(ref_edges)).sum() / cand_count)
    structure_score = 1.0 - float(np.mean(np.abs(ref_gray - cand_gray)) / 255.0)
    ref_detail = float(np.mean(ref_energy))
    cand_detail = float(np.mean(cand_energy))
    detail_ratio = cand_detail / max(ref_detail, 1e-6)
    return {
        "structure_score": round(structure_score, 5),
        "edge_recall": round(edge_recall, 5),
        "edge_precision": round(edge_precision, 5),
        "detail_ratio": round(detail_ratio, 5),
        "color_histogram_intersection": round(histogram_intersection(reference, candidate), 5),
    }


def check_case(case: dict, manifest_dir: Path) -> dict:
    reference_path = (manifest_dir / case["reference"]).resolve()
    candidate_path = (manifest_dir / case["candidate"]).resolve()
    reference_image = Image.open(reference_path)
    reference = load_rgb(reference_path)
    candidate = load_rgb(candidate_path, reference_image.size)
    metrics = measure(reference, candidate)
    thresholds = case.get("thresholds", {})
    failures: list[str] = []
    for name in ("structure_score", "edge_recall", "edge_precision", "color_histogram_intersection"):
        minimum = thresholds.get(f"min_{name}")
        if minimum is not None and metrics[name] < float(minimum):
            failures.append(f"{name}={metrics[name]} < {minimum}")
    minimum = thresholds.get("min_detail_ratio")
    maximum = thresholds.get("max_detail_ratio")
    if minimum is not None and metrics["detail_ratio"] < float(minimum):
        failures.append(f"detail_ratio={metrics['detail_ratio']} < {minimum}")
    if maximum is not None and metrics["detail_ratio"] > float(maximum):
        failures.append(f"detail_ratio={metrics['detail_ratio']} > {maximum}")
    return {
        "id": case["id"],
        "failure_class": case.get("failure_class"),
        "reference": str(reference_path),
        "candidate": str(candidate_path),
        "metrics": metrics,
        "thresholds": thresholds,
        "passed": not failures,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    results = [check_case(case, args.manifest.parent) for case in payload["cases"]]
    report = {
        "passed": all(item["passed"] for item in results),
        "passed_cases": sum(item["passed"] for item in results),
        "total_cases": len(results),
        "cases": results,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
