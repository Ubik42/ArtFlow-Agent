# M3-S2 real local ComfyUI capability attestation

Date: 2026-08-25  
Evidence level: A3 — read-only real local host observation  
Prompt queue, upload, generation or hosted call used: no

## Observed environment

The read-only `ComfyGateway.inspect()` path called only `/system_stats` and `/object_info` and
recorded:

- ComfyUI `0.28.0`;
- Python `3.12.13`;
- PyTorch `2.13.0+cu130`;
- `cuda:0 NVIDIA GeForce RTX 4080 : cudaMallocAsync`;
- 16,375 MB VRAM;
- 1,301 observed node types;
- 7 observed model files.

For reviewed recipe `composition-preserving-v1` all 16 required node types and all three required
model files were observed, so the attestation status is `supported`. The complete bounded evidence
is saved at `artifacts/goal/m3-s2-comfy-attestation.json` with environment SHA-256
`fb554b803670614980b91e4b8eea209796e6a415b8f1e6e48bf50df4660afee0`.

## Harness behavior

- unreachable evidence becomes `unknown`, never supported;
- missing model/node or insufficient VRAM becomes `unsupported` with reason codes;
- attestation JSON is independently fingerprint-verified and tampering fails;
- duplicate observation of the same environment fingerprint is event-idempotent;
- the attestation must match the selected provider/model before it enters Agent state;
- `capability_attested` replays through the reducer and appears as observed evidence in Scene Lab.

Browser evidence: `artifacts/goal/m3-s2-comfy-attested-ui.png`.

## Verification

```text
python -m ruff check <attestation, runtime, projection, CLI and focused tests>
All checks passed

python -m pytest <attestation, routing, projection, runtime, Comfy and API tests> -q
19 passed

npm run build
Vite production build passed

powershell -ExecutionPolicy Bypass -File scripts/validate.ps1 -Tier quick
50 passed in 1.80s
```

## Evidence ceiling

This proves current local readiness for the reviewed recipe, not a new generation. The fictional
route model ID remains a policy-facing adapter identity; the attestation separately proves the
actual workflow dependencies. Provider execution and crash reconciliation remain unproven.
