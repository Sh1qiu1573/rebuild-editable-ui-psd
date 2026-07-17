#!/usr/bin/env python3
"""Run the v3 Photoshop save/reopen and component-loop integration tests."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from inspect_psd import inspect
from photoshop_bridge import execute_job, probe_job, validate_job


ROOT = Path(__file__).resolve().parent


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def shape_job(root: Path, name: str, radius: int) -> dict:
    return {
        "document": {"width": 240, "height": 160, "resolution": 72, "depth": 8, "name": name},
        "output": {
            "psd": str(root / f"{name}.psd"),
            "preview": str(root / f"{name}.png"),
            "report": str(root / f"{name}-report.json"),
        },
        "layers": [
            {"id": "ui", "name": "20_UI", "kind": "group", "z": 10},
            {
                "id": "test_shape", "name": "test_shape", "kind": "shape", "parent": "ui", "z": 20,
                "shape": "rounded-rectangle", "bounds": [30, 30, 210, 130], "radius": radius, "fill": "#467BD8",
                "effects": {"stroke": {"size": 3, "color": "#17233F", "position": "inside", "opacity": 100}},
            },
        ],
    }


def text_job(root: Path, name: str, font: str) -> dict:
    return {
        "document": {"width": 300, "height": 120, "resolution": 72, "depth": 8, "name": name},
        "output": {
            "psd": str(root / f"{name}.psd"),
            "preview": str(root / f"{name}.png"),
            "report": str(root / f"{name}-report.json"),
        },
        "layers": [
            {"id": "ui", "name": "20_UI", "kind": "group", "z": 10},
            {
                "id": "background", "name": "background", "kind": "shape", "parent": "ui", "z": 11,
                "shape": "rounded-rectangle", "bounds": [0, 0, 300, 120], "radius": 0, "fill": "#243B63",
            },
            {
                "id": "test_text", "name": "test_text", "kind": "text", "parent": "ui", "z": 20,
                "bounds": [45, 32, 255, 84], "baseline_y": 82, "text": "Codex v3", "font": font,
                "size_px": 42, "tracking": 0, "fill": "#FFFFFF",
                "effects": {"stroke": {"size": 1, "color": "#111827", "position": "outside", "opacity": 100}},
            },
        ],
    }


def assert_probe(work: Path, timeout: float) -> None:
    probe_dir = work / "probe"
    probe_dir.mkdir(parents=True, exist_ok=True)
    raw = probe_job(probe_dir)
    job = validate_job(raw, work, overwrite=True)
    report = execute_job(job, work / "probe" / "compiled.jsx", timeout)
    if not report.get("preexisting_documents", {}).get("preserved"):
        raise RuntimeError(f"Probe did not preserve pre-existing Photoshop documents: {report.get('preexisting_documents')}")
    structure = inspect(Path(report["psd"]))
    expected = {"Group": 2, "ShapeLayer": 1, "TypeLayer": 1, "SmartObjectLayer": 1}
    for kind, count in expected.items():
        if structure["counts"].get(kind) != count:
            raise RuntimeError(f"Probe expected {count} {kind}, got {structure['counts']}")
    if structure["counts"].get("PixelLayer", 0):
        raise RuntimeError("Probe retained an undocumented bootstrap pixel layer")
    shape = next(layer for layer in structure["layers"] if layer["name"] == "probe_shape")
    if not {"Stroke", "DropShadow"}.issubset(set(shape["effects"])):
        raise RuntimeError(f"Probe shape effects were not preserved: {shape['effects']}")
    preview = Image.open(report["preview"]).convert("RGB")
    if preview.size != (360, 220):
        raise RuntimeError(f"Probe preview size changed: {preview.size}")
    curved_sample = preview.getpixel((45, 60))
    if curved_sample[2] < 80:
        raise RuntimeError(f"Rounded corner regressed to a diagonal chamfer: {curved_sample}")
    text_crop = np.asarray(preview.crop((70, 90, 230, 135)))
    if not np.any((text_crop[..., 0] > 235) & (text_crop[..., 1] > 235) & (text_crop[..., 2] > 235)):
        raise RuntimeError("Nested live text is hidden by incorrect sibling-group stacking")
    object_crop = np.asarray(preview.crop((268, 82, 325, 140)))
    if not np.any((object_crop[..., 0] > 220) & (object_crop[..., 1] > 160) & (object_crop[..., 2] < 100)):
        raise RuntimeError("Nested smart object is hidden by incorrect sibling-group stacking")


def assert_component_loop(work: Path, timeout: float) -> None:
    reference_raw = shape_job(work, "reference", 30)
    reference_job = validate_job(reference_raw, work, overwrite=True)
    reference_report = execute_job(reference_job, work / "reference.jsx", timeout)

    base = shape_job(work, "base-unused", 0)
    fallback = shape_job(work, "fallback-unused", 30)
    base_path = work / "base-job.json"
    fallback_path = work / "fallback-job.json"
    write_json(base_path, base)
    write_json(fallback_path, fallback)
    config = {
        "component_id": "test_shape",
        "layer_id": "test_shape",
        "reference": reference_report["preview"],
        "base_job": str(base_path),
        "output_dir": str(work / "tuning"),
        "max_sweeps": 1,
        "photoshop_timeout_seconds": timeout,
        "photoshop_retries": 0,
        "thresholds": {
            "min_structure_score": 0.999,
            "min_edge_recall": 0.999,
            "min_edge_precision": 0.999,
            "min_color_histogram_intersection": 0.999,
            "min_detail_ratio": 0.999,
            "max_detail_ratio": 1.001,
        },
        "parameter_families": [{"name": "radius", "field": "radius", "values": [10]}],
        "fallback_jobs": [{"representation": "custom-vector-path", "job": str(fallback_path)}],
    }
    config_path = work / "tuning-config.json"
    write_json(config_path, config)
    result = subprocess.run(
        [sys.executable, str(ROOT / "tune_component.py"), str(config_path)],
        text=True,
        capture_output=True,
        timeout=max(timeout * 5, 60),
    )
    if result.returncode != 0:
        raise RuntimeError(f"Component loop failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    report = json.loads((work / "tuning" / "component-regression.json").read_text(encoding="utf-8"))
    if report["accepted_representation"] != "custom-vector-path":
        raise RuntimeError(f"Fail-closed fallback was not selected: {report['accepted_representation']}")
    if len(report["attempts"]) < 3 or report["attempts"][0]["gate"]["passed"]:
        raise RuntimeError("Component loop did not prove baseline failure before fallback")


def assert_text_candidate_loop(work: Path, timeout: float) -> None:
    reference_raw = text_job(work, "text-reference", "Arial-BoldMT")
    reference_job = validate_job(reference_raw, work, overwrite=True)
    reference_report = execute_job(reference_job, work / "text-reference.jsx", timeout)
    base = text_job(work, "text-base-unused", "ArialMT")
    base_path = work / "text-base-job.json"
    write_json(base_path, base)
    config = {
        "component_id": "test_text",
        "layer_id": "test_text",
        "reference": reference_report["preview"],
        "base_job": str(base_path),
        "output_dir": str(work / "text-tuning"),
        "photoshop_timeout_seconds": timeout,
        "photoshop_retries": 0,
        "candidate_sets": [{
            "label": "photoshop-font-01",
            "representation": "native-text",
            "values": {"font": "Arial-BoldMT", "size_px": 42, "tracking": 0, "effects.stroke.size": 1},
        }],
        "parameter_families": [],
        "fallback_jobs": [],
        "thresholds": {
            "min_structure_score": 0.999,
            "min_edge_recall": 0.999,
            "min_edge_precision": 0.999,
            "min_color_histogram_intersection": 0.999,
            "min_detail_ratio": 0.999,
            "max_detail_ratio": 1.001,
        },
    }
    config_path = work / "text-tuning-config.json"
    write_json(config_path, config)
    result = subprocess.run(
        [sys.executable, str(ROOT / "tune_component.py"), str(config_path)],
        text=True,
        capture_output=True,
        timeout=max(timeout * 4, 60),
    )
    if result.returncode != 0:
        raise RuntimeError(f"Text candidate loop failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    report = json.loads((work / "text-tuning" / "component-regression.json").read_text(encoding="utf-8"))
    if report["accepted_representation"] != "native-text" or report["attempts"][0]["gate"]["passed"]:
        raise RuntimeError("Photoshop TypeLayer shortlist did not reject the baseline and accept the exact candidate")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=45)
    args = parser.parse_args()
    if args.work_dir:
        args.work_dir.mkdir(parents=True, exist_ok=True)
        work = args.work_dir.resolve()
        assert_probe(work, args.timeout)
        assert_component_loop(work, args.timeout)
        assert_text_candidate_loop(work, args.timeout)
    else:
        with tempfile.TemporaryDirectory(prefix="rebuild-ui-photoshop-test-") as temp:
            work = Path(temp)
            assert_probe(work, args.timeout)
            assert_component_loop(work, args.timeout)
            assert_text_candidate_loop(work, args.timeout)
    print(json.dumps({"passed": True, "tests": ["native-psd-reopen", "rounded-path", "layer-effects", "smart-object", "component-fallback-loop", "photoshop-text-candidate-loop"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
