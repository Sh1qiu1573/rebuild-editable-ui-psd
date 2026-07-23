# Whole-scene regeneration and replacement

## Contract

V3.5 uses `full-scene-regeneration` by default. Generate one complete UI-free scene and use it as the entire scene smart object.

Do not:

- Use masked inpainting as the default scene route.
- Restore source pixels outside former UI regions.
- Hard-splice generated pixels through UI masks.
- Mosaic multiple scene candidates.
- Hide generation seams beneath reconstructed UI.

Selecting this skill accepts scene drift unless the user separately states that visible scene pixels must remain unchanged. If source preservation becomes a requirement, stop and use a source-preserving workflow instead of silently reverting to masked patching.

## Procedure

1. Use the source screenshot as a style, layout, subject, and camera reference.
2. Describe the complete scene without UI, text, buttons, icons, overlays, or interface lighting.
3. Generate complete full-frame candidates.
4. Inspect candidates before review 2 for obvious unwanted UI, duplicated subjects, missing major scene elements, or incompatible camera framing.
5. Select one candidate and normalize it once to the exact target canvas. Record scale, crop, padding, resampling, and color-profile handling.
6. Save the selected full image as `clean_scene.png`.
7. Use `clean_scene.png` whole. Do not composite source pixels into it.
8. Include this exact scene in `review-composite.png` for final human approval.

## Records

Create `clean-scene-job.json` containing:

- `mode: full-scene-regeneration`
- Source references and prompt.
- Raw candidate paths and dimensions.
- Selected candidate.
- Normalization transform.
- Target dimensions and color profile.
- Review-2 revision and approval status.

Add the same generation event to `gpt-image-log.json`.

## Acceptance

Scene acceptance occurs in human review 2 as part of the complete composition. Do not run an AI scene-only acceptance gate after approval.

Before review 2, deterministic checks may confirm dimensions, file readability, and absence of accidental alpha. These checks do not replace human approval.

## Failure handling

- **UI remains in the scene:** regenerate the whole scene.
- **Candidate dimensions differ:** normalize the complete candidate once and record the transform; do not treat it as a local registration.
- **Subject or environment is unacceptable:** regenerate the whole scene with better references.
- **The user now requires original scene preservation:** stop and switch to a source-preserving workflow; do not introduce masked splicing into v3.5.
- **Review 2 rejects the scene:** replace it with another whole-scene candidate and repeat the complete review composite.
