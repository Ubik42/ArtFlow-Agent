# M4-S1 — Replayable independent tribunal foundation

Date: 2026-08-25

## Result

The two real M3 candidates now share one immutable evaluation dossier. Two separately named deterministic evaluators emit typed claims and limitations. The reducer persists the aggregate as event 9, and neither evaluator selects a winner.

## Dossier

- Dossier: `tribunal-cb27aaf04613ab68d36d`
- Dossier SHA-256: `ff89b99691fb7edc16993c42c274a38683c5aa922afa774e09e107f8656ff19d`
- Scene archive: `130c94284deb5fddb18c52d604b615ca1a071e42afc8149604f76130fe412f76`
- Unreal beauty: `f6d4005de3b73fa0a59b63f2924e76f40cede01797187f2527f6d45d74d466d9`
- Local Comfy candidate: `8029f4a558e3bfefbbfa0f63a513c640d3080e31574ecfba9f0eb98ff6cd13e7`
- Codex image candidate: `a8430dc9b8290bd658dd276cc7e9a9c490ca6a25a5accff70145a2d6704f54d5`
- Report: `artifacts/goal/m4-s1-tribunal/tribunal-report.json`

## Independent claims

`integrity_guard/1.0.0` hashes persisted bytes against receipt identity. This is a hard eligibility gate and makes no quality claim.

`composition_guard/1.0.0` reports:

- aspect-ratio drift as a hard framing gate;
- cosine similarity of autocontrasted `FIND_EDGES` images normalized to `64 × 36` as a non-hard appearance/layout proxy.

The proxy explicitly does not claim semantic geometry or camera-pose preservation.

| Candidate | Hash | Aspect drift | Coarse edge-layout proxy | Eligible | Adopted |
|---|---:|---:|---:|---|---|
| Local ComfyUI | pass | `0.000000` | `0.998838` | yes | no |
| Codex GPT Image 2 | pass | `0.000531` | `0.419993` | yes | no |

The different proxy values are visible disagreement evidence, not a winner decision.

## Recovery and hard-failure evidence

- First evaluation appended `tribunal_report_recorded` as event 9.
- Re-running the evaluator leaves the stream at 9 events and reuses the same dossier/report.
- A focused tamper case proves a candidate with matching visual proxy but mismatched bytes is ineligible; aggregate state cannot override the failed hash gate.
- Adoption remains `unselected` in both report and Scene Lab.

## UI and validation

- Wide tribunal: `artifacts/goal/m4-s1-tribunal/tribunal-wide.png`
- Narrow tribunal: `artifacts/goal/m4-s1-tribunal/tribunal-narrow.png`
- Wide viewport: no horizontal overflow at 1440 px
- Narrow viewport: no horizontal overflow at 390 px; all three claims become full-width cards
- Browser console: zero errors and zero warnings
- Focused tribunal/Agent/API tests: `13 passed`
- Full Python suite: `83 passed`
- Changed-file Ruff: passed
- Frontend production build: passed, 1,804 modules transformed

## Truth boundary

This slice proves replayable evidence binding, deterministic hard-failure precedence, separated evaluator identities, narrowly stated visual proxies and visible disagreement. It does not yet prove multimodal semantic critique, attractive-invalid rejection, winner adoption, bounded revision or Unreal return.
