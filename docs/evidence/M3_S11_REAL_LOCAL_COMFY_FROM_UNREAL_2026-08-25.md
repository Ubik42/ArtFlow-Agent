# M3-S11 — Real local Comfy execution from Unreal evidence

Date: 2026-08-25

## Result

The exact M3-S10 Unreal archive ran once through the reviewed
`composition-preserving-v1@1.1.0` recipe on the existing local ComfyUI/RTX 4080 runtime. The local
route crossed no permission prompt: deterministic policy, source hashes, recipe slots and live
environment attestation were the execution boundary.

## Bound identities

- Scene archive SHA-256: `130c94284deb5fddb18c52d604b615ca1a071e42afc8149604f76130fe412f76`
- Run: `local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb`
- Execution: `exec-130c94284deb5fddb18c`
- Route fingerprint: `e3447db845897fff202cf8294ec10664f1ce9c22afe195418e6fa522b2d0c652`
- Environment fingerprint: `fb554b803670614980b91e4b8eea209796e6a415b8f1e6e48bf50df4660afee0`
- ComfyUI prompt ID: `0f515f4b-d465-4132-ae72-b3ceb5dba465`
- Candidate SHA-256: `8029f4a558e3bfefbbfa0f63a513c640d3080e31574ecfba9f0eb98ff6cd13e7`
- Candidate dimensions: 1024 × 576 PNG

The 640 × 360 evidence capture and 1024 × 576 provider output are intentionally separate. They
preserve the same 16:9 composition while satisfying the reviewed recipe's output constraints.

## Durable execution evidence

The SQLite event stream contains seven ordered facts:

1. run created;
2. verified scene attached;
3. local route deterministically accepted;
4. live capability attested;
5. execution reserved before the side effect;
6. ComfyUI prompt identity recorded;
7. receipt and candidate hash verified.

Running the same integration entry point again reconstructed the terminal state and verified the
content-addressed candidate. Event count remained `7 → 7`; no upload or prompt submission was
repeated. Existing failure-injection tests continue to prove that a lost response becomes
`completion_unknown` and reconciliation does not duplicate the provider request.

## Scene Lab evidence

Scene Lab now serves a provider artifact only when its bytes match a successful persisted receipt.
A tampered local file returns HTTP 409. The real run displays:

- UE source and local candidate in an interactive split view;
- provider/model, prompt ID, output hash and `UNSELECTED / tribunal pending` state;
- real Unreal provenance, route facts and live RTX 4080 attestation;
- all seven reducer-replayed events, including autonomous local policy acceptance.

Browser checks at 1440 px and 390 px found no horizontal overflow, both images decoded at their
real dimensions, and the final reload reported zero console errors.

- `artifacts/goal/m3-s11-real-local-wide.png`
- `artifacts/goal/m3-s11-real-local-narrow.png`
- `artifacts/goal/m3-s11-local-run/final-state.json`
- `artifacts/goal/m3-s11-local-run/compiled-request.json`

## Evidence ceiling

This proves one real Unreal-originated local generation, not artistic success. The conservative
candidate remains deliberately unselected until independent evaluation exists. It does not prove a
Codex GPT Image 2 comparison, tribunal judgment, revision, Unreal return or final adoption.
