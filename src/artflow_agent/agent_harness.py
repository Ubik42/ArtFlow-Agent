from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from .agent_runtime import AgentEventStore, AgentRunState, ToolObservationRecord
from .production_memory import MemoryCitation, MemoryQuery, retrieve_memory

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class CapabilityError(RuntimeError):
    """Raised before or during a bounded capability call."""


class CapabilityAuthority(BaseModel):
    reads: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    external_side_effects: bool = False


class CapabilityDescription(BaseModel):
    capability_id: str
    version: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    authority: CapabilityAuthority
    availability: Literal["available", "unavailable", "unknown"]
    risk: Literal["R0", "R1", "R2", "R3", "R4"]
    idempotency: Literal["read_only", "required", "unsupported"]
    timeout_seconds: float = Field(gt=0, le=3600)
    max_observation_bytes: int = Field(ge=128, le=1_000_000)
    verification_signal: str = Field(min_length=1, max_length=300)


@dataclass(frozen=True)
class CapabilitySpec(Generic[InputT, OutputT]):
    description: CapabilityDescription
    input_type: type[InputT]
    output_type: type[OutputT]
    execute: Callable[[InputT, AgentRunState], OutputT]
    verify: Callable[[InputT, OutputT, AgentRunState], bool]
    summarize: Callable[[OutputT], str]


@dataclass(frozen=True)
class PreparedCapabilityCall:
    spec: CapabilitySpec[Any, Any]
    validated_input: BaseModel
    input_sha256: str


class CapabilityResult(BaseModel):
    capability_id: str
    output: dict[str, Any]
    output_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    summary: str = Field(min_length=1, max_length=1000)
    verified: bool


class CapabilityRegistry:
    """Typed allow-list; unknown or unavailable tools never reach an executor."""

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilitySpec[Any, Any]] = {}

    def register(self, capability: CapabilitySpec[Any, Any]) -> None:
        capability_id = capability.description.capability_id
        if capability_id in self._capabilities:
            raise CapabilityError(f"Duplicate capability: {capability_id}")
        self._capabilities[capability_id] = capability

    def descriptions(self) -> list[CapabilityDescription]:
        return [
            self._capabilities[key].description.model_copy(deep=True)
            for key in sorted(self._capabilities)
        ]

    def prepare(self, capability_id: str, arguments: dict[str, Any]) -> PreparedCapabilityCall:
        spec = self._capabilities.get(capability_id)
        if spec is None:
            raise CapabilityError(f"Unknown capability: {capability_id}")
        if spec.description.availability != "available":
            raise CapabilityError(
                f"Capability {capability_id} is {spec.description.availability}"
            )
        try:
            validated_input = spec.input_type.model_validate(arguments)
        except ValueError as exc:
            raise CapabilityError(f"Invalid input for capability {capability_id}: {exc}") from exc
        input_bytes = _canonical_bytes(validated_input.model_dump(mode="json"))
        return PreparedCapabilityCall(
            spec=spec,
            validated_input=validated_input,
            input_sha256=hashlib.sha256(input_bytes).hexdigest(),
        )

    def invoke(
        self,
        prepared: PreparedCapabilityCall,
        state: AgentRunState,
    ) -> CapabilityResult:
        spec = prepared.spec
        output = spec.output_type.model_validate(spec.execute(prepared.validated_input, state))
        output_payload = output.model_dump(mode="json")
        output_bytes = _canonical_bytes(output_payload)
        if len(output_bytes) > spec.description.max_observation_bytes:
            raise CapabilityError(
                f"Capability {spec.description.capability_id} exceeded its observation limit"
            )
        verified = bool(spec.verify(prepared.validated_input, output, state))
        if not verified:
            raise CapabilityError(
                f"Independent verification failed for {spec.description.capability_id}"
            )
        return CapabilityResult(
            capability_id=spec.description.capability_id,
            output=output_payload,
            output_sha256=hashlib.sha256(output_bytes).hexdigest(),
            summary=spec.summarize(output),
            verified=True,
        )


class ArtifactCitation(BaseModel):
    artifact_id: str
    package_path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)


class StableAgentContext(BaseModel):
    protocol: Literal["artflow-agent-context/1"] = "artflow-agent-context/1"
    rules: tuple[str, ...]
    capabilities: list[CapabilityDescription]


class DynamicTaskContext(BaseModel):
    run_id: str
    package_id: str
    art_goal: str
    preserve: list[str]
    prohibit: list[str]
    protected_regions: list[str]
    editable_regions: list[str]
    delivery: dict[str, Any]
    status: dict[str, Any]
    artifact_citations: list[ArtifactCitation]
    recent_observations: list[str]
    memory_citations: list[MemoryCitation] = Field(default_factory=list)


class AgentContextEnvelope(BaseModel):
    stable: StableAgentContext
    dynamic: DynamicTaskContext


