# Single-object extraction and whole-component redraw

## 1. Object-instance rule

Create one raster layer per semantic object instance. If an editor could reasonably move, hide, recolor, or replace one item without another, assign separate IDs.

Repeated objects receive separate IDs, masks, assets, and layers. Detached stars, sparkles, hearts, bubbles, icons, badges, and decorations are separate objects even when stylistically similar.

Name final object layers by role: `Icon_` for icons and currency/heart-style symbols, `Img_`/`Image_` for ordinary artwork or decoration, and `Bg_`/`BG_` for backgrounds or body artwork. When an object belongs to a button, keep it inside that independent `Btn_`/`Button_` group.

## 2. Human-approved classification

Do not extract production assets from the draft inventory. Human review 1 must first approve:

- The object list and class of every item.
- Split/merge decisions.
- Draft masks and complete/amodal extents.
- Corrections for over-masking, under-masking, missing items, extra items, and neighbor contamination.

Store approved masks under `masks/approved/` and record their review revision in the manifest.

## 3. Required records

For each raster object record:

- `object_id`, source bounds, approved class, and review revision.
- `visible_mask` for a fully visible source extraction.
- `complete_mask` or proposed complete extent when the source object is occluded.
- `silhouette_mask` for the final asset.
- `redraw_mode`: `none` or `whole-component-redraw`.
- Generation input/output when redraw is required.
- Alpha bounds, crop origin, padding, and final placement.

## Background-removal tool selection

Before removing a background, inspect the rembg deployment result from `scripts/check_environment.py`; rerun the check if the environment may have changed.

- When rembg is detected through its Python module or CLI, use rembg as the preferred background-removal tool.
- When rembg is not detected, explicitly notify the user that rembg was not detected, then continue with the existing segmentation and matting route.

Regardless of the selected tool, preserve every existing approved-mask, trimap, partial-alpha, silhouette, bounds, audit, and human-review requirement below. Do not add, remove, or reorder a workflow step.

## 4. Fully visible objects

When an object is fully visible and undamaged:

1. Segment it using its approved instance-specific mask.
2. Use a conservative trimap that retains antialiasing, partial alpha, holes, thin parts, glow, fur, glass, and soft edges.
3. Remove neighboring contamination without contracting the intended silhouette.
4. Trim to minimal nonzero-alpha bounds plus 0-2 px safety padding.
5. Include the result in the review composite and optional contact sheet.

## 5. Occluded, damaged, or incomplete objects

When any portion of a raster object is hidden, damaged, or unavailable, redraw the complete component.

1. Prepare one context image containing one target object and enough style reference.
2. Call the image-generation/editing tool once for that object.
3. Request one complete replacement component, including both previously visible and hidden portions.
4. Preserve identity, role, style, palette, material, perspective, scale, and orientation, but do not require source-visible pixels to remain identical.
5. Do not generate unrelated objects, text, or a background-dependent rectangular patch.
6. Do not composite source-visible fragments over the result.
7. Do not splice only the generated hidden part into the source extraction.
8. Re-segment the generated complete component from scratch.
9. Re-matte its full silhouette, preserve partial alpha, and trim it tightly.
10. Record the entire component as generated in `gpt-image-log.json` and `limitations.md`.

Prompt scaffold:

```text
Use case: whole-component-redraw
Input: one UI component shown in context; it may be partly occluded or damaged
Primary request: redraw one complete standalone version of <object_id>, including the entire visible and formerly hidden shape
Preserve: semantic identity, style, palette, material, perspective, scale, orientation, lighting, and edge character
Output constraints: exactly one complete component; transparent or separable background; no text; no watermark; no unrelated object
Avoid: partial patch, hidden-region-only completion, source/generated stitching, duplicate components, rectangular background cutout
```

If the redraw fails, regenerate the whole component with one targeted prompt change. Never repair it by splicing source fragments.

## 6. Alpha and tight bounds

The final alpha must follow the complete object silhouette:

- Alpha 0 outside the object.
- Appropriate opaque interior.
- Graduated alpha for antialiased, translucent, smoky, glowing, furry, or glass edges.
- Transparent holes and gaps.

Use `scripts/trim_alpha.py` for lossless alpha-bound trimming. Store `crop_origin` and placement data.

Deterministic checks may identify rectangular alpha, clipped nonzero pixels, reused mask paths, or multiple instances. These are preparation checks before human review 2, not post-approval AI acceptance.

## 7. Review 2

Place every final object at its intended coordinates in `review-composite.png`. When small or translucent objects are difficult to judge, add them to `object-contact-sheet.png` over checkerboard, black, white, and mid-gray backgrounds.

Human review 2 decides whether:

- The correct object was extracted or redrawn.
- The complete silhouette is credible.
- The mask over-cuts or under-cuts.
- Halos, rectangular alpha, missing holes, or neighbor contamination remain.
- Placement, scale, rotation, and z-order are correct.

After approval, do not run AI alpha or visual acceptance. If an asset changes, repeat review 2.

## 8. Failure handling

- **Wrong class or instance:** return to human review 1.
- **Over/under-masking:** revise the full-object matte and repeat review 2.
- **Redraw changes the component too much:** regenerate the entire component with better references.
- **Redraw contains multiple objects:** tighten the context and redraw the single target again.
- **A hidden shape is ambiguous:** provide up to three whole-component candidates for human selection.
- **Alpha is rectangular:** re-segment/re-matte; trimming alone is insufficient.
- **Soft edge is clipped:** refine the trimap or add at most 2 px safety padding.
- **Neighboring object leaks into the asset:** correct the full mask and repeat the review composite.
- **Built-in generation is unavailable:** request approval before using an API/CLI fallback requiring credentials.
