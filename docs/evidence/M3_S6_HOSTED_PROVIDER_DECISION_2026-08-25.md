# M3-S6 current hosted-provider decision and authorization dossier

Date: 2026-08-25  
Evidence level: A2 — current official documentation plus locally validated decision artifact  
Credential inspection, upload, generation or paid call used: no

## Result

OpenAI Images API with fixed model snapshot `gpt-image-2-2026-04-21` is selected for the portfolio
demo adapter. The decision compared it with `gemini-3.1-flash-image` using current official model,
editing, output-size, price, retention, background-state and provenance documentation.

The decisive fit is exact 1280×720 support, high-fidelity image editing, a fixed model snapshot and
official C2PA plus SynthID output claims. Gemini is cheaper and has retrievable background
Interactions, but background mode requires stored state (55 days by default, configurable down to
7) and the reviewed API exposes no client idempotency-key lookup.

OpenAI Images also exposes no documented client idempotency key or job lookup. ArtFlow therefore
does not claim exactly-once hosted execution: a connection loss after request transmission becomes
unknown completion, consumes its authority and cannot be automatically retried. This is persisted
as policy rather than hidden behind a generic retry.

Full sourced decision: `docs/decisions/M3_S6_HOSTED_PROVIDER_DECISION_2026-08-25.md`.

## Bounded dossier

`artifacts/goal/m3-s6-live-run-authorization.json` is validated by
`LiveRunAuthorizationDossier` and records:

- `authorization_state=awaiting_user` and every action `authorized=false`;
- fixture-level Scene Package evidence, not a claimed Unreal capture;
- local recipe and real Comfy capability-attestation fingerprint;
- fixed hosted model, endpoint, privacy class and credential variable name without reading a value;
- only `beauty` permitted remotely; depth, world-normal and object-ID remain local-only;
- one medium 1280×720 PNG and USD 0.25 ArtFlow ceiling, explicitly not provider-enforced;
- unresolved organization verification, ZDR, exact cost, real Unreal capture and Unreal write
  authority.

The generated `live-run-authorization-dossier/1` JSON Schema makes this boundary reviewable outside
Python. Tests prove the dossier cannot mark its own actions authorized or expand the upload
allowlist to auxiliary passes.

## Verification

```text
python -m ruff check <dossier model, test and schema exporter>
All checks passed

python -m pytest <dossier, hosted boundary and routing tests> -q
11 passed in 0.80s

powershell -ExecutionPolicy Bypass -File scripts/validate.ps1 -Tier quick
65 passed in 2.47s

python scripts/export_contract_schemas.py --check
generated schemas synchronized
```

## Evidence ceiling

This proves a current, source-backed provider decision and an unexecuted authorization boundary. It
does not prove credential readiness, live API compatibility, exact billed cost, output quality or
real-provider success. The research also exposed that current routing conflates generation controls
with local evaluation passes; real approval must wait for that contract correction.
