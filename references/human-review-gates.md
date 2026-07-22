# Human review gates

Human review is blocking in v3.3. Record both review rounds in `human-review.json`. Do not infer approval from silence, a previous task, or an AI assessment.

## Review 1: classification and masks

Prepare:

- `classification-review.png` with numbered object outlines, IDs, proposed classes, and z-order arrows.
- `classification-review.json` with bounds, class, confidence, questions, and proposed text units.
- Draft visible/complete masks shown as colored overlays at 100% and 200% crops.

Ask the reviewer to correct:

- Missing or extra objects.
- Wrong `scene`, `editable-text`, `editable-shape`, or `raster-object` classification.
- Objects that need splitting or merging.
- Over-masking, under-masking, missing holes, clipped thin parts, or neighboring pixels.
- Wrong text transcription or text-unit grouping.
- Wrong bounds, names, groups, and z-order.

After corrections, issue a new review revision. Approval must name the approved revision and set `classification_and_masks.status` to `approved`.

## Review 2: assembled composition

Prepare:

- `review-composite.png` at the source canvas size.
- `object-contact-sheet.png` when individual transparent objects need larger inspection.
- A short change list identifying whole-scene and whole-component generations.

The composite must contain the exact scene, objects, text, shapes, transforms, effects, and layer order intended for the PSD.

Ask the reviewer to check:

- Completeness, identity, wording, scale, position, rotation, opacity, and z-order.
- Scene UI residue and unwanted generated content.
- Over/under-masking, halos, hard rectangles, missing holes, and clipped effects.
- Whole-component redraw fidelity and consistency.
- Text, shape, and button construction.

After corrections, freeze the approved manifest and asset hashes. Approval must set `assembled_composite.status` to `approved` and record the approved `review-composite.png` hash.

## Approval record

Use this baseline schema:

```json
{
  "classification_and_masks": {
    "status": "approved",
    "revision": 3,
    "review_asset": "classification-review.png",
    "corrections": [],
    "reviewer_note": "",
    "approved_at": ""
  },
  "assembled_composite": {
    "status": "approved",
    "revision": 2,
    "review_asset": "review-composite.png",
    "review_asset_sha256": "",
    "manifest_sha256": "",
    "asset_hashes": {},
    "corrections": [],
    "reviewer_note": "",
    "approved_at": ""
  }
}
```

## After review 2 approval

- Treat the human-approved composite as the final visual authority.
- Do not run AI visual acceptance, scene-only AI review, component regression, or source-difference adjudication.
- Permit only deterministic assembly and mechanical file-existence checks.
- If an approved visual asset or transform changes, invalidate approval and repeat review 2.
