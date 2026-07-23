# Shadow and occlusion analysis

Infer z-order only when the flattened image provides evidence. Store results in `occlusion-graph.json`.

## Evidence hierarchy

Use evidence in this order:

1. **Hard contour interruption:** the front object's contour terminates or hides the back object.
2. **T-junction:** the continuous bar of the T is usually in front of the terminated contour.
3. **Cast shadow:** if object A casts a shadow onto object B, A is in front of or above B.
4. **Contact shadow:** a tight dark band can indicate touching surfaces but is weaker than a cast shadow.
5. **Texture continuation:** a texture continuing behind another contour supports the continuing surface being behind.
6. **Semantic expectation:** use only as a low-confidence tie-breaker.

Do not infer z-order from ambient shading, a painted outline, inner glow, or a shadow baked into one icon unless it clearly lands on another object.

## Procedure

1. Identify every pair of masks whose bounds overlap or come within the shadow search distance.
2. Inspect the source at 200% around their boundary.
3. Trace cast-shadow direction and softness. Confirm that the shadow follows the front object's silhouette and falls onto the candidate back surface.
4. Inspect contour continuity and T-junctions at multiple points.
5. Add a directed edge from `front` to `back` only when at least one strong or two independent weak cues agree.
6. Record conflicting cues instead of forcing an edge.
7. Topologically sort the graph. If it contains a cycle, recheck the lowest-confidence edge.

Use this schema:

```json
{
  "front": "dialog_bubble",
  "back": "bubble_04",
  "evidence": [
    {"type": "contour_interruption", "region": [0, 0, 0, 0]},
    {"type": "cast_shadow", "direction_degrees": 95.0}
  ],
  "confidence": "high",
  "status": "verified"
}
```

## PSD assembly rule

Place `front` above `back`: within one sibling scope, assign `front` a higher explicit numeric `z` than `back`. Across groups, compare the first differing ancestors because groups are atomic. Preserve the cast shadow with the front object when it is intrinsic to that object's effect. When the shadow falls across several back layers, use a separate prefixed clipped/masked image layer placed above those receivers and below the casting object.

Reconstruct both front and back objects as complete/amodal objects before stacking. Never cut the back shape to its visible fragment. For regular or custom-vector frames, extend hidden tangent and parallel edges geometrically; use GPT Image only for hidden irregular raster artwork. Preserve each button's own outer stroke, inner shadow/glow, bevel, texture, and drop shadow before evaluating the combined render.

Run `scripts/audit_occlusion_graph.py layer-manifest.json occlusion-graph.json`. Every pair with overlapping bounds must have a directed relation or documented `unknown`, and verified edges must remain acyclic.

Completion criterion: every actual overlap has either a verified directed relation or a documented `unknown`; the graph is acyclic; every non-reference sibling has an explicit unique numeric `z`; PSD z-order follows the verified graph.
