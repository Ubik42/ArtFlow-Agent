# M2-S2 live typed events and persisted approval evidence

Date: 2026-08-25  
Evidence level: A2 — local SSE, browser and event-store interaction  
GPU or paid provider used: no

## Outcome

- `/api/agent/runs/{run_id}/stream` emits bounded `agent-ui-event/1` SSE envelopes for replayed
  run events, reducer snapshots and human interrupts;
- stored sequence IDs and the `after` cursor allow clients to resume without treating transport
  messages as state authority;
- Scene Lab listens for typed event names and refreshes its reducer-backed projection;
- a pending `route_approval` opens a factual modal with decision identity, content fingerprint,
  human-only authority and explicit state effect;
- approve and reject endpoints append through `AgentEventStore`; neither path starts generation;
- an approved state survived a browser reload and the dialog did not return;
- unknown/corrupt run behavior and all v0 endpoints remain intact.

Browser evidence: `artifacts/goal/m2-s2-route-approval.png`.

## Verification

```text
python -m ruff check <focused Agent projection, stream, API and tests>
All checks passed

python -m pytest <focused Agent, API, RunStore and Scene Package tests> -q
18 passed

npm run build
Vite production build passed

powershell -ExecutionPolicy Bypass -File scripts/validate.ps1 -Tier quick
44 passed in 1.60s
```

The real browser flow opened a six-event pending interrupt, approved its exact fingerprint, received
the resulting typed update, reloaded and reconstructed the approved seven-event state. The console
reported 0 errors and 0 warnings.

## Evidence ceiling

This proves local event streaming and durable human approval. It does not prove distributed event
delivery, provider execution, crash reconciliation or candidate comparison in the new Agent path.
