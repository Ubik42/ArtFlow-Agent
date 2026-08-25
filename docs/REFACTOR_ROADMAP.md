# ArtFlow refactor roadmap

This roadmap uses a strangler migration. The current working vertical slice remains runnable while
new contracts and capabilities replace it from the edges. Do not perform a big-bang rewrite.

## Baseline that must keep working

- deterministic brief planning and optional PydanticAI planning;
- reviewed ComfyUI recipes with allowlisted slots;
- live `/system_stats` and `/object_info` preflight;
- explicit approval before GPU execution;
- resumable direction-level execution and external receipts;
- candidate review, deterministic checks and delivery packaging;
- local React workbench;
- run `862ac768a2f2` as the real RTX 4080 baseline.

The baseline remains a regression fixture until the Unreal-originated loop supersedes it. Its
incomplete human selection is recorded honestly and must not be rewritten as a completed run.

## M0 — contracts and migration seams

Deliverables:

- `scene-constraint-package/1` typed model and exported JSON Schema;
- provider capability manifest and route-decision contract;
- current provider execution hidden behind an explicit adapter boundary;
- ADRs for suite ownership, receipt authority and failure semantics;
- a contract fixture readable from Python, TypeScript and an Unreal-side parser.

Exit evidence:

- the same fixture validates in all implemented languages;
- unsafe relative paths, duplicate passes and missing required passes fail closed;
- current tests and real Comfy doctor remain green.

## M1 — real Unreal scene bridge

Create a separate installable Unreal plugin repository. Its first scope is one disposable scene and
one selected camera.

Deliverables:

- read-only capture preview;
- camera transform/projection and engine version;
- beauty, depth, world-normal and object-ID outputs;
- protected/editable object selection;
- atomic scene package with hashes;
- ArtFlow import and constraint inspection;
- selected result reimported as a review Texture2D or review board, not claimed as a final 3D asset.

Exit evidence:

- visible Unreal capture and reimport;
- a package produced from a real UE scene, not a hand-authored JSON fixture;
- missing or mismatched passes rejected before generation.

## M2 — provider routing and matched execution

Deliverables:

- local ComfyUI adapter retained as the offline route;
- one hosted frontier image-edit adapter behind explicit cost/privacy approval;
- capability manifests covering supported controls, limits, versions and cost class;
- deterministic route policy plus model-assisted route explanation;
- normalized candidates and receipts;
- explicit fallback proposal when a provider is unavailable or incompatible.

Exit evidence:

- the same scene package runs through local and hosted providers;
- route choice and rejected alternatives are recorded;
- switching privacy or cost class invalidates the previous approval.

## M3 — evaluation tribunal

Deliverables:

- camera framing and silhouette preservation;
- object-ID protected-region leakage;
- depth/edge structure alignment;
- palette and material consistency;
- delivery dimension/format checks;
- independent multimodal critic with a fixed rubric;
- disagreement and uncertainty displayed in the workbench;
- a small negative-control corpus.

Exit evidence:

- at least one visually attractive candidate is rejected for violating a production constraint;
- deterministic checks and the critic cannot silently override each other;
- evaluator output is replayable without rerunning generation.

## M4 — durable recovery, observability and external tools

Deliverables:

- SQLite-backed event store and deterministic state reducer;
- idempotency keys and stage checkpoints across provider processes;
- structured recovery proposals for Comfy outage, timeout, rate limit and missing output;
- W3C trace propagation and allowlisted OpenTelemetry spans;
- safe ArtFlow MCP server exposing inspection and bounded capabilities;
- Comfy MCP remains an optional beta adapter, not the source of truth.

Exit evidence:

- crash after local generation resumes without duplicating the completed provider call;
- a fallback that changes cost/privacy waits for new approval;
- trace, state and receipt IDs correlate without logging prompts, secrets or thought process.

## M5 — provenance and portfolio delivery

Deliverables:

- C2PA-compatible ingredient/action provenance and independent verification;
- reimportable delivery package with checksums and provider/model identity;
- final Unreal → two providers → evaluation → selection → revision → reimport demo;
- failure-injection demo and architecture/evidence pages;
- clean-install verification for each deployable repository.

Exit evidence:

- one complete human-approved run and one bounded revision;
- C2PA or sidecar validation independently succeeds;
- all public claims map to inspectable artifacts;
- no production project writes occur outside an explicitly approved target.

## Development discipline

- Prioritize one real vertical proof per milestone over broad feature counts.
- Keep tests near 15–25% of implementation effort: contracts, gates, state transitions, recovery and
  external protocol parsing receive tests; simple adapters do not get mock matrices.
- Run targeted checks during development and full gates only at milestone boundaries.
- Every external cost, GPU run, visible host mutation and production-path write remains a separate
  human decision.
- Do not commit, push, publish, install a host plugin or create a new repository without explicit
  authorization.

