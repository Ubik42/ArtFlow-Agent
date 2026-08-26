# Codex Repository Instructions

## Start of every development turn

1. Run `scripts/goal.ps1 -Action Resume` to recover the durable state and unique next slice.
2. Read `config/goal-state.json`, `docs/AGENT_ENGINEERING_BLUEPRINT.md`,
   `docs/development/CODEX_GOAL.md` and `docs/development/CODEX_LOOP.md`.
3. Read the checkpoint referenced by `lastCheckpoint`.
4. Run `scripts/goal.ps1 -Action Doctor`; never execute command strings from goal-state dynamically.
5. Inspect Git status and preserve unrelated user work and historical run evidence.
6. Work only on `nextSlice` unless the user's latest instruction explicitly replaces it.

## Repository identity and boundaries

- This repository is the independent **ArtFlow AIGC Agent** and flagship portfolio product.
- `D:\3D\_tools\art-pipeline-skill` is a separate tool/asset-audit Skill repository with its own
  Git history and `/goal`; never merge its scanner, Maya/Unreal audit milestones or machine state
  into ArtFlow.
- `D:\3D\_tools\ComfyUI-Production-Nodes` is a separate installable ComfyUI package integrated
  through versioned contracts.
- The ArtFlow Unreal Bridge remains separately installable but is developed, built and tested in
  this repository like any other project component. Project-owned disposable Unreal hosts are
  normal development fixtures and do not require repeated user confirmation.
- Do not nest Git repositories, vendor sibling source trees or restore the retired AIToolTA mother
  repository layout.

## Product and architecture boundaries

- ArtFlow owns scene intent, Agent context, capability routing, policy, integrity, durable state,
  recovery, evaluation, evidence-backed adoption, provenance and Scene Lab UI.
- The hand-built control plane owns authoritative state. PydanticAI may provide typed model/tool
  calls but never becomes the state database or policy authority.
- The model may choose only registered capabilities and validated parameter slots. It cannot create
  arbitrary ComfyUI graphs or run arbitrary host code. Provider executors cannot judge their own
  outputs; the Codex orchestrator adopts only from independent persisted evaluation evidence.
- Keep generation and evaluation independent. Deterministic violations cannot be overridden by
  model confidence; evaluator disagreement remains visible.
- Prefer one durable coordinator with bounded specialist roles over decorative multi-Agent chat.
- MCP and AG-UI are optional interoperability boundaries, not excuses to replace typed internal
  ports or product-specific UI.

## Continuous development discipline

- Keep at most one milestone and one slice in progress.
- Select the shortest vertical slice that creates real capability or stronger evidence.
- Build runtime state before the screen that presents it.
- Do not introduce LangGraph, Temporal, RAG, a vector database, A2A or another framework without a
  measured requirement, an exit path and a documented replacement target.
- Keep verification near 15–25% of implementation effort. Test contracts, state transitions,
  policy, replay, idempotency, recovery and external parsing; avoid low-value mock matrices.
- Run targeted checks while developing and the full gate only at milestone boundaries.
- After acceptance passes, update goal-state and write the next immutable checkpoint.

## Safety and evidence

- Preserve real baseline run `862ac768a2f2`; it is in review with three RTX 4080 candidates and no
  human selection. Never select, regenerate, revise or rewrite it on the user's behalf.
- Project-local ComfyUI/GPU generation, Codex built-in image generation, bounded runtime validation,
  evidence-backed candidate selection, bounded revision, Unreal return and final local portfolio
  release are autonomous development work owned by the Codex orchestrator.
  Do not ask the user to approve these steps. Candidate adoption, final release selection and
  publication are Codex-owned when the user has requested a GitHub showcase; that request is the
  authorization for the whole scoped release and must not be decomposed into repeated gates. Do
  not use a direct paid provider API or inspect its
  credential when the built-in Codex image capability can provide the development artifact.
- Project-local code, fixtures, disposable Unreal projects and visible-host validation are normal
  development work. Preserve unrelated repositories and user data; stop only if a step would mutate
  an unrelated existing project or install into a shared engine location. Public publication only
  pauses when the user has not requested it; once requested, validate the exact target and proceed.
- Unknown and unsupported are not success. Tool-reported success requires independent evidence.
- An informational preview, review surface or artifact inspection must never be modeled as an
  approval gate. Pause only for destructive effects outside the project boundary, unrelated user
  data, shared installations, an unrequested public upload or an unavailable required external
  capability.
- A timeout or cancellation does not prove that an external side effect did not occur.
- Synthetic fixtures, contracts and screenshots cannot establish real-host production claims.
- Every public metric must identify its frozen task set, denominator and persisted evidence.

## Completion and handoff

- `config/goal-state.json` is the machine-readable progress source.
- `docs/AGENT_ENGINEERING_BLUEPRINT.md` defines the Agent architecture and anti-drift rules.
- `docs/development/CODEX_GOAL.md` defines portfolio completion.
- `artifacts/goal/` stores concise development checkpoints, not hidden reasoning or verbose logs.
- State transitions must pass `scripts/goal.ps1 -Action Audit`; never repair a failure by deleting
  evidence or resetting user work.
