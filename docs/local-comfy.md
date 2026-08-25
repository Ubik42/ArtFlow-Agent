# Local ComfyUI baseline

Verified on 2026-08-24 against the existing local runtime.

## Runtime

- Root: an existing local ComfyUI checkout
- Background launcher: `launch_comfyui_hidden.ps1`
- API: `http://127.0.0.1:8188`
- GPU: NVIDIA GeForce RTX 4080
- Reported VRAM: 16,375 MB
- Shared model root: configured through ComfyUI's `extra_model_paths.yaml`
- Model mapping: the runtime's `extra_model_paths.yaml`

ArtFlow reads the runtime location from the caller's environment and does not copy or mutate the
ComfyUI installation, its models, or its personal workflows.

## Relevant installed assets

| Category | Available assets |
| --- | --- |
| Diffusion models | `flux-2-klein-base-4b-fp8.safetensors`, `z_image_turbo_int8_convrot.safetensors` |
| Text encoders | `qwen_3_4b.safetensors`, `qwen_3_4b_fp8_mixed.safetensors` |
| VAE | `ae.safetensors`, `full_encoder_small_decoder.safetensors` |
| Traditional checkpoints | none |

The composition recipe therefore uses the split FLUX.2 loader chain (`UNETLoader`, `CLIPLoader`,
`VAELoader`) rather than `CheckpointLoaderSimple`.

## Evidence

The live `/system_stats` and `/object_info` responses confirmed:

- CUDA is available through the runtime's Python environment;
- all nodes needed by `composition-preserving-v1` are installed;
- the recipe's three exact model assets are visible to ComfyUI;
- `Recipe.validate_environment` reports no compatibility problems.
- both bundled workflows pass live node/input/link/value schema preflight before queueing.

This is a capability and graph-schema baseline, not yet an end-to-end generation receipt. A real
approved smoke run is still required before either recipe is considered visually validated.
