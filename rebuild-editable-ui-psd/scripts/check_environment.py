#!/usr/bin/env python3
"""Report readiness for the hybrid editable-UI PSD workflow."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
from pathlib import Path

from install_rembg import REMBG_VERSION, backend_status, nvidia_status


MODULES = {
    "Pillow": "PIL",
    "numpy": "numpy",
    "psd-tools": "psd_tools",
    "aggdraw": "aggdraw",
    "OpenCV (optional)": "cv2",
    "pywin32": "win32com.client",
}

REMBG_MODULE = "rembg"


def module_available(import_name: str) -> bool:
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ModuleNotFoundError, AttributeError):
        return False


def managed_rembg_status() -> dict:
    nvidia = nvidia_status()
    cpu = backend_status("cpu")
    gpu = backend_status("gpu")
    cpu_verified = cpu["ready"] and bool((cpu.get("inference_probe") or {}).get("passed"))
    gpu_verified = gpu["ready"] and bool((gpu.get("inference_probe") or {}).get("passed"))
    selected = "gpu" if nvidia["detected"] and gpu_verified else "cpu" if cpu_verified else None
    return {
        "ready": selected is not None,
        "selected_backend": selected,
        "rembg_version": REMBG_VERSION,
        "nvidia": nvidia,
        "gpu": gpu,
        "cpu": cpu,
        "fallback_ready": cpu_verified,
    }


def find_photoshop() -> list[str]:
    system = platform.system()
    candidates: list[Path] = []

    if system == "Windows":
        for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
            root = os.environ.get(env_name)
            if not root:
                continue
            adobe = Path(root) / "Adobe"
            if adobe.exists():
                candidates.extend(adobe.glob("Adobe Photoshop*"))
    elif system == "Darwin":
        candidates.extend(Path("/Applications").glob("Adobe Photoshop*.app"))

    return sorted({str(path.resolve()) for path in candidates if path.exists()})


def build_report() -> dict:
    modules = {label: module_available(name) for label, name in MODULES.items()}
    rembg_module = module_available(REMBG_MODULE)
    rembg_cli = shutil.which("rembg")
    managed_rembg = managed_rembg_status()
    required_modules = ("Pillow", "numpy", "psd-tools")
    font_roots = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"] if platform.system() == "Windows" else []
    font_files = sorted(
        str(path.resolve())
        for root in font_roots
        if root.exists()
        for pattern in ("*.ttf", "*.otf", "*.ttc")
        for path in root.glob(pattern)
    )
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "modules": modules,
        "executables": {
            "ImageMagick (optional)": shutil.which("magick"),
            "Tesseract OCR (optional)": shutil.which("tesseract"),
        },
        "rembg": {
            "detected": managed_rembg["ready"] or rembg_module or bool(rembg_cli),
            "managed": managed_rembg,
            "python_module": rembg_module,
            "cli": rembg_cli,
            "preferred_for_background_removal": managed_rembg["selected_backend"],
        },
        "rembg_ready": managed_rembg["ready"],
        "photoshop_candidates": find_photoshop(),
        "python_audit_ready": all(modules[name] for name in required_modules),
        "forced_psd_composite_ready": all(
            modules[name] for name in (*required_modules, "aggdraw")
        ),
        "button_analysis_ready": all(
            modules[name] for name in ("Pillow", "numpy", "OpenCV (optional)")
        ),
        "high_fidelity_gate_ready": all(
            modules[name] for name in ("Pillow", "numpy", "OpenCV (optional)")
        ),
        "system_font_file_count": len(font_files),
        "native_psd_backend_detected": bool(find_photoshop()),
        "codex_photoshop_v3_ready": platform.system() == "Windows"
        and bool(find_photoshop())
        and managed_rembg["ready"]
        and modules["pywin32"]
        and all(modules[name] for name in ("Pillow", "numpy", "psd-tools", "OpenCV (optional)")),
    }


def print_human(report: dict) -> None:
    print(f"Platform: {report['platform']}")
    print(f"Python: {report['python']}")
    print("Python modules:")
    for label, available in report["modules"].items():
        print(f"  {'OK' if available else 'MISSING':7} {label}")
    print("Executables:")
    for label, path in report["executables"].items():
        print(f"  {'OK' if path else 'MISSING':7} {label}: {path or '-'}")
    rembg = report["rembg"]
    print("rembg deployment:")
    print(f"  {'DETECTED' if rembg['detected'] else 'NOT DETECTED'}")
    print(f"  Managed runtime ready: {rembg['managed']['ready']}")
    print(f"  Selected backend: {rembg['managed']['selected_backend'] or '-'}")
    print(f"  Managed version: {rembg['managed']['rembg_version']}")
    print(f"  NVIDIA detected: {rembg['managed']['nvidia']['detected']}")
    print(f"  GPU ready: {rembg['managed']['gpu']['ready']}")
    print(f"  GPU providers: {', '.join(rembg['managed']['gpu']['provider'].get('providers', [])) or '-'}")
    print(f"  CPU fallback ready: {rembg['managed']['fallback_ready']}")
    print(f"  CPU CLI: {rembg['managed']['cpu']['cli'] or '-'}")
    print(f"  Python module: {rembg['python_module']}")
    print(f"  CLI: {rembg['cli'] or '-'}")
    print("Photoshop candidates:")
    if report["photoshop_candidates"]:
        for path in report["photoshop_candidates"]:
            print(f"  OK      {path}")
    else:
        print("  NOT DETECTED (GUI or remote access may still be available)")
    print(f"Python audit ready: {report['python_audit_ready']}")
    print(f"Forced PSD composite ready: {report['forced_psd_composite_ready']}")
    print(f"Button analysis ready: {report['button_analysis_ready']}")
    print(f"High-fidelity gates ready: {report['high_fidelity_gate_ready']}")
    print(f"System font files found: {report['system_font_file_count']}")
    print(f"Native PSD backend detected: {report['native_psd_backend_detected']}")
    print(f"Codex Photoshop v3 ready: {report['codex_photoshop_v3_ready']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a human report")
    args = parser.parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report)
    return 0 if report["python_audit_ready"] and report["rembg_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
