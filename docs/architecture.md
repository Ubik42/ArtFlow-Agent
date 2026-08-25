# Architecture

This document describes the retained v0 implementation. The accepted target architecture and
migration order are defined in [PRODUCT_VISION_2026.md](PRODUCT_VISION_2026.md),
[REFACTOR_ROADMAP.md](REFACTOR_ROADMAP.md), and the ADR directory. New work must preserve this
working slice until a milestone exit proves its replacement.

ArtFlow separates probabilistic decisions from deterministic execution.

- `Planner`: turns an `ArtBrief` into reviewable directions.
- `Recipe catalog`: exposes only workflows compatible with the task and machine.
- `Comfy gateway`: inspects, validates, queues, monitors, and collects jobs.
- `Run store`: persists approvals, tool events, receipts, and artifacts outside model context.
- `Evaluator`: combines deterministic checks with a visual rubric.

Model-backed planning implements the existing `Planner` protocol. ComfyUI execution remains
behind typed adapters so tests never require a live GPU runtime.

## Implemented boundaries

```text
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
- `run_store.py` keeps mutable execution state and append-only events in `runs/<run-id>/`; it
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
- `delivery.py` packages only completed human-selected runs and writes a SHA-256 manifest alongside
  state, events, receipts and artifacts.
- `web_api.py` exposes only typed run operations; the React workbench cannot submit arbitrary
  workflow graphs and preserves the same approval gate as the CLI.

Tests use HTTP mock transports and local image fixtures. They do not need a model key, ComfyUI,
or a GPU.
