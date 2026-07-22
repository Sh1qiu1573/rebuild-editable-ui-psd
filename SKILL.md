---
name: rebuild-editable-ui-psd
description: Rebuild a flattened app or game UI screenshot into a hybrid editable Photoshop PSD on Windows using whole-scene regeneration, whole-component redraw for occluded raster artwork, two blocking human-review gates, semantic one-object-per-layer extraction, measured text and shape reconstruction, deterministic Photoshop assembly, and transparent PNG export for every non-reference PSD layer. Use when the user asks to split, reverse-engineer, reconstruct, or convert a PNG/JPG interface screenshot into an editable layered PSD and accepts a regenerated scene plus human approval instead of post-assembly AI verification.
---

# Rebuild Editable UI PSD v3.3

Build a hybrid PSD. Use one regenerated full-canvas scene smart object; rebuild ordinary UI as native text, shape, and grouped layers; retain irregular artwork as separate raster layers or smart objects.

This is a controlled reconstruction from visible pixels, not recovery of the original source file.

Read `skill-metadata.json` first. Copy its version and update timestamp into `task-audit.json` and the handoff report.

This is the Codex Desktop + Windows Photoshop v3.3 branch. Use `references/codex-photoshop-v3.md` and the bundled automation scripts for assembly and layer export.

## Load the operating references

Before acting, read:

- `references/prerequisites.md` for tool routing and Photoshop requirements.
- `references/implementation-plan.md` for the complete phase sequence and deliverables.
- `references/human-review-gates.md` before preparing either review package or recording approval.
- `references/clean-scene-reconstruction.md` before regenerating the scene.
- `references/object-extraction.md` before extracting or redrawing raster objects.
- `references/button-reconstruction.md` before reconstructing any button or frame.
- `references/text-reconstruction.md` before creating live text.
- `references/overlap-analysis.md` when overlaps require front/back analysis.
- `references/fidelity-quality-gates.md` before choosing native, vector, or raster representation.
- `references/codex-photoshop-v3.md` before Photoshop assembly.

## Establish the contract

Collect or infer:

- Source PNG/JPG and optional reference PSD.
- Output PSD path.
- Exact fonts and source assets when available.
- Whether reference-PSD assets may be reused.
- Whether local artwork may be sent to GPT Image or another network service.

Default to the hybrid scope. Keep the main subject, environment, fixed props, and integrated lighting inside `scene`. Extract independently selectable overlays such as bubbles, hearts, sparkles, icons, buttons, badges, and detached title decorations.

The source screenshot remains the authority for component identity, text, layout, and z-order. The scene appearance may drift because v3.3 defaults to whole-scene regeneration and direct replacement. Do not request separate scene-drift approval unless the user has explicitly required source-scene preservation.

Completion criterion: every visible item belongs to exactly one class: `scene`, `editable-text`, `editable-shape`, or `raster-object`; every non-scene item has one stable semantic object ID.

## Run the workflow

1. **Preflight.** Run `scripts/check_environment.py`, then `scripts/photoshop_bridge.py probe <work>/photoshop-probe --timeout 45`. Confirm permission before sending local artwork to a network service. Block native assembly when the Photoshop bridge fails.
2. **Inventory.** Measure the source, transcribe text, identify semantic object instances, classify every item, create draft visible masks, and record uncertain boundaries and overlaps.
3. **Human review 1: classification and masks.** Produce the classification overlay, object list, and draft masks. Pause for a human to correct missing items, extra items, over-masking, under-masking, merged/split instances, wrong classes, names, and z-order. Do not generate final scene or component assets until approval is recorded.
4. **Plan layers.** Create `layer-manifest.json` from the approved inventory. Run `scripts/audit_object_manifest.py` and resolve structural violations.
5. **Regenerate the scene.** Generate a complete clean scene without UI at the target dimensions. Use the accepted candidate as the entire scene; do not splice source pixels, local patches, or masked inpaint results into it.
6. **Rebuild components.** Extract complete visible objects normally. When any raster object has missing, damaged, or occluded pixels, redraw the entire component in one image-generation job, then segment/matte the redrawn result again. Do not combine its original visible fragment with generated pixels. Rebuild text and regular geometry as editable Photoshop layers where practical; reconstruct complete overlapped shapes before stacking.
7. **Human review 2: assembled review composite.** Assemble the regenerated scene and every rebuilt/extracted component at final coordinates into one source-size `review-composite.png`. Also provide an object contact sheet when individual alpha edges are hard to inspect. Pause for human corrections. Approval is the final visual gate; after approval, do not run AI visual review, isolated component regression, scene-only comparison, or reopened-PSD verification.
8. **Assemble, export layers, and hand off.** Build the PSD from the approved manifest and approved assets through the Photoshop bridge. Mark the hidden reference branch with `reference: true`, set `output.layer_png_dir` to `png`, and save `final.psd` under a new name. From the completed PSD, export every non-reference layer and layer group as a full-canvas transparent PNG named exactly `<layer name>.png` into `png/`. Export `preview.png` from the same approved composition and deliver the complete package. Perform only mechanical output checks needed to confirm that the PSD, preview, report, and expected layer PNGs were written; do not add a post-assembly AI review phase.

