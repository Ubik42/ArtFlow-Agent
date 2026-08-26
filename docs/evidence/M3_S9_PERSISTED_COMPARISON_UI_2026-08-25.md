# M3-S9 persisted comparison lifecycle and Scene Lab review surface

Date: 2026-08-25  
Evidence level: A2 — append-only recorded state plus local browser verification  
Real provider, GPU generation, credential inspection or Unreal write used: no

## Durable control-plane result

The Agent event vocabulary now includes `comparison_planned`, `comparison_authorized` and
`comparison_manifest_recorded`. Their payloads are validated against the comparison contracts,
content-bound to the Scene Package and exact plan fingerprint, appended idempotently and rebuilt by
the deterministic reducer after restart.

A comparison plan creates a dedicated `comparison_authorization` interrupt. The legacy route
approval endpoint explicitly refuses that interrupt, closing a potential authority bypass. The
dedicated API accepts only a human-owner identity; action IDs, dossier hash and plan fingerprint are
derived from the persisted pending plan, so a client cannot expand approval to Unreal return or a
different provider action. Repeating the same API operation reuses the recorded authorization.

Typed run projections and SSE snapshots expose the plan, authorization and manifest without raw
provider payloads, event hashes or hidden reasoning.

## Scene Lab result

Following the updated frontend fast-path skill, the UI uses a visual production topology rather
than another dashboard card grid:

- the Scene Package and art intent form a shared central origin;
- local Comfy and hosted OpenAI occupy separate cyan and amber execution rails;
- each rail exposes its own model, upload, output contract, authority and terminal state;
- the review sheet shows exact cost/privacy/upload consequences and requires the human to type an
  owner identity before the button enables;
- successful and unknown-completion manifests remain explicitly unselected;
- the evidence lens shows only persisted preview facts and unresolved real-host limitations.

The local recorded-state seeder creates awaiting, authorized, succeeded and
`needs_human_recovery` states without touching either provider.

## Verification

```text
ruff check <M3-S9 backend, tests, fixture seeder and schema exporter>
All checks passed

python -m pytest -q
77 passed in 3.31s

powershell -File scripts/validate.ps1 -Tier quick
83 passed in 3.57s

web/npm run build
TypeScript and Vite build passed
```

Playwright verified all four persisted lifecycle states at 1440×1000 and 390×844. It exercised the
owner-identity form and dedicated authorization endpoint, observed the session list update from
awaiting to approved, found zero console errors/warnings, and measured zero horizontal overflow at
390px.

Visual evidence:

- `artifacts/goal/m3-s9-recovery-wide.png`;
- `artifacts/goal/m3-s9-approval-wide.png`;
- `artifacts/goal/m3-s9-approval-narrow.png`;
- `artifacts/goal/m3-s9-authorized-narrow.png`;
- `artifacts/goal/m3-s9-success-wide.png`.

## Evidence ceiling

This proves event persistence, authorization scoping, typed projection and browser behavior against
recorded fixtures. It does not prove a real Unreal capture, actual GPU/provider execution, billed
cost, provider provenance, human candidate adoption or Unreal reimport. The UI labels fixture facts
and never presents them as a live comparison.
