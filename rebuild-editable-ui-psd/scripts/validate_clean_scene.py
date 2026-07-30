#!/usr/bin/env python3
"""Validate the contract between a generated clean-scene candidate and its source."""

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


def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)


def load_mask(path: Path, size: tuple[int, int]) -> np.ndarray:
    image = Image.open(path).convert("L")
    if image.size != size:
        raise ValueError(f"Mask size {image.size} does not match source size {size}")
    return np.asarray(image, dtype=np.uint8) > 0


def metrics(delta: np.ndarray) -> dict[str, float]:
    if not delta.size:
        return {"mae": 0.0, "p95_channel_error": 0.0, "identical_pixels_percent": 100.0}
    if delta.ndim >= 2 and delta.shape[-1] in (3, 4):
        per_pixel_max = delta.max(axis=-1)
    else:
        per_pixel_max = delta
    return {
        "mae": round(float(delta.mean()), 4),
        "p95_channel_error": round(float(np.percentile(delta, 95)), 4),
        "identical_pixels_percent": round(float((per_pixel_max == 0).mean() * 100), 4),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--mode", choices=("masked-inpaint", "full-scene-regeneration"), required=True)
    parser.add_argument("--mask", type=Path, help="Required for masked-inpaint")
    parser.add_argument("--clean-scene", type=Path, help="Optional prepared full-canvas scene to audit")
    parser.add_argument("--user-approved-scene-drift", action="store_true")
    parser.add_argument("--max-unmasked-mae", type=float, default=2.0)
    parser.add_argument("--max-unmasked-p95", type=float, default=5.0)
    parser.add_argument("--max-boundary-p95", type=float, default=12.0)
    parser.add_argument("--boundary-width", type=int, default=3)
    parser.add_argument("--diff", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    source_image = Image.open(args.source).convert("RGB")
    candidate_image = Image.open(args.candidate).convert("RGB")
    same_size = candidate_image.size == source_image.size
    failures: list[str] = []
    checks: dict[str, object] = {
        "dimensions": {
            "passed": same_size,
            "source": list(source_image.size),
            "candidate": list(candidate_image.size),
        }
    }
    if not same_size:
        failures.append("candidate dimensions do not match source; blind resize is forbidden")

    source = np.asarray(source_image, dtype=np.float32)
    candidate = np.asarray(candidate_image, dtype=np.float32) if same_size else None
    full_delta = np.abs(candidate - source) if candidate is not None else None
    mask: np.ndarray | None = None

    if args.mode == "masked-inpaint":
        if not args.mask:
            failures.append("masked-inpaint requires --mask")
        elif same_size:
            try:
                mask = load_mask(args.mask, source_image.size)
            except ValueError as error:
                failures.append(str(error))
            else:
                if not np.any(mask):
                    failures.append("mask is empty")
                if np.all(mask):
                    failures.append("mask covers the full canvas; use full-scene-regeneration")
                outside = ~mask
                outside_metrics = metrics(full_delta[outside])
                kernel_size = max(1, int(args.boundary_width)) * 2 + 1
                kernel = np.ones((kernel_size, kernel_size), np.uint8)
                outer_ring = cv2.dilate(mask.astype(np.uint8), kernel).astype(bool) & outside
                boundary_metrics = metrics(full_delta[outer_ring])
                unmasked_passed = (
                    outside_metrics["mae"] <= args.max_unmasked_mae
                    and outside_metrics["p95_channel_error"] <= args.max_unmasked_p95
                )
                boundary_passed = boundary_metrics["p95_channel_error"] <= args.max_boundary_p95
                checks["unmasked_stability"] = {
                    "passed": unmasked_passed,
                    **outside_metrics,
                    "thresholds": {"max_mae": args.max_unmasked_mae, "max_p95": args.max_unmasked_p95},
                }
                checks["splice_boundary"] = {
                    "passed": boundary_passed,
                    **boundary_metrics,
                    "threshold": {"max_p95": args.max_boundary_p95},
                }
                checks["mask"] = {"passed": bool(np.any(mask) and not np.all(mask)), "coverage_percent": round(float(mask.mean() * 100), 4)}
                if not unmasked_passed:
                    failures.append("candidate changes pixels outside the edit mask; full-scene regeneration suspected")
                if not boundary_passed:
                    failures.append("candidate/source boundary is unsafe for masked compositing")
    else:
        approval_passed = bool(args.user_approved_scene_drift)
        checks["scene_drift_approval"] = {"passed": approval_passed, "approved": approval_passed}
        if not approval_passed:
            failures.append("full-scene-regeneration requires explicit user approval for scene drift")
        if full_delta is not None:
            checks["disclosed_full_scene_drift"] = metrics(full_delta)

    if args.clean_scene:
        clean_image = Image.open(args.clean_scene).convert("RGB")
        clean_same_size = clean_image.size == source_image.size
        checks["prepared_clean_scene_dimensions"] = {
            "passed": clean_same_size,
            "source": list(source_image.size),
            "clean_scene": list(clean_image.size),
        }
        if not clean_same_size:
            failures.append("prepared clean scene dimensions do not match source")
        elif args.mode == "masked-inpaint" and mask is not None:
            clean = np.asarray(clean_image, dtype=np.float32)
            clean_outside_metrics = metrics(np.abs(clean - source)[~mask])
            clean_outside_passed = (
                clean_outside_metrics["mae"] <= args.max_unmasked_mae
                and clean_outside_metrics["p95_channel_error"] <= args.max_unmasked_p95
            )
            checks["prepared_scene_preserves_unmasked_pixels"] = {
                "passed": clean_outside_passed,
                **clean_outside_metrics,
                "thresholds": {"max_mae": args.max_unmasked_mae, "max_p95": args.max_unmasked_p95},
            }
            if not clean_outside_passed:
                failures.append("prepared clean scene changes protected pixels outside the edit mask")
        elif args.mode == "full-scene-regeneration" and candidate is not None:
            clean = np.asarray(clean_image, dtype=np.float32)
            candidate_match = metrics(np.abs(clean - candidate))
            candidate_match_passed = candidate_match["mae"] == 0.0
            checks["prepared_scene_uses_full_candidate"] = {"passed": candidate_match_passed, **candidate_match}
            if not candidate_match_passed:
                failures.append("full-scene regeneration was not used as the complete prepared scene")

    report = {
        "passed": not failures,
        "mode": args.mode,
        "source": str(args.source.resolve()),
        "candidate": str(args.candidate.resolve()),
        "checks": checks,
        "failures": failures,
        "rules": [
            "masked-inpaint candidates must remain registered to the source and preserve unmasked pixels",
            "full-scene regeneration must be accepted as a whole after explicit scene-drift approval",
            "never hard-splice a full-scene regeneration through local UI masks",
        ],
    }

    if args.diff and full_delta is not None:
        args.diff.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(np.clip(full_delta * 4.0, 0, 255).astype(np.uint8), mode="RGB").save(args.diff)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
