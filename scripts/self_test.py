#!/usr/bin/env python3
"""Run deterministic regression tests for the maximum-fidelity gates."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from photoshop_bridge import BridgeError, validate_job


ROOT = Path(__file__).resolve().parent


def run(arguments: list[str], expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([sys.executable, *arguments], text=True, capture_output=True)
    if result.returncode != expected:
        raise RuntimeError(f"Expected exit {expected}, got {result.returncode}: {' '.join(arguments)}\n{result.stdout}\n{result.stderr}")
    return result


def rounded_mask(size: tuple[int, int], angle: float, notch: bool = False) -> Image.Image:
    base = Image.new("L", size, 0)
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle((36, 70, size[0] - 36, size[1] - 70), radius=28, fill=255)
    if notch:
        draw.rectangle((size[0] // 2 - 10, 68, size[0] // 2 + 10, 88), fill=0)
    return base.rotate(angle, resample=Image.Resampling.NEAREST, expand=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="rebuild-ui-skill-") as temp:
        work = Path(temp)
        source = Image.new("RGB", (320, 260), (180, 160, 140))
        source_path = work / "source.png"
        source.save(source_path)
        export_job = {
            "document": {"width": 320, "height": 260, "depth": 8},
            "output": {
                "psd": str(work / "export-contract.psd"),
                "preview": str(work / "export-contract.png"),
                "layer_png_dir": str(work / "export-contract" / "png"),
                "report": str(work / "export-contract-report.json"),
            },
            "layers": [
                {"id": "reference", "name": "00_REFERENCE", "kind": "group", "reference": True},
                {
                    "id": "source_reference", "name": "source_reference", "kind": "smart-object",
                    "parent": "reference", "source_asset": str(source_path),
                },
                {"id": "ui", "name": "Panel_UI", "kind": "group", "z": 100},
                {"id": "button", "name": "Btn_Primary", "kind": "group", "z": 200},
                {
                    "id": "button_body", "name": "Bg_Primary", "kind": "shape", "parent": "button", "z": 0,
                    "bounds": [20, 20, 180, 80],
                },
            ],
        }
        validated_export_job = validate_job(export_job, work)
        if [item["name"] for item in validated_export_job["layer_png_exports"]] != ["Panel_UI", "Btn_Primary", "Bg_Primary"]:
            raise RuntimeError("Reference branch exclusion failed in the layer PNG export contract")
        invalid_job = json.loads(json.dumps(export_job))
        invalid_job["layers"][4]["name"] = "bad/name"
        try:
            validate_job(invalid_job, work)
        except BridgeError as error:
            if error.code != "E_INPUT":
                raise
        else:
            raise RuntimeError("Invalid Windows layer PNG filename was accepted")
        invalid_text_job = json.loads(json.dumps(export_job))
        invalid_text_job["layers"].append({
            "id": "button_text", "name": "StartText", "kind": "text", "parent": "button", "z": 20,
            "bounds": [40, 30, 160, 65], "text": "Start",
        })
        try:
            validate_job(invalid_text_job, work)
        except BridgeError as error:
            if "must start with @" not in str(error):
                raise
        else:
            raise RuntimeError("Unprefixed text layer was accepted")
        invalid_order_job = json.loads(json.dumps(export_job))
        invalid_order_job["layers"].append({
            "id": "button_text", "name": "@StartText", "kind": "text", "parent": "button", "z": -1,
            "bounds": [40, 30, 160, 65], "text": "Start",
        })
        try:
            validate_job(invalid_order_job, work)
        except BridgeError as error:
            if "Background layers must have lower z" not in str(error):
                raise
        else:
            raise RuntimeError("Button background was accepted above foreground text")
        missing_body_job = json.loads(json.dumps(export_job))
        missing_body_job["layers"][4]["name"] = "Icon_Primary"
        try:
            validate_job(missing_body_job, work)
        except BridgeError as error:
            if "requires a Bg_/BG_ body" not in str(error):
                raise
        else:
            raise RuntimeError("Button group without a background body was accepted")
        nested_button_job = json.loads(json.dumps(export_job))
        nested_button_job["layers"][3]["parent"] = "ui"
        nested_button_job["layers"][3]["z"] = 10
        try:
            validate_job(nested_button_job, work)
        except BridgeError as error:
            if "must be top-level" not in str(error):
                raise
        else:
            raise RuntimeError("Nested button group was accepted")
        for label, angle in (("horizontal", 0), ("diamond", 45), ("vertical", 90)):
            mask_path = work / f"{label}.png"
            rounded_mask(source.size, angle).save(mask_path)
            report_path = work / f"{label}.json"
            run([str(ROOT / "analyze_button.py"), str(source_path), str(mask_path), "--output", str(report_path)])
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if not report["shape_model"]["native_shape_allowed"]:
                raise RuntimeError(f"Regular {label} rounded rectangle was rejected: {report['shape_model']}")

        custom_path = work / "custom.png"
        rounded_mask(source.size, 0, notch=True).save(custom_path)
        custom_report = work / "custom.json"
        run([str(ROOT / "analyze_button.py"), str(source_path), str(custom_path), "--output", str(custom_report)])
        if json.loads(custom_report.read_text(encoding="utf-8"))["shape_model"]["native_shape_allowed"]:
            raise RuntimeError("Decorative notch was incorrectly accepted as a native rounded rectangle")

        exact = Image.new("L", (160, 120), 0)
        ImageDraw.Draw(exact).rounded_rectangle((15, 15, 145, 105), radius=18, fill=255)
        exact_path, eroded_path = work / "exact.png", work / "eroded.png"
        exact.save(exact_path)
        exact.filter(ImageFilter.MinFilter(5)).save(eroded_path)
        run([str(ROOT / "audit_alpha_recall.py"), str(exact_path), str(exact_path)])
        run([str(ROOT / "audit_alpha_recall.py"), str(exact_path), str(eroded_path)], expected=1)

        manifest_path = work / "visual.json"
        manifest_path.write_text(json.dumps({"cases": [{
            "id": "exact", "reference": str(exact_path), "candidate": str(exact_path),
            "thresholds": {"min_structure_score": 0.99, "min_edge_recall": 0.99, "min_edge_precision": 0.99, "min_detail_ratio": 0.99, "max_detail_ratio": 1.01}
        }]}), encoding="utf-8")
        run([str(ROOT / "visual_regression_gate.py"), str(manifest_path)])

        scene_source = Image.new("RGB", (96, 72), (180, 160, 140))
        scene_source_path = work / "scene-source.png"
        scene_source.save(scene_source_path)
        scene_mask = Image.new("L", scene_source.size, 0)
        ImageDraw.Draw(scene_mask).rectangle((30, 20, 65, 51), fill=255)
        scene_mask_path = work / "scene-mask.png"
        scene_mask.save(scene_mask_path)

        masked_candidate = scene_source.copy()
        ImageDraw.Draw(masked_candidate).rectangle((30, 20, 65, 51), fill=(120, 110, 100))
        masked_candidate_path = work / "masked-candidate.png"
        masked_candidate.save(masked_candidate_path)
        run([
            str(ROOT / "validate_clean_scene.py"), str(scene_source_path), str(masked_candidate_path),
            "--mode", "masked-inpaint", "--mask", str(scene_mask_path),
        ])

        full_redraw = Image.new("RGB", scene_source.size, (80, 100, 130))
        full_redraw_path = work / "full-redraw.png"
        full_redraw.save(full_redraw_path)
        run([
            str(ROOT / "validate_clean_scene.py"), str(scene_source_path), str(full_redraw_path),
            "--mode", "masked-inpaint", "--mask", str(scene_mask_path),
        ], expected=1)
        run([
            str(ROOT / "validate_clean_scene.py"), str(scene_source_path), str(full_redraw_path),
            "--mode", "full-scene-regeneration", "--user-approved-scene-drift",
        ])

        wrong_size = full_redraw.resize((120, 90))
        wrong_size_path = work / "wrong-size.png"
        wrong_size.save(wrong_size_path)
        run([
            str(ROOT / "validate_clean_scene.py"), str(scene_source_path), str(wrong_size_path),
            "--mode", "masked-inpaint", "--mask", str(scene_mask_path),
        ], expected=1)

        font_path = Path("C:/Windows/Fonts/arialbd.ttf")
        if font_path.exists():
            mask = Image.new("L", (180, 72), 0)
            font = ImageFont.truetype(str(font_path), 48)
            ImageDraw.Draw(mask).text((5, 4), "SSR", font=font, fill=255, stroke_width=2, stroke_fill=255)
            text_mask = work / "text.png"
            mask.save(text_mask)
            run([
                str(ROOT / "search_text_style.py"), str(text_mask), "--text", "SSR", "--font", str(font_path),
                "--size-min", "46", "--size-max", "50", "--tracking-min", "-1", "--tracking-max", "1",
                "--stroke-min", "1", "--stroke-max", "3",
            ])

    print(json.dumps({"passed": True, "tests": ["layer-png-export-contract", "ui-prefix-validation", "button-group-validation", "top-level-button-validation", "background-z-validation", "rotated-shape-fit", "custom-shape-rejection", "alpha-recall", "visual-gate", "clean-scene-masked-pass", "clean-scene-full-redraw-rejection", "clean-scene-approved-full-route", "clean-scene-size-rejection", "text-search"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
