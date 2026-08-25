# ArtFlow 2026 product vision

Status: accepted direction for the next refactor track  
Decision date: 2026-08-25

## Product thesis

ArtFlow is a visual-production control plane for game-art iteration. Foundation models provide
visual intelligence; ArtFlow owns scene intent, capability routing, approvals, durable execution,
independent verification, human adoption, provenance, and delivery back to a DCC or engine.

The product does not compete with frontier models on raw image quality and does not expose arbitrary
ComfyUI graph generation. A technical artist may inspect and author graphs, but an artist interacts
with briefs, references, spatial constraints, reviewable candidates, and explicit decisions.

## Flagship system and deployable boundaries

```text
Unreal scene
  -> ArtFlow Unreal Bridge (separate installable repository)
  -> scene-constraint-package/1
  -> ArtFlow Agent control plane (this repository)
  -> capability-aware route
       -> reviewed local ComfyUI recipe
       -> explicitly approved hosted image provider
  -> deterministic checks + independent visual critic
  -> human selection / bounded revision
  -> reimportable package + signed provenance
```

The suite has three deployable products:

1. **ArtFlow Agent** remains the flagship application and owns the user-visible production state.
2. **ArtFlow Unreal Bridge** will be a separate repository because it is installed into Unreal.
3. **ComfyUI Production Nodes** remains a separate reusable custom-node package and supplies
   runtime-side gates and production metadata.

The existing `verified-art-pipeline-agent` is not duplicated. Its proven patterns for typed intent,
approval recovery, context boundaries, hash-chained events, OpenTelemetry, and independent
verification are candidates for extraction into shared AIToolTA packages or for protocol-level
reuse. ArtFlow keeps its Python execution plane and consumes shared contracts rather than copying a
second control plane wholesale.

## Core innovation: a scene constraint compiler

The durable abstraction is a provider-neutral scene package, not a prompt and not a ComfyUI graph.
It carries:

- camera projection, transform and raster dimensions;
- beauty, depth, world-normal and object-ID passes;
- protected and editable regions;
- user-owned preserve and prohibit constraints;
- source application, project and level provenance;
- delivery requirements and source hashes.

Provider adapters compile the same package into reviewed local recipes or hosted edit requests.
Their output is normalized into the same candidate and receipt model. A route may change; the
approved intent and verification contract do not.

## Bounded agent roles

ArtFlow uses several roles inside one durable, inspectable state machine:

- **Intent planner** proposes typed visual directions.
- **Capability router** proposes only routes declared by provider manifests.
- **Policy layer** deterministically enforces privacy, cost, licensing and approval boundaries.
- **Provider executors** call only registered, slot-bounded capabilities.
- **Evaluation tribunal** combines deterministic spatial checks with an independent multimodal
  critic and reports disagreements rather than hiding them.
- **Recovery planner** may retry or propose a compatible fallback, but any privacy or cost boundary
  change creates a new approval request.
- **Human owner** approves spend, selects an adopted candidate and accepts delivery.

Multiple roles are not multiple agents chatting for show. Every role has a restricted input schema,
restricted tools, an evidence requirement, and no authority to mark its own output as adopted.

## Portfolio claim

The final case study should prove:

> Unreal supplies spatial facts, models supply visual intelligence, and ArtFlow compiles intent into
> controlled execution, survives failure, rejects attractive but invalid results, and returns a
> human-approved asset with verifiable provenance.

## Non-goals

- generic image chat or prompt marketplace;
- unrestricted workflow generation;
- a replacement ComfyUI canvas;
- support for every DCC before one Unreal loop is real;
- a second copy of the existing AIToolTA Agent kernel;
- production claims based only on mocks, schemas, or screenshots;
- automatic learning from private project data without explicit authorization.

