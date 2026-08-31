from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from .agent_runtime import AgentRunState

SceneDomain = Literal["image", "material", "asset", "pcg", "lighting"]
SceneDomainReadiness = Literal["ready", "guarded", "experimental"]
SCENE_SESSION_STRATEGY_VERSION = "scene-session-strategy/1"

DOMAIN_ORDER: tuple[SceneDomain, ...] = (
    "image",
    "material",
    "asset",
    "pcg",
    "lighting",
)


class SceneSessionDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = Field(min_length=10, max_length=600)
    domains: list[SceneDomain] = Field(min_length=1, max_length=len(DOMAIN_ORDER))

    @field_validator("intent")
    @classmethod
    def normalize_intent(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 10:
            raise ValueError("scene session intent must contain at least 10 non-space characters")
        return normalized

    @field_validator("domains")
    @classmethod
    def require_unique_domains(cls, value: list[SceneDomain]) -> list[SceneDomain]:
        if len(value) != len(set(value)):
            raise ValueError("scene session domains must be unique")
        selected = set(value)
        return [domain for domain in DOMAIN_ORDER if domain in selected]


class SceneSessionStartRequest(SceneSessionDraftRequest):
    action_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    expected_draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SceneStageRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SceneSpectrumNode(BaseModel):
    domain: SceneDomain
    label: str
    readiness: SceneDomainReadiness
    action: str
    reason: str
    verification: str
    depends_on: list[SceneDomain] = Field(default_factory=list)


class SceneSessionDraft(BaseModel):
    schema_id: Literal["artflow-scene-session-draft/1"] = (
        "artflow-scene-session-draft/1"
    )
    draft_id: str
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: str
    basis_sequence: int = Field(ge=1)
    source_scene: str
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    capability_environment_sha256s: list[str] = Field(default_factory=list)
    intent: str
    preserve: list[str]
    prohibit: list[str]
    nodes: list[SceneSpectrumNode]
    ready_domain_count: int = Field(ge=0)
    guarded_domain_count: int = Field(ge=0)
    experimental_domain_count: int = Field(ge=0)
    can_stage: bool
    next_action: str


class SceneSession(BaseModel):
    schema_id: Literal["artflow-scene-session/1"] = "artflow-scene-session/1"
    session_id: str
    session_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    strategy_version: Literal["scene-session-strategy/1"] = SCENE_SESSION_STRATEGY_VERSION
    run_id: str
    source_scene: str
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    start_action_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    supersedes_session_id: str | None = None
    draft: SceneSessionDraft

    @model_validator(mode="after")
    def verify_identity(self) -> SceneSession:
        expected = _content_sha256(self._identity_payload())
        if self.session_sha256 != expected:
            raise ValueError("scene session content hash is invalid")
        if self.session_id != f"scene-session-{expected[:12]}":
            raise ValueError("scene session id is invalid")
        if self.run_id != self.draft.run_id:
            raise ValueError("scene session draft references another run")
        if self.scene_package_sha256 != self.draft.scene_package_sha256:
            raise ValueError("scene session draft references another Scene Package")
        return self

    def _identity_payload(self) -> dict[str, object]:
        return {
            "strategy_version": self.strategy_version,
            "run_id": self.run_id,
            "source_scene": self.source_scene,
            "scene_package_sha256": self.scene_package_sha256,
            "start_action_id": self.start_action_id,
            "supersedes_session_id": self.supersedes_session_id,
            "draft": self.draft.model_dump(mode="json"),
        }


class SceneStageOperation(BaseModel):
    domain: SceneDomain
    readiness: SceneDomainReadiness
    action: str
    verification: str
    depends_on: list[SceneDomain] = Field(default_factory=list)


class SceneStageRequest(BaseModel):
    schema_id: Literal["artflow-scene-stage-request/1"] = "artflow-scene-stage-request/1"
    request_id: str
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{7,199}$")
    run_id: str
    basis_sequence: int = Field(ge=1)
    session_id: str
    session_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    strategy_version: Literal["scene-session-strategy/1"] = SCENE_SESSION_STRATEGY_VERSION
    source_scene: str
    candidate_destination: str
    operations: list[SceneStageOperation] = Field(min_length=1)

    @model_validator(mode="after")
    def verify_identity(self) -> SceneStageRequest:
        expected = _content_sha256(self._identity_payload())
        if self.request_sha256 != expected:
            raise ValueError("scene stage request content hash is invalid")
        if self.request_id != f"stage-request-{expected[:12]}":
            raise ValueError("scene stage request id is invalid")
        if self.idempotency_key != f"scene-stage:{expected}":
            raise ValueError("scene stage request idempotency key is invalid")
        expected_destination = (
            f"/Game/ArtFlow/Sessions/AF_{self.session_sha256[:12]}"
            f"/Candidates/C_{expected[:12]}"
        )
        if self.candidate_destination != expected_destination:
            raise ValueError("scene stage request candidate destination is invalid")
        return self

    def _identity_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "basis_sequence": self.basis_sequence,
            "session_id": self.session_id,
            "session_sha256": self.session_sha256,
            "draft_sha256": self.draft_sha256,
            "scene_package_sha256": self.scene_package_sha256,
            "strategy_version": self.strategy_version,
            "source_scene": self.source_scene,
            "operations": [item.model_dump(mode="json") for item in self.operations],
        }


