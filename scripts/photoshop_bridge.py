#!/usr/bin/env python3
"""Validate, compile, and execute isolated Photoshop assembly jobs on Windows."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "photoshop_runner.jsx"
SUPPORTED_KINDS = {"group", "shape", "text", "smart-object", "raster-object", "scene"}
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_STEMS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
EXIT_CODES = {
    "OK": 0,
    "E_INPUT": 2,
    "E_PHOTOSHOP_UNAVAILABLE": 3,
    "E_PHOTOSHOP_SCRIPT": 4,
    "E_OUTPUT": 5,
    "E_PHOTOSHOP_TIMEOUT": 6,
    "E_PREEXISTING_DOCUMENT_CLOSED": 7,
}


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def absolute_path(value: str, base: Path) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return str(path.resolve()).replace("\\", "/")


def validate_png_stem(value: str, layer_id: str) -> str:
    if not value or value in {".", ".."} or value.endswith((" ", ".")):
        raise BridgeError("E_INPUT", f"Layer name cannot be used verbatim as a PNG filename for {layer_id}: {value!r}")
    if INVALID_FILENAME.search(value):
        raise BridgeError("E_INPUT", f"Layer name contains a Windows filename character for {layer_id}: {value!r}")
    if value.split(".", 1)[0].upper() in WINDOWS_RESERVED_STEMS:
        raise BridgeError("E_INPUT", f"Layer name is reserved by Windows for {layer_id}: {value!r}")
    if len(value) > 240:
        raise BridgeError("E_INPUT", f"Layer name is too long for a reliable PNG filename for {layer_id}")
    return value


def validate_job(payload: dict[str, Any], base: Path, overwrite: bool = False) -> dict[str, Any]:
    job = deepcopy(payload)
    document = job.get("document")
    output = job.get("output")
    layers = job.get("layers")
    if not isinstance(document, dict) or not isinstance(output, dict) or not isinstance(layers, list):
        raise BridgeError("E_INPUT", "Job requires document, output, and layers fields")
    for field in ("width", "height"):
        if float(document.get(field, 0)) <= 0:
            raise BridgeError("E_INPUT", f"document.{field} must be positive")
    if int(document.get("depth", 8)) != 8:
        raise BridgeError("E_INPUT", "The v3 runner currently accepts RGB/8 jobs only")

    for field in ("psd", "preview", "report"):
        if not output.get(field):
            raise BridgeError("E_INPUT", f"output.{field} is required")
        output[field] = absolute_path(str(output[field]), base)
        target = Path(output[field])
        if target.exists() and not overwrite:
            raise BridgeError("E_INPUT", f"Refusing to overwrite existing output: {target}")
    if output.get("scene_preview"):
        output["scene_preview"] = absolute_path(str(output["scene_preview"]), base)
        scene_target = Path(output["scene_preview"])
        if scene_target.exists() and not overwrite:
            raise BridgeError("E_INPUT", f"Refusing to overwrite existing output: {scene_target}")
    if not output.get("layer_png_dir"):
        raise BridgeError("E_INPUT", "output.layer_png_dir is required and must name a png folder")
    output["layer_png_dir"] = absolute_path(str(output["layer_png_dir"]), base)
    layer_png_dir = Path(output["layer_png_dir"])
    if layer_png_dir.name.casefold() != "png":
        raise BridgeError("E_INPUT", "output.layer_png_dir must point to a folder named png")
    if layer_png_dir.exists() and not overwrite:
        raise BridgeError("E_INPUT", f"Refusing to reuse existing layer PNG folder: {layer_png_dir}")

    seen: set[str] = set()
    group_ids: set[str] = set()
    items_by_id: dict[str, dict[str, Any]] = {}
    sibling_names: set[tuple[str, str]] = set()
    for index, layer in enumerate(layers):
        if not isinstance(layer, dict):
            raise BridgeError("E_INPUT", f"layers[{index}] must be an object")
        layer_id = str(layer.get("id", "")).strip()
        kind = str(layer.get("kind", "")).strip()
        if not layer_id or layer_id in seen:
            raise BridgeError("E_INPUT", f"layers[{index}].id is missing or duplicated")
        if kind not in SUPPORTED_KINDS:
            raise BridgeError("E_INPUT", f"Unsupported layer kind for {layer_id}: {kind}")
        layer_name = str(layer.get("name") or layer_id)
        if not layer_name.strip():
            raise BridgeError("E_INPUT", f"layers[{index}].name cannot be blank")
        layer["name"] = layer_name
        parent_key = str(layer.get("parent") or "").casefold()
        sibling_key = (parent_key, layer_name.casefold())
        if sibling_key in sibling_names:
            raise BridgeError("E_INPUT", f"Sibling layer name is duplicated: {layer_name!r}")
        sibling_names.add(sibling_key)
        seen.add(layer_id)
        items_by_id[layer_id] = layer
        if kind == "group":
            group_ids.add(layer_id)
        if kind in {"shape", "text"}:
            bounds = layer.get("bounds")
            if not isinstance(bounds, list) or len(bounds) != 4:
                raise BridgeError("E_INPUT", f"{layer_id} requires four-value bounds")
        if kind in {"smart-object", "raster-object", "scene"}:
            if not layer.get("source_asset"):
                raise BridgeError("E_INPUT", f"{layer_id} requires source_asset")
            layer["source_asset"] = absolute_path(str(layer["source_asset"]), base)
            if not Path(layer["source_asset"]).exists():
                raise BridgeError("E_INPUT", f"Missing source asset for {layer_id}: {layer['source_asset']}")

    for layer in layers:
        parent = layer.get("parent")
        if parent and parent not in group_ids:
            raise BridgeError("E_INPUT", f"Unknown group parent for {layer['id']}: {parent}")
    reference_cache: dict[str, bool] = {}

    def is_reference(layer_id: str, trail: set[str] | None = None) -> bool:
        if layer_id in reference_cache:
            return reference_cache[layer_id]
        trail = set() if trail is None else trail
        if layer_id in trail:
            raise BridgeError("E_INPUT", f"Group parent cycle includes {layer_id}")
        trail.add(layer_id)
        item = items_by_id[layer_id]
        parent = item.get("parent")
        result = item.get("reference") is True or (bool(parent) and is_reference(str(parent), trail))
        reference_cache[layer_id] = result
        trail.remove(layer_id)
        return result

    export_names: set[str] = set()
    layer_png_exports: list[dict[str, str]] = []
    for layer in layers:
        if is_reference(layer["id"]):
            continue
        name = validate_png_stem(layer["name"], layer["id"])
        name_key = name.casefold()
        if name_key in export_names:
            raise BridgeError("E_INPUT", f"Layer PNG filename would be duplicated: {name}.png")
        export_names.add(name_key)
        layer_png_exports.append({"id": layer["id"], "name": name, "kind": layer["kind"], "filename": f"{name}.png"})
    if not layer_png_exports:
        raise BridgeError("E_INPUT", "The job has no non-reference layers to export as PNG")
    job["layer_png_exports"] = layer_png_exports
    if output.get("scene_preview"):
        scene_group_id = str(job.get("scene_group_id", "")).strip()
        if not scene_group_id or scene_group_id not in group_ids:
            raise BridgeError("E_INPUT", "output.scene_preview requires a valid top-level scene_group_id")
        scene_group = next(layer for layer in layers if layer["id"] == scene_group_id)
        if scene_group.get("parent"):
            raise BridgeError("E_INPUT", "scene_group_id must identify a top-level group")
    return job


def compile_jsx(job: dict[str, Any]) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    embedded = json.dumps(job, ensure_ascii=False, separators=(",", ":"))
    if "__JOB_JSON__" not in template:
        raise BridgeError("E_OUTPUT", "Photoshop JSX template token is missing")
    return template.replace("__JOB_JSON__", embedded, 1)


def dispatch_photoshop():
    if sys.platform != "win32":
        raise BridgeError("E_PHOTOSHOP_UNAVAILABLE", "Photoshop COM automation is available only on Windows")
    try:
        import win32com.client  # type: ignore[import-untyped]

        return win32com.client.Dispatch("Photoshop.Application")
    except Exception as error:  # pragma: no cover - platform-specific
        raise BridgeError("E_PHOTOSHOP_UNAVAILABLE", f"Cannot connect to Photoshop.Application: {error}") from error


def _execute_job_in_process(job: dict[str, Any]) -> dict[str, Any]:
    script = compile_jsx(job)
    try:
        raw = dispatch_photoshop().DoJavaScript(script)
    except BridgeError:
        raise
    except Exception as error:  # pragma: no cover - Photoshop-specific
        report_path = Path(job["output"]["report"])
        if report_path.exists():
            try:
                report = json.loads(report_path.read_text(encoding="utf-8-sig"))
                raise BridgeError(report.get("code", "E_PHOTOSHOP_SCRIPT"), report.get("message", str(error))) from error
            except json.JSONDecodeError:
                pass
        raise BridgeError("E_PHOTOSHOP_SCRIPT", str(error)) from error

    report_path = Path(job["output"]["report"])
    if not report_path.exists():
        raise BridgeError("E_OUTPUT", f"Photoshop did not create its report: {report_path}; return={raw!r}")
    report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    if report.get("status") != "ok":
        raise BridgeError(report.get("code", "E_PHOTOSHOP_SCRIPT"), report.get("message", "Photoshop job failed"))
    required_outputs = ["psd", "preview"]
    if job["output"].get("scene_preview"):
        required_outputs.append("scene_preview")
    for field in required_outputs:
        if not Path(report[field]).is_file() or Path(report[field]).stat().st_size <= 0:
            raise BridgeError("E_OUTPUT", f"Photoshop reported a missing {field}: {report[field]}")
    reported_pngs = report.get("layer_pngs")
    if not isinstance(reported_pngs, list) or len(reported_pngs) != len(job["layer_png_exports"]):
        raise BridgeError("E_OUTPUT", "Photoshop did not report the expected number of layer PNG files")
    expected_ids = [item["id"] for item in job["layer_png_exports"]]
    if [item.get("id") for item in reported_pngs] != expected_ids:
        raise BridgeError("E_OUTPUT", "Photoshop layer PNG report does not match the validated export order")
    for item in reported_pngs:
        path = Path(str(item.get("path", "")))
        if not path.is_file() or path.stat().st_size <= 0:
            raise BridgeError("E_OUTPUT", f"Photoshop reported a missing layer PNG: {path}")
    return report


def execute_job(
    job: dict[str, Any],
    keep_jsx: Path | None = None,
    timeout_seconds: float = 120,
) -> dict[str, Any]:
    """Run COM in a child process so a busy Photoshop cannot hang Codex forever."""
    script = compile_jsx(job)
    if keep_jsx:
        keep_jsx.parent.mkdir(parents=True, exist_ok=True)
        keep_jsx.write_text(script, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="codex-photoshop-bridge-") as temp:
        temp_dir = Path(temp)
        job_path = temp_dir / "job.json"
        result_path = temp_dir / "result.json"
        job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        command = [sys.executable, str(Path(__file__).resolve()), "_worker", str(job_path), str(result_path)]
        try:
            completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            raise BridgeError(
                "E_PHOTOSHOP_TIMEOUT",
                f"Photoshop did not complete the isolated job within {timeout_seconds:g} seconds",
            ) from error
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("status") == "ok":
                return result["report"]
            raise BridgeError(result.get("code", "E_PHOTOSHOP_SCRIPT"), result.get("message", "Photoshop job failed"))
        raise BridgeError(
            "E_PHOTOSHOP_SCRIPT",
            completed.stderr.strip() or completed.stdout.strip() or f"Photoshop worker exited {completed.returncode}",
        )


def worker(job_path: Path, result_path: Path) -> int:
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
        report = _execute_job_in_process(job)
        payload = {"status": "ok", "code": "OK", "report": report}
        code = 0
    except BridgeError as error:
        payload = {"status": "error", "code": error.code, "message": str(error)}
        code = EXIT_CODES.get(error.code, 1)
    except Exception as error:  # pragma: no cover - worker safety net
        payload = {"status": "error", "code": "E_PHOTOSHOP_SCRIPT", "message": str(error)}
        code = EXIT_CODES["E_PHOTOSHOP_SCRIPT"]
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return code


def probe_job(output_dir: Path) -> dict[str, Any]:
    asset = output_dir / "probe-smart-object.png"
    if not asset.exists():
        from PIL import Image, ImageDraw

        image = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((3, 3, 44, 44), fill=(255, 210, 30, 255), outline=(30, 30, 30, 255), width=3)
        image.save(asset)
    return {
        "document": {"width": 360, "height": 220, "resolution": 72, "depth": 8, "name": "codex-v3-probe"},
        "output": {
            "psd": str(output_dir / "photoshop-probe.psd"),
            "preview": str(output_dir / "photoshop-probe.png"),
            "scene_preview": str(output_dir / "photoshop-probe-scene.png"),
            "layer_png_dir": str(output_dir / "png"),
            "report": str(output_dir / "photoshop-probe-report.json"),
        },
        "scene_group_id": "ui",
        "layers": [
            {"id": "reference", "name": "00_REFERENCE", "kind": "group", "z": 0, "visible": False, "reference": True},
            {
                "id": "source_reference", "name": "source_reference", "kind": "smart-object",
                "parent": "reference", "z": 0, "visible": False, "source_asset": str(asset),
                "bounds": [0, 0, 48, 48],
            },
            {"id": "ui", "name": "20_UI", "kind": "group", "z": 10},
            {"id": "content", "name": "content", "kind": "group", "parent": "ui", "z": 15},
            {
            "id": "probe_shape", "name": "probe_shape", "kind": "shape", "shape": "rounded-rectangle",
                "parent": "content", "z": 20, "bounds": [38, 42, 322, 178], "radius": 28, "fill": "#3F77D8",
                "effects": {
                    "stroke": {"size": 4, "color": "#14213D", "opacity": 100, "position": "inside"},
                    "drop_shadow": {"distance": 5, "size": 7, "spread": 8, "angle": 90, "opacity": 42, "color": "#000000"},
                },
            },
            {
                "id": "probe_text", "name": "probe_text", "kind": "text", "parent": "content", "z": 30,
                "bounds": [74, 88, 250, 126], "baseline_y": 124, "text": "Codex v3", "font": "Arial-BoldMT",
                "size_px": 34, "tracking": 0, "fill": "#FFFFFF",
            },
            {
                "id": "probe_object", "name": "probe_object", "kind": "smart-object", "parent": "content", "z": 40,
                "source_asset": str(asset), "bounds": [272, 86, 320, 134],
            },
        ],
    }


def render_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser("compile", help="Validate a job and emit self-contained JSX")
    compile_parser.add_argument("job", type=Path)
    compile_parser.add_argument("jsx", type=Path)
    compile_parser.add_argument("--overwrite", action="store_true")

    run_parser = subparsers.add_parser("run", help="Run a validated job through Photoshop COM")
    run_parser.add_argument("job", type=Path)
    run_parser.add_argument("--keep-jsx", type=Path)
    run_parser.add_argument("--overwrite", action="store_true")
    run_parser.add_argument("--timeout", type=float, default=120)

    probe_parser = subparsers.add_parser("probe", help="Save, close, reopen, and inspect a disposable native PSD")
    probe_parser.add_argument("output_dir", type=Path)
    probe_parser.add_argument("--keep-jsx", type=Path)
    probe_parser.add_argument("--overwrite", action="store_true")
    probe_parser.add_argument("--timeout", type=float, default=120)

    worker_parser = subparsers.add_parser("_worker", help=argparse.SUPPRESS)
    worker_parser.add_argument("job", type=Path)
    worker_parser.add_argument("result", type=Path)

    args = parser.parse_args()
    if args.command == "_worker":
        return worker(args.job, args.result)
    try:
        if args.command == "probe":
            args.output_dir.mkdir(parents=True, exist_ok=True)
            raw_job = probe_job(args.output_dir.resolve())
            job = validate_job(raw_job, args.output_dir.resolve(), overwrite=args.overwrite)
            report = execute_job(job, args.keep_jsx, args.timeout)
            print(render_result(report))
            return 0

        payload = json.loads(args.job.read_text(encoding="utf-8"))
        job = validate_job(payload, args.job.parent.resolve(), overwrite=args.overwrite)
        if args.command == "compile":
            if args.jsx.exists() and not args.overwrite:
                raise BridgeError("E_INPUT", f"Refusing to overwrite JSX: {args.jsx}")
            args.jsx.parent.mkdir(parents=True, exist_ok=True)
            args.jsx.write_text(compile_jsx(job), encoding="utf-8")
            print(render_result({"status": "ok", "code": "OK", "jsx": str(args.jsx.resolve())}))
            return 0
        report = execute_job(job, args.keep_jsx, args.timeout)
        print(render_result(report))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        bridge_error = BridgeError("E_INPUT", str(error))
    except BridgeError as error:
        bridge_error = error
    print(render_result({"status": "error", "code": bridge_error.code, "message": str(bridge_error)}), file=sys.stderr)
    return EXIT_CODES.get(bridge_error.code, 1)


if __name__ == "__main__":
    raise SystemExit(main())
