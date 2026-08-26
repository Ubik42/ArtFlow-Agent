# M4-S3 — Autonomous adoption and mask-bounded revision

Date: 2026-08-25

## Result

The Codex orchestrator autonomously adopted the uniquely strongest eligible production direction,
sealed a mask-bound revision request before generation, executed one real Codex built-in image edit,
and delivered a corrected composite with zero changed pixels outside the persisted editable mask.
No user approval interrupt was created.

## Evidence-backed adoption

- Decision: `adoption-94e130b6934d34a4606d`
- Decider: `codex-orchestrator`
- Selected role: `codex_image`
- Selected artifact: `a8430dc9b8290bd658dd276cc7e9a9c490ca6a25a5accff70145a2d6704f54d5`
- Base tribunal fingerprint: `4d762766256ccd4d5acdbc8358f0b5d906ea5c87fc8fb3eab0bbf217c7a51ad5`
- Multimodal tribunal fingerprint: `8ea5e5d0f1008a546226058927d9891cc1214ce1294c85b11d461e6682e82dca`
- Selected critic result: aesthetic `pass`, confidence `0.97`
- Persisted dissent: local Comfy has the stronger non-semantic edge-layout proxy,
  `0.998838` versus `0.419993`

The negative-control role is excluded by the adoption contract type and cannot enter ranking. Replaying
the decision retained event 12 and the same decision ID.

## Sealed revision request

- Revision: `revision-1f1bda22b84085443dcd`
- Request fingerprint: `916dab844b071db8ec304e2b59937eeca3318ff27914d3fc1420d5ef1ad1cb3e`
- Prompt SHA-256: `93d28aaec5715a0c1b8824ace3406593061260849abf83808f6cb37eb87228c6`
- Editable region: `editable-selection` / `Editable_Form`
- Protected region: `protected-selection`
- Mask SHA-256: `6ebf0948181b61c25ef1611cf0ab2ccd711314c324bffdc2f9d17a0ef413cb48`
- Mask dimensions: `1672 × 941`
- Editable pixels: `42,994` (`2.732637%` of the parent)
- Inputs supplied to the built-in edit: adopted parent plus binary editable mask

The UE object-ID capture contains shaded grayscale rather than a flat ID LUT. The mask compiler therefore
uses a reproducible right-connected-silhouette selection and conservative erosion. That limitation is
persisted; the pixel guard, not the weak object-ID interpretation, is authoritative for containment.

## Real built-in image edit

- Tool: Codex built-in image generation
- Requested family: `gpt-image-2`
- Raw output: `0bd4446d4eee0b48a412ee32e9fc80fa6b6f230e981471b069e1a351cf0b8d50`
- Raw dimensions: `1672 × 941`
- Observed model snapshot and upstream request ID: unavailable, retained as `null`
- Final composite: `97b697f3a8bfa8bf3c489ed12866d9330942fe495287c0fc088d62eef73d72e3`

The exact prompt is persisted at `artifacts/goal/m4-s3-bounded-revision/prompt.txt`. The final project-bound
raw and composite assets are under the same evidence directory; the result does not depend on the Codex
generated-image cache.

## Failure and recovery evidence

Attempt 1 used a hard binary paste. It passed mechanical leakage checks but visual inspection exposed a
visible seam because the source object-ID silhouette was slightly smaller than the generated parent sphere.
The attempt remains event 14 and its composite remains content-addressed; history was not rewritten.

Attempt 2 reused the exact same raw tool output and request. `feathered-inside-mask-v2` feathers only inside
the already authorized white region, superseding the visual failure as event 15. Re-running correction
reuses event 15 and performs no new image call.

## Pixel-exact verification

| Measure | Result |
|---|---:|
| Outside-mask pixels | `1,530,358` |
| Outside changed pixels | `0` |
| Inside-mask pixels | `42,994` |
| Inside changed pixels | `42,803` |
| Inside change ratio | `99.555752%` |

The verifier independently recomputes RGB difference between the adopted parent and final composite.
This proves containment only; it does not claim hidden 3D topology or semantic quality inside the mask.

## UI and API evidence

- Wide UI: `artifacts/goal/m4-s3-bounded-revision/scene-lab-wide.png`
- Narrow UI: `artifacts/goal/m4-s3-bounded-revision/scene-lab-narrow.png`
- 1440 px and 390 px viewports: no horizontal overflow
- Parent, final composite and mask loaded at their persisted `1672 × 941` dimensions
- Browser console: zero errors and warnings
- Content endpoints reject an unrecorded hash with `409`
- Scene Lab shows autonomous adoption, the compare slider, mask, attempt lineage and the zero-leak proof

The new capability panel is written in natural Simplified Chinese for the portfolio audience. The older
workspace still contains historical English UI and requires a later dedicated localization/refinement slice;
this slice does not misstate that broader interface as complete.

## Validation

- Full Python suite: `89 passed`
- Quick gate: `95 passed`
- Focused adoption/revision/runtime/API tests: `21 passed`
- Changed-file Ruff: passed
- Frontend production build: passed, 1,804 modules transformed
- Goal audit: passed

## Truth boundary

M4 now proves independent deterministic and multimodal evaluation, attractive-invalid rejection,
evidence-backed autonomous adoption, one real built-in revision, persisted failure correction and exact
outside-mask containment. It does not yet prove systematic crash recovery, OpenTelemetry correlation,
governed memory, frozen Harness evaluation, Unreal reimport or C2PA delivery.
