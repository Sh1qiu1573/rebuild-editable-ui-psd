# Measured button reconstruction

## Contents

1. Scope and evidence
2. Required measurements
3. Prepare masks
4. Run deterministic analysis
5. Reconstruct Photoshop layers
6. Prepare each parameter for human review
7. Failure handling

## 1. Scope and evidence

Apply this process independently to every rectangular, rounded, rotated, diamond-like, hand-drawn, tab-like, or glossy button/frame. Do not copy a preset merely because two buttons look similar.

The source screenshot is the visual authority. A reference PSD may explain construction but must not override the measured source appearance.

Create one `button-measurements.json` entry per button instance. Every supported property must state:

- `present`: `true`, `false`, or `unknown`.
- Estimated parameters and units.
- Evidence region or measurement method.
- Confidence: `high`, `medium`, or `low`.
- Final Photoshop values after visual calibration.

Completion criterion: no button effect is silently omitted and no value is accepted solely because it came from a template.

## 2. Required measurements

Measure and record:

- Axis-aligned bounds and oriented bounds.
- Button rotation angle.
- Width and height.
- Corner radius for all four corners; do not assume equal radii until measured.
- Shape family: strict regular rounded rectangle, custom vector frame, or source-raster frame.
- Fill type: solid, linear/radial gradient, or raster texture.
- Fill colors, opacity, and gradient angle/stops when present.
- Outer stroke: presence, width, color/gradient, opacity, and inside/center/outside placement.
- Inner glow: presence, color, opacity, blend behavior, choke/range, and size.
- Inner shadow: presence, angle, distance, choke, size, color, opacity, and blend mode.
- Bevel/emboss: presence, style, technique, depth, direction, size, soften, light angle/altitude, highlight/shadow colors and opacities.
- Outer shadow: presence, direction angle, offset/distance, spread, blur/size, color, opacity, and noise when visible.
- Texture/pattern: presence, source crop, scale, offset, rotation angle, blend mode, and opacity.
- Highlight overlays and clipped decoration layers.

When a parameter cannot be recovered uniquely from flattened pixels, record an estimate and confidence rather than inventing certainty.

## 3. Prepare masks

Create:

- `button_visible_body_mask`: only body pixels visible in the source.
- `button_body_mask`: the complete/amodal button body, including regions hidden by overlapping buttons, excluding shadow and unrelated content.
- `button_content_exclusion_mask`: text, icons, highlights, and other content that would contaminate texture sampling.
- `button_effect_context`: a crop extending beyond the expected shadow by at least the measured blur distance.

The body mask must follow the real silhouette at its real rotation. Use a separate mask for each button instance. Do not derive the complete mask by polygonizing the visible fragment.

Completion criterion: the body mask contains one button body, the exclusion mask covers all foreground content, and the context includes the entire shadow.

## 4. Run deterministic analysis

Run:

```text
python scripts/analyze_button.py source.png button_body_mask.png \
  --visible-body-mask button_visible_body_mask.png \
  --content-exclusion-mask button_content_exclusion_mask.png \
  --output button-analysis.json
```

The script estimates:

- Bounds, oriented size, and rotation.
- Strict rounded-rectangle fit, shape-family routing, and per-corner radius.
- Median fill color.
- Evidence for outer shadow, inner glow, inner shadow, bevel/emboss, and outer stroke.
- Texture presence and dominant direction.

Treat low-confidence effect values as starting points. Confirm them by inspecting de-rotated inward/outward edge profiles:

1. Sample perpendicular to several clean edges.
2. Compare the core fill, inner edge band, stroke band, shadow band, and distant background.
3. Use at least two sides not covered by text or icons.
4. Reject an effect when the apparent band follows the scene background rather than the button contour.

For shadow angle, use the cast-shadow displacement from button center. Record the angle convention. Convert it to Photoshop's light-angle convention during assembly rather than copying the number blindly.

For texture, inspect the high-frequency residual after excluding text/icons and removing the smooth fill/gradient. Confirm that the signal moves with the button rather than the scene background.

Completion criterion: the JSON report exists and every low-confidence field has a visual confirmation or an `unknown` status.

