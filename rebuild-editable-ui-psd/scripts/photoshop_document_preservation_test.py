#!/usr/bin/env python3
"""Prove that a Photoshop job preserves two pre-opened same-name documents."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from photoshop_bridge import execute_job, probe_job, validate_job


def jsx_string(value: str) -> str:
    return json.dumps(value.replace("\\", "/"), ensure_ascii=False)


def setup_script(paths: list[Path]) -> str:
    embedded = ",".join(jsx_string(str(path.resolve())) for path in paths)
    return f'''#target photoshop
(function () {{
    var original = app.documents.length ? app.activeDocument : null;
    var paths = [{embedded}];
    app.displayDialogs = DialogModes.NO;
    for (var i = 0; i < paths.length; i += 1) {{
        var document = app.documents.add(UnitValue(180, "px"), UnitValue(100, "px"), 72, "codex-preservation", NewDocumentMode.RGB, DocumentFill.TRANSPARENT);
        var text = document.artLayers.add();
        text.kind = LayerKind.TEXT;
        text.textItem.contents = "Preserve " + (i + 1);
        text.textItem.position = [UnitValue(20, "px"), UnitValue(55, "px")];
        text.textItem.size = UnitValue(20, "px");
        var options = new PhotoshopSaveOptions();
        options.layers = true;
        document.saveAs(new File(paths[i]), options, false, Extension.LOWERCASE);
    }}
    if (original) {{ app.activeDocument = original; }}
    return "ok";
}}());'''


def cleanup_script(paths: list[Path]) -> str:
    embedded = ",".join(jsx_string(str(path.resolve())) for path in paths)
    return f'''#target photoshop
(function () {{
    var paths = [{embedded}];
    function matches(document, pathValue) {{
        try {{ return document.fullName.fsName.toLowerCase() === new File(pathValue).fsName.toLowerCase(); }} catch (ignored) {{ return false; }}
    }}
    for (var i = app.documents.length - 1; i >= 0; i -= 1) {{
        for (var j = 0; j < paths.length; j += 1) {{
            if (matches(app.documents[i], paths[j])) {{
                app.documents[i].close(SaveOptions.DONOTSAVECHANGES);
                break;
            }}
        }}
    }}
    return "ok";
}}());'''


def inventory(app: Any) -> list[dict[str, Any]]:
    records = []
    for index in range(1, int(app.Documents.Count) + 1):
        document = app.Documents.Item(index)
        try:
            path = str(document.FullName)
        except Exception:
            path = None
        records.append({"name": str(document.Name), "path": path, "saved": bool(document.Saved)})
    return records


def worker(mode: str, root: Path, result_path: Path) -> int:
    targets = [root / "a" / "same-name.psd", root / "b" / "same-name.psd"]
    try:
        import win32com.client  # type: ignore[import-untyped]

        app = win32com.client.Dispatch("Photoshop.Application")
        if mode == "setup":
            app.DoJavaScript(setup_script(targets))
            payload = {"status": "ok", "documents": inventory(app)}
        elif mode == "cleanup":
            app.DoJavaScript(cleanup_script(targets))
            payload = {"status": "ok", "documents": inventory(app)}
        elif mode == "inventory":
            payload = {"status": "ok", "documents": inventory(app)}
        else:
            raise ValueError(f"Unknown worker mode: {mode}")
        code = 0
    except Exception as error:  # pragma: no cover - Photoshop-specific
        payload = {"status": "error", "message": str(error)}
        code = 1
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return code


def run_worker(mode: str, root: Path, timeout: float) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="codex-photoshop-preservation-worker-") as temp:
        result_path = Path(temp) / "result.json"
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--worker-mode", mode,
                "--worker-root", str(root),
                "--worker-result", str(result_path),
            ],
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        if not result_path.exists():
            raise RuntimeError(completed.stderr or completed.stdout or f"{mode} worker exited {completed.returncode}")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if payload.get("status") != "ok":
            raise RuntimeError(payload.get("message", f"{mode} worker failed"))
        return payload


def normalized_paths(records: list[dict[str, Any]]) -> set[str]:
    return {
        os.path.normcase(os.path.abspath(record["path"]))
        for record in records
        if record.get("path")
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--worker-mode", choices=("setup", "cleanup", "inventory"), help=argparse.SUPPRESS)
    parser.add_argument("--worker-root", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--worker-result", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker_mode:
        if not args.worker_root or not args.worker_result:
            raise SystemExit("Worker mode requires --worker-root and --worker-result")
        return worker(args.worker_mode, args.worker_root, args.worker_result)

    if args.work_dir:
        root = args.work_dir.resolve()
        root.mkdir(parents=True, exist_ok=True)
        cleanup_temp = None
    else:
        cleanup_temp = tempfile.TemporaryDirectory(prefix="rebuild-ui-preservation-test-")
        root = Path(cleanup_temp.name)
    targets = [root / "a" / "same-name.psd", root / "b" / "same-name.psd"]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()

    audit: dict[str, Any] = {"targets": [str(path) for path in targets]}
    try:
        run_worker("cleanup", root, args.timeout)
        setup = run_worker("setup", root, args.timeout)
        audit["before"] = setup["documents"]
        expected = {os.path.normcase(os.path.abspath(str(path))) for path in targets}
        if not expected.issubset(normalized_paths(setup["documents"])):
            raise RuntimeError("Could not establish two pre-opened same-name test documents")

        probe_dir = root / "probe"
        probe_dir.mkdir(parents=True, exist_ok=True)
        job = validate_job(probe_job(probe_dir), root, overwrite=True)
        report = execute_job(job, probe_dir / "compiled.jsx", args.timeout)
        after = run_worker("inventory", root, args.timeout)
        audit["after"] = after["documents"]
        audit["bridge_report"] = report
        audit["passed"] = expected.issubset(normalized_paths(after["documents"])) and bool(
            report.get("preexisting_documents", {}).get("preserved")
        )
        if not audit["passed"]:
            raise RuntimeError("Photoshop bridge did not preserve both same-name documents")
    finally:
        try:
            cleanup = run_worker("cleanup", root, args.timeout)
            audit["after_cleanup"] = cleanup["documents"]
        except Exception as error:
            audit["cleanup_error"] = str(error)
        report_path = root / "document-preservation-test.json"
        report_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if cleanup_temp:
            cleanup_temp.cleanup()
    print(json.dumps({"passed": True, "report": str((root / 'document-preservation-test.json').resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
