# M4-S2 — Attractive-invalid control and multimodal critic

Date: 2026-08-25

## Result

The real Unreal source and both production candidates now share a bounded multimodal review with a
deliberately attractive but invalid Codex-built-in control. The critic rates that control visually
coherent at `0.99`, while the deterministic framing gate rejects it. Hard-failure precedence is
persisted, replayable and visible; neither production candidate is adopted in this slice.

## Real negative control

- Tool surface: Codex built-in image generation, requested family `gpt-image-2`
- Control: `negative-e7b801516f0b4e28fbc8`
- Source archive: `130c94284deb5fddb18c52d604b615ca1a071e42afc8149604f76130fe412f76`
- Source beauty: `f6d4005de3b73fa0a59b63f2924e76f40cede01797187f2527f6d45d74d466d9`
- Output: `1122 × 1402`, `2394302` bytes
- Output SHA-256: `e7b801516f0b4e28fbc83ff761c3c2c90fcd5930959ce8f3f1bceff0daa01859`
- Request binding: `d652498583123e850e8a89f4a0d99960cd708ce68cc316be85dc0f2cf96b1a99`
- Intended violations: protected geometry redesign, sphere relocation, camera framing change and
  ground-plane composition change
- Minimal disclosure: only beauty pixels were supplied; depth, world normal and object ID stayed local

The exact observed model snapshot and upstream request ID were unavailable from the built-in surface,
so both fields remain `null` instead of being invented.

## Independent evidence

The fixed four-image critic input is source, local ComfyUI candidate, Codex candidate and negative
control. The rubric hash is
`4456d1bae71124be53571bbbf4573dc5354bcb7c4c5d8262ac80f80349185c3a`.
Only concise observations, verdicts, confidence, evidence hashes and limitations are stored; hidden
reasoning is explicitly excluded.

| Candidate | Aesthetic | Visible geometry | Visible camera | Deterministic eligibility |
|---|---:|---:|---:|---:|
| Local ComfyUI | uncertain `0.98` | pass `0.99` | pass `0.99` | eligible |
| Codex built-in | pass `0.97` | pass `0.90` | pass `0.94` | eligible |
| Attractive-invalid control | pass `0.99` | fail `0.99` | fail `0.99` | rejected |

The negative control has valid artifact identity but fails aspect-ratio drift at `0.549840 > 0.02`.
Its coarse edge-layout proxy also fails at `0.226506 < 0.35`, but that metric remains non-hard and
non-semantic. The aggregate report records `hard_gate_precedence`; critic appeal cannot override it.

## Replay and UI evidence

- Report: `artifacts/goal/m4-s2-negative-control/multimodal-tribunal-report.json`
- Report ID: `multimodal-e453601397b2a5d4f217`
- First import/evaluation appended events 10 and 11.
- Re-running both scripts retained exactly 11 events, one control and the same report ID.
- The immutable artifact endpoint returned `200 image/png`; its 2,394,302 bytes re-hashed to the
  persisted output identity.
- Wide UI: `artifacts/goal/m4-s2-negative-control/scene-lab-full.png`
- Narrow UI: `artifacts/goal/m4-s2-negative-control/scene-lab-narrow.png`
- 1440 px and 390 px inspections showed no horizontal overflow; browser console had zero errors.

## Validation

- Quick gate: `90 passed`
- Full Python suite: `84 passed`
- Changed-file Ruff: passed
- Frontend production build: passed, 1,804 modules transformed
- Goal audit and `git diff --check`: passed
- UE 5.8 `ArtFlowBridgeHostEditor` rebuilt successfully after removing misleading approval language

## Autonomy correction

The UE menu previously described a completed export as a “read-only review.” That was informational,
not a runtime permission check, but it encoded the wrong product model. The source, repository rules
and durable goal now state that project-local candidate adoption, bounded revision, Unreal return and
local release are orchestrator-owned. Preview surfaces cannot create an approval interrupt.

## Truth boundary

This slice proves a real attractive-invalid result, independent bounded multimodal claims, visible
critic/guard disagreement, deterministic precedence and replay without regeneration. It does not yet
prove production-candidate adoption, mask-bounded revision, Unreal return, recovery scorecards,
governed memory or C2PA delivery.
