---
name: rebuild-editable-ui-psd
description: Rebuild a flattened app or game UI screenshot into a hybrid editable Photoshop PSD on Windows using Codex Desktop's signed-in GPT Image 2 entitlement, bundled rembg extraction, whole-scene regeneration, whole-component redraw, two blocking human-review gates, semantic layers, editable ordinary text, raster title artwork, deterministic Photoshop assembly, and transparent layer exports. Automatically use when the user says “把图片拆解为PSD”, “图片拆解成PSD”, “图片转可编辑PSD”, “把截图拆成PSD图层”, “截图转分层PSD”, “拆图做PSD”, “UI截图还原成PSD”, or equivalent requests to split, reverse-engineer, reconstruct, or convert a PNG/JPG UI screenshot into an editable layered PSD.
---

# Rebuild Editable UI PSD v3.6

Build a hybrid PSD. Use one regenerated full-canvas scene smart object; rebuild ordinary UI as native text, shape, and grouped layers; treat decorative or artistic headline text as raster artwork; retain other irregular artwork as separate raster layers or smart objects.

This is a controlled reconstruction from visible pixels, not recovery of the original source file.

Read `skill-metadata.json` first. Copy its version and update timestamp into `task-audit.json` and the handoff report.

This is the Codex Desktop + Windows Photoshop v3.6 branch. Use `references/codex-photoshop-v3.md` and the bundled automation scripts for assembly and layer export.

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
- `references/psd-layer-structure.md` before naming layers, assigning groups, setting `z`, or writing the final Photoshop job.
- `references/codex-photoshop-v3.md` before Photoshop assembly.

## Establish the contract

Collect or infer:

- Source PNG/JPG and optional reference PSD.
- Output PSD path.
- Available fonts and source assets when useful; ordinary editable text only needs a broadly similar appearance.
- Whether reference-PSD assets may be reused.
- Whether the user has prohibited use of the signed-in Codex Desktop GPT Image 2 entitlement. Never use an external image API by default.

Default to the hybrid scope. Keep the main subject, environment, fixed props, and integrated lighting inside `scene`. Extract independently selectable overlays such as bubbles, hearts, sparkles, icons, buttons, badges, and detached title decorations.

The source screenshot remains the authority for component identity, wording, layout, and z-order. Ordinary editable text needs only broad visual similarity; preserve wording, grouping, position, scale, color family, and hierarchy without exhaustive font matching. Classify decorative or artistic headline lettering as raster artwork rather than editable text. The scene appearance may drift because v3.6 defaults to whole-scene regeneration and direct replacement. Do not request separate scene-drift approval unless the user has explicitly required source-scene preservation.

Completion criterion: every visible item belongs to exactly one class: `scene`, `editable-text`, `editable-shape`, or `raster-object`; every non-scene item has one stable semantic object ID.

## Run the workflow

1. **Preflight.** Run `scripts/install_rembg.py --ensure`, then `scripts/check_environment.py`; record the managed rembg deployment and run `scripts/photoshop_bridge.py probe <work>/photoshop-probe --timeout 45`. Use Codex Desktop's current signed-in account and GPT Image 2 allowance for scene/component generation without requesting API credentials. Ask permission only before using a third-party service or external API. Block native assembly when the Photoshop bridge fails.
2. **Inventory.** Measure the source, transcribe text, identify semantic object instances, classify every item, create draft visible masks, and record uncertain boundaries and overlaps.
3. **Human review 1: classification and masks.** Produce the classification overlay, object list, and draft masks. Pause for a human to correct missing items, extra items, over-masking, under-masking, merged/split instances, wrong classes, names, and z-order. Do not generate final scene or component assets until approval is recorded.
4. **Plan layers.** Create `layer-manifest.json` from the approved inventory. Apply `references/psd-layer-structure.md`: assign every non-reference layer or group a required semantic prefix, place each button in its own `Btn_`/`Button_` group, and assign explicit sibling-scoped `z` values from back to front. Run `scripts/audit_object_manifest.py` and resolve structural violations.
5. **Regenerate the scene.** Generate a complete clean scene without UI at the target dimensions. Use the accepted candidate as the entire scene; do not splice source pixels, local patches, or masked inpaint results into it.
6. **Rebuild components.** Extract complete visible objects with bundled rembg plus the approved masks. When any raster object has missing, damaged, or occluded pixels, redraw the entire component in one GPT Image 2 job through the signed-in Codex Desktop account, then run rembg and refine the matte again. Do not combine its original visible fragment with generated pixels. Rebuild ordinary text and regular geometry as editable Photoshop layers where practical; treat artistic title lettering as one or more raster artwork objects; reconstruct complete overlapped shapes before stacking.
7. **Human review 2: assembled review composite.** Assemble the regenerated scene and every rebuilt/extracted component at final coordinates into one source-size `review-composite.png`. Also provide an object contact sheet when individual alpha edges are hard to inspect. Pause for human corrections. Approval is the final visual gate; after approval, do not run AI visual review, isolated component regression, scene-only comparison, or reopened-PSD verification.
8. **Assemble, export layers, and hand off.** Build the PSD from the approved manifest and approved assets through the Photoshop bridge. Treat naming, button containment, explicit unique sibling `z`, and background-before-foreground validation as blocking. Mark the hidden reference branch with `reference: true`, set `output.layer_png_dir` to `png`, and save `final.psd` under a new name. From the completed PSD, export every non-reference layer and layer group as a full-canvas transparent PNG named exactly `<layer name>.png` into `png/`. Export `preview.png` from the same approved composition and deliver the complete package. Perform only mechanical output checks needed to confirm that the PSD, preview, report, and expected layer PNGs were written; do not add a post-assembly AI review phase.

