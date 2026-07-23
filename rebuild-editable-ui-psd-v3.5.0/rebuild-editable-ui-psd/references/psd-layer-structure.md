# PSD layer naming, grouping, and stack order

Apply this contract to `layer-manifest.json`, the final Photoshop job, the assembled PSD, and Unity-facing layer exports. Treat violations as blocking input errors.

## 1. Naming prefixes

Name every non-reference layer and group with the prefix for its semantic role:

| Role | Required prefix | Examples |
|---|---|---|
| Button group | `Btn_` or `Button_` | `Btn_Close`, `Btn_ClaimX3` |
| Ordinary image or decoration | `Img_` or `Image_` | `Img_Star`, `Img_Crown` |
| Background or body artwork | `Bg_` or `BG_` | `Bg_MainFrame`, `Bg_Mask` |
| Icon | `Icon_` | `Icon_Gold`, `Icon_Heart` |
| Text | `@` | `@GoldText`, `@TitleText` |
| Panel or popup group | `Panel_` or `Popup_` | `Panel_Fail`, `Popup_Help` |

Use a non-empty semantic suffix. Keep names unique case-insensitively across the PSD because each non-reference layer and group exports to `<layer name>.png`. Do not use numeric ordering prefixes, generic names such as `Layer 1`, or unprefixed aliases. `00_REFERENCE` and its descendants are the only exception because they are hidden and excluded from Unity-facing PNG export.

Name native text layers and approved raster text fallbacks with `@`. Mark a raster fallback with `text_fallback: true` in the Photoshop job so validation can distinguish it from an incorrectly named image.

## 2. Independent button groups

Create one independent group for every button instance. Name the group with `Btn_` or `Button_`; never apply a button prefix to an ordinary layer.

Keep all parts belonging to that button inside its group:

```text
Btn_Start [group]
  @StartText [live text]
  Icon_Start [optional icon]
  Img_StartDecoration [optional image or decoration]
  Bg_Start [button body/background]
```

This tree is shown in Photoshop panel order from top to bottom. The matching sibling `z` values run in the opposite visual direction: `Bg_Start` has the lowest value, then decorations/icons, and `@StartText` has the highest value.

Require at least one `Bg_`/`BG_` body in each button group. Text and decoration layers are optional, but when present they must remain in the same button group. Do not place unrelated UI inside a button group. Keep every button group at the top level, outside `Panel_`/`Popup_` and other UI groups, so each button remains an independently selectable folder.

## 3. Stack order from back to front

Photoshop renders the Layers panel from bottom to top. The Photoshop job uses ascending sibling-scoped `z`: lower `z` is created first and ends lower/farther back; higher `z` ends higher/in front.

- Assign every non-reference layer and group an explicit numeric `z`.
- Make sibling `z` values unique. Do not rely on manifest array order as a tie-breaker.
- Put the canvas or section background at the lowest `z` in its sibling scope.
- Put panels, popups, images, icons, buttons, and text above their background.
- Within a button group, put `Bg_`/`BG_` at the lowest `z`; put `@` text at the highest `z` when present.
- Preserve verified occlusion relations from `occlusion-graph.json`; a front object must have a higher effective stack position than the back object.
- Remember that groups are atomic. Children cannot interleave with the group's siblings.

Example final hierarchy in Photoshop panel order:

```text
Btn_Start
  @StartText
  Icon_Start
  Img_StartDecoration
  Bg_Start
Popup_Help
  @HelpText
  Img_HelpArt
  Bg_HelpFrame
Panel_Header
  @TitleText
  Icon_Gold
  Bg_Header
Bg_MainScene
  Bg_CleanScene
00_REFERENCE [hidden]
```

`00_REFERENCE` may use a negative `z`. In every other sibling scope, the actual numeric gaps are arbitrary; only uniqueness and the back-to-front comparisons matter.

## 4. Review and assembly checks

During human review 1, approve semantic names, button membership, parent groups, and proposed `z`. During human review 2, verify that the full composite matches the intended bottom-to-top stack.

Before Photoshop assembly, require `scripts/photoshop_bridge.py` validation to reject:

- Missing or incorrect prefixes.
- Text without `@`, or `@` on a non-text layer without `text_fallback: true`.
- `Btn_`/`Button_` on a non-group, a button group below another parent, or a button group without a `Bg_`/`BG_` body.
- Disallowed or nested groups inside a button group, or non-button content mixed into it.
- Missing, nonnumeric, or duplicate sibling `z` values.
- A background whose `z` is not lower than its foreground siblings.

If a naming or stacking change is needed after human review 2, update the manifest and Photoshop job. If the change alters the visible composite, invalidate review 2 and obtain approval again.
