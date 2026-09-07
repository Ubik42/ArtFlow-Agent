from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .scene_lifecycle import canonical_sha256

RouteId = Literal["cloth_banner", "damage_variant", "mechanism_shot"]
StageCapabilityId = Literal[
    "comfy.material.banner_pattern.v1",
    "blender.cloth.banner_authoring.v1",
    "unreal.asset.static_cloth_banner.v1",
    "comfy.spatial.damage_field.v1",
    "blender.boolean.material_damage.v1",
    "unreal.asset.damage_variant.v1",
    "blender.armature.articulated_gate.v1",
    "unreal.sequencer.mechanism_shot.v1",
]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DccRouteCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_id: RouteId
    label: str = Field(min_length=2, max_length=40)
    ready: bool
    match_score: int = Field(ge=0, le=20)
    matched_terms: list[str] = Field(max_length=8)
    stage_capability_ids: list[StageCapabilityId] = Field(min_length=2, max_length=3)
    readiness_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class DccRouteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-dcc-route-decision/1"] = "artflow-dcc-route-decision/1"
    decision_id: str = Field(pattern=r"^dcc-route-[a-f0-9]{12}$")
    decision_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    policy_version: Literal["dcc-route-policy/1"] = "dcc-route-policy/1"
    run_id: str
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    session_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    intent_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    selected_route_id: RouteId
    selected_stage_capability_ids: list[StageCapabilityId] = Field(min_length=2, max_length=3)
    selection_basis: list[str] = Field(min_length=2, max_length=5)
    candidates: list[DccRouteCandidate] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def verify_identity_and_selection(self) -> DccRouteDecision:
        candidate_ids = [candidate.route_id for candidate in self.candidates]
        if candidate_ids != ["cloth_banner", "damage_variant", "mechanism_shot"]:
            raise ValueError("DCC route catalog order changed")
        ready = [candidate for candidate in self.candidates if candidate.ready]
        expected = max(
            ready, key=lambda item: (item.match_score, -candidate_ids.index(item.route_id))
        )
        if (
            self.selected_route_id != expected.route_id
            or self.selected_stage_capability_ids != expected.stage_capability_ids
        ):
            raise ValueError("selected DCC route does not match the bounded policy")
        unsigned = self.model_dump(mode="json", exclude={"decision_id", "decision_sha256"})
        digest = canonical_sha256(unsigned)
        if self.decision_id != f"dcc-route-{digest[:12]}" or self.decision_sha256 != digest:
            raise ValueError("DCC route decision fingerprint mismatch")
        return self


ROUTES: tuple[tuple[RouteId, str, tuple[str, ...], tuple[StageCapabilityId, ...], str], ...] = (
    (
        "cloth_banner",
        "风场旗帜",
        ("材质", "布料", "织物", "风", "旗帜"),
        (
            "comfy.material.banner_pattern.v1",
            "blender.cloth.banner_authoring.v1",
            "unreal.asset.static_cloth_banner.v1",
        ),
        "artifacts/goal/m58-s1-live-cloth-banner/live-cloth-banner-work-receipt.json",
    ),
    (
        "damage_variant",
        "破损变体",
        ("破损", "损伤", "旧化", "残损", "缺口"),
        (
            "comfy.spatial.damage_field.v1",
            "blender.boolean.material_damage.v1",
            "unreal.asset.damage_variant.v1",
        ),
        "artifacts/goal/m56-s1-live-damage-variant/live-damage-variant-work-receipt.json",
    ),
    (
        "mechanism_shot",
        "机关镜头",
        ("机关", "动画", "镜头", "运动", "开合"),
        ("blender.armature.articulated_gate.v1", "unreal.sequencer.mechanism_shot.v1"),
        "artifacts/goal/m54-s1-live-mechanism-shot/live-mechanism-shot-work-receipt.json",
    ),
)


def select_dcc_route(
    *,
    project_root: Path,
    run_id: str,
    session_id: str,
    session_sha256: str,
    scene_package_sha256: str,
    intent: str,
) -> DccRouteDecision:
    normalized = "".join(intent.lower().split())
    candidates: list[dict[str, object]] = []
    for route_id, label, terms, stages, receipt_relative in ROUTES:
        receipt_path = project_root / receipt_relative
        ready = receipt_path.is_file()
        matched = [term for term in terms if term in normalized]
        scene_fit = 1 if route_id == "cloth_banner" and "材质" in normalized else 0
        candidates.append(
            {
                "route_id": route_id,
                "label": label,
                "ready": ready,
                "match_score": len(matched) * 4 + scene_fit,
                "matched_terms": matched,
                "stage_capability_ids": list(stages),
                "readiness_receipt_sha256": file_sha256(receipt_path) if ready else "0" * 64,
            }
        )
    ready_candidates = [item for item in candidates if item["ready"]]
    if not ready_candidates:
        raise ValueError("no verified DCC production route is ready")
    selected = max(
        ready_candidates,
        key=lambda item: (
            int(item["match_score"]),
            -next(index for index, route in enumerate(ROUTES) if route[0] == item["route_id"]),
        ),
    )
    matched_text = (
        "、".join(str(term) for term in selected["matched_terms"]) or "当前场景可编辑资产"
    )
    payload = {
        "schema_id": "artflow-dcc-route-decision/1",
        "policy_version": "dcc-route-policy/1",
        "run_id": run_id,
        "session_id": session_id,
        "session_sha256": session_sha256,
        "scene_package_sha256": scene_package_sha256,
        "intent_sha256": canonical_sha256({"intent": intent}),
        "selected_route_id": selected["route_id"],
        "selected_stage_capability_ids": selected["stage_capability_ids"],
        "selection_basis": [
            f"当前意图命中：{matched_text}",
            "所选路线的 ComfyUI、Blender 与 Unreal 回执均已就绪",
            "采用已验证路线中的最高语义匹配分，不调用未登记宿主能力",
        ],
        "candidates": candidates,
    }
    digest = canonical_sha256(payload)
    payload["decision_id"] = f"dcc-route-{digest[:12]}"
    payload["decision_sha256"] = digest
    return DccRouteDecision.model_validate(payload)
