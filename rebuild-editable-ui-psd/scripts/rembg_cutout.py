#!/usr/bin/env python3
"""Run rembg with GPU priority and transparent CPU retry."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from install_rembg import backend_status, clean_output, ensure_install, runtime_python


def command_for(backend: str, args: argparse.Namespace, output: Path) -> list[str]:
    worker = Path(__file__).resolve().with_name("rembg_worker.py")
    command = [
        str(runtime_python(backend)),
        str(worker),
        str(args.input.resolve()),
        str(output.resolve()),
        "--backend",
        backend,
        "--model",
        args.model,
    ]
    if args.alpha_matting:
        command.append("--alpha-matting")
    if args.only_mask:
        command.append("--only-mask")
    return command


def select_without_install(requested: str) -> str:
    if requested in {"cpu", "gpu"}:
        status = backend_status(requested)
        if not status["ready"]:
            raise RuntimeError(f"Managed rembg {requested} backend is not ready")
        return requested
    gpu = backend_status("gpu")
    if gpu["ready"] and (gpu.get("inference_probe") or {}).get("passed"):
        return "gpu"
    cpu = backend_status("cpu")
    if cpu["ready"]:
        return "cpu"
    raise RuntimeError("No managed rembg backend is ready")


def run_backend(backend: str, args: argparse.Namespace) -> dict[str, Any]:
    python = runtime_python(backend)
    if not python.is_file():
        return {"backend": backend, "status": "error", "error": f"Managed rembg runtime not found: {python}"}
    suffix = args.output.suffix or ".png"
    temporary = args.output.with_name(f".{args.output.stem}.{backend}.rembg-tmp{suffix}")
    if temporary.exists():
        temporary.unlink()
    command = command_for(backend, args, temporary)
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        if temporary.exists():
            temporary.unlink()
        return {
            "backend": backend,
            "status": "error",
            "python": str(python),
            "error": clean_output(result.stderr) or clean_output(result.stdout) or "rembg inference failed",
        }
    if not temporary.is_file() or temporary.stat().st_size == 0:
        return {"backend": backend, "status": "error", "python": str(python), "error": "rembg wrote no output"}
    temporary.replace(args.output)
    return {
        "backend": backend,
        "status": "ok",
        "python": str(python),
        "output": str(args.output.resolve()),
        "worker": clean_output(result.stdout),
    }


def execute_with_fallback(
    selected: str,
    requested: str,
    args: argparse.Namespace,
    runner: Callable[[str, argparse.Namespace], dict[str, Any]] = run_backend,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    order = [selected]
    if requested == "auto" and selected == "gpu":
        order.append("cpu")
    attempts: list[dict[str, Any]] = []
    for backend in order:
        attempt = runner(backend, args)
        attempts.append(attempt)
        if attempt["status"] == "ok":
            return attempt, attempts
    return None, attempts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="u2net")
    parser.add_argument("--alpha-matting", action="store_true")
    parser.add_argument("--only-mask", action="store_true")
    parser.add_argument("--backend", choices=("auto", "gpu", "cpu"), default="auto")
    parser.add_argument("--no-install", action="store_true", help="Fail instead of repairing managed runtimes")
    args = parser.parse_args()

    if not args.input.is_file():
        print(json.dumps({"status": "error", "error": f"Input not found: {args.input}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)

    try:
        if args.no_install:
            selected = select_without_install(args.backend)
        else:
            install = ensure_install(backend=args.backend, actual_probe=False)
            selected = install["selected_backend"]
        success, attempts = execute_with_fallback(selected, args.backend, args)
        if success is None:
            raise RuntimeError("; ".join(f"{item['backend']}: {item['error']}" for item in attempts))
    except Exception as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    print(json.dumps({
        "status": "ok",
        "input": str(args.input.resolve()),
        "output": str(args.output.resolve()),
        "model": args.model,
        "alpha_matting": args.alpha_matting,
        "only_mask": args.only_mask,
        "backend_requested": args.backend,
        "backend_used": success["backend"],
        "fallback_used": success["backend"] != selected,
        "attempts": attempts,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
