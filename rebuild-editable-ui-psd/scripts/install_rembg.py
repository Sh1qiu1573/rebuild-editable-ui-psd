#!/usr/bin/env python3
"""Install GPU-first rembg runtimes with an isolated CPU fallback."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


SKILL_NAME = "rebuild-editable-ui-psd"
SKILL_VERSION = "3.6.2"
RUNTIME_VERSION = "3.6.1"
REMBG_VERSION = "2.0.77"
ROOT = Path(__file__).resolve().parent.parent
BACKENDS = ("cpu", "gpu")


def runtime_base() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "Codex" / "skill-runtime" / SKILL_NAME


def runtime_dir(backend: str = "cpu") -> Path:
    validate_backend(backend)
    return runtime_base() / f"rembg-{RUNTIME_VERSION}-{backend}"


def runtime_python(backend: str = "cpu", path: Path | None = None) -> Path:
    root = path or runtime_dir(backend)
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def runtime_cli(backend: str = "cpu", path: Path | None = None) -> Path:
    root = path or runtime_dir(backend)
    return root / ("Scripts/rembg.exe" if os.name == "nt" else "bin/rembg")


def requirements_path(backend: str) -> Path:
    validate_backend(backend)
    return ROOT / f"requirements-rembg-{backend}.txt"


def aggregate_record_path() -> Path:
    return runtime_base() / f"rembg-{RUNTIME_VERSION}-install-record.json"


def validate_backend(backend: str) -> None:
    if backend not in BACKENDS:
        raise ValueError(f"Unsupported rembg backend: {backend}")


def run(
    command: list[str],
    *,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check, timeout=timeout)


def interpreter_usable(executable: Path) -> bool:
    if not executable.is_file():
        return False
    result = run(
        [str(executable), "-c", "import sys,venv; raise SystemExit(not ((3,11) <= sys.version_info[:2] < (3,14)))"],
        check=False,
        timeout=15,
    )
    return result.returncode == 0


def candidate_interpreters() -> list[Path]:
    candidates: list[Path] = [Path(sys.executable)]
    candidates.append(
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "python"
        / ("python.exe" if os.name == "nt" else "bin/python")
    )
    for name in ("python3.13", "python3.12", "python3.11", "python"):
        located = shutil.which(name)
        if located:
            candidates.append(Path(located))
    if os.name == "nt" and shutil.which("py"):
        for version in ("3.13", "3.12", "3.11"):
            result = run(["py", f"-{version}", "-c", "import sys; print(sys.executable)"], check=False, timeout=15)
            if result.returncode == 0 and result.stdout.strip():
                candidates.append(Path(result.stdout.strip()))
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).casefold()
        if key not in seen:
            unique.append(candidate)
            seen.add(key)
    return unique


def select_interpreter() -> Path:
    for candidate in candidate_interpreters():
        if interpreter_usable(candidate):
            return candidate
    raise RuntimeError("No Python 3.11-3.13 interpreter with venv support was found for rembg")


def installed_version(python: Path) -> str | None:
    if not python.is_file():
        return None
    result = run(
        [str(python), "-c", "import importlib.metadata as m; print(m.version('rembg'))"],
        check=False,
        timeout=30,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def expected_version(backend: str) -> str:
    requirements = requirements_path(backend)
    for line in requirements.read_text(encoding="utf-8").splitlines():
        requirement = line.strip()
        if requirement.startswith("rembg[") and "==" in requirement:
            return requirement.rsplit("==", 1)[1].strip()
    raise RuntimeError(f"Pinned rembg version not found in {requirements}")


def requirements_sha256(backend: str) -> str:
    return hashlib.sha256(requirements_path(backend).read_bytes()).hexdigest()


def clean_output(value: str) -> str:
    """Make native Windows DLL errors readable when a subprocess emits NUL-padded text."""
    return value.replace("\x00", "").strip()


def nvidia_status() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"detected": False, "executable": None, "gpus": [], "error": "nvidia-smi not found"}
    result = run(
        [
            executable,
            "--query-gpu=name,driver_version,memory.total,compute_cap",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        timeout=20,
    )
    if result.returncode != 0:
        return {
            "detected": False,
            "executable": executable,
            "gpus": [],
            "error": result.stderr.strip() or result.stdout.strip() or "nvidia-smi failed",
        }
    gpus: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) >= 4:
            gpus.append({
                "name": fields[0],
                "driver_version": fields[1],
                "memory_mib": fields[2],
                "compute_capability": fields[3],
            })
    return {"detected": bool(gpus), "executable": executable, "gpus": gpus, "error": None}


def provider_status(backend: str) -> dict[str, Any]:
    validate_backend(backend)
    python = runtime_python(backend)
    if not python.is_file():
        return {"ready": False, "providers": [], "error": "runtime Python missing"}
    code = """
