# M3-S12 — Codex GPT Image 2 matched candidate evidence

Date: 2026-08-25

## Result

The exact Unreal beauty evidence used by the real local ComfyUI run was supplied to the Codex built-in image-generation surface. Codex generated the candidate, normalized it into the Agent event stream, and exposed it beside the local result without a user approval interrupt, direct provider API, API key, or paid-API fallback.

No candidate is adopted in this slice. Both lanes remain explicitly `UNSELECTED` until the independent tribunal is implemented.

## Source binding

- Run: `local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb`
- Scene Package: `artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6`
- Archive SHA-256: `130c94284deb5fddb18c52d604b615ca1a071e42afc8149604f76130fe412f76`
- Beauty SHA-256: `f6d4005de3b73fa0a59b63f2924e76f40cede01797187f2527f6d45d74d466d9`
- Prompt SHA-256: `88c30433a2229860f8ae6ab77bd384a4924bb021eba8a1d7fbd1633dffa8f265`
- Request binding SHA-256: `b600180b885852f7d8817efa2663defba769c73712c62fdc3381cda7d8514d99`

Only `beauty` pixels plus bounded art direction were sent. `depth`, `world_normal`, and `object_id` are recorded as withheld local tribunal evidence.

## Returned candidate

- Candidate: `codex-a8430dc9b8290bd658dd`
- Tool surface: `codex-builtin-imagegen`
- Requested model family: `gpt-image-2`
- Observed exact model ID: unavailable from the built-in surface, therefore persisted as `null`
- PNG dimensions: `1672 × 941`
- Bytes: `2,115,802`
- Artifact SHA-256: `a8430dc9b8290bd658dd276cc7e9a9c490ca6a25a5accff70145a2d6704f54d5`
- Persisted artifact: `artifacts/goal/m3-s11-local-run/.agent-artifacts/provider-outputs/a8430dc9b8290bd658dd276cc7e9a9c490ca6a25a5accff70145a2d6704f54d5.png`
- Persisted normalized receipt: `artifacts/goal/m3-s11-local-run/.agent-artifacts/codex-receipts/codex-a8430dc9b8290bd658dd.json`

The built-in surface honored the requested landscape composition but returned its native `1672 × 941` raster rather than an exact caller-controlled `1024 × 576` size. The receipt records observed pixels rather than inventing unsupported provider metadata.

## Durable and boundary evidence

- Event 8: `codex_image_candidate_recorded`
- Re-import: `8 → 8` events and `1 → 1` Codex candidate
- Mismatched expected archive binding: rejected before persistence
- Persisted file tamper: artifact endpoint returns HTTP 409
- Valid artifact endpoint: HTTP 200, exact `X-Content-SHA256`, 2,115,802 bytes
- Pending permission decisions: zero

## Scene Lab evidence

- Wide Codex lane: `artifacts/goal/m3-s12-codex-image/matched-codex-wide.png`
- Wide local lane: `artifacts/goal/m3-s12-codex-image/matched-wide.png`
- Narrow local lane: `artifacts/goal/m3-s12-codex-image/matched-narrow.png`
- Wide viewport: `scrollWidth = clientWidth = 1440`
- Narrow viewport: `scrollWidth = clientWidth = 390`
- Both real candidate images decoded at their recorded dimensions
- Browser console: zero errors and zero warnings

## Validation

- Focused Agent/API tests: `11 passed`
- Full Python suite: `81 passed`
- Changed-file Ruff: passed
- Frontend production build: passed, 1,804 modules transformed

## Truth boundary

This evidence proves a real Codex built-in image candidate, exact local source binding, minimal remote disclosure, durable normalization, idempotent recovery, tamper-evident serving, and a truthful two-lane UI. It does not prove evaluator quality, winner selection, bounded revision, Unreal reimport, C2PA signing, or the exact backend model build behind the built-in tool surface.
