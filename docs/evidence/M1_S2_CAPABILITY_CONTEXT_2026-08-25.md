# M1-S2 bounded capability and context evidence

Date: 2026-08-25  
Evidence level: A2 — deterministic local execution with a frozen Scene Package fixture  
Real model, network, GPU and paid provider used: no

## Outcome

ArtFlow now has a small hand-built Agent Harness above the event kernel:

- `CapabilityRegistry` is a typed allow-list whose entries expose input/output schemas, read/write
  authority, availability, risk, idempotency, timeout, observation limit and an independent
  verification signal;
- duplicate IDs and unknown or unavailable capabilities fail before the executor is invoked;
- inputs and outputs are validated by Pydantic and oversized observations fail closed;
- `ContextAssembler` keeps cache-stable rules and tool schemas separate from the dynamic task,
  reducer status, recent bounded summaries and content-addressed artifact citations;
- `OfflineCoordinator` proves decide → validate → reserve budget → execute → observe → verify while
  all authoritative changes continue to pass through `AgentEventStore`;
- iteration and tool-call usage are event-reduced, code-enforced and reconstructed after restart;
- pending tool calls and verified observations are explicit durable state rather than model prose;
- the model-facing `AgentDecision` is only a proposal and has no state mutation field.

The public network-free demonstration entrypoint is:

```text
artflow run-offline-agent-step <run-id>
```

## Verification

```text
python -m ruff check src/artflow_agent/agent_runtime.py src/artflow_agent/agent_harness.py src/artflow_agent/cli.py tests/test_agent_runtime.py tests/test_agent_harness.py
All checks passed

python -m pytest tests/test_agent_runtime.py tests/test_agent_harness.py tests/test_run_store.py tests/test_scene_packages.py -q
12 passed

powershell -ExecutionPolicy Bypass -File scripts/validate.ps1 -Tier quick
40 passed in 1.30s
```

The focused failure cases prove that an unavailable or unknown capability does not execute, a
duplicate registry entry is rejected, large payloads are not needed in context, and replay cannot
reset an exhausted tool or iteration budget.

## Evidence ceiling

This proves the local deterministic Harness spine and a read-only capability loop. It does not yet
prove a real model decision, streamed UI event protocol, provider side-effect recovery, distributed
durability, or a real Unreal-originated package. Those remain later milestones.
