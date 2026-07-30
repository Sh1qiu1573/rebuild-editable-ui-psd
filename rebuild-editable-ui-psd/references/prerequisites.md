# Prerequisites and tool routing

## Required capabilities

| Capability | Preferred route | Gate |
|---|---|---|
| Inspect source pixels | Original-resolution image viewer | Required |
| Read/write files and run scripts | Shell plus Python 3.10+ | Required |
| Generate the whole clean scene | Codex Desktop built-in GPT Image 2 using the current signed-in account allowance | Required |
| Redraw a complete occluded/damaged raster component | Codex Desktop built-in GPT Image 2, one object per job | Required when applicable |
| Segment and matte objects | Instance segmentation plus partial-alpha matting | Required |
| Assemble native PSD and export layer PNGs | `photoshop_bridge.py` through Windows Photoshop | Required for `final.psd` and `png/` |
| OCR/transcribe | Agent vision or suitable OCR | Required |
| Human review packages | Labeled overlays, mask previews, full review composite | Required twice |
| Install and detect rembg | `scripts/install_rembg.py --ensure`, then `scripts/check_environment.py` | Required before background removal |

Use the signed-in Codex Desktop GPT Image 2 entitlement by default; do not request API keys or route generation through an external API. If the user marks the input confidential or prohibits built-in generation, stop before upload and ask for an allowed route. Ask permission before any third-party network service.

## Python packages

The bundled scripts may use:

```text
Pillow
numpy
psd-tools[composite]
pywin32
opencv-python-headless
```

Run the managed rembg installer first, then the environment check:

```text
python scripts/install_rembg.py --ensure
python scripts/check_environment.py
```

Install only dependencies required by the selected route.

## Bundled rembg route

Install `danielgatis/rembg` with the skill. The installer creates an isolated managed environment and installs the CPU library/CLI extras required by this Windows workflow. It is idempotent and may be run again after a skill upgrade.

- Use `scripts/rembg_cutout.py` as the default background-removal command for raster objects.
- Keep the approved instance mask, partial-alpha matting, mask audit, and human-review requirements unchanged after rembg inference.
- If the managed runtime is missing, rerun `scripts/install_rembg.py --ensure`. If installation or inference fails again, block extraction and report the exact error.

Do not silently replace rembg with an external background-removal API. Model files downloaded by rembg on first use belong to rembg's normal managed runtime behavior.

## Native PSD backend

V3.5 requires Codex Desktop on Windows and Adobe Photoshop registered as `Photoshop.Application`.

1. Run `scripts/photoshop_bridge.py probe <work>/photoshop-probe --timeout 45`.
2. Confirm native group, text, shape, embedded smart-object, and transparent per-layer PNG export support.
3. Assemble production output with `scripts/photoshop_bridge.py run`.
4. Do not use foreground keystrokes as the primary production assembly route.
5. If the bridge is unavailable, finish the human-approved assets and manifest, then report PSD assembly as blocked.

The bridge probe is an environment test, not the deleted final reopen-and-verify phase.

## Scene generation route

Generate a complete UI-free scene and use it whole. Do not use masked-inpaint patches, restore source pixels, or composite multiple candidates.

Whole-scene drift is accepted by selecting v3.6 unless the user explicitly requires source-scene preservation. When preservation is required, stop and use a different workflow.

## Component generation route

For every occluded, damaged, or incomplete raster object:

- Use one image-generation job for one whole component.
- Request the complete object, not only the hidden region.
- Do not restore the original visible fragment.
- Re-segment and re-matte the entire generated result.

Fully visible undamaged raster objects may be extracted from the source after human review 1 approves the class and mask.

## Fonts and external assets

- Use available licensed fonts for ordinary editable text; broad similarity is sufficient and exhaustive font matching is unnecessary.
- Classify decorative or artistic headline lettering as raster artwork, not editable text or a text fallback.
- Record ordinary-text substitutions and raster title artwork.
- Do not download or redistribute commercial fonts without authorization.
- Prefer embedded smart objects for a portable PSD.

## Human review requirement

The workflow must pause twice:

1. After draft classification and masks.
2. After all scene/components have been assembled into `review-composite.png`.

After review 2 approval, do not run AI visual validation or a final reopen-and-verify stage. Only deterministic assembly and mechanical file-write checks remain.
