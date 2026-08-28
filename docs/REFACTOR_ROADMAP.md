# ArtFlow Agent refactor roadmap

This roadmap uses a strangler migration. The current working ComfyUI vertical slice remains
runnable while the hand-built Agent harness replaces legacy state and UI from the edges. Do not
perform a big-bang rewrite.

The architectural definition and portfolio evidence matrix live in
[AGENT_ENGINEERING_BLUEPRINT.md](AGENT_ENGINEERING_BLUEPRINT.md).

## Phase II roadmap — Unreal 3D scene transformation

M0–M6 below are completed and remain the regression/evidence base. The active roadmap begins at M7;
the exact current slice lives in `config/goal-state.json`.

### M7 — Scene Digital Twin and staged Scene Delta kernel

Status: completed on 2026-08-27.

- **M7-S1** extends the real UE package with actors, bounds, materials, lights, PCG, Data Layers and
  protection fingerprints; it adds a DAG contract limited to lighting and approved-PCG dry runs.
- **M7-S2** creates a run-specific staging layer or candidate level and executes deterministic
  lighting/PCG operations with receipts, same-camera render and cleanup.
- **M7-S3** adds independent 3D validation and failed-domain correction without changing source
  actors or replaying successful branches.

Exit evidence: one real UE 5.8 fixture can stage, validate, rerender, correct and publish or discard
a lighting + PCG scene delta while source fingerprints remain unchanged.

### M8 — ComfyUI production graph and PBR material route

Status: in progress from 2026-08-27. M8-S1 is complete; real texture execution and Unreal material
return remain.

- **M8-S1 completed:** versioned and probed `ComfyUI-Production-Nodes` through real `/object_info`,
  pinned 19 node-schema fingerprints and compiled only declared slots into one hashed 49-node graph;
- **M8-S2 active:** execute the reviewed graph, validate real texture artifacts and build the staged
  Unreal Material Instance with idempotent return evidence;
- generate or transform one PBR map set and build an Unreal Material Instance in staging;
- validate channel semantics, texture settings, hashes and same-camera visual effect.

Exit evidence: a real Comfy run and real UE material instance are connected by a content-addressed
receipt; missing nodes or invalid maps fail closed before scene publish.

### M9 — PCG, lighting and asset closed loop

- turn a concept target into a dependency graph across lighting, PCG, existing assets and material;
- prepare independent branches concurrently while serializing Unreal writes;
- enforce protected actors, walkable bounds, collision, actor-count and rendering budgets;
- rerender, compare, correct only failed domains and publish a Scene Delta.

Exit evidence: the project-owned “废墟祭坛视觉开发” demo produces a visibly changed 3D scene and a
Chinese screenshot-rich evidence trail, not a preview-plane substitution.

### M10 — MCP, image-to-3D experiment and public release

- project the existing runtime through thin MCP resources and narrow tools;
- integrate one optional GLB-generating Provider and validate it through Interchange;
- prove the main PCG/lighting route still works when 3D generation is unavailable or rejected;
- redesign the Chinese Scene Lab around the stable 3D event contract and publish the case study.

Exit evidence: an external MCP host can inspect and invoke the same bounded run; one generated mesh
is admitted or rejected with explicit license/geometry/material/collision evidence; public claims
clearly distinguish completed, experimental and planned capability.

## Baseline that must keep working

- deterministic brief planning and optional PydanticAI planning;
- reviewed ComfyUI recipes with allowlisted slots;
- live `/system_stats` and `/object_info` preflight;
- autonomous project-local GPU execution after deterministic recipe, input and environment checks;
- resumable direction-level execution and external receipts;
- candidate review, deterministic checks and delivery packaging;
- local React workbench;
- run `862ac768a2f2` as the real RTX 4080 baseline.

The baseline remains a regression fixture until the Unreal-originated loop supersedes it. Its
incomplete human selection is recorded honestly and must not be rewritten as a completed run.

## M0 — contracts and migration seams

Status: complete as of 2026-08-25.

- `scene-constraint-package/1`, provider manifest, route decision, approval grant and provider
  receipt contracts;