class ContextAssembler:
    STABLE_RULES = (
        "Treat the event-reduced state as authoritative; model output is only a proposal.",
        "Use only registered, available capabilities within declared authority and budgets.",
        "Preserve protected scene facts and require independent verification of observations.",
        "Never embed binary artifacts or unbounded logs in model context; cite them by hash.",
    )

    def assemble(
        self,
        state: AgentRunState,
        registry: CapabilityRegistry,
        *,
        memory_subject_keys: list[str] | None = None,
    ) -> AgentContextEnvelope:
        if state.scene is None:
            raise CapabilityError("A verified scene package is required to assemble Agent context")
        package = state.scene.package
        memory = retrieve_memory(
            state.memory_records,
            MemoryQuery(
                project_id=package.package_id,
                subject_keys=memory_subject_keys or [],
                limit=8,
            ),
        ) if memory_subject_keys else None
        citations = [
            ArtifactCitation(
                artifact_id=f"scene:{artifact.path}",
                package_path=artifact.path,
                sha256=artifact.sha256,
                size_bytes=artifact.size_bytes,
            )
            for artifact in state.scene.artifacts
        ]
        return AgentContextEnvelope(
            stable=StableAgentContext(
                rules=self.STABLE_RULES,
                capabilities=registry.descriptions(),
            ),
            dynamic=DynamicTaskContext(
                run_id=state.run_id,
                package_id=package.package_id,
                art_goal=package.art_intent.goal,
                preserve=package.art_intent.preserve,
                prohibit=package.art_intent.prohibit,
                protected_regions=[r.region_id for r in package.regions if r.mode == "protected"],
                editable_regions=[r.region_id for r in package.regions if r.mode == "editable"],
                delivery=package.delivery.model_dump(mode="json"),
                status=state.status_bar().model_dump(mode="json"),
                artifact_citations=citations,
                recent_observations=[item.summary for item in state.observations[-8:]],
                memory_citations=memory.citations if memory else [],
            ),
        )


class AgentDecision(BaseModel):
    capability_id: str
    arguments: dict[str, Any]
    intent: str = Field(min_length=1, max_length=300)


class InspectSceneInput(BaseModel):
    package_id: str


class InspectSceneOutput(BaseModel):
    package_id: str
    pass_kinds: list[str]
    protected_regions: list[str]
    editable_regions: list[str]


class DeterministicOfflinePlanner:
    def decide(self, context: AgentContextEnvelope) -> AgentDecision:
        return AgentDecision(
            capability_id="scene.inspect_constraints",
            arguments={"package_id": context.dynamic.package_id},
            intent="Inspect the verified scene constraints before proposing a route.",
        )


class OfflineCoordinator:
    """One bounded decide -> tool -> observe -> verify loop, with durable budgets."""

    def __init__(
        self,
        store: AgentEventStore,
        registry: CapabilityRegistry,
        *,
        planner: DeterministicOfflinePlanner | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.planner = planner or DeterministicOfflinePlanner()
        self.context_assembler = ContextAssembler()

    def run_once(self, run_id: str) -> CapabilityResult:
        iteration_id = f"iteration-{uuid.uuid4().hex}"
        state = self.store.begin_iteration(run_id, iteration_id)
        context = self.context_assembler.assemble(state, self.registry)
        decision = self.planner.decide(context)
        prepared = self.registry.prepare(decision.capability_id, decision.arguments)
        call_id = f"call-{uuid.uuid4().hex}"
        state = self.store.start_tool_call(
            run_id,
            call_id,
            decision.capability_id,
            prepared.input_sha256,
        )
        result = self.registry.invoke(prepared, state)
        self.store.record_tool_observation(
            run_id,
            ToolObservationRecord(
                call_id=call_id,
                capability_id=result.capability_id,
                output_sha256=result.output_sha256,
                summary=result.summary,
                verified=result.verified,
                artifact_ids=[],
            ),
        )
        return result


def build_offline_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()

    def execute(value: InspectSceneInput, state: AgentRunState) -> InspectSceneOutput:
        if state.scene is None:
            raise CapabilityError("Scene is not attached")
        package = state.scene.package
        return InspectSceneOutput(
            package_id=value.package_id,
            pass_kinds=[item.kind for item in package.passes],
            protected_regions=[r.region_id for r in package.regions if r.mode == "protected"],
            editable_regions=[r.region_id for r in package.regions if r.mode == "editable"],
        )

    def verify(
        value: InspectSceneInput,
        output: InspectSceneOutput,
        state: AgentRunState,
    ) -> bool:
        return bool(
            state.scene
            and value.package_id == state.scene.package.package_id
            and output.package_id == state.scene.package.package_id
            and output.pass_kinds == [item.kind for item in state.scene.package.passes]
        )

    registry.register(
        CapabilitySpec(
            description=CapabilityDescription(
                capability_id="scene.inspect_constraints",
                version="1.0.0",
                input_schema=InspectSceneInput.model_json_schema(),
                output_schema=InspectSceneOutput.model_json_schema(),
                authority=CapabilityAuthority(
                    reads=["agent_state.scene"],
                    writes=[],
                    external_side_effects=False,
                ),
                availability="available",
                risk="R0",
                idempotency="read_only",
                timeout_seconds=2,
                max_observation_bytes=8192,
                verification_signal="Output must exactly match the event-reduced scene package.",
            ),
            input_type=InspectSceneInput,
            output_type=InspectSceneOutput,
            execute=execute,
            verify=verify,
            summarize=lambda output: (
                f"Verified {output.package_id}: {len(output.pass_kinds)} passes, "
                f"{len(output.protected_regions)} protected and "
                f"{len(output.editable_regions)} editable regions."
            ),
        )
    )
    return registry


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