Do not move past either human-review gate until approval and requested corrections are recorded.

## Bundled background removal

Use the skill-managed rembg installation inside the existing segmentation and matting actions; do not add, remove, reorder, or bypass any workflow phase or review gate.

- Install rembg during skill installation with `scripts/install_rembg.py --ensure`. The first preflight reruns this idempotently so copied or upgraded skill folders self-heal.
- Invoke `scripts/rembg_cutout.py` by default for every raster-object background-removal pass, then apply the approved mask, partial-alpha, silhouette, audit, and human-review rules unchanged.
- If installation or invocation still fails, block the affected extraction step and report the exact error; do not silently switch to an unrelated background-removal service.

## Representation policy

Use this order for each component:

1. Native Photoshop text for ordinary copy and labels when it is readable and broadly similar, or a native shape when its construction is credible.
2. Custom vector path for crisp nonstandard contours.
3. Whole-component raster smart object for artistic headline lettering, irregular, textured, damaged, or occluded artwork.
4. Block and report when required evidence or authorized assets are unavailable.

Human approval of `review-composite.png` determines visual acceptance. Do not substitute a later AI score for that decision.

## Guardrails

- Preserve the original input files; never overwrite them.
- Never describe the output as the original recovered PSD.
- Never use masked inpainting or source/generated pixel splicing for the scene. Regenerate and replace the whole scene.
- Never patch only the hidden portion of an occluded raster component. Redraw the whole component, then re-segment and re-matte it.
- Do not restore original visible component pixels after a whole-component redraw.
- Never generate ordinary UI copy inside the scene or component image model when it should be editable. Transcribe and typeset it with broadly similar styling.
- Treat decorative or artistic headline text as image artwork, preserve its readable wording where practical, and name it with `Img_`/`Image_`; do not force it into a live TypeLayer or mark it as a text fallback.
- Use only Codex Desktop's built-in GPT Image 2 route and the current signed-in account allowance by default. Do not request or use external API keys unless the user explicitly chooses an external provider.
- Use one image-generation job per occluded or damaged raster object. Do not redraw multiple unrelated objects together.
- Keep one semantic object instance per raster layer. Repeated instances receive separate IDs, assets, and masks.
- Use silhouette-following alpha with partial transparency where needed. Do not accept opaque rectangular cutouts.
- Classify and mask first, then require human corrections for over-masking, under-masking, missed objects, extra objects, merged/split objects, and wrong classes.
- Build every overlapped shape or component as a complete object and use verified z-order for overlap.
- Keep distant text clusters in separate TypeLayers.
- Name every non-reference text layer with `@`; use `Btn_`/`Button_`, `Img_`/`Image_`, `Bg_`/`BG_`, `Icon_`, and `Panel_`/`Popup_` exactly as defined in `references/psd-layer-structure.md`. The hidden reference branch is the only naming exception.
- Put each button in one independent top-level `Btn_` or `Button_` group outside `Panel_`/`Popup_` groups. Keep its `Bg_`/`BG_` body, `Img_`/`Image_` decoration, `Icon_` artwork, and `@` text inside that group; never mix unrelated UI into it.
- Require an explicit, unique numeric `z` for every pair of siblings. Lower `z` is farther back and must appear lower in the Photoshop Layers panel; backgrounds must have lower `z` than foreground panels, buttons, icons, images, and text in the same scope.
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
- `task-audit.json`: skill version/timestamp, inputs, `codex-desktop-gpt-image-2` generation route, managed rembg version/runtime, human approvals, and exclusions.
- `photoshop-report.json`: Photoshop bridge execution and output-write status; it is not an AI visual-acceptance report.
