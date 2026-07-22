# Codex Desktop + Photoshop v3.4 execution contract

## 1. Compatibility boundary

Use this route only in Codex Desktop on Windows with Adobe Photoshop registered as `Photoshop.Application`. Use Photoshop COM/ExtendScript for deterministic construction. Computer Use may inspect or recover the visible window but must not be the primary assembly method.

Every script owns only documents it creates. It must never save, close, flatten, rename, or overwrite a document that was open before the script started.

Use RGB/8. Block unsupported color modes, depths, or linked-asset jobs rather than silently degrading them.

## 2. Fixed sequence

1. Run `python scripts/check_environment.py --json`.
2. Run `python scripts/photoshop_bridge.py probe <work>/photoshop-probe --timeout 45`.
3. Complete human review 1.
4. Produce the approved manifest, whole scene, raster assets, text, shapes, and overlap order.
5. Apply `psd-layer-structure.md`: validate semantic prefixes, independent button groups, button content containment, and explicit unique sibling `z` from back to front.
6. Build and obtain human approval for `review-composite.png`.
7. Freeze the approved manifest and asset hashes.
8. Write one final Photoshop job using exactly those approved versions.
9. Run `python scripts/photoshop_bridge.py run <final-job.json> --keep-jsx <work>/final-job.jsx --timeout 120`.
10. Export every non-reference layer and layer group from the completed PSD to `png/<layer name>.png` with full-canvas transparency.
11. Confirm mechanically that `final.psd`, `preview.png`, `photoshop-report.json`, and every reported layer PNG were written and are non-empty.
12. Hand off without a separate AI reopen-and-verify phase.

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
    "layer_png_dir": "png",
    "report": "photoshop-report.json"
  },
  "layers": [
    {"id": "reference", "name": "00_REFERENCE", "kind": "group", "z": 0, "visible": false, "reference": true},
    {"id": "scene", "name": "Bg_MainScene", "kind": "group", "z": 0},
    {
      "id": "clean_scene",
      "name": "Bg_CleanScene",
      "kind": "scene",
      "parent": "scene",
      "z": 10,
      "source_asset": "clean_scene.png",
      "bounds": [0, 0, 1080, 2340]
    },
    {"id": "panel_header", "name": "Panel_Header", "kind": "group", "z": 100},
    {"id": "button_start", "name": "Btn_Start", "kind": "group", "z": 200},
    {"id": "button_start_bg", "name": "Bg_Start", "kind": "shape", "parent": "button_start", "z": 0, "bounds": [360, 1900, 720, 2020]},
    {"id": "button_start_text", "name": "@StartText", "kind": "text", "parent": "button_start", "z": 20, "bounds": [450, 1930, 630, 1990], "text": "Start"}
  ]
}
```

Supported kinds are `group`, `shape`, `text`, `smart-object`, `raster-object`, and `scene`. Raster and scene layers require approved `source_asset` paths. Reject duplicate IDs, missing parents/assets, unsupported kinds, or attempts to overwrite without explicit authorization.

Treat `z` as scoped to siblings. Require an explicit unique numeric `z` for every non-reference layer and group. Lower `z` is farther back and appears lower in the Photoshop Layers panel; backgrounds must be lower than foreground siblings. A group is an atomic stack; children cannot interleave with the group's siblings.

Before compilation, the bridge also enforces the semantic naming and button structure contract in `psd-layer-structure.md`, including top-level placement for every button group. `00_REFERENCE` and descendants are exempt. Use `text_fallback: true` only for an approved raster/smart-object text fallback whose layer name still starts with `@`.

## 4. Layer PNG export contract

- Require `output.layer_png_dir` and resolve it to a folder named exactly `png` beside the job outputs.
- Mark the hidden reference group or reference image layer with `reference: true`. Exclude that layer and all descendants from export; export every other manifest layer, including groups.
- Use the PSD layer name verbatim as the PNG filename stem. Require unique case-insensitive Windows-safe names before assembly; reject invalid characters, reserved device names, trailing spaces/dots, or filename collisions.
- Preserve `@` in text filenames; for example, `@TitleText` exports as `@TitleText.png`.
- Export from the completed, reopened PSD. Use a separate transparent RGB/8 document at the exact PSD dimensions and resolution for each layer. Preserve canvas coordinates; do not trim.
- Export an individual layer with forced visibility. Export a group as a composite of its children while retaining child visibility, masks, opacity, and effects.
- Record `id`, `name`, `kind`, and output path for every PNG in `photoshop-report.json`. Treat a missing, empty, duplicated, or unexpected export as `E_OUTPUT`.

## 5. Approved-input rule

The final job must use the manifest and asset hashes recorded in `human-review.json` for review 2. Do not tune or replace a visual component during assembly.

If assembly exposes a required visual change:

1. Stop assembly.
2. Revise the affected asset or transform.
3. Regenerate `review-composite.png`.
4. Obtain human review 2 approval again.
5. Build a new final job from the newly approved hashes.

## 6. Text and shape preparation

Font search, measurement, and candidate preparation occur before review 2. The review composite must show the exact text/shape representation intended for the PSD.

When native construction is unavailable or unacceptable to the reviewer, use the approved raster smart-object fallback. Do not add a post-approval component-regression loop.

## 7. Status handling

| Code | Meaning | Action |
|---|---|---|
| `OK` | Assembly job completed and outputs were written | Hand off after mechanical checks |
| `E_INPUT` | Invalid job, missing asset, duplicate ID, or overwrite refusal | Fix input; do not retry unchanged |
| `E_PHOTOSHOP_UNAVAILABLE` | Photoshop unavailable | Retry once after confirming Photoshop is running, then block |
| `E_PHOTOSHOP_TIMEOUT` | Photoshop unresponsive | Retry once after recovery, then block |
| `E_PHOTOSHOP_SCRIPT` | Deterministic script/job failed | Fix the job; do not blind-retry |
| `E_OUTPUT` | PSD, preview, report, or an expected layer PNG is missing | Inspect output paths and permissions |
| `E_PREEXISTING_DOCUMENT_CLOSED` | A pre-existing document disappeared | Stop automation and investigate |

An implementation may internally save, close, or reopen its own document to complete file writing, but this is not a human- or AI-acceptance stage. Do not inspect that state with AI after review 2 approval.

## 8. Completion gate

Completion requires:

- Passing environment probe.
- Both human reviews approved.
- Approved asset/manifest hashes supplied to the final job.
- Prefix-compliant names, independent button groups, button content containment, and valid background-to-foreground `z` order accepted by bridge validation.
- `final.psd`, `preview.png`, `photoshop-report.json`, and every expected file in `png/` present and non-empty.
- No post-review-2 AI visual review or separate reopen-and-verify phase.