class SceneCandidatePCGToolCall(BaseModel):
    operation_type: Literal["apply_pcg_layout"] = "apply_pcg_layout"
    operation_id: str
    domain: Literal["pcg"] = "pcg"
    tool_name: Literal["unreal.pcg.layout.apply"] = "unreal.pcg.layout.apply"
    target_actor_id: str
    target_actor_label: str
    expected_source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    component_id: str
    approved_graph_path: str
    seed: int = Field(ge=0, le=2_147_483_647)
    max_generated_instances: int = Field(ge=1, le=10_000)


class SceneCandidateLightingToolCall(BaseModel):
    operation_type: Literal["set_lighting_rig"] = "set_lighting_rig"
    operation_id: str
    domain: Literal["lighting"] = "lighting"
    tool_name: Literal["unreal.lighting.rig.patch"] = "unreal.lighting.rig.patch"
    target_actor_id: str
    target_actor_label: str
    expected_source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    intensity: float = Field(ge=0, le=1_000_000)
    use_temperature: Literal[True] = True
    temperature_kelvin: float = Field(ge=1_000, le=20_000)


SceneCandidateToolCall = Annotated[
    SceneCandidatePCGToolCall | SceneCandidateLightingToolCall,
    Field(discriminator="operation_type"),
]


class SceneCandidatePlan(BaseModel):
    schema_id: Literal["artflow-scene-candidate-plan/1"] = (
        "artflow-scene-candidate-plan/1"
    )
    plan_id: str
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: str
    basis_sequence: int = Field(ge=1)
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    session_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    stage_request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    strategy_version: Literal["scene-session-strategy/1"] = SCENE_SESSION_STRATEGY_VERSION
    source_scene: str
    candidate_destination: str
    operations: list[SceneCandidateToolCall] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def verify_identity(self) -> SceneCandidatePlan:
        expected = _content_sha256(self._identity_payload())
        if self.plan_sha256 != expected:
            raise ValueError("scene candidate plan content hash is invalid")
        if self.plan_id != f"candidate-plan-{expected[:12]}":
            raise ValueError("scene candidate plan id is invalid")
        if not self.candidate_destination.startswith("/Game/ArtFlow/Sessions/"):
            raise ValueError("scene candidate plan escaped the ArtFlow Sessions namespace")
        return self

    def _identity_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "basis_sequence": self.basis_sequence,
            "scene_package_sha256": self.scene_package_sha256,
            "session_sha256": self.session_sha256,
            "draft_sha256": self.draft_sha256,
            "stage_request_sha256": self.stage_request_sha256,
            "strategy_version": self.strategy_version,
            "source_scene": self.source_scene,
            "candidate_destination": self.candidate_destination,
            "operations": [item.model_dump(mode="json") for item in self.operations],
        }


