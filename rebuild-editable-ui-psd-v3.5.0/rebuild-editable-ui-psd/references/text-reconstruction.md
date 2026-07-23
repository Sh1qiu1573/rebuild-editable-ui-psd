# Measured live-text reconstruction

Apply this process to every spatial text unit. Keep distant characters/clusters in separate TypeLayers even when they form one phrase.

## Required evidence

For every text unit, retain:

- OCR token or character boxes.
- Spatial-unit grouping result from `scripts/split_text_units.py`.
- Fill-only glyph mask.
- Total glyph mask including outline/stroke.
- Candidate font family and weight.
- Visible ink thickness and glyph-height ratio.
- Outline presence, width, color, opacity, and placement when recoverable.
- Font size, tracking, leading, alignment, fill color, and rotation.

## Text-unit separation

Create a new text unit when any condition holds:

- The gap exceeds the configured spatial threshold.
- An icon, divider, star, or other object interrupts the characters.
- The clusters use independent alignment, rotation, font size, color, or effect.
- Moving one cluster independently is a plausible editing operation.

Do not simulate distant placement with repeated spaces inside one TypeLayer.

## Thickness and outline analysis

Create a fill-only mask and a fill-plus-outline mask at source resolution, then run:

```text
python scripts/analyze_text_style.py source.png text_fill_mask.png \
  --total-mask text_total_mask.png \
  --output text-style.json
```

The script reports visible ink thickness, a low-confidence weight class, fill color, and outline presence/width/color. Use the weight class only to define a broad search range. Run `scripts/search_text_style.py` over actual licensed font files, sizes, tracking values, and stroke widths; do not select a weight from the label alone.

If the total mask cannot be separated reliably, set outline status to `unknown` and inspect clean edge profiles manually. Do not silently assume no outline.

## Photoshop reconstruction

1. Create one live TypeLayer per spatial text unit and name it with `@`, such as `@TitleText` or `@GoldText`.
2. Exhaustively render and rank candidate font files/weights, sizes, tracking, and stroke widths. Increase the search range until a candidate passes or all credible fonts are exhausted.
3. Match font size, tracking, leading, alignment, rotation, and fill.
4. When an outline exists, add a native text Stroke effect with measured width and color. Record inside/center/outside placement and opacity when recoverable.
5. Keep glow/shadow effects separate from the outline measurement.
6. Render the intended text representation before review 2 and include it at final coordinates in `review-composite.png`.
7. Apply position corrections before requesting review 2 approval.

If no credible live TypeLayer is available, use a human-approved source-raster smart object or substitution, keep the `@` name, set `text_fallback: true` in the Photoshop job, and keep an optional hidden live transcription marked `non-rendering-edit-helper`. Completion criterion: wording is exact, distant clusters are separate, measured style information is recorded, and human review 2 approves the appearance and placement. After approval, do not run AI visual regression or a reopened-PSD verification phase.
