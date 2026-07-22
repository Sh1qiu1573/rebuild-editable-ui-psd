# Prerequisites and tool routing

## Required capabilities

| Capability | Preferred route | Gate |
|---|---|---|
| Inspect source pixels | Original-resolution image viewer | Required |
| Read/write files and run scripts | Shell plus Python 3.10+ | Required |
| Generate the whole clean scene | Built-in GPT Image or approved equivalent | Required |
| Redraw a complete occluded/damaged raster component | Built-in GPT Image, one object per job | Required when applicable |
| Segment and matte objects | Instance segmentation plus partial-alpha matting | Required |
| Assemble native PSD and export layer PNGs | `photoshop_bridge.py` through Windows Photoshop | Required for `final.psd` and `png/` |
| OCR/transcribe | Agent vision or suitable OCR | Required |
| Human review packages | Labeled overlays, mask previews, full review composite | Required twice |

Confirm permission before sending local artwork to any network service. Prefer local processing for confidential inputs.

## Python packages

The bundled scripts may use:

```text
Pillow
numpy
psd-tools[composite]
pywin32
opencv-python-headless
```

Run:

```text
python scripts/check_environment.py
```

Install only dependencies required by the selected route.

## Native PSD backend

V3.4 requires Codex Desktop on Windows and Adobe Photoshop registered as `Photoshop.Application`.

1. Run `scripts/photoshop_bridge.py probe <work>/photoshop-probe --timeout 45`.
2. Confirm native group, text, shape, embedded smart-object, and transparent per-layer PNG export support.
3. Assemble production output with `scripts/photoshop_bridge.py run`.
4. Do not use foreground keystrokes as the primary production assembly route.
5. If the bridge is unavailable, finish the human-approved assets and manifest, then report PSD assembly as blocked.

The bridge probe is an environment test, not the deleted final reopen-and-verify phase.

## Scene generation route

Generate a complete UI-free scene and use it whole. Do not use masked-inpaint patches, restore source pixels, or composite multiple candidates.

Whole-scene drift is accepted by selecting v3.4 unless the user explicitly requires source-scene preservation. When preservation is required, stop and use a different workflow.

## Component generation route

For every occluded, damaged, or incomplete raster object:

- Use one image-generation job for one whole component.
- Request the complete object, not only the hidden region.
- Do not restore the original visible fragment.
- Re-segment and re-matte the entire generated result.

Fully visible undamaged raster objects may be extracted from the source after human review 1 approves the class and mask.

## Fonts and external assets

- Request exact licensed fonts when typography must match.
- Record substitutions and raster fallbacks.
- Do not download or redistribute commercial fonts without authorization.
- Prefer embedded smart objects for a portable PSD.

## Human review requirement

The workflow must pause twice:

1. After draft classification and masks.
2. After all scene/components have been assembled into `review-composite.png`.

After review 2 approval, do not run AI visual validation or a final reopen-and-verify stage. Only deterministic assembly and mechanical file-write checks remain.
