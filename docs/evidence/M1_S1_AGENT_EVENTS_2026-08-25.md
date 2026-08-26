# M1-S1 durable Agent event evidence

Date: 2026-08-25  
Evidence level: A2 — deterministic local execution with frozen Scene Package fixtures  
Real host, GPU and paid provider used: no

## Outcome

ArtFlow now has a hand-built SQLite event kernel alongside the retained v0 `RunStore`:

- `AgentEventStore` appends content-hashed events in a `BEGIN IMMEDIATE` transaction;
- `(run_id, idempotency_key)` is unique in the same database write that records the event;
- the current event chain is verified and the candidate transition is reduced while the SQLite
  write lock is held, preventing incompatible concurrent transitions;
- a verified `ScenePackagePreview` becomes a `scene_attached` event bound to the archive SHA-256;
- reopening the database reconstructs the same `AgentRunState` from events only;
- route-approval interrupts survive restart and can be resolved through typed events;
- the code-generated status bar reports stage, approval, pending decisions, failure count, budgets
  and content-addressed Scene Package artifacts;
- modified JSON payloads, broken hashes, illegal transitions and expected-hash mismatches fail
  before reduction;
- the legacy JSON `RunStore` and real v0 run format were not rewritten.

## Public development entrypoints

```text
artflow create-agent-run
artflow attach-scene-package
artflow agent-status
```

These commands use `runs/agent-events.sqlite3` by default and do not call a model, ComfyUI or a
hosted provider.

## Verification

```text
powershell -ExecutionPolicy Bypass -File scripts/validate.ps1 -Tier quick
36 passed in 1.31s

python -m ruff check src/artflow_agent/agent_runtime.py src/artflow_agent/cli.py tests/test_agent_runtime.py
All checks passed
```

Targeted cases cover restart equivalence, idempotent duplicate attachment, persisted pending
approval, approval resolution, illegal transition, expected archive hash mismatch and mutation of a
stored SQLite event.

## Evidence ceiling

This proves a local durable state and replay boundary. It does not yet prove model-driven planning,
capability selection, tool execution, crash recovery across a real provider, distributed durability
or a real Unreal-originated package. Those claims remain pending later slices.

