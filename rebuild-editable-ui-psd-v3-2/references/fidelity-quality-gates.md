# V3.2 representation and human quality gates

## 1. Acceptance authority

V3.2 uses two blocking human-review gates:

1. Human approval of classification, instances, masks, text units, and z-order.
2. Human approval of one full-size composite containing the exact scene and components intended for the PSD.

The second approval is the final visual authority. After it passes, do not run AI visual inspection, component regression, scene-only AI review, difference adjudication, or a reopen-and-verify phase.

## 2. Representation policy

Choose independently for each component:

1. Native Photoshop text or shape for credible editable construction.
2. Custom vector path for crisp nonstandard contours.
3. Whole-component raster smart object for irregular, textured, distressed, damaged, or occluded artwork.
4. Block when required evidence or authorized assets are unavailable.

Do not simplify a component into the wrong shape merely to keep it editable. Human review 2 determines whether the selected representation is acceptable.

## 3. Shape-family routing

Classify buttons and frames as:

- `regular-rounded-rectangle`
- `custom-vector-frame`
- `whole-component-raster-frame`

Use `scripts/analyze_button.py` as measurement support before review 2. Permit a native rounded rectangle only when its strict contour fit is credible. Decorative notches, unequal radii, hand-drawn contours, distressed frames, or damaged/occluded raster artwork should use a custom path or whole-component redraw.

Build complete/amodal geometry before overlap. Never carve a back object to match only its visible fragment.

## 4. Typography

Use exact wording and separate spatially distant text units. Measure weight, glyph thickness, outline, tracking, size, rotation, and color using available scripts and font files.

Create live TypeLayers when credible. When exact typography is unavailable, use a documented raster fallback or human-approved substitution. Do not rely on an AI post-assembly regression score.

## 5. Scene policy

Generate and replace the entire scene. Do not use local masked inpaint, source-pixel restoration, or source/generated mosaics. Include the exact selected full scene in review 2.

## 6. Raster-object policy

- Fully visible objects may be extracted from source with approved masks.
- Damaged, incomplete, or occluded objects must be redrawn as complete components.
- Never splice original visible pixels with a generated hidden continuation.
- Re-segment and re-matte every whole-component redraw.
- Preserve silhouette-following alpha, holes, and partial transparency.

Use structural audits before review 2 to catch reused masks, rectangular alpha, missing assets, invalid bounds, or multiple object instances. Human review decides whether the visual result is acceptable.

## 7. Human review 1 gate

Block production asset generation until a human has corrected and approved:

- Missing/extra items.
- Wrong classes.
- Split/merge errors.
- Over/under-masking.
- Text and z-order errors.

## 8. Human review 2 gate

Create `review-composite.png` at source dimensions and optionally `object-contact-sheet.png`. The reviewer checks completeness, silhouette quality, redraw fidelity, typography, button construction, position, rotation, effects, and z-order.

Freeze asset and manifest hashes on approval. Any later visual change invalidates approval and returns the task to review 2.

## 9. Permitted post-approval checks

After review 2, permit only mechanical checks such as:

- Required file exists and is non-empty.
- Output path is writable.
- Assembly job completed without an execution error.
- Approved manifest and asset hashes are the versions supplied to assembly.

These checks must not become AI visual review. Do not reopen the final PSD for a separate verification phase.
