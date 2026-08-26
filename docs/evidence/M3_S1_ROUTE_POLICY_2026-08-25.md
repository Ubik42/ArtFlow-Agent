# M3-S1 matched-provider route policy evidence

Date: 2026-08-25  
Evidence level: A2 — deterministic fixtures, CLI, event replay and browser  
Provider execution used: no

## Outcome

- a normalized execution intent derives reference, depth, world-normal and object-ID controls,
  output dimensions/format/count and an art-intent hash from the same verified Scene Package;
- `route_scene_package` evaluates typed local and hosted candidates for availability, task support,
  controls, privacy ceiling and cost ceiling before deterministic ranking;
- the selected provider and every rejected alternative carry machine-readable reason codes;
- `RouteDecision.approval_fingerprint()` now binds provider, model, package content, normalized
  execution intent, privacy ceiling and cost ceiling;
- `route_proposed` persists the complete decision and creates the human interrupt through the
  event reducer;
- `assert_route_authorized` rejects any execution intent whose bound fingerprint changed;
- the offline CLI `propose-offline-route` exposes the policy without calling a provider;
- Scene Lab projects the real bound provider/model/privacy/cost fields into the approval surface.

The checked example chose `comfy-local/flux-depth-local` and rejected
`frontier-image-fixture/frontier-edit` because its availability remained unknown. This is a fixture
policy proof, not a claim that either model is installed or executed.

Browser evidence: `artifacts/goal/m3-s1-bound-route.png`.

## Verification

```text
python scripts/export_contract_schemas.py --check
passed

python -m ruff check <focused contracts, routing, runtime, projection, CLI and tests>
All checks passed

python -m pytest <focused M0-M3 policy, replay and compatibility tests> -q
22 passed

npm run build
Vite production build passed

powershell -ExecutionPolicy Bypass -File scripts/validate.ps1 -Tier quick
47 passed in 1.83s
```

## Evidence ceiling

This proves route policy and approval binding only. Hosted availability is intentionally unknown,
the local fixture model identity is not yet attested against ComfyUI, and no provider ran.
