# Codex Desktop + Photoshop v3.2 execution contract

## 1. Compatibility boundary

Use this route only in Codex Desktop on Windows with Adobe Photoshop registered as `Photoshop.Application`. Use Photoshop COM/ExtendScript for deterministic construction. Computer Use may inspect or recover the visible window but must not be the primary assembly method.

Every script owns only documents it creates. It must never save, close, flatten, rename, or overwrite a document that was open before the script started.

Use RGB/8. Block unsupported color modes, depths, or linked-asset jobs rather than silently degrading them.

## 2. Fixed sequence

1. Run `python scripts/check_environment.py --json`.
2. Run `python scripts/photoshop_bridge.py probe <work>/photoshop-probe --timeout 45`.
3. Complete human review 1.
4. Produce the approved manifest, whole scene, raster assets, text, shapes, and overlap order.
5. Build and obtain human approval for `review-composite.png`.
6. Freeze the approved manifest and asset hashes.
7. Write one final Photoshop job using exactly those approved versions.
8. Run `python scripts/photoshop_bridge.py run <final-job.json> --keep-jsx <work>/final-job.jsx --timeout 120`.
9. Confirm mechanically that `final.psd`, `preview.png`, and `photoshop-report.json` were written and are non-empty.
10. Hand off without a separate AI reopen-and-verify phase.

Run runner self-tests only when the runner code itself changes. They are development tests, not task-level visual approval.

## 3. Photoshop job contract

Use a JSON object with `document`, `output`, and `layers`:

```json
{
  "document": {
    "width": 1080,
    "height": 2340,
    "resolution": 72,
    "depth": 8,
    "name": "final"
  },
  "output": {
    "psd": "final.psd",
    "preview": "preview.png",
    "report": "photoshop-report.json"
  },
  "layers": [
    {"id": "scene", "name": "10_SCENE", "kind": "group", "z": 10},
    {
      "id": "clean_scene",
      "name": "clean_scene",
      "kind": "scene",
      "parent": "scene",
      "z": 10,
      "source_asset": "clean_scene.png",
      "bounds": [0, 0, 1080, 2340]
    },
    {"id": "ui", "name": "20_UI", "kind": "group", "z": 100}
  ]
}
```

Supported kinds are `group`, `shape`, `text`, `smart-object`, `raster-object`, and `scene`. Raster and scene layers require approved `source_asset` paths. Reject duplicate IDs, missing parents/assets, unsupported kinds, or attempts to overwrite without explicit authorization.

Treat `z` as scoped to siblings. A group is an atomic stack; children cannot interleave with the group's siblings.

## 4. Approved-input rule

The final job must use the manifest and asset hashes recorded in `human-review.json` for review 2. Do not tune or replace a visual component during assembly.

If assembly exposes a required visual change:

1. Stop assembly.
2. Revise the affected asset or transform.
3. Regenerate `review-composite.png`.
4. Obtain human review 2 approval again.
5. Build a new final job from the newly approved hashes.

## 5. Text and shape preparation

Font search, measurement, and candidate preparation occur before review 2. The review composite must show the exact text/shape representation intended for the PSD.

When native construction is unavailable or unacceptable to the reviewer, use the approved raster smart-object fallback. Do not add a post-approval component-regression loop.

## 6. Status handling

| Code | Meaning | Action |
|---|---|---|
| `OK` | Assembly job completed and outputs were written | Hand off after mechanical checks |
| `E_INPUT` | Invalid job, missing asset, duplicate ID, or overwrite refusal | Fix input; do not retry unchanged |
| `E_PHOTOSHOP_UNAVAILABLE` | Photoshop unavailable | Retry once after confirming Photoshop is running, then block |
| `E_PHOTOSHOP_TIMEOUT` | Photoshop unresponsive | Retry once after recovery, then block |
| `E_PHOTOSHOP_SCRIPT` | Deterministic script/job failed | Fix the job; do not blind-retry |
| `E_OUTPUT` | PSD, preview, or report is missing | Inspect output paths and permissions |
| `E_PREEXISTING_DOCUMENT_CLOSED` | A pre-existing document disappeared | Stop automation and investigate |

An implementation may internally save, close, or reopen its own document to complete file writing, but this is not a human- or AI-acceptance stage. Do not inspect that state with AI after review 2 approval.

## 7. Completion gate

Completion requires:

- Passing environment probe.
- Both human reviews approved.
- Approved asset/manifest hashes supplied to the final job.
- `final.psd`, `preview.png`, and `photoshop-report.json` present and non-empty.
- No post-review-2 AI visual review or separate reopen-and-verify phase.
