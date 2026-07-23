#!/usr/bin/env python3
"""Audit one-object-per-layer and instance-specific mask requirements."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    layers = payload.get("layers", [])
    objects = [layer for layer in layers if layer.get("kind") == "raster-object"]
    violations: list[dict] = []

    ids = [obj.get("object_id") for obj in objects]
    duplicate_ids = {value for value, count in Counter(ids).items() if value and count > 1}
    mask_fields = ("visible_mask", "occlusion_mask", "silhouette_mask")
    mask_paths = {field: [obj.get(field) for obj in objects if obj.get(field)] for field in mask_fields}

    for obj in objects:
        object_id = obj.get("object_id") or obj.get("id") or "<missing>"
        if not obj.get("object_id"):
            violations.append({"object_id": object_id, "rule": "missing_object_id"})
        if obj.get("instance_count") != 1:
            violations.append({"object_id": object_id, "rule": "instance_count_must_equal_1", "value": obj.get("instance_count")})
        if obj.get("template_reused") not in (False, None):
            violations.append({"object_id": object_id, "rule": "template_reuse_forbidden"})
        for field in mask_fields:
            if not obj.get(field):
                violations.append({"object_id": object_id, "rule": f"missing_{field}"})
        if obj.get("object_id") in duplicate_ids:
            violations.append({"object_id": object_id, "rule": "duplicate_object_id"})

    for field, paths in mask_paths.items():
        duplicates = {value for value, count in Counter(paths).items() if count > 1}
        for path in sorted(duplicates):
            violations.append({"rule": "instance_mask_path_reused", "field": field, "path": path})

    result = {"raster_object_count": len(objects), "violation_count": len(violations), "violations": violations}
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if not violations else 2


if __name__ == "__main__":
    raise SystemExit(main())