## 5. Reconstruct Photoshop layers

Use `shape_model.recommended_reconstruction` before choosing a body layer:

- `native-rounded-rectangle`: only when the strict fit passes.
- `custom-vector-path`: trace the actual contour, including notches and unequal/hand-drawn corners; do not replace curves with diagonal chamfers.
- `source-raster-smart-object`: preserve textured/distressed outlines and inseparable effects when vector output cannot pass the isolated comparison.

Create one independent group per button and use this layer structure when the corresponding parts exist:

```text
Btn_<SemanticName> [group]
  @<SemanticName>Text [live text, separate unit]
  Icon_<SemanticName> [optional separate icon]
  Img_<SemanticName>Decoration [optional clipped raster/smart object]
  Bg_<SemanticName> [native shape, vector path, or smart-object body]
```

The tree is shown in Photoshop panel order. Assign `Bg_` the lowest sibling `z`, decorations/icons above it, and `@` text the highest `z` when present. Keep every button group independent at the top level, outside panels and popups; do not place unrelated UI inside it. Use `Button_` instead of `Btn_` only when that convention is more appropriate for the project, but never mix unprefixed button groups into the PSD.

Apply native layer effects to the `Bg_` button body or the custom path when they reproduce the source:

- Outer stroke as Stroke.
- Inner glow as Inner Glow.
- Inner shadow as Inner Shadow.
- Bevel/emboss as Bevel & Emboss with measured light angle/altitude.
- Outer shadow as Drop Shadow.
- Fill as solid or Gradient Overlay.

Use a clipped smart object for a real texture/pattern. Preserve its measured scale, offset, and angle; do not bake label text or icons into the texture.

If a native Photoshop effect cannot reproduce the source, use a separate documented effect layer while keeping the body editable.

Completion criterion: the independent button group contains its `Bg_`/`BG_` body and any `Img_`/`Image_` decoration, `Icon_` artwork, and `@` label; all detected effects are represented by native effects or documented effect layers; the chosen body representation is included in the assembled human-review composite. Visual fidelity takes priority over forcing the body to remain native.

## 6. Prepare each parameter for human review

Render the reconstructed button without surrounding UI for measurement, then include it at final coordinates in `review-composite.png` and, when useful, `object-contact-sheet.png`.

Check in this order:

1. Bounds, center, and rotation.
2. Corner radii and silhouette.
3. Stroke width and color.
4. Fill/gradient.
5. Texture scale, offset, and angle.
6. Inner glow.
7. Shadow angle, distance, spread, blur, opacity, and color.
8. Highlight overlays.
9. Overlap render against every adjacent button, including which rounded corner/outline remains visible.

Change one parameter family at a time before review 2. Place the result in the full review composite so the human reviewer can judge it in context.

Record `final_values` separately from `initial_estimates` in `button-measurements.json`.

Human review 2 is the final acceptance gate. Record the approved values in `button-measurements.json`. After approval, do not run AI component regression or reopen-and-verify checks. If the button changes, invalidate the approval and repeat review 2.

## 7. Failure handling

- **Mask includes label/icon:** fix the exclusion mask before trusting texture or fill measurements.
- **Background gradient resembles shadow:** sample multiple sides and use contour-following evidence; set shadow to `unknown` when evidence conflicts.
- **Unequal corners:** preserve four independent radii or reproduce with a custom vector path.
- **Decorative notches or hand-drawn black outline:** keep the actual custom path or source raster; never replace with a chamfered polygon or omit the outline.
- **Rotated/diamond frame:** deskew for measurement, test width/height-swapped angle equivalents, then restore its actual transform.
- **Overlap hides a corner:** infer a complete/amodal body from unoccluded tangent/parallel edges or repeated geometry; keep every button complete and use z-order.
- **Texture score is caused by compression:** compare frequency and direction across the button core and nearby background.
- **Effect is inseparable from artwork:** use a separate clipped effect layer and document why a native parameter could not be recovered.
- **Two buttons appear identical:** still measure and record both instances; reuse values only after measurements agree within tolerance.
