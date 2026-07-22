# Hybrid PSD v3.4 implementation plan

## Contents

1. Definition of done
2. Output structure
3. Phase 0 - intake and preflight
4. Phase 1 - draft inventory and classification
5. Phase 2 - human review of classification and masks
6. Phase 3 - approved manifest and full-scene regeneration
7. Phase 4 - component extraction and whole-component redraw
8. Phase 5 - editable UI reconstruction
9. Phase 6 - assembled human review
10. Phase 7 - Photoshop assembly and handoff
11. Failure handling

## 1. Definition of done

The result is complete only when:

- The PSD canvas and pixel dimensions equal the source.
- The scene is a full-canvas generated smart object with no baked-in UI and no source/generated pixel splicing.
- Every ordinary label, number, and paragraph is editable text or a documented raster fallback.
- Every regular panel, separator, progress bar, and suitable button is editable geometry or a documented exception.
- Every independently selectable irregular object is a separate raster layer or embedded smart object.
- Every damaged, incomplete, or occluded raster object has been redrawn as a whole component and re-segmented; no original/generated fragment composite is used.
- Every raster asset follows its silhouette and contains one semantic object instance.
- Human review 1 has approved classification, object instances, masks, names, and z-order after correcting over-masking, under-masking, missing items, extra items, and class errors.
- Every non-reference layer and group follows `psd-layer-structure.md`; every button is an independent top-level group containing its body and any decoration, icon, and text layers.
- Every non-reference sibling has an explicit unique numeric `z`; backgrounds are lower than foreground interaction elements in the same scope.
- Human review 2 has approved one full source-size composition containing the regenerated scene and all final components at final coordinates.
- The final PSD is assembled only from the assets and manifest approved in review 2.
- Every non-reference PSD layer and layer group is exported from the completed PSD to `png/<layer name>.png` on a transparent source-size canvas.
- The reference branch and only the reference branch is excluded from layer PNG export.
- No AI visual validation or reopen-and-verify phase runs after review 2 approval.
- Every approximation, redraw, and font substitution is recorded in `limitations.md`.

## 2. Output structure

Use this baseline hierarchy. It is shown in Photoshop panel order from top to bottom:

```text
Btn_PrimaryAction
  @PrimaryActionText
  Icon_PrimaryAction [optional]
  Img_PrimaryActionDecoration [optional]
  Bg_PrimaryAction
Popup_Dialog
  @DialogText
  Img_DialogArt
  Bg_DialogFrame
Panel_Header
  @TitleText
  Icon_Status
  Bg_Header
Bg_MainScene
  Bg_CleanScene [embedded smart object]
00_REFERENCE [hidden, optional]
  source_reference
```

Do not prepend numeric ordering codes to Unity-facing names. Use explicit `z` for order and the semantic prefixes in `psd-layer-structure.md`. `00_REFERENCE` and its descendants are the only naming exception.

## 3. Phase 0 - intake and preflight

Actions:

1. Copy inputs to the working directory without modifying originals.
2. Record paths, hashes, dimensions, color mode, profile, output path, font availability, reference-asset reuse permission, and network-upload permission.
3. Record the source screenshot as authority for identity, text, geometry, layout, and z-order.
4. Record v3.4 scene policy: whole-scene regeneration and direct replacement are the default. Source-scene pixel preservation is not expected.
5. Run `scripts/check_environment.py`.
6. Run `scripts/photoshop_bridge.py probe <work>/photoshop-probe --timeout 45` and confirm the native assembly route is available.
7. Create `task-audit.json` from `skill-metadata.json`.

Completion criterion: inputs and output are accessible, permissions are recorded, and the Photoshop assembly route is available or precisely blocked.

## 4. Phase 1 - draft inventory and classification

Inspect the source at original resolution. Divide the screen into semantic regions, then identify each semantic instance.

For every item record:

- Stable ID, prefix-compliant name, region, parent group, bounds, and explicit sibling-scoped numeric `z`.
- Exact visible text and token/character boxes.
- Proposed class: `scene`, `editable-text`, `editable-shape`, or `raster-object`.
- Draft visible mask and draft complete/amodal mask when overlap exists.
- Whether the object is complete, damaged, or occluded.
- Evidence for front/back relations.
- Confidence and questions for human review.

Repeated objects receive separate IDs even when similar. A raster item may not contain multiple independently selectable objects.

Produce:

- `classification-review.png`: source screenshot with numbered outlines, IDs, classes, and z-order indicators.
- Draft `layer-manifest.json`.
- Draft masks in `masks/draft/`.
- `classification-review.json`: item list, confidence, unresolved questions, and proposed corrections.

