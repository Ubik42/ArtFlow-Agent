# M0 contract and migration-seam evidence — 2026-08-25

## What is proven

- `scene-constraint-package/1` validates the same fixture in Python, TypeScript/Ajv and compiled C++
  using RapidJSON distributed with Unreal Engine 5.8.
- All three consumers reject package-relative path traversal, duplicate render pass kinds and a
  missing required production pass.
- Provider selection is represented by `route-decision/1`; human approval is bound to its
  policy-sensitive SHA-256 fingerprint through `approval-grant/1`.
- Changing the input package, provider, model, execution kind, privacy class or cost class makes the
  old grant unusable and returns `RunStore` to `awaiting_approval`.
- Provider outcomes normalize through `provider-execution-receipt/1` and package-relative artifact
  hashes.
- Existing local Comfy execution is behind `RecipeExecutionProvider`; v0 remains readable and its
  historical absolute artifact paths are resolved only through a run-root-confined compatibility
  fallback.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts\export_contract_schemas.py --check
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix web run verify:contracts
npm --prefix web run build
.\scripts\verify_unreal_contract.ps1
.\.venv\Scripts\artflow.exe doctor
```

Observed on 2026-08-25:

- Ruff passed.
- 24 Python tests passed in 0.88 seconds.
- TypeScript contract verification passed.
- Unreal-side C++ contract verification compiled and passed.
- React production build passed.
- ComfyUI 0.28.0 was reachable on an NVIDIA GeForce RTX 4080 with 16 GB VRAM and 1,301 nodes.

No GPU generation, hosted-provider call, candidate selection, Unreal project write or plugin install
was performed for this evidence.
