#!/usr/bin/env python3
"""Run the skill-managed rembg CLI for one raster object."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from install_rembg import ensure_install, runtime_cli


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="u2net")
    parser.add_argument("--alpha-matting", action="store_true")
    parser.add_argument("--only-mask", action="store_true")
    parser.add_argument("--no-install", action="store_true", help="Fail instead of repairing a missing managed runtime")
    args = parser.parse_args()

    if not args.input.is_file():
        print(json.dumps({"status": "error", "error": f"Input not found: {args.input}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    try:
        if not args.no_install:
            ensure_install()
        cli = runtime_cli()
        if not cli.is_file():
            raise RuntimeError(f"Managed rembg CLI not found: {cli}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        command = [str(cli), "i", "-m", args.model]
        if args.alpha_matting:
            command.append("-a")
        if args.only_mask:
            command.append("-om")
        command.extend([str(args.input.resolve()), str(args.output.resolve())])
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "rembg inference failed")
        if not args.output.is_file() or args.output.stat().st_size == 0:
            raise RuntimeError(f"rembg did not write a non-empty output: {args.output}")
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
        "cli": str(cli),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
