# M3-S3 crash-safe provider execution ledger

Date: 2026-08-25  
Evidence level: A2 — deterministic offline failure injection  
Real prompt queue, upload, GPU generation, hosted call or Unreal write used: no

## Proven behavior

The provider coordinator now persists an execution reservation and idempotency key before the
provider can observe a submission. Reservation is rejected unless the exact route fingerprint has
a persisted approval and a content-valid, supported capability attestation for the selected
provider and model.

The durable reducer reconstructs these states from SQLite events:

- `reserved` before any external side effect;
- `submitted` after the external request identity is known;
- `completion_unknown` when observation times out or disappears;
- terminal `succeeded`, `failed` or `cancelled` only after a normalized receipt is accepted.

Failure injection crashes the coordinator after the simulator accepts the request but before the
local acknowledgement is written. On restart, lookup by the previously persisted idempotency key
recovers the external request and the submit counter remains one. A running observation becomes
unknown completion rather than assumed failure, so retry performs reconciliation instead of blind
resubmission.

Before success becomes authoritative, the coordinator independently fetches every receipt artifact
and checks its SHA-256. The event store separately checks execution identity, approved route
fingerprint, provider/model identity and provider request identity. A tampered artifact and a
mismatched receipt both fail closed.

The typed projection now includes the execution ledger, summary status and lifecycle timeline for
Scene Lab consumers. This slice adds no provider-specific network adapter and makes no claim of a
real generation.

## Verification

```text
python -m ruff check <runtime, attestation, projection, execution and focused tests>
All checks passed

python -m pytest tests/test_provider_execution.py tests/test_agent_projection.py -q
7 passed in 1.12s

python -m pytest -q
47 passed in 1.98s

powershell -ExecutionPolicy Bypass -File scripts/validate.ps1 -Tier quick
53 passed in 2.04s
```

## Evidence ceiling

This proves offline orchestration and recovery semantics against a stateful simulator. It does not
prove ComfyUI queue compatibility, a real GPU result, a hosted provider result or Unreal reimport.
