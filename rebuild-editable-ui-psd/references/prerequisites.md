# Prerequisites and tool routing

## Required capabilities

| Capability | Preferred route | Gate |
|---|---|---|
| Inspect source pixels | Original-resolution image viewer | Required |
| Read/write files and run scripts | Shell plus Python 3.10+ | Required |
| Generate the whole clean scene | Invoke Codex `$imagegen` in default built-in mode | Required |
| Redraw a complete occluded/damaged raster component | Invoke Codex `$imagegen` in default built-in mode, one object per job | Required when applicable |
| Segment and matte objects | Instance segmentation plus partial-alpha matting | Required |
| Assemble native PSD and export layer PNGs | `photoshop_bridge.py` through Windows Photoshop | Required for `final.psd` and `png/` |
| OCR/transcribe | Agent vision or suitable OCR | Required |
| Human review packages | Labeled overlays, mask previews, full review composite | Required twice |
| Install and detect rembg | GPU-first and isolated CPU fallback through `scripts/install_rembg.py --ensure`, then `scripts/check_environment.py` | Required before background removal |

Load the Codex `$imagegen` skill before the first generation job and follow its current instructions. Use its default built-in tool mode through the signed-in Codex account; do not request `OPENAI_API_KEY`, call its CLI, or route generation through an external API by default. If the user marks the input confidential or prohibits built-in generation, stop before upload and ask for an allowed route. Use a CLI/API fallback only after the user explicitly requests or confirms the fallback under `$imagegen` rules.

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

Install pinned `danielgatis/rembg` GPU and CPU library/CLI extras with the skill in separate managed environments. The installer always prepares CPU fallback. When NVIDIA is detected, it also installs the GPU backend and selects it only after `CUDAExecutionProvider` and an actual rembg inference pass. It is idempotent and may be run again after a skill upgrade.

On NVIDIA systems, the managed GPU environment installs its own pinned ONNX Runtime CUDA 13 and cuDNN DLLs and preloads them before rembg creates a session. This avoids requiring a separately configured CUDA Toolkit, but the first installation downloads several gigabytes and should have at least 8 GB of free disk space. Systems without NVIDIA, or systems whose GPU probe fails, keep using the much smaller CPU runtime.

- Use `scripts/rembg_cutout.py --backend auto` as the default background-removal command for raster objects. It uses verified GPU first and retries CPU automatically after a GPU invocation error.
- Keep the approved instance mask, partial-alpha matting, mask audit, and human-review requirements unchanged after rembg inference.
- Record the selected backend, actual backend, probe results, and fallback events in `task-audit.json`.
- If the CPU fallback runtime is missing, rerun `scripts/install_rembg.py --ensure`. If CPU installation or inference fails again, block extraction and report the exact error.

Do not silently replace rembg with an external background-removal API. Model files downloaded by rembg on first use belong to rembg's normal managed runtime behavior.

## Native PSD backend

V3.6.2 requires Codex Desktop on Windows and Adobe Photoshop registered as `Photoshop.Application`.

1. Run `scripts/photoshop_bridge.py probe <work>/photoshop-probe --timeout 45`.
2. Confirm native group, text, shape, embedded smart-object, and transparent per-layer PNG export support.
3. Assemble production output with `scripts/photoshop_bridge.py run`.
4. Do not use foreground keystrokes as the primary production assembly route.
5. If the bridge is unavailable, finish the human-approved assets and manifest, then report PSD assembly as blocked.

The bridge probe is an environment test, not the deleted final reopen-and-verify phase.

## Scene generation route

Invoke `$imagegen` in its default built-in mode to generate a complete UI-free scene and use it whole. Follow `$imagegen` input-image and save-path rules, and copy the selected project asset into the task workspace. Do not use masked-inpaint patches, restore source pixels, or composite multiple candidates.

Whole-scene drift is accepted by selecting v3.6.2 unless the user explicitly requires source-scene preservation. When preservation is required, stop and use a different workflow.

## Component generation route

For every occluded, damaged, or incomplete raster object:

- Use one image-generation job for one whole component.
- Invoke `$imagegen` and keep its default built-in mode; use a CLI/API fallback only with the explicit approval required by `$imagegen`.
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
