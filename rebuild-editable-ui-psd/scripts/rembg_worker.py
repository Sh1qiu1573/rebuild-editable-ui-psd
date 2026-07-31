#!/usr/bin/env python3
"""Run one rembg inference inside a managed CPU or GPU virtual environment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--backend", choices=("gpu", "cpu"), required=True)
    parser.add_argument("--model", default="u2net")
    parser.add_argument("--alpha-matting", action="store_true")
    parser.add_argument("--only-mask", action="store_true")
    args = parser.parse_args()

    import onnxruntime as ort

    if args.backend == "gpu" and hasattr(ort, "preload_dlls"):
        ort.preload_dlls(directory="")

    from rembg import new_session, remove

    session = new_session(args.model)
    providers = session.inner_session.get_providers()
    required = "CUDAExecutionProvider" if args.backend == "gpu" else "CPUExecutionProvider"
    if required not in providers:
        raise RuntimeError(f"{required} is unavailable in session providers: {providers}")
    result = remove(
        args.input.read_bytes(),
        session=session,
        alpha_matting=args.alpha_matting,
        only_mask=args.only_mask,
        force_return_bytes=True,
    )
    args.output.write_bytes(result)
    print(json.dumps({"providers": providers, "active_provider": providers[0] if providers else None}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
