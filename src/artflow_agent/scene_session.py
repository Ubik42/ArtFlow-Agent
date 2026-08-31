from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .agent_runtime import AgentRunState

SceneDomain = Literal["image", "material", "asset", "pcg", "lighting"]
SceneDomainReadiness = Literal["ready", "guarded", "experimental"]

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
    source_scene: str
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    intent: str
    preserve: list[str]
    prohibit: list[str]
    nodes: list[SceneSpectrumNode]
    ready_domain_count: int = Field(ge=0)
    guarded_domain_count: int = Field(ge=0)
    experimental_domain_count: int = Field(ge=0)
    can_stage: bool
    next_action: str


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
        "scene_package_sha256": state.scene.archive_sha256,
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
        source_scene=package.provenance.scene_name,
        scene_package_sha256=state.scene.archive_sha256,
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
