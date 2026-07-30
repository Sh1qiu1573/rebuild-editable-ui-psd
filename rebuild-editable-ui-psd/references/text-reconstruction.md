# Ordinary editable text and artistic title artwork

First classify lettering as either ordinary editable text or artistic title artwork. Do not apply the live-text workflow to both.

## Classification

Use `editable-text` for ordinary labels, numbers, captions, paragraphs, counters, and button copy whose primary role is readable UI information.

Use `raster-object` for a decorative or artistic headline when the lettering is logo-like, illustrated, highly distorted, textured, extruded, integrated with ornaments, or otherwise functions as a graphic. Name it `Img_<SemanticName>` or `Image_<SemanticName>`, not `@...`, and do not set `text_fallback: true`. Preserve it as extracted artwork when complete or redraw the entire title artwork with built-in GPT Image 2 when damaged or occluded.

Record the classification in review 1. When uncertain, present the title crop and ask the human reviewer to choose between editable copy and raster artwork.

## Ordinary text evidence

For each ordinary text unit, retain:

- Exact transcription and punctuation.
- OCR token or character boxes when useful.
- Spatial-unit grouping from `scripts/split_text_units.py` when the grouping is ambiguous.
- Approximate font family/category and weight.
- Approximate size, tracking, leading, alignment, fill color, rotation, and outline.

Do not spend substantial time matching glyph contours or finding the exact font. Broad similarity is sufficient when the text is readable, correctly grouped, positioned, scaled, and visually consistent with the UI hierarchy.

## Text-unit separation

Create a new ordinary text unit when any condition holds:

- The gap exceeds the configured spatial threshold.
- An icon, divider, star, or other object interrupts the characters.
- The clusters use independent alignment, rotation, size, color, or effect.
- Moving one cluster independently is a plausible editing operation.

Do not simulate distant placement with repeated spaces inside one TypeLayer.

## Photoshop reconstruction

1. Create one live TypeLayer per ordinary spatial text unit and name it with `@`, such as `@BodyText` or `@GoldCount`.
2. Choose a readily available licensed font with roughly similar category, weight, and proportions. Do not run exhaustive font search unless the user explicitly asks for close typography matching.
3. Match wording exactly and approximate size, tracking, leading, alignment, rotation, fill, and outline.
4. Keep glow/shadow effects separate when practical.
5. Include the intended text at final coordinates in `review-composite.png`.
6. Accept the ordinary text when it is readable, semantically correct, and broadly similar in hierarchy and placement.

If no readable live TypeLayer is practical for ordinary text, use a documented raster fallback, retain the `@` name, set `text_fallback: true`, and optionally keep a hidden live transcription marked `non-rendering-edit-helper`.

Artistic title artwork is not a text fallback. It follows the raster-object extraction, whole-component redraw, rembg, alpha, naming, and review rules.

Human review 2 approves the final appearance and placement. After approval, do not run AI visual regression or a reopened-PSD verification phase.
