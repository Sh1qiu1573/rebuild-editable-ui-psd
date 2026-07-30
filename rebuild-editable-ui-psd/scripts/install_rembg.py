#!/usr/bin/env python3
"""Install rembg into an isolated runtime managed by this skill."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


SKILL_NAME = "rebuild-editable-ui-psd"
SKILL_VERSION = "3.6"
ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements-rembg.txt"


def runtime_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "Codex" / "skill-runtime" / SKILL_NAME / f"rembg-{SKILL_VERSION}"


def runtime_python(path: Path | None = None) -> Path:
    root = path or runtime_dir()
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def runtime_cli(path: Path | None = None) -> Path:
    root = path or runtime_dir()
    return root / ("Scripts/rembg.exe" if os.name == "nt" else "bin/rembg")


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check)


def interpreter_usable(executable: Path) -> bool:
    if not executable.is_file():
        return False
    result = run(
        [str(executable), "-c", "import sys,venv; raise SystemExit(not ((3,11) <= sys.version_info[:2] < (3,14)))"],
        check=False,
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
            result = run(["py", f"-{version}", "-c", "import sys; print(sys.executable)"], check=False)
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
    )
    return result.stdout.strip() if result.returncode == 0 else None


def expected_version() -> str:
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        requirement = line.strip()
        if requirement and not requirement.startswith("#") and "==" in requirement:
            return requirement.rsplit("==", 1)[1].strip()
    raise RuntimeError(f"Pinned rembg version not found in {REQUIREMENTS}")


def ensure_install(force: bool = False) -> dict:
    if not REQUIREMENTS.is_file():
        raise RuntimeError(f"Missing requirements file: {REQUIREMENTS}")
    target = runtime_dir()
    python = runtime_python(target)
    before = installed_version(python)
    expected = expected_version()
    needs_install = force or before != expected
    if needs_install:
        if not python.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            base_python = select_interpreter()
            result = run([str(base_python), "-m", "venv", str(target)], check=False)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Failed to create rembg runtime")
        result = run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(REQUIREMENTS)],
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Failed to install rembg")
    version = installed_version(python)
    cli = runtime_cli(target)
    if version != expected or not cli.is_file():
        raise RuntimeError(f"rembg installation is not ready: expected {expected}, found {version or 'missing'}")
    record = {
        "status": "ok",
        "skill": SKILL_NAME,
        "skill_version": SKILL_VERSION,
        "runtime": str(target),
        "python": str(python),
        "cli": str(cli),
        "rembg_version": version,
        "changed": needs_install,
    }
    (target / "install-record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ensure", action="store_true", help="Install only when the managed runtime is missing")
    parser.add_argument("--force", action="store_true", help="Reinstall the pinned rembg dependency")
    args = parser.parse_args()
    try:
        record = ensure_install(force=args.force)
    except Exception as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