Completion criterion: every visible item appears once in the draft inventory and every uncertain boundary or class is explicitly marked.

## 5. Phase 2 - human review of classification and masks

Read `human-review-gates.md`. Present the classification overlay, item list, and mask previews to a human reviewer.

Require the reviewer to check:

- Missing and extra objects.
- Wrong class assignments.
- Objects that should be merged or split.
- Over-masking and under-masking.
- Neighbor contamination and missing holes/thin parts.
- Incorrect prefixes, button membership, parent groups, bounds, or bottom-to-top z-order.
- Incorrect text transcription or text-unit grouping.

Apply every requested correction and regenerate the review package. Repeat until approval is recorded in `human-review.json` as `classification_and_masks: approved`.

Do not generate final scene or component assets before this approval.

Completion criterion: the human-approved inventory and masks uniquely determine every PSD layer and extraction target.

## 6. Phase 3 - approved manifest and full-scene regeneration

### Manifest

Promote the approved inventory to the production `layer-manifest.json`. Run `scripts/audit_object_manifest.py` and resolve structural violations. Record the review version and approval record used.

### Scene

Read `clean-scene-reconstruction.md`.

1. Create a full-canvas generation input that communicates scene style and the UI-free requirement.
2. Generate a complete replacement scene at the target aspect ratio.
3. Normalize the selected candidate once to exact target dimensions and record crop, scale, padding, and resampling.
4. Use the selected candidate as `clean_scene.png` in full.
5. Never restore source pixels, mask-patch UI regions, or combine multiple scene candidates.
6. Record all candidates and the selected candidate in `clean-scene-job.json` and `gpt-image-log.json`.

Scene-drift approval is implicit in selecting this v3.4 skill. Ask again only when the user separately requires original scene preservation.

Completion criterion: one target-size, UI-free scene asset is selected for use as the entire scene.

## 7. Phase 4 - component extraction and whole-component redraw

Read `object-extraction.md`.

For a fully visible raster object:

1. Segment it from the source using the approved mask.
2. Preserve partial alpha, holes, thin parts, and soft edges.
3. Trim to minimal alpha bounds plus 0-2 px safety padding.

For a damaged, incomplete, or occluded raster object:

1. Create one context image containing one target object.
2. Generate a complete replacement of the entire component in one dedicated image-generation job.
3. Do not ask for only the hidden continuation.
4. Do not composite original visible pixels over the generated component.
5. Re-segment and re-matte the generated complete component from scratch.
6. Trim it to tight alpha bounds and record the redraw in `gpt-image-log.json` and `limitations.md`.

Run structural mask and bounds audits before review 2, but treat them as preparation rather than visual acceptance.

Completion criterion: every raster object has one complete transparent asset and no object contains a stitched original/generated boundary.

## 8. Phase 5 - editable UI reconstruction

### Text

1. Split spatially distant clusters into separate text units.
2. Transcribe exact wording and punctuation.
3. Measure fill, weight, size, tracking, leading, rotation, and outline.
4. Use real local font files and Photoshop font names where available.
5. Create live TypeLayers when credible; otherwise use a documented raster fallback plus optional hidden transcription.

### Shapes and buttons

1. Reconstruct complete/amodal bodies before stacking.
2. Use a native rounded rectangle only after strict shape-family analysis permits it.
3. Use a custom vector path for crisp irregular contours.
4. Use a whole-component raster smart object for painterly, distressed, damaged, or occluded frames that should be redrawn as one asset.
5. Keep labels and icons separate from button bodies.
6. Create one independent top-level `Btn_`/`Button_` group per button, outside panels and popups. Keep its `Bg_`/`BG_` body, `Img_`/`Image_` decoration, `Icon_` artwork, and `@` label inside that group.
7. Record button measurements and unknown properties.

### Overlap

Use `occlusion-graph.json` for front/back order. Do not cut a back object to its visible fragment.

Completion criterion: every editable and raster component is ready to be placed in the full review composite.

## 9. Phase 6 - assembled human review

Assemble a single full-size `review-composite.png` using:

- The selected full-scene regeneration.
- Every extracted or redrawn raster component.
- Every reconstructed text and shape component.
- Final coordinates, rotation, opacity, effects, and z-order.

Also produce `object-contact-sheet.png` when transparent edges or small components are difficult to inspect in context.

Present the composite and contact sheet to a human reviewer. Require checks for:

- Missing, duplicated, or misclassified items.
- Over/under-masked edges, halos, rectangular alpha, and neighbor contamination.
- Incorrect redraws, scale, rotation, position, and z-order.
- Incorrect wording, text grouping, fonts, or button construction.
- Unwanted UI embedded in the regenerated scene.

Apply corrections and regenerate the full composite until `human-review.json` records `assembled_composite: approved` and identifies the exact approved asset/manifest versions.

This approval is the final visual acceptance gate. After approval:

- Do not run AI visual inspection.
- Do not run isolated component regression.
- Do not compare the result against the source with an AI decision.
- Do not reopen the final PSD for a verification phase.
- Do not change approved visual assets unless the human reviewer reopens review 2.

Completion criterion: one human-approved full composition is frozen as the authority for assembly.

## 10. Phase 7 - Photoshop assembly and handoff

1. Create a source-size RGB/8 Photoshop document.
2. Place the approved `clean_scene.png` as a full-canvas embedded smart object named `Bg_CleanScene` inside `Bg_MainScene`.
3. Create prefix-compliant semantic groups; do not use numeric ordering prefixes outside `00_REFERENCE`.
4. Place every approved raster object independently using approved bounds.
5. Create approved text and shapes from the manifest.
6. Apply approved clipping and effects. Assign every non-reference sibling an explicit unique numeric `z`, with backgrounds lower than foreground panels, popups, buttons, images, icons, and text.
7. Mark the hidden `00_REFERENCE` group with `reference: true`; descendants inherit reference exclusion.
8. Ensure every non-reference layer and layer-group name follows `psd-layer-structure.md` and is a unique case-insensitive Windows-safe filename stem. Ensure every button is an independent top-level group with a background body and only its own prefixed content.
9. Set `output.layer_png_dir` to `png`, run the Photoshop assembly job, and save `final.psd` under a new name.
10. Reopen the completed PSD through the bridge and export every non-reference layer and layer group to `png/<layer name>.png`. Preserve the full PSD canvas, original layer coordinates, alpha, masks, and layer effects; export groups as their child-layer composite.
11. Export `preview.png` from the same approved composition or approved assembly job.
12. Confirm mechanically that the PSD, preview, report, and every expected layer PNG exist and are non-empty. Require the reported PNG IDs to equal the validated non-reference manifest IDs. Do not turn this into visual AI verification.
13. Deliver the package and `limitations.md`.

The final preview must derive from the exact asset/manifest versions approved in review 2. If assembly requires a visual change, return to review 2 rather than silently modifying the approved result.

Completion criterion: required outputs exist, `png/` contains the reported export for every non-reference layer and group, the approval record matches the assembled asset versions, and no post-approval AI review was performed.

## 11. Failure handling

- **No Photoshop:** finish both review packages and approved assets, then report native assembly as blocked.
- **Network upload not allowed:** use an approved local image-generation/redraw route or report scene/component generation as blocked.
- **Classification review finds errors:** correct the inventory and masks, regenerate review 1, and request approval again.
- **Whole-scene candidate contains UI:** regenerate the entire scene; do not patch the UI area.
- **Whole scene has unacceptable drift:** regenerate the entire scene or switch skills/workflows if the user now requires source preservation.
- **Occluded component redraw changes visible design:** regenerate the whole component with stronger references; do not restore the old visible fragment.
- **Component redraw contains multiple objects:** tighten the context and regenerate the whole target alone.
- **Mask over-cuts or under-cuts:** correct it and include the revised asset in review 2.
- **Review 2 finds an error:** revise assets or layout and repeat review 2.
- **A post-approval change is required:** invalidate the previous review-2 approval and obtain a new approval.
- **Font missing:** record a substitute or raster fallback according to the human-approved choice.
- **Assembly output is missing or empty:** fix the deterministic job and rerun; do not add an AI visual-review phase.
- **A layer PNG name is invalid or duplicated:** rename the manifest/PSD layer semantically before assembly; never sanitize or suffix the exported filename silently.
- **A layer or group violates its role prefix:** rename it in the manifest and regenerate the review package when the visible composition or reviewer-facing structure changes.
- **A button is not an independent group or contains unrelated UI:** restructure the manifest before assembly; keep the body, decoration, icon, and text inside the button group.
- **A sibling `z` is missing/duplicated or a background is above foreground:** correct the explicit `z` values and repeat review 2 if the visible stack changes.
- **A layer PNG is missing or empty:** treat assembly as incomplete, fix the deterministic export, and rerun without adding AI visual review.