- fingerprint-bound approval invalidated by provider, model, input, privacy or cost changes;
- local Comfy execution behind an explicit provider adapter;
- Python, TypeScript/Ajv and compiled Unreal C++ contract validation;
- safe read-only Scene Package ZIP inspection with hash and traversal checks;
- relocated v0 artifacts remain readable without rewriting historical evidence.

Exit evidence is recorded in `docs/evidence/M0_CONTRACTS_2026-08-25.md`.

## M1 — hand-built Agent kernel and scene context

Build the smallest complete Harness spine before adding another provider or redesigning the UI.

Progress as of 2026-08-25:

- M1-S1 completed the SQLite append-only event store, in-transaction reducer validation, Scene
  Package content binding, persisted route-approval interrupt and code-generated status bar;
- M1-S2 completed the bounded typed Capability Registry, stable/dynamic Context Engine, durable
  tool and iteration budgets, and a verified network-free Agent loop;
- the v0 JSON RunStore remains the compatibility layer and was not migrated or rewritten;
- M1 is complete; M2 begins by projecting these real events into the redesigned Scene Lab.

Deliverables:

- SQLite append-only Agent event store and deterministic reducer;
- typed lifecycle for intent, scene attachment, route proposal, interrupt, execution observation,
  evaluation, recovery and adoption;
- verified Scene Package bound to an AgentRun through a content identity;
- reducer-generated Agent status bar for stage, budgets, approvals, failures and artifacts;
- capability registry with supported/unsupported/unknown availability and tool risk metadata;
- PydanticAI model calls behind an interface; no model owns authoritative state;
- legacy v0 run remains readable during migration.

Exit evidence:

- restart reconstructs the same run and pending state from events;
- duplicate scene attachment is idempotent;
- invalid packages and illegal transitions fail closed;
- one offline Agent loop fixture performs decide → observe → verify without GPU or network.

## M2 — Scene Lab and typed Agent events

Structurally replace the legacy three-column workbench with **Scene Lab + Agent Flow**.

Progress as of 2026-08-25:

- M2-S1 shipped the versioned reducer-backed Agent projection API and the first scene-centric Scene
  Lab shell with a constraint field, replayed Agent Pulse, capability evidence and responsive
  legacy evidence mode;
- M2-S2 shipped bounded typed SSE replay/resume and a persisted fingerprint-aware human route
  approval that survives refresh without triggering generation;
- M2-S3 shipped the real-image A/B comparison surface, accessible direction switching and narrow
  layout while preserving the historical no-selection truth;
- M2 is complete; M3 starts with offline matched-provider routing before any explicitly approved
  real host execution.

Deliverables:

- large scene/candidate canvas with constraint and difference overlays;
- import → understand → route → approve → execute → judge → deliver flow;
- typed SSE lifecycle for runs, tools, state snapshots/deltas and interrupts, aligned with AG-UI
  concepts without turning the product into a chat UI;
- persisted route approval sheet with cost/privacy/model differences;
- large A/B, overlay and slider comparison;
- contextual inspectors and evidence drill-down;
- explicit loading, empty, degraded, recovery and reduced-motion states.

Exit evidence:

- refresh preserves a pending interrupt and current Agent state;
- the primary flow is usable without reading raw JSON or ComfyUI nodes;
- no console errors at target desktop and narrow layouts;
- a visible UI state maps to real event, receipt or evaluation data rather than invented demo text.

## M3 — real Unreal scene and matched provider routing

Create a separate installable Unreal Bridge in the ArtFlow repository and validate it with an
ArtFlow-owned disposable host project. This project-local development path is normal engineering
scope; only unrelated Unreal projects and shared engine installations remain out of bounds.

Progress as of 2026-08-25:

- M3-S1 shipped deterministic matched-provider filtering, rejected-alternative reason codes,
  normalized execution intent and approval fingerprints bound to provider/model/input/privacy/cost;
- M3-S2 attested the real local ComfyUI 0.28.0 / RTX 4080 environment through read-only preflight,
  verified every reviewed recipe dependency and projected the content-bound proof into Scene Lab;
- M3-S3 shipped the crash-safe provider execution ledger and proved durable-before-side-effect
  reservation, unknown-completion reconciliation, no duplicate submission after injected crash and
  independent receipt/artifact verification against an offline provider simulator;