import json
import onnxruntime as ort
if __BACKEND__ == "gpu" and hasattr(ort, "preload_dlls"):
    ort.preload_dlls(directory="")
print(json.dumps({'providers': ort.get_available_providers(), 'device': ort.get_device()}))
""".replace("__BACKEND__", repr(backend))
    result = run([str(python), "-c", code], check=False, timeout=60)
    if result.returncode != 0:
        return {
            "ready": False,
            "providers": [],
            "error": clean_output(result.stderr) or clean_output(result.stdout) or "provider query failed",
        }
    try:
        payload = json.loads(result.stdout.strip())
    except json.JSONDecodeError as error:
        return {"ready": False, "providers": [], "error": f"invalid provider response: {error}"}
    required = "CUDAExecutionProvider" if backend == "gpu" else "CPUExecutionProvider"
    providers = payload.get("providers", [])
    return {
        "ready": required in providers,
        "providers": providers,
        "device": payload.get("device"),
        "error": None if required in providers else f"{required} is unavailable",
    }


def inference_probe(backend: str) -> dict[str, Any]:
    validate_backend(backend)
    python = runtime_python(backend)
    code = r'''
import json
import time
from PIL import Image, ImageDraw
import onnxruntime as ort
if __BACKEND__ == "gpu" and hasattr(ort, "preload_dlls"):
    ort.preload_dlls(directory="")
from rembg import new_session, remove

started = time.perf_counter()
session = new_session("u2net")
providers = session.inner_session.get_providers()
required = "CUDAExecutionProvider" if __BACKEND__ == "gpu" else "CPUExecutionProvider"
if required not in providers:
    raise RuntimeError(f"{required} is unavailable in session providers: {providers}")
image = Image.new("RGB", (128, 128), "white")
ImageDraw.Draw(image).ellipse((24, 18, 108, 114), fill=(220, 35, 65))
output = remove(image, session=session)
if output.mode != "RGBA" or output.size != image.size:
    raise RuntimeError(f"Unexpected rembg output: mode={output.mode}, size={output.size}")
print(json.dumps({
    "passed": True,
    "providers": providers,
    "active_provider": providers[0] if providers else None,
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "output_mode": output.mode,
    "output_size": list(output.size),
}))
'''.replace("__BACKEND__", repr(backend))
    result = run([str(python), "-c", code], check=False, timeout=600)
    if result.returncode != 0:
        return {
            "passed": False,
            "providers": [],
            "active_provider": None,
            "error": clean_output(result.stderr) or clean_output(result.stdout) or "rembg inference probe failed",
        }
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as error:
        return {"passed": False, "providers": [], "active_provider": None, "error": str(error)}
    payload["error"] = None
    return payload


def read_backend_record(backend: str) -> dict[str, Any] | None:
    path = runtime_dir(backend) / "install-record.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def backend_status(backend: str) -> dict[str, Any]:
    validate_backend(backend)
    python = runtime_python(backend)
    cli = runtime_cli(backend)
    version = installed_version(python)
    provider = provider_status(backend) if version == REMBG_VERSION else {"ready": False, "providers": [], "error": "rembg version mismatch"}
    record = read_backend_record(backend)
    probe = record.get("inference_probe") if record else None
    return {
        "backend": backend,
        "runtime": str(runtime_dir(backend)),
        "python": str(python) if python.is_file() else None,
        "cli": str(cli) if cli.is_file() else None,
        "version": version,
        "provider": provider,
        "inference_probe": probe,
        "ready": bool(version == REMBG_VERSION and cli.is_file() and provider.get("ready")),
    }


def ensure_backend(backend: str, *, force: bool = False, actual_probe: bool = True) -> dict[str, Any]:
    validate_backend(backend)
    requirements = requirements_path(backend)
    if not requirements.is_file():
        raise RuntimeError(f"Missing requirements file: {requirements}")
    target = runtime_dir(backend)
    python = runtime_python(backend, target)
    before = installed_version(python)
    expected = expected_version(backend)
    requirement_hash = requirements_sha256(backend)
    previous = read_backend_record(backend)
    needs_install = force or before != expected or (previous or {}).get("requirements_sha256") != requirement_hash
    if needs_install:
        if not python.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            base_python = select_interpreter()
            result = run([str(base_python), "-m", "venv", str(target)], check=False, timeout=180)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"Failed to create {backend} runtime")
        result = run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements)],
            check=False,
            timeout=1200,
        )
        if result.returncode != 0:
            raise RuntimeError(clean_output(result.stderr) or clean_output(result.stdout) or f"Failed to install rembg {backend} backend")
    version = installed_version(python)
    cli = runtime_cli(backend, target)
    if version != expected or not cli.is_file():
        raise RuntimeError(f"rembg {backend} installation is not ready: expected {expected}, found {version or 'missing'}")
    provider = provider_status(backend)
    if not provider["ready"]:
        raise RuntimeError(provider["error"] or f"rembg {backend} provider is unavailable")
    previous_probe = previous.get("inference_probe") if previous else None
    should_probe = actual_probe or needs_install or not (previous_probe and previous_probe.get("passed"))
    probe = inference_probe(backend) if should_probe else previous_probe
    if not probe or not probe.get("passed"):
        raise RuntimeError((probe or {}).get("error") or f"rembg {backend} inference probe failed")
    record = {
        "status": "ok",
        "skill": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "backend": backend,
        "runtime": str(target),
        "python": str(python),
        "cli": str(cli),
        "rembg_version": version,
        "requirements_sha256": requirement_hash,
        "provider": provider,
        "inference_probe": probe,
        "changed": needs_install,
    }
    (target / "install-record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def ensure_install(
    *,
    force: bool = False,
    backend: str = "auto",
    actual_probe: bool = True,
) -> dict[str, Any]:
    if backend not in {"auto", *BACKENDS}:
        raise ValueError(f"Unsupported rembg backend selection: {backend}")
    nvidia = nvidia_status()
    cpu = ensure_backend("cpu", force=force, actual_probe=actual_probe)
    gpu: dict[str, Any] | None = None
    gpu_error: str | None = None
    should_try_gpu = backend == "gpu" or (backend == "auto" and nvidia["detected"])
    if should_try_gpu:
        try:
            gpu = ensure_backend("gpu", force=force, actual_probe=actual_probe)
        except Exception as error:
            gpu_error = str(error)
            if backend == "gpu":
                raise
    selected = "gpu" if gpu else "cpu"
    record = {
        "status": "ok",
        "skill": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "rembg_version": REMBG_VERSION,
        "requested_backend": backend,
        "selected_backend": selected,
        "nvidia": nvidia,
        "gpu": gpu,
        "gpu_error": gpu_error,
        "cpu": cpu,
        "fallback_ready": True,
    }
    runtime_base().mkdir(parents=True, exist_ok=True)
    aggregate_record_path().write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ensure", action="store_true", help="Ensure GPU-first rembg plus CPU fallback")
    parser.add_argument("--force", action="store_true", help="Reinstall the pinned rembg dependencies")
    parser.add_argument("--backend", choices=("auto", "cpu", "gpu"), default="auto")
    parser.add_argument("--no-actual-probe", action="store_true", help="Skip a repeated image inference probe when a prior probe passed")
    args = parser.parse_args()
    try:
        record = ensure_install(
            force=args.force,
            backend=args.backend,
            actual_probe=not args.no_actual_probe,
        )
    except Exception as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
