# Architecture

ArtFlow separates probabilistic decisions from deterministic execution.

- `Planner`: turns an `ArtBrief` into reviewable directions.
- `Recipe catalog`: exposes only workflows compatible with the task and machine.
- `Comfy gateway`: inspects, validates, queues, monitors, and collects jobs.
- `Run store`: persists approvals, tool events, receipts, and artifacts outside model context.
- `Evaluator`: combines deterministic checks with a visual rubric.

Model-backed planning will implement the existing `Planner` protocol. ComfyUI execution will remain behind typed adapters so tests never require a live GPU runtime.

