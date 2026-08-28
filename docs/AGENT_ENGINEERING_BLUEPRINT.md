# ArtFlow Agent engineering blueprint

Status: Phase I 已验证，Phase II 已接受

Initial decision: 2026-08-25

Phase II decision: 2026-08-27
Primary goal: prove a modern, hand-built Agent harness through useful Unreal scene-transformation loops.

## Phase II extension — visual intent to staged 3D scene delta

M0–M6 established the durable harness, real UE capture, matched image providers, independent
tribunal, bounded revision, recovery, memory and provenance. Phase II does not discard that work.
It changes the product endpoint from an adopted 2D image on a preview plane to a verified 3D scene
delta inside Unreal.

The new portfolio thesis is:

> ArtFlow reads a real Unreal scene as a digital twin, treats a concept image as visual intent,
> compiles a typed dependency graph of lighting, PCG, material and asset changes, executes it in an
> isolated staging layer, independently evaluates the rerender and 3D constraints, corrects only
> failed domains, and publishes a replayable scene delta.

The authority model remains `Agent = Model + Harness`. The model may analyze intent and propose a
typed plan. The hand-built Harness owns facts, tool discovery, DAG validation, write scopes,
fingerprints, idempotency, staging, serial Unreal transactions, recovery, technical validation,
visual evaluation, correction and publish/discard.

Phase II roles are bounded views of one durable run, not free-chat workers:

| Role | May produce | May not do |
| --- | --- | --- |
| Scene Analyst | source-bound scene observations | write the host or infer missing facts as truth |
| Visual Director | target attributes and uncertainty | emit host commands |
| Scene Delta Planner | typed operation DAG | execute or publish it |
| Domain Specialists | material, asset, PCG or lighting proposals | cross another domain's write scope |
| Unreal Executor | receipts from frozen operations | invent parameters or override policy |
| Technical Judge / Visual Critic | independent findings | adopt their own evaluated result |
| Correction Planner | a minimal failed-domain patch | restart the whole run without cause |
| Publisher / Reconciler | publish, discard and recovery receipts | reinterpret unknown completion as failure |

MCP is deliberately outside the kernel: it projects existing ArtFlow resources and tools for
external Agent hosts, while every call still enters the same policy and event path. ComfyUI uses a
reviewed subgraph compiler, and image-to-3D models remain replaceable candidate providers. The
normative decision is [ADR-0004](adr/0004-unreal-scene-delta-orchestration-and-mcp-boundary.md);
research and evidence bounds are in
[UNREAL_AIGC_SCENE_TRANSFORMATION_2026-08-27.md](research/UNREAL_AIGC_SCENE_TRANSFORMATION_2026-08-27.md).

## 1. Decision

ArtFlow remains an Agent product. It is not being replaced by a generic Skill and it is not a
ComfyUI dashboard with an LLM button. The sibling Art Pipeline Skill is a separately versioned,
progressively disclosed domain capability pack that ArtFlow may call through explicit contracts; it
does not own ArtFlow orchestration, durable state or the user experience.

The portfolio thesis is:

> ArtFlow compiles a human art direction and Unreal scene facts into bounded visual-generation
> work, selects compatible bounded capabilities, survives partial failure, rejects attractive but
> invalid results, and returns an evidence-selected asset with verifiable
> provenance.

This directly follows the book's production formula:

> Agent = Model + Harness = LLM + Context + Tools + Constrain + Verify + Correct

