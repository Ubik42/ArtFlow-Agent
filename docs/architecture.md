# Architecture

This document records the retained v0 implementation. The current target architecture and product
order are defined in [PRODUCT_VISION_2026.md](PRODUCT_VISION_2026.md),
[PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md), and the ADR directory. New work must preserve proven
contracts and evidence while moving user entry points toward live Scene Sessions.

The active product path separates probabilistic direction from deterministic scene execution:

```text
Unreal Scene Digital Twin + explicit intent
  -> deterministic Scene Session draft
  -> typed multi-domain Scene Delta
  -> isolated Unreal candidate stage
  -> technical judge + visual critic
  -> failed-domain correction
  -> reconciled publish
```

The append-only Agent event store and reducer own state; Scene Session, MCP and the browser are typed
projections over that control plane. `scene_session.py` provides content-addressed drafts, persistent
Session identity and deterministic candidate-stage requests. A stage request is an execution input,
not a completion receipt; scene writes continue through registered Unreal tools and never through
browser-authored code.

The original v0 compatibility path remains readable and separates probabilistic decisions from
deterministic execution:

- `Planner`: turns an `ArtBrief` into reviewable directions.
- `Recipe catalog`: exposes only workflows compatible with the task and machine.
- `Comfy gateway`: inspects, validates, queues, monitors, and collects jobs.
- `Run store`: persists approvals, tool events, receipts, and artifacts outside model context.
- `Evaluator`: combines deterministic checks with a visual rubric.

Model-backed planning implements the existing `Planner` protocol. ComfyUI execution remains
behind typed adapters so tests never require a live GPU runtime.

## Implemented boundaries

```text
Retained v0 compatibility path
ArtBrief
  -> Planner (deterministic or PydanticAI)
  -> RunPlan + explicit approval
  -> RecipeCatalog (reviewed graph + allowlisted slots)
  -> ComfyGateway (inspect / queue / wait / collect)
  -> GenerationReceipt + Candidate records
  -> contact sheet + human selection
  -> trajectory evaluation
```

- `planning.py` reasserts project name, variant count, recipe choice, approval, and user-owned
  constraints after model output. The model cannot relax these invariants.
- `recipes.py` rejects undeclared workflow edits and validates node, model, and VRAM compatibility
  before queueing.
- `run_store.py` keeps the legacy mutable execution state and append-only events in `runs/<run-id>/`; it
  rejects generation before approval and selection before review. A revision can only inherit the
  recorded artifact from a completed, human-selected parent run.
- `execution.py` hashes the exact instantiated graph and records resolved inputs, runtime/model/node
  fingerprints, timestamps, and ComfyUI outputs.
- `batch.py` uploads the source once, skips completed directions on retry, persists direction-level
  failures, downloads outputs, and moves the run to review only after every direction completes.
- `review.py` keeps deterministic trajectory checks separate from future visual-quality judgment.
- `evaluation.py` measures resolution, aspect ratio, edge-structure similarity, dynamic range, and
  optional unmasked-region stability without spending model tokens. Its separate PydanticAI visual
  evaluator is invoked only through an explicit model-bearing command and cannot change run state.
- `delivery.py` packages legacy completed, selected runs and writes a SHA-256 manifest alongside
  state, events, receipts and artifacts.
- `web_api.py` exposes legacy run operations plus reducer-projected Agent and Scene Session operations;
  the React workbench cannot submit arbitrary workflow graphs or host code. Historical cost/privacy
  authority contracts remain limited to the external Provider boundary and are not a local UI gate.

Tests use HTTP mock transports and local image fixtures. They do not need a model key, ComfyUI,
or a GPU.