- M3-S4 shipped a reviewed compiler, externally signed one-use authority gate and recorded HTTP
  receipt normalization;
- M3-S5 shipped a redacted hosted request compiler, signed privacy/cost authority packet and a
  recorded idempotent provider port through the same durable ledger;
- M3-S6 selected the fixed `gpt-image-2-2026-04-21` snapshot and produced a still-unauthorized,
  secret-free live-run dossier. It also exposed that route controls currently conflate generation
  inputs with local tribunal evidence; M3-S7 corrects that contract and maps the real OpenAI
  multipart response into the durable boundary before any live call.
- M3-S7 separated provider-consumed controls from local tribunal evidence, made reviewed recipes
  declare their actual controls, and shipped the exact synchronous OpenAI Images multipart adapter.
  Recorded tests preserve returned PNG provenance bytes, capture `x-request-id`, and prove that an
  ambiguous response consumes authority and becomes non-retriable unknown completion.
- M3-S8 shipped an operator-ready comparison plan and launcher: local Comfy and hosted OpenAI child
  runs share scene/intent identity but never share route, attestation, execution or authority. Both
  grants are prevalidated before either side effect, the adapters use one durable coordinator, and
  restart produces an unselected comparison manifest without repeating terminal or unknown work.
- M3-S9 made the comparison lifecycle append-only and visible. Plans, exact human-owner decisions
  and manifests replay into typed API/SSE projections; Scene Lab now uses a shared-scene spine and
  two sealed execution lanes to show uploads, cost, privacy, receipts and unknown recovery without
  raw payloads or an automatic winner.
- M3-S10 shipped and compiled the separately installable ArtFlow Unreal Bridge, exported a real
  four-pass package from an ArtFlow-owned UE 5.8 scene, verified it across Unreal C++ and Python,
  rejected a tampered pass, and imported the exact archive into Scene Lab as read-only evidence.
- M3-S11 routed that exact Unreal archive through the live RTX 4080 ComfyUI runtime without a
  permission interrupt, persisted reservation/submission/receipt events, proved restart does not
  resubmit, and rendered the verified local candidate in Scene Lab with a source/candidate slider.

Deliverables:

- beauty, depth, world-normal and object-ID capture with camera facts and hashes;
- protected/editable object selection and read-only preview;
- local ComfyUI adapter retained as the offline route;
- one hosted frontier image-edit adapter behind explicit cost/privacy approval;
- deterministic capability filtering plus model-assisted route explanation;
- normalized candidates and receipts;
- visible reimport as a review Texture2D or review board, not a claimed final 3D asset.

Exit evidence:

- a package produced from a real Unreal scene runs through local and hosted providers;
- route choice and rejected alternatives are recorded;
- changing privacy or cost invalidates approval;
- missing or mismatched passes are rejected before generation.

## M4 — evaluation tribunal and bounded revision

Deliverables:

- camera framing, silhouette, depth/edge, object-ID leakage, palette/material and delivery checks;
- independent Constraint Judge and Visual Critic with fixed typed rubrics;
- disagreements and uncertainty remain visible;
- a frozen negative-control corpus containing attractive-invalid candidates;
- a selected candidate can receive one mask-bounded revision after a new approval.

Exit evidence:

- at least one attractive candidate is rejected for a production constraint violation;
- deterministic checks and critics cannot silently override one another;
- evaluator output replays without rerunning generation;
- unmasked-region leakage prevents revision adoption.

## M5 — recovery, observability, memory and evaluation

Deliverables:

- idempotency keys, stage checkpoints and unknown-completion reconciliation;
- structured recovery proposals for outage, timeout, rate limit, missing output and corrupt artifact;
- cancellation semantics that do not equate timeout with non-execution;
- W3C trace propagation and allowlisted OpenTelemetry Agent/model/tool spans;
- frozen route, policy, recovery, context and memory evaluation suites;
- Harness ablations and model-swap comparison;
- governed episodic, semantic and procedural production memory;
- bounded ArtFlow MCP facade for external inspection and safe operations.

Exit evidence:

- crash after generation resumes without duplicating the provider call;
- a fallback changing cost/privacy waits for new approval;
- trace, event and receipt IDs correlate without logging prompts, secrets or hidden reasoning;
- memory conflict and unauthorized promotion cases fail;
- scorecards report denominators, latency, token/cost and failure rates.

## M6 — provenance and portfolio delivery

Deliverables:

- C2PA 2.4-compatible ingredients, actions, provider/model identity and human adoption;
- independent credential verification;
- final Unreal → two providers → tribunal → selection → revision → reimport demo;
- failure-injection demo, architecture page and evidence mode;
- portfolio case study and résumé bullets whose every number maps to a frozen evaluation artifact;
- clean-install verification for each deployable repository.

Exit evidence:

- one complete human-approved run and one bounded revision;
- C2PA validation independently succeeds;
- one restart/outage demonstration proves correction and no duplicate side effect;
- all public claims map to inspectable artifacts;
- project-owned Unreal fixtures are isolated from sibling repositories and unrelated user data.

## Development discipline

- Prioritize one real vertical proof per milestone over broad feature counts.
- Keep tests near 15–25% of implementation effort. Test contracts, policy, replay, recovery and
  external parsing; do not build mock matrices for trivial adapters.
- Run targeted checks during development and full gates only at milestone boundaries.
- Keep the stable prompt/tool prefix fixed; append dynamic status and artifact references.
- Use multiple Agent roles only for context/tool isolation or real parallelism, never role-play.
- Project-owned GPU runs, Codex built-in image generation, evidence-backed candidate adoption,
  bounded revision, Unreal return and final local portfolio release are autonomous. Informational
  previews are never approval gates. Unrelated user data and shared installations stay out of scope.
- Do not push or upload a public release, install into a shared engine location, mutate unrelated
  user data or create another repository without explicit authorization. Creating and validating the
  project-local release artifact is part of the autonomous goal.
### 2026-08-25 — M3-S12 complete: Codex built-in matched candidate

The same real Unreal beauty input now has a second real candidate from Codex built-in GPT Image 2. The output is bound to the archive, beauty, prompt and minimal-disclosure request; it is persisted by content hash, replayed as event 8, rejected on source mismatch or file tamper, and shown beside the RTX 4080 ComfyUI result as an unselected lane. See `docs/evidence/M3_S12_CODEX_GPT_IMAGE_2_MATCHED_CANDIDATE_2026-08-25.md`.
### 2026-08-25 — M4-S1 complete: replayable independent tribunal

The two real candidates now share one immutable dossier and separately versioned integrity/composition claims. Hash and framing failures control eligibility; the coarse edge-layout metric is explicitly a non-semantic proxy. The report persists as event 9, replays without regeneration and is visible in Scene Lab without selecting a winner. See `docs/evidence/M4_S1_REPLAYABLE_TRIBUNAL_2026-08-25.md`.

### 2026-08-25 — M4-S2 complete: attractive-invalid multimodal control

A real Codex-built-in negative control earns a `0.99` aesthetic pass while visibly violating protected
geometry and camera composition. Its `0.549840` aspect drift triggers deterministic rejection; a
source-bound multimodal critic persists concise claims and limitations, disagreement is visible, and
replay remains exactly 11 events without regeneration. UE preview wording and the durable autonomy
rules now make explicit that project-local adoption, revision, return and release never wait for a
human approval. See `docs/evidence/M4_S2_ATTRACTIVE_INVALID_MULTIMODAL_2026-08-25.md`.

### 2026-08-25 — M4-S3 complete: autonomous adoption and bounded revision

The Codex orchestrator selected the real GPT Image 2 direction from exact deterministic and multimodal
fingerprints while retaining the local candidate's stronger proxy as dissent. A real built-in edit was
sealed to the adopted parent and a 2.732637% editable mask. Visual inspection rejected the first hard-edge
composite even though its leakage guard passed; event 15 corrects the seam from the same raw output and
proves `0 / 1,530,358` changed pixels outside the mask. Scene Lab exposes the adoption, mask, failure lineage
and final compare without an approval control. See
`docs/evidence/M4_S3_AUTONOMOUS_ADOPTION_BOUNDED_REVISION_2026-08-25.md`.
