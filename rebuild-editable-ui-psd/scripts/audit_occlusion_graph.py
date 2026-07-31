#!/usr/bin/env python3
"""Validate that overlapping components have complete, acyclic z-order evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def overlaps(a: list[float], b: list[float]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("graph", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    graph = json.loads(args.graph.read_text(encoding="utf-8"))
    layers = {item["id"]: item for item in manifest.get("layers", []) if item.get("bounds") and item.get("kind") != "group"}
    relations = graph.get("relations", graph if isinstance(graph, list) else [])
    relation_pairs: set[frozenset[str]] = set()
    adjacency: dict[str, set[str]] = {layer_id: set() for layer_id in layers}
    failures: list[str] = []
    for relation in relations:
        front, back = relation.get("front"), relation.get("back")
        if front not in layers or back not in layers or front == back:
            failures.append(f"invalid relation: {front!r} -> {back!r}")
            continue
        relation_pairs.add(frozenset((front, back)))
        if relation.get("status") != "unknown":
            if not relation.get("evidence"):
                failures.append(f"relation has no evidence: {front} -> {back}")
            adjacency[front].add(back)

    ids = list(layers)
    missing_pairs: list[list[str]] = []
    for index, left in enumerate(ids):
        for right in ids[index + 1 :]:
            if overlaps(layers[left]["bounds"], layers[right]["bounds"]) and frozenset((left, right)) not in relation_pairs:
                missing_pairs.append([left, right])
    if missing_pairs:
        failures.append(f"missing overlap relations: {missing_pairs}")

    state: dict[str, int] = {node: 0 for node in adjacency}
    cycle: list[str] = []
    stack: list[str] = []

    def visit(node: str) -> bool:
        state[node] = 1
        stack.append(node)
        for child in adjacency[node]:
            if state[child] == 1:
                cycle.extend(stack[stack.index(child) :] + [child])
                return True
            if state[child] == 0 and visit(child):
                return True
        stack.pop()
        state[node] = 2
        return False

    for node in adjacency:
        if state[node] == 0 and visit(node):
            failures.append(f"cycle detected: {' -> '.join(cycle)}")
            break

    report = {
        "passed": not failures,
        "layer_count": len(layers),
        "relation_count": len(relations),
        "missing_overlap_pairs": missing_pairs,
        "cycle": cycle,
        "failures": failures,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
