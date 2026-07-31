#!/usr/bin/env python3
"""Run a fail-closed Photoshop render/gate/tune/fallback loop for one component."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from photoshop_bridge import BridgeError, execute_job, validate_job
from visual_regression_gate import check_case


DEFAULT_THRESHOLDS = {
    "min_structure_score": 0.985,
    "min_edge_recall": 0.985,
    "min_edge_precision": 0.985,
    "min_color_histogram_intersection": 0.97,
    "min_detail_ratio": 0.95,
    "max_detail_ratio": 1.05,
}


class TuneError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TuneError(f"Expected a JSON object: {path}")
    return payload


def resolve_path(value: str, base: Path) -> Path:
    path = Path(value)
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def find_layer(job: dict[str, Any], layer_id: str) -> dict[str, Any]:
    matches = [layer for layer in job.get("layers", []) if layer.get("id") == layer_id]
    if len(matches) != 1:
        raise TuneError(f"Expected exactly one layer with id {layer_id!r}; found {len(matches)}")
    return matches[0]


def get_field(target: dict[str, Any], dotted: str) -> Any:
    current: Any = target
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def set_field(target: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    current = target
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def objective(case: dict[str, Any]) -> float:
    metrics = case["metrics"]
    detail = max(float(metrics["detail_ratio"]), 1e-6)
    return (
        float(metrics["structure_score"])
        + float(metrics["edge_recall"])
        + float(metrics["edge_precision"])
        + float(metrics["color_histogram_intersection"])
        - abs(math.log(detail))
    )


def prepare_attempt_job(raw_job: dict[str, Any], attempt_dir: Path, base: Path) -> dict[str, Any]:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    job = deepcopy(raw_job)
    job["output"] = {
        "psd": str(attempt_dir / "candidate.psd"),
        "preview": str(attempt_dir / "candidate.png"),
        "layer_png_dir": str(attempt_dir / "png"),
        "report": str(attempt_dir / "photoshop-report.json"),
    }
    return validate_job(job, base, overwrite=True)


def render_with_retry(
    job: dict[str, Any],
    attempt_dir: Path,
    timeout_seconds: float,
    retries: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    for retry in range(retries + 1):
        try:
            return execute_job(job, attempt_dir / "compiled.jsx", timeout_seconds), failures
        except BridgeError as error:
            failures.append({"retry": retry, "code": error.code, "message": str(error)})
            if error.code not in {"E_PHOTOSHOP_TIMEOUT", "E_PHOTOSHOP_UNAVAILABLE"} or retry >= retries:
                raise
            time.sleep(min(2 ** retry, 8))
    raise AssertionError("unreachable")


def copy_accepted(report: dict[str, Any], output_dir: Path, attempt: dict[str, Any]) -> dict[str, str]:
    accepted_dir = output_dir / "accepted"
    accepted_dir.mkdir(parents=True, exist_ok=True)
    psd = accepted_dir / "component.psd"
    preview = accepted_dir / "component.png"
    shutil.copy2(report["psd"], psd)
    shutil.copy2(report["preview"], preview)
    (accepted_dir / "accepted-attempt.json").write_text(
        json.dumps(attempt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"psd": str(psd.resolve()), "preview": str(preview.resolve())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--plan-only", action="store_true", help="Validate and print the candidate plan without opening Photoshop")
    args = parser.parse_args()

    config_path = args.config.resolve()
    config_dir = config_path.parent
    try:
        config = read_json(config_path)
        component_id = str(config["component_id"])
        layer_id = str(config.get("layer_id", component_id))
        reference = resolve_path(str(config["reference"]), config_dir)
        base_job_path = resolve_path(str(config["base_job"]), config_dir)
        output_dir = resolve_path(str(config.get("output_dir", f"work/tuning/{component_id}")), config_dir)
        candidate_sets = config.get("candidate_sets", [])
        families = config.get("parameter_families", [])
        fallbacks = config.get("fallback_jobs", [])
        if not reference.exists() or not base_job_path.exists():
            raise TuneError("reference and base_job must exist")
        if not isinstance(candidate_sets, list) or not isinstance(families, list) or not isinstance(fallbacks, list):
            raise TuneError("candidate_sets, parameter_families, and fallback_jobs must be arrays")
        raw_base = read_json(base_job_path)
        base_layer = find_layer(raw_base, layer_id)
        for family in families:
            if not family.get("field") or not isinstance(family.get("values"), list) or not family["values"]:
                raise TuneError("Each parameter family requires field and non-empty values")
        for candidate in candidate_sets:
            if not isinstance(candidate.get("values"), dict):
                raise TuneError("Each candidate set requires a values object")
        plan = {
            "component_id": component_id,
            "layer_id": layer_id,
            "baseline": {family["field"]: get_field(base_layer, family["field"]) for family in families},
            "candidate_sets": candidate_sets,
            "parameter_families": families,
            "fallbacks": [item.get("representation", item.get("job")) for item in fallbacks],
        }
        if args.plan_only:
            print(json.dumps({"status": "ok", "plan": plan}, ensure_ascii=False, indent=2))
            return 0

        output_dir.mkdir(parents=True, exist_ok=True)
        thresholds = {**DEFAULT_THRESHOLDS, **config.get("thresholds", {})}
        timeout_seconds = float(config.get("photoshop_timeout_seconds", 120))
        retries = int(config.get("photoshop_retries", 1))
        max_sweeps = max(1, int(config.get("max_sweeps", 2)))
        attempts: list[dict[str, Any]] = []
        attempt_counter = 0

        def evaluate(
            raw_job: dict[str, Any],
            label: str,
            representation: str,
            job_base: Path = base_job_path.parent,
        ) -> tuple[dict[str, Any], dict[str, Any]]:
            nonlocal attempt_counter
            attempt_counter += 1
            attempt_dir = output_dir / f"attempt-{attempt_counter:03d}-{label}"
            job = prepare_attempt_job(raw_job, attempt_dir, job_base)
            photoshop_report, retry_failures = render_with_retry(job, attempt_dir, timeout_seconds, retries)
            case = check_case(
                {
                    "id": component_id,
                    "reference": str(reference),
                    "candidate": photoshop_report["preview"],
                    "thresholds": thresholds,
                },
                config_dir,
            )
            attempt = {
                "attempt": attempt_counter,
                "label": label,
                "representation": representation,
                "parameters": {family["field"]: get_field(find_layer(raw_job, layer_id), family["field"]) for family in families},
                "candidate_layer": deepcopy(find_layer(raw_job, layer_id)),
                "photoshop": photoshop_report,
                "retry_failures": retry_failures,
                "gate": case,
                "objective": objective(case),
            }
            attempts.append(attempt)
            return attempt, job

        current_job = deepcopy(raw_base)
        best_attempt, best_job = evaluate(current_job, "baseline", str(base_layer.get("kind", "unknown")))
        accepted: tuple[dict[str, Any], dict[str, Any]] | None = (best_attempt, best_job) if best_attempt["gate"]["passed"] else None

        for candidate_index, candidate in enumerate(candidate_sets):
            if accepted:
                break
            candidate_job = deepcopy(raw_base)
            candidate_layer = find_layer(candidate_job, layer_id)
            for field, value in candidate["values"].items():
                set_field(candidate_layer, field, value)
            attempt, rendered_job = evaluate(
                candidate_job,
                str(candidate.get("label", f"candidate-set-{candidate_index + 1}")),
                str(candidate.get("representation", candidate_layer.get("kind", "unknown"))),
            )
            if attempt["objective"] > best_attempt["objective"]:
                best_attempt = attempt
                current_job = candidate_job
            if attempt["gate"]["passed"]:
                accepted = (attempt, rendered_job)

        for sweep in range(max_sweeps):
            if accepted:
                break
            improved = False
            for family_index, family in enumerate(families):
                family_best_attempt = best_attempt
                family_best_job = current_job
                current_layer = find_layer(current_job, layer_id)
                current_value = get_field(current_layer, family["field"])
                for value_index, value in enumerate(family["values"]):
                    if value == current_value:
                        continue
                    candidate_job = deepcopy(current_job)
                    set_field(find_layer(candidate_job, layer_id), family["field"], value)
                    attempt, rendered_job = evaluate(
                        candidate_job,
                        f"s{sweep + 1}-f{family_index + 1}-v{value_index + 1}",
                        str(find_layer(candidate_job, layer_id).get("kind", "unknown")),
                    )
                    if attempt["objective"] > family_best_attempt["objective"]:
                        family_best_attempt, family_best_job = attempt, candidate_job
                    if attempt["gate"]["passed"]:
                        accepted = (attempt, rendered_job)
                        break
                if accepted:
                    break
                if family_best_attempt is not best_attempt:
                    best_attempt = family_best_attempt
                    current_job = family_best_job
                    improved = True
            if not improved:
                break

        if not accepted:
            for fallback_index, fallback in enumerate(fallbacks):
                fallback_path = resolve_path(str(fallback["job"]), config_dir)
                fallback_job = read_json(fallback_path)
                find_layer(fallback_job, layer_id)
                attempt, rendered_job = evaluate(
                    fallback_job,
                    f"fallback-{fallback_index + 1}",
                    str(fallback.get("representation", "fallback")),
                    fallback_path.parent,
                )
                if attempt["gate"]["passed"]:
                    accepted = (attempt, rendered_job)
                    break

        report: dict[str, Any] = {
            "component_id": component_id,
            "passed": bool(accepted),
            "thresholds": thresholds,
            "attempts": attempts,
            "accepted_attempt": accepted[0]["attempt"] if accepted else None,
            "accepted_representation": accepted[0]["representation"] if accepted else None,
            "failure_code": None if accepted else "E_FALLBACK_EXHAUSTED",
        }
        if accepted:
            report["accepted_outputs"] = copy_accepted(accepted[0]["photoshop"], output_dir, accepted[0])
            (output_dir / "accepted-job.json").write_text(
                json.dumps(accepted[1], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        report_path = output_dir / "component-regression.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if accepted else 1
    except (KeyError, OSError, ValueError, json.JSONDecodeError, TuneError, BridgeError) as error:
        payload = {"passed": False, "failure_code": getattr(error, "code", "E_INPUT"), "message": str(error)}
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
