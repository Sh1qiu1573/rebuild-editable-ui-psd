#!/usr/bin/env python3
"""Inventory the exact fonts exposed to Photoshop, including PostScript names."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT = r'''#target photoshop
(function () {
    function clean(value) {
        return String(value || "").replace(/[\t\r\n]/g, " ");
    }
    var rows = [];
    var i;
    for (i = 0; i < app.fonts.length; i += 1) {
        var font = app.fonts[i];
        var postScript = "";
        try { postScript = font.postScriptName; } catch (ignored) {}
        if (!postScript) { postScript = font.name; }
        rows.push([
            clean(postScript),
            clean(font.name),
            clean(font.family),
            clean(font.style)
        ].join("\t"));
    }
    return rows.join("\n");
}());'''


def worker(result_path: Path) -> int:
    try:
        import win32com.client  # type: ignore[import-untyped]

        raw = win32com.client.Dispatch("Photoshop.Application").DoJavaScript(SCRIPT)
        records = []
        for line in str(raw or "").splitlines():
            values = line.split("\t")
            if len(values) == 4:
                records.append(dict(zip(("postscript_name", "name", "family", "style"), values)))
        records.sort(key=lambda item: (item["family"].casefold(), item["style"].casefold(), item["postscript_name"].casefold()))
        payload = {"status": "ok", "count": len(records), "fonts": records}
        code = 0
    except Exception as error:  # pragma: no cover - Photoshop-specific
        payload = {"status": "error", "code": "E_PHOTOSHOP_SCRIPT", "message": str(error)}
        code = 4
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--filter", help="Case-insensitive regex over family, style, name, and PostScript name")
    parser.add_argument("--timeout", type=float, default=45)
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker)

    with tempfile.TemporaryDirectory(prefix="codex-photoshop-fonts-") as temp:
        result_path = Path(temp) / "result.json"
        try:
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--worker", str(result_path)],
                text=True,
                capture_output=True,
                timeout=args.timeout,
            )
        except subprocess.TimeoutExpired:
            print(json.dumps({"status": "error", "code": "E_PHOTOSHOP_TIMEOUT", "message": "Font inventory timed out"}), file=sys.stderr)
            return 6
        if not result_path.exists():
            print(completed.stderr or completed.stdout or "Font inventory worker failed", file=sys.stderr)
            return completed.returncode or 1
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    if payload.get("status") != "ok":
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 4
    if args.filter:
        pattern = re.compile(args.filter, re.IGNORECASE)
        payload["fonts"] = [
            item for item in payload["fonts"]
            if pattern.search(" ".join(item.values()))
        ]
        payload["count"] = len(payload["fonts"])
        payload["filter"] = args.filter
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