class SceneSessionHandshakeReceipt(BaseModel):
    schema_id: Literal["artflow-scene-session-handshake/1"] = (
        "artflow-scene-session-handshake/1"
    )
    handshake_id: str
    handshake_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    action_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    run_id: str
    source_scene: str
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    event_sequence: int = Field(ge=1)
    session: SceneSession
    stage_request: SceneStageRequest
    candidate_plan: SceneCandidatePlan | None = None

    @model_validator(mode="after")
    def verify_identity(self) -> SceneSessionHandshakeReceipt:
        expected = _content_sha256(self._identity_payload())
        if self.handshake_sha256 != expected:
            raise ValueError("scene session handshake content hash is invalid")
        if self.handshake_id != f"scene-handshake-{expected[:12]}":
            raise ValueError("scene session handshake id is invalid")
        if self.action_id != self.session.start_action_id:
            raise ValueError("scene session handshake action identity is invalid")
        if self.run_id != self.session.run_id or self.run_id != self.stage_request.run_id:
            raise ValueError("scene session handshake references another run")
        if self.scene_package_sha256 != self.session.scene_package_sha256:
            raise ValueError("scene session handshake references another Scene Package")
        if self.session.session_sha256 != self.stage_request.session_sha256:
            raise ValueError("scene session handshake stage request references another Session")
        if self.source_scene != self.session.source_scene:
            raise ValueError("scene session handshake references another source scene")
        if self.source_scene != self.stage_request.source_scene:
            raise ValueError("scene session handshake stage request references another source scene")
        if self.event_sequence != self.stage_request.basis_sequence:
            raise ValueError("scene session handshake event sequence is invalid")
        if self.candidate_plan is not None:
            if self.candidate_plan.run_id != self.run_id:
                raise ValueError("scene candidate plan references another run")
            if self.candidate_plan.session_sha256 != self.session.session_sha256:
                raise ValueError("scene candidate plan references another Session")
            if self.candidate_plan.stage_request_sha256 != self.stage_request.request_sha256:
                raise ValueError("scene candidate plan references another stage request")
        return self

    def _identity_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "action_id": self.action_id,
            "run_id": self.run_id,
            "source_scene": self.source_scene,
            "scene_package_sha256": self.scene_package_sha256,
            "event_sequence": self.event_sequence,
            "session": self.session.model_dump(mode="json"),
            "stage_request": self.stage_request.model_dump(mode="json"),
        }
        if self.candidate_plan is not None:
            payload["candidate_plan"] = self.candidate_plan.model_dump(mode="json")
        return payload