The source is Li Bojie's open book, *AI Agents in Depth*, especially the chapters on
[Harness engineering](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter1.md),
[context engineering](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter2.md),
[tools](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter4.md), and
[evaluation](https://github.com/bojieli/ai-agent-book/blob/main/book/chapter6.md). Local reading notes
live at `D:\Obsidian\CS\Vibe Coding\Agent开发\书籍_深入理解Al Agent：设计原理与工程实践.md`.

## 2. What the portfolio must prove

Framework names are supporting evidence, not the claim. Each capability must have a visible
behavior, an inspectable artifact and a failure case.

| Capability | ArtFlow implementation | Portfolio proof |
| --- | --- | --- |
| Agent loop | typed decide → act → observe → verify → correct loop | one trace with several real tool calls and a changed plan |
| Context engineering | stable prefix, bounded tool schemas, reducer-built status bar, artifact references and compression | context inspector shows what was retained, summarized and excluded |
| Tool engineering | capability registry, Pydantic inputs/outputs, read/write scope, timeout, cancellation and result verification | invalid and unavailable capabilities fail closed with a useful observation |
| Constrain | deterministic privacy, licensing, scene-scope and integrity policy | changing provider, model or inputs invalidates execution identity |
| Verify | deterministic scene checks plus independent multimodal critics | an attractive negative control is rejected for a measurable violation |
| Correct | retry classification, idempotency, checkpoints, fallback proposal and human escalation | crash or outage resumes without repeating a completed generation |
| Durable state | SQLite append-only events plus deterministic reducer and immutable external receipts | restart reconstructs the same run and pending interrupt |
| Decision custody | persisted propose, evaluate, reject and adopt decisions with separated roles | refresh/restart preserves the evidence behind every decision |
| Multi-agent work | programmatic delegation to bounded specialists with isolated inputs and no self-adoption authority | critic disagreement and recovery proposal are visible and attributable |
| Memory | versioned project rules, episodic run lessons and procedural recipes; governed writes | a proposed memory update retains evidence and requires review before activation |
| Observability | W3C trace propagation and allowlisted OpenTelemetry Agent/model/tool spans | run, state event, provider receipt and evaluation share correlation IDs |
| Evaluation | frozen tasks, negative controls, failure injection, model/Harness ablations and cost/latency metrics | a reproducible scorecard, not a hand-picked successful screenshot |
| Agent UI | typed streaming lifecycle, state snapshots/deltas, interrupts and evidence drill-down | Scene Lab shows the Agent's work without exposing hidden reasoning |
| Provenance | source hashes, provider/model identity, actions, evidence-backed adoption and C2PA 2.4 credential | independently validated delivery package |

## 3. Hand-built control plane

The orchestration core is deliberately ours:

```text
User intent + SceneConstraintPackage
                 │
                 ▼
        Context Assembler
  stable rules + status + cited artifacts
                 │
                 ▼
       ArtFlow Coordinator loop
    decide → tool call → observation
                 │
        ┌────────┼─────────┐
        ▼        ▼         ▼
   Capability  Policy   Event Store
    Registry    Guard   + State Reducer
        │        │         │
        └────────┼─────────┘
                 ▼
       Provider / evaluator tools
                 │
                 ▼
       Verify → correct / interrupt
```

PydanticAI remains the typed model-call layer: model adapters, dependency injection, tool schemas,
structured outputs and evaluation hooks. It must not become the source of run truth. The custom
state reducer, policy, approval fingerprint, tool registry, receipts and recovery planner remain
visible in repository code.

LangGraph is a reference implementation and an optional adapter experiment, not the default
orchestrator. Its official strengths—durable execution, persistence, streaming and human
interrupts—define comparison cases for our implementation. We introduce it only if a measured
requirement is cheaper to satisfy than maintaining our kernel, and then document what remains
hand-built.

Temporal, DBOS, Prefect or Restate are deferred. PydanticAI now supports these durable systems, but
local SQLite durability is sufficient for the first single-machine portfolio loop. A distributed
runtime is justified only by multi-process, multi-day or deployment requirements.

## 4. Context engine

Every model call receives four explicit layers:

1. **Stable prefix:** product identity, immutable safety rules and stable core tool definitions.
2. **Task contract:** user intent, preserve/prohibit constraints, accepted cost/privacy envelope and
   completion definition.
3. **Trajectory:** model messages and compact tool observations with source labels.
4. **Status bar:** reducer-generated current stage, remaining budget, pending decisions, completed
   actions, failure counters and relevant artifact IDs.

Rules:

- dynamic state is appended, never interpolated into the stable prefix;
- status and counts are computed by code, not trusted to an LLM summary;
- large scene passes, manifests, logs and image evaluations live as content-addressed artifacts;
- the model receives bounded summaries plus artifact references and can request narrow reads;
- compression preserves user constraints, approvals, decisions, failures and citations;
- retrieved or provider-supplied text is marked as data and cannot authorize a tool action;
- prompt text, secrets, private imagery and hidden reasoning are excluded from telemetry by default.

## 5. Tool and policy model

Every capability declares:

- versioned name and input/output schema;
- read set, possible write set and external side effects;
- availability state: `supported`, `unsupported` or `unknown`;
- risk class, reversibility, cost and privacy class;
- timeout, cancellation and retry semantics;
- idempotency key strategy;
- independent verification signal;
- maximum observation size and artifact fallback.

Perception tools may run automatically when low risk. Execution tools pass deterministic policy.
The model may propose an action but cannot relax a scene constraint or convert `unknown` into
success. The orchestrator may adopt a candidate only from persisted independent evaluation evidence;
the provider executor that produced it cannot judge or adopt it.

MCP exposes a safe subset of inspection and bounded operations to external hosts. It does not own
memory or orchestration. A2A is out of scope until independently deployed Agents actually need to
discover and communicate with one another.

## 6. Bounded Agent roles

ArtFlow has one durable coordinator and specialist roles, not an open-ended chat room:

| Role | Authority | Forbidden authority |
| --- | --- | --- |
| Intent Planner | propose typed visual directions and missing facts | bypass deterministic policy |
| Capability Router | rank compatible declared routes and explain trade-offs | bypass deterministic policy |
| Provider Executor | execute one bounded capability and return a receipt | alter scope or judge adoption |
| Constraint Judge | evaluate spatial, protected-region and delivery constraints | rewrite the candidate or hide uncertainty |
| Visual Critic | evaluate art-direction quality with a fixed rubric | override deterministic failures |
| Recovery Planner | classify failure and propose retry/fallback/escalation | bypass scope or deterministic failures |
| Codex Orchestrator | adopt or reject from persisted tribunal evidence and deliver the portfolio result | erase dissent, override deterministic failure or call `unknown` success |

Delegation is used only for context isolation, genuinely different tools or parallel independent
checks. Most transitions are programmatic hand-offs. Each role receives the minimum typed context,
returns structured evidence and has a tool/iteration budget.

## 7. Memory and controlled evolution

ArtFlow does not need a generic personal-memory demo. It needs production memory with three stores:

- **episodic:** immutable run decisions, failures, approvals and human selections;
- **semantic:** versioned project rules, style constraints and approved exceptions with sources;
- **procedural:** reviewed recipes, evaluation rubrics and recovery playbooks.

New memory is proposed from run evidence, checked for conflicts and reviewed before activation.
Private project material is never silently promoted into shared memory. Retrieval begins with
metadata and exact identifiers; hybrid search is added only when the corpus demonstrates a recall
problem. Indexes are rebuildable derivatives, not the source of truth.

Continuous evolution initially changes prompts, tools, rubrics, recipes and retrieval policy—not
model weights. Every proposed change must beat the frozen evaluation set and preserve safety cases.

## 8. Durable events, UI and observability

The authoritative run model is an append-only SQLite event log plus a deterministic reducer. Events
include intent accepted, scene imported, route proposed, approval requested/resolved, tool started,
tool observed, candidate received, evaluation recorded, recovery proposed and candidate adopted.

Provider receipts remain immutable external facts linked from events. Side effects execute with an
idempotency key and a preflight/execute/observe split. Cancellation is a requested state until the
provider confirms a terminal outcome; a timeout never implies that nothing happened.

The React Scene Lab consumes typed streaming events. The event vocabulary should remain compatible
with AG-UI concepts—run lifecycle, tool-call lifecycle, state snapshot/delta and interrupts—without
forcing chat to become the primary interface. The UI displays concise decision explanations and
evidence, never hidden chain-of-thought.

OpenTelemetry records `invoke_agent`, model and `execute_tool` spans with correlation IDs, latency,
tokens, cost class, retry count and outcome. Content capture is opt-in and separately governed.

## 9. Evaluation program

Evaluation targets the model plus Harness, not the model in isolation.

### Frozen suites

- route selection across capability, cost and privacy conflicts;
- tool-schema and unavailable-capability errors;
- approval bypass and approval invalidation attempts;
- Comfy timeout, unknown completion, missing output and corrupted artifact;
- protected-region leakage, camera drift and object-identity changes;
- critic disagreement and uncertainty;
- restart at every state boundary;
- context compression with buried constraints and stale observations;
- memory conflict and unauthorized memory promotion.

### Metrics

- end-to-end task success and human adoption rate;
- production-constraint pass rate and attractive-invalid rejection rate;
- route/tool selection accuracy;
- approval bypass rate and false-interrupt rate;
- recovery success and duplicate side-effect rate;
- restart equivalence and event replay determinism;
- context tokens, cacheable-prefix ratio, latency and provider cost;
- evaluator agreement, calibration and false accept/false reject rates.

### Experiments

- fixed Harness, swap model;
- fixed model, remove status bar, verifier, critic or recovery policy one at a time;
- sequential versus parallel independent evaluators;
- full tool output versus artifact summary;
- deterministic-only versus deterministic plus multimodal evaluation.

Claims require enough repeated cases to report a denominator. A single polished run is demo
evidence, not a benchmark.

## 10. Frontend product surface

The existing three-column workbench will be structurally replaced by **Scene Lab + Agent Flow**:

- large scene/candidate canvas with camera, object-ID, protected/editable and difference overlays;
- compact production flow showing import, understand, route, approve, execute, judge and deliver;
- contextual drawers instead of permanent run and inspector rails;
- large A/B, overlay and slider comparison instead of three equal thumbnail cards;
- persisted approval sheets showing route differences, cost, privacy and consequences;
- critic disagreement, recovery and provenance attached to the affected candidate or step;
- an evidence mode for portfolio review that links each claim to a trace, receipt or artifact.

The interface is a visual-production workspace, not a generic chat dashboard and not a ComfyUI
canvas clone.

## 11. Technology decisions

| Layer | Decision now | Trigger for change |
| --- | --- | --- |
| Model/tool loop | PydanticAI typed calls inside custom coordinator | measured provider or eval limitation |
| State | custom SQLite event store + reducer | distributed/multi-day deployment |
| Durable runtime | local custom checkpoints/idempotency | then compare Temporal/DBOS/Restate |
| External tools | internal typed adapters; bounded MCP facade later | real external Agent client |
| Agent UI stream | typed SSE aligned with AG-UI event concepts | adopt SDK when it removes real integration work |
| Observability | OpenTelemetry, local exporter first | team dashboard need → Phoenix/Logfire/Langfuse |
| Multi-agent | programmatic specialists within one run | A2A only for independent deployed Agents |
| Memory search | metadata/exact lookup first | measured corpus recall problem → hybrid retrieval |
| Provenance | C2PA 2.4 compatible credential and verifier | follow later compatible revisions deliberately |

## 12. Anti-drift rules

- Do not replace the flagship Agent with a generic Skill, asset scanner or framework tutorial.
- Do not count a framework import, schema, mock, screenshot or self-reported success as capability.
- Do not add RAG, multi-agent, A2A, Temporal or a vector database without a demonstrated problem.
- Do not expose arbitrary ComfyUI graphs or arbitrary host Python to the model.
- Do not let a provider executor judge its own output or silently weaken user-owned constraints.
- Do not optimize tests for volume; test contracts, policy, replay, recovery and external parsing.
- Do not postpone the real Unreal → providers → tribunal → evidence-backed adoption loop for broad platform work.
- Do not publish invented metrics. Every number must identify task set, denominator and evidence.

## Research anchors

These primary sources define the external direction used by this plan. Recheck them before adopting
a dependency because APIs and protocol versions can move faster than the product architecture.

- [ComfyUI App Mode](https://docs.comfy.org/interface/app-mode): supports moving the node canvas
  behind a bounded application surface.
- [PydanticAI agents](https://pydantic.dev/docs/ai/core-concepts/agent/),
  [multi-agent patterns](https://pydantic.dev/docs/ai/guides/multi-agent-applications/) and
  [durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/): typed
  model/tool integration and comparison points, not the owner of ArtFlow state.
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview),
  [persistence](https://docs.langchain.com/oss/python/langgraph/persistence) and
  [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts): reference behavior for
  durable state, pending writes and human-in-the-loop.
- [AG-UI architecture](https://docs.ag-ui.com/concepts/architecture): typed run, tool-call,
  snapshot/delta and interrupt concepts for the Scene Lab event boundary.
- [MCP 2026-07-28 update](https://blog.modelcontextprotocol.io/posts/2026-07-28/): external tool and
  long-running Task interoperability; not an internal orchestrator.
- [OpenTelemetry GenAI observability](https://opentelemetry.io/blog/2026/genai-observability/):
  Agent, model and tool span semantics with privacy-aware content capture.
- [C2PA 2.4](https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html):
  interoperable, tamper-evident content provenance without making a value judgment about truth.

## 13. Definition of portfolio-complete

The project is portfolio-complete only when a reviewer can inspect one real end-to-end run and one
failure-injected run and verify all of the following:

1. real Unreal scene facts entered through the package boundary;
2. the Agent assembled bounded context and chose among declared tools;
3. route, privacy/integrity trade-offs and policy state were visible;
4. at least one real provider call survived or recovered from interruption without duplication;
5. deterministic and multimodal evaluators disagreed or rejected an attractive invalid candidate;
6. the orchestrator adopted a candidate from persisted tribunal evidence and executed a bounded revision;
7. restart reconstructed the same run and pending decisions;
8. trace, event, receipt, evaluation and artifact identities correlated;
9. a C2PA-compatible delivery credential validated independently;
10. a frozen evaluation report quantified capability, failure and cost rather than listing features.