Do not move past either human-review gate until approval and requested corrections are recorded.

## Representation policy

Use this order for each component:

1. Native Photoshop text or shape when its construction is credible and editable.
2. Custom vector path for crisp nonstandard contours.
3. Whole-component raster smart object for irregular, textured, damaged, or occluded artwork.
4. Block and report when required evidence or authorized assets are unavailable.

Human approval of `review-composite.png` determines visual acceptance. Do not substitute a later AI score for that decision.

## Guardrails

- Preserve the original input files; never overwrite them.
- Never describe the output as the original recovered PSD.
- Never use masked inpainting or source/generated pixel splicing for the scene. Regenerate and replace the whole scene.
- Never patch only the hidden portion of an occluded raster component. Redraw the whole component, then re-segment and re-matte it.
- Do not restore original visible component pixels after a whole-component redraw.
- Never generate text inside the scene or component image model when it should be editable. Transcribe and typeset it.
- Use one image-generation job per occluded or damaged raster object. Do not redraw multiple unrelated objects together.
- Keep one semantic object instance per raster layer. Repeated instances receive separate IDs, assets, and masks.
- Use silhouette-following alpha with partial transparency where needed. Do not accept opaque rectangular cutouts.
- Classify and mask first, then require human corrections for over-masking, under-masking, missed objects, extra objects, merged/split objects, and wrong classes.
- Build every overlapped shape or component as a complete object and use verified z-order for overlap.
- Keep distant text clusters in separate TypeLayers.
- Mark `00_REFERENCE` with `reference: true`; all descendants inherit exclusion from per-layer PNG export. Do not exclude any other layer.
- Before assembly, make every non-reference PSD layer name a unique case-insensitive Windows-safe filename stem. Do not silently sanitize, suffix, or overwrite layer PNG filenames.
- Record font substitutions and generated/redrawn components in `limitations.md`.
- After the second human approval, do not initiate AI visual review or reopen-and-verify loops.
- If Photoshop, fonts, or assets are missing, finish the approved inventory and asset package, then report the exact blocker.

## Required deliverables

- `final.psd`: native layered document assembled from approved assets.
- `preview.png`: flattened output matching the approved review composite.
- `png/`: one full-canvas transparent PNG for every non-reference PSD layer and layer group, named exactly `<layer name>.png`.
- `review-composite.png`: full source-size composition used for the second human review.
- `object-contact-sheet.png`: optional review board for individual objects and alpha edges.
- `classification-review.png`: labeled overlay used for the first human review.
- `human-review.json`: both review rounds, corrections, approver notes, timestamps, and approval status.
- `clean_scene.png`: accepted full-scene regeneration used whole.
- `clean-scene-job.json`: prompt, input references, transforms, target dimensions, candidates, and selected scene.
- `layer-manifest.json`: one record for every visible component and any hidden reference layers.
- `objects/`: one transparent asset per raster-object instance.
- `masks/`: approved visible and final silhouette masks keyed by object ID.
- `gpt-image-log.json`: one record for the scene and each whole-component redraw.
- `button-measurements.json`, `text-measurements.json`, and `occlusion-graph.json` where applicable.
- `limitations.md`: generated areas, whole-component redraws, font substitutions, approximations, and blocked items.
- `task-audit.json`: skill version/timestamp, inputs, selected routes, human approvals, and exclusions.
- `photoshop-report.json`: Photoshop bridge execution and output-write status; it is not an AI visual-acceptance report.