def compile_scene_session_draft(
    state: AgentRunState,
    request: SceneSessionDraftRequest,
) -> SceneSessionDraft:
    if state.scene is None:
        raise ValueError("scene session requires an attached Scene Package")

    package = state.scene.package
    has_supported_runtime = any(
        item.status == "supported" for item in state.capability_attestations
    )
    has_scene_twin = package.scene_digital_twin is not None

    definitions: dict[SceneDomain, SceneSpectrumNode] = {
        "image": SceneSpectrumNode(
            domain="image",
            label="视觉参考",
            readiness="ready",
            action="生成保持相机与主体关系的视觉方向",
            reason="Scene Package 已绑定 Beauty、Depth、Normal 与 Object ID。",
            verification="画幅、相机代理指标与受保护区域检查",
        ),
        "material": SceneSpectrumNode(
            domain="material",
            label="材质",
            readiness="ready" if has_supported_runtime else "guarded",
            action="生成并校验 BaseColor、Normal、Roughness、Metallic 与 AO",
            reason=(
                "本地生成运行时已完成能力实测。"
                if has_supported_runtime
                else "尚未取得本次运行的 ComfyUI 能力实测。"
            ),
            verification="逐通道语义、尺寸、内容哈希与 Shader-ready 回渲",
            depends_on=["image"] if "image" in request.domains else [],
        ),
        "asset": SceneSpectrumNode(
            domain="asset",
            label="三维资产",
            readiness="experimental",
            action="优先复用项目资产，必要时生成 GLB 候选",
            reason="图生 3D 已接入候选路径，但仍定位为实验性几何草案。",
            verification="许可证、外部 URI、比例、面数、材质、碰撞与命名空间",
            depends_on=["image"] if "image" in request.domains else [],
        ),
        "pcg": SceneSpectrumNode(
            domain="pcg",
            label="空间布局",
            readiness="ready" if has_scene_twin else "guarded",
            action="通过固定 PCG 图布置项目资产",
            reason=(
                "Scene Digital Twin 可提供边界与保护对象事实。"
                if has_scene_twin
                else "当前 Scene Package 未绑定 Scene Digital Twin。"
            ),
            verification="实例数量、保护区侵入、依赖图指纹与重复执行",
            depends_on=["asset"] if "asset" in request.domains else [],
        ),
        "lighting": SceneSpectrumNode(
            domain="lighting",
            label="灯光",
            readiness="ready" if has_scene_twin else "guarded",
            action="在候选关卡调整强度、色温与方向",
            reason=(
                "Scene Digital Twin 可提供灯光身份与相机事实。"
                if has_scene_twin
                else "当前 Scene Package 未绑定可写灯光身份。"
            ),
            verification="参数范围、源关卡指纹与同机位亮度回渲",
        ),
    }
    nodes = [definitions[domain] for domain in request.domains]
    canonical = {
        "run_id": state.run_id,
        "basis_sequence": state.last_sequence,
        "scene_package_sha256": state.scene.archive_sha256,
        "capability_environment_sha256s": sorted(
            item.environment_sha256 for item in state.capability_attestations
        ),
        "intent": request.intent,
        "preserve": package.art_intent.preserve,
        "prohibit": package.art_intent.prohibit,
        "nodes": [node.model_dump(mode="json") for node in nodes],
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    ready_count = sum(node.readiness == "ready" for node in nodes)
    guarded_count = sum(node.readiness == "guarded" for node in nodes)
    experimental_count = sum(node.readiness == "experimental" for node in nodes)
    can_stage = guarded_count == 0
    return SceneSessionDraft(
        draft_id=f"scene-draft-{digest[:12]}",
        draft_sha256=digest,
        run_id=state.run_id,
        basis_sequence=state.last_sequence,
        source_scene=package.provenance.scene_name,
        scene_package_sha256=state.scene.archive_sha256,
        capability_environment_sha256s=sorted(
            item.environment_sha256 for item in state.capability_attestations
        ),
        intent=request.intent,
        preserve=package.art_intent.preserve,
        prohibit=package.art_intent.prohibit,
        nodes=nodes,
        ready_domain_count=ready_count,
        guarded_domain_count=guarded_count,
        experimental_domain_count=experimental_count,
        can_stage=can_stage,
        next_action=(
            "创建隔离候选关卡并执行已接入领域"
            if can_stage
            else "先补齐受保护三维事实或运行时能力，再进入候选执行"
        ),
    )


def build_scene_session(
    state: AgentRunState,
    draft: SceneSessionDraft,
    *,
    action_id: str,
) -> SceneSession:
    if state.scene is None:
        raise ValueError("scene session requires an attached Scene Package")
    if draft.run_id != state.run_id or draft.scene_package_sha256 != state.scene.archive_sha256:
        raise ValueError("scene session draft does not match the current run and Scene Package")
    if draft.basis_sequence != state.last_sequence:
        raise ValueError("scene session draft is stale; compile it again from the current event state")
    validate_scene_session_draft(state, draft)
    previous = state.scene_sessions[-1] if state.scene_sessions else None
    payload = {
        "strategy_version": SCENE_SESSION_STRATEGY_VERSION,
        "run_id": state.run_id,
        "source_scene": draft.source_scene,
        "scene_package_sha256": draft.scene_package_sha256,
        "start_action_id": action_id,
        "supersedes_session_id": previous.session_id if previous else None,
        "draft": draft.model_dump(mode="json"),
    }
    digest = _content_sha256(payload)
    return SceneSession(
        session_id=f"scene-session-{digest[:12]}",
        session_sha256=digest,
        strategy_version=SCENE_SESSION_STRATEGY_VERSION,
        run_id=state.run_id,
        source_scene=draft.source_scene,
        scene_package_sha256=draft.scene_package_sha256,
        start_action_id=action_id,
        supersedes_session_id=previous.session_id if previous else None,
        draft=draft,
    )


def compile_scene_stage_request(
    state: AgentRunState,
    *,
    expected_draft_sha256: str,
) -> SceneStageRequest:
    if state.scene is None or not state.scene_sessions:
        raise ValueError("candidate staging requires a persisted Scene Session")
    session = state.scene_sessions[-1]
    if session.draft.draft_sha256 != expected_draft_sha256:
        raise ValueError("candidate staging rejected a stale Scene Session draft identity")
    if session.scene_package_sha256 != state.scene.archive_sha256:
        raise ValueError("candidate staging Scene Package no longer matches the active scene")
    if state.last_sequence != session.draft.basis_sequence + 1:
        raise ValueError("candidate staging Session is stale; start a new Scene Session")
    if not session.draft.can_stage:
        raise ValueError("candidate staging is guarded until all selected domains are ready")
    operations = [
        SceneStageOperation(
            domain=node.domain,
            readiness=node.readiness,
            action=node.action,
            verification=node.verification,
            depends_on=node.depends_on,
        )
        for node in session.draft.nodes
    ]
    payload = {
        "run_id": state.run_id,
        "basis_sequence": state.last_sequence,
        "session_id": session.session_id,
        "session_sha256": session.session_sha256,
        "draft_sha256": session.draft.draft_sha256,
        "scene_package_sha256": session.scene_package_sha256,
        "strategy_version": session.strategy_version,
        "source_scene": session.source_scene,
        "operations": [item.model_dump(mode="json") for item in operations],
    }
    digest = _content_sha256(payload)
    return SceneStageRequest(
        request_id=f"stage-request-{digest[:12]}",
        request_sha256=digest,
        idempotency_key=f"scene-stage:{digest}",
        run_id=state.run_id,
        basis_sequence=state.last_sequence,
        session_id=session.session_id,
        session_sha256=session.session_sha256,
        draft_sha256=session.draft.draft_sha256,
        scene_package_sha256=session.scene_package_sha256,
        strategy_version=session.strategy_version,
        source_scene=session.source_scene,
        candidate_destination=(
            f"/Game/ArtFlow/Sessions/AF_{session.session_sha256[:12]}"
            f"/Candidates/C_{digest[:12]}"
        ),
        operations=operations,
    )


def compile_scene_candidate_plan(
    state: AgentRunState,
    *,
    expected_stage_request_sha256: str,
) -> SceneCandidatePlan:
    if state.scene is None or state.scene.digital_twin is None:
        raise ValueError("scene candidate plan requires a Scene Digital Twin")
    session = state.scene_sessions[-1] if state.scene_sessions else None
    if session is None:
        raise ValueError("scene candidate plan requires a persisted Scene Session")
    stage_request = compile_scene_stage_request(
        state,
        expected_draft_sha256=session.draft.draft_sha256,
    )
    if stage_request.request_sha256 != expected_stage_request_sha256:
        raise ValueError("scene candidate plan rejected a stale stage request identity")
    domains = [operation.domain for operation in stage_request.operations]
    unsupported = sorted(set(domains) - {"pcg", "lighting"})
    if unsupported:
        raise ValueError(
            "scene candidate execution is not registered for domains: "
            + ", ".join(unsupported)
        )

    twin = state.scene.digital_twin
    pcg_targets = [
        (actor, component)
        for actor in twin.actors
        if actor.editable
        for component in actor.pcg_components
    ]
    light_targets = [
        actor for actor in twin.actors if actor.light is not None and not actor.protected
    ]
    named_key_lights = [actor for actor in light_targets if actor.label == "ArtFlow_KeyLight"]
    if named_key_lights:
        light_targets = named_key_lights
    tool_calls: list[SceneCandidateToolCall] = []
    for operation in stage_request.operations:
        if operation.domain == "pcg":
            if len(pcg_targets) != 1:
                raise ValueError("registered PCG execution requires exactly one editable component")
            actor, component = pcg_targets[0]
            tool_calls.append(
                SceneCandidatePCGToolCall(
                    operation_id="pcg-layout-main",
                    target_actor_id=actor.actor_id,
                    target_actor_label=actor.label,
                    expected_source_fingerprint=actor.source_fingerprint,
                    component_id=component.component_id,
                    approved_graph_path=component.graph_path,
                    seed=240_827,
                    max_generated_instances=64,
                )
            )
        elif operation.domain == "lighting":
            if len(light_targets) != 1:
                raise ValueError("registered lighting execution requires exactly one light target")
            actor = light_targets[0]
            tool_calls.append(
                SceneCandidateLightingToolCall(
                    operation_id="lighting-rig-main",
                    target_actor_id=actor.actor_id,
                    target_actor_label=actor.label,
                    expected_source_fingerprint=actor.source_fingerprint,
                    intensity=5.5,
                    temperature_kelvin=4_200,
                )
            )

    payload = {
        "run_id": state.run_id,
        "basis_sequence": state.last_sequence,
        "scene_package_sha256": state.scene.archive_sha256,
        "session_sha256": session.session_sha256,
        "draft_sha256": session.draft.draft_sha256,
        "stage_request_sha256": stage_request.request_sha256,
        "strategy_version": session.strategy_version,
        "source_scene": session.source_scene,
        "candidate_destination": stage_request.candidate_destination,
        "operations": [item.model_dump(mode="json") for item in tool_calls],
    }
    digest = _content_sha256(payload)
    return SceneCandidatePlan(
        plan_id=f"candidate-plan-{digest[:12]}",
        plan_sha256=digest,
        **payload,
    )


def build_scene_session_handshake_receipt(
    state: AgentRunState,
    *,
    action_id: str,
) -> SceneSessionHandshakeReceipt:
    if not state.scene_sessions:
        raise ValueError("scene session handshake requires a persisted Scene Session")
    session = state.scene_sessions[-1]
    if session.start_action_id != action_id:
        raise ValueError("scene session handshake action does not match the active Session")
    stage_request = compile_scene_stage_request(
        state,
        expected_draft_sha256=session.draft.draft_sha256,
    )
    selected_domains = {operation.domain for operation in stage_request.operations}
    candidate_plan = (
        compile_scene_candidate_plan(
            state,
            expected_stage_request_sha256=stage_request.request_sha256,
        )
        if selected_domains and selected_domains <= {"pcg", "lighting"}
        else None
    )
    payload = {
        "action_id": action_id,
        "run_id": state.run_id,
        "source_scene": session.source_scene,
        "scene_package_sha256": session.scene_package_sha256,
        "event_sequence": state.last_sequence,
        "session": session.model_dump(mode="json"),
        "stage_request": stage_request.model_dump(mode="json"),
    }
    if candidate_plan is not None:
        payload["candidate_plan"] = candidate_plan.model_dump(mode="json")
    digest = _content_sha256(payload)
    return SceneSessionHandshakeReceipt(
        handshake_id=f"scene-handshake-{digest[:12]}",
        handshake_sha256=digest,
        action_id=action_id,
        run_id=state.run_id,
        source_scene=session.source_scene,
        scene_package_sha256=session.scene_package_sha256,
        event_sequence=state.last_sequence,
        session=session,
        stage_request=stage_request,
        candidate_plan=candidate_plan,
    )


def validate_scene_session_draft(
    state: AgentRunState,
    draft: SceneSessionDraft,
) -> None:
    expected = compile_scene_session_draft(
        state,
        SceneSessionDraftRequest(
            intent=draft.intent,
            domains=[node.domain for node in draft.nodes],
        ),
    )
    if expected.draft_sha256 != draft.draft_sha256:
        raise ValueError("scene session draft does not match current typed scene facts")


def _content_sha256(payload: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
