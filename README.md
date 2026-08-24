# ArtFlow Agent

ArtFlow Agent is an AIGC-first portfolio project for game-art iteration. It uses an agent as the control layer and ComfyUI as the generation runtime.

The target loop is:

```text
art brief -> environment inspection -> recipe selection -> approval
          -> ComfyUI execution -> candidate evaluation -> human selection
          -> directed revision -> reproducible run package
```

## Current status

Foundation scaffold. The repository currently provides typed domain models, a deterministic planning seam, a ComfyUI health check, an example brief, and tests. Model-backed planning and workflow execution are the next milestones.

## Principles

- A narrow game-art task instead of a general-purpose chatbot.
- Validated workflow recipes instead of unrestricted graph generation.
- Typed tools and explicit side-effect boundaries.
- Human approval before generation cost or final asset adoption.
- External run state, receipts, and reproducible artifacts.
- Technical checks and visual judgment are evaluated separately.

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\artflow validate-brief examples\brief.example.json
.\.venv\Scripts\pytest
```

Check a local ComfyUI instance:

```powershell
.\.venv\Scripts\artflow doctor --comfy-url http://127.0.0.1:8188
```

## Repository layout

```text
src/artflow_agent/   Typed models, ports, planning and CLI
examples/            Copyright-safe example inputs
recipes/             Reviewed ComfyUI workflow recipes
tests/               Fast deterministic tests
docs/                Architecture and delivery notes
runs/                 Local runtime state; ignored by Git
outputs/              Generated images and packages; ignored by Git
```

## Roadmap

1. Add ComfyUI object-info and queue adapters.
2. Add two reviewed recipes: composition-preserving variants and masked refinement.
3. Add PydanticAI planning behind the existing `Planner` protocol.
4. Persist run state and generation receipts.
5. Add candidate contact sheets, human selection, and trajectory evals.

