from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Annotated, Literal

from mcp import types
from mcp.server import MCPServer
from pydantic import Field

from artflow_agent.contracts import MultiDomainSceneDeltaPlan, SceneDigitalTwin
from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import (
    DomainCorrectionPlan,
    SceneDeltaEvaluation,
    SceneLifecycleLedger,
    VerifiedDispositionReceipt,
    VerifiedDispositionRequest,
)
from artflow_agent.scene_orchestration import (
    CapabilityAttestation,
    MultiDomainDryRunReceipt,
    compile_multi_domain_dry_run,
)

MCP_RESOURCE_URIS = {
    "twin": "artflow://scene/current/twin",
    "lifecycle": "artflow://runs/m9/lifecycle",
    "verification": "artflow://runs/m9/verification",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SceneTwinSummary(StrictContract):
    schema_id: Literal["mcp-scene-twin-summary/1"] = "mcp-scene-twin-summary/1"
    twin_id: str
    twin_sha256: str = Field(pattern=SHA256_PATTERN)
    scene_path: str
    actor_count: int = Field(ge=1)
    editable_actor_ids: list[str]
    protected_actor_ids: list[str]
    light_actor_ids: list[str]
    pcg_component_ids: list[str]
    available_staging_strategies: list[str]
    source_resource_uri: Literal["artflow://scene/current/twin"] = MCP_RESOURCE_URIS["twin"]


class CorrectionInspection(StrictContract):
    schema_id: Literal["mcp-correction-inspection/1"] = "mcp-correction-inspection/1"
    evaluation_sha256: str = Field(pattern=SHA256_PATTERN)
    correction_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    failed_domains: list[str]
    rerun_domains: list[str]
    preserved_domains: list[str]
    requested_lighting_intensity: float
    lifecycle_resource_uri: Literal["artflow://runs/m9/lifecycle"] = MCP_RESOURCE_URIS[
        "lifecycle"
    ]


class DispositionVerification(StrictContract):
    schema_id: Literal["mcp-disposition-verification/1"] = "mcp-disposition-verification/1"
    disposition_id: str
    status: Literal["verified"] = "verified"
    published_scene_path: str
    published_scene_sha256: str = Field(pattern=SHA256_PATTERN)
    source_scene_unchanged: Literal[True] = True
    duplicate_side_effect_count: Literal[0] = 0
    verification_resource_uri: Literal["artflow://runs/m9/verification"] = MCP_RESOURCE_URIS[
        "verification"
    ]


class ArtFlowMCPFacade:
    """Content-addressed adapter over ArtFlow's existing contracts and durable evidence."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.twin_package = self.repo_root / "artifacts/goal/m7-s1-scene-dry-run/scene-package.zip"
        self.plan_path = self.repo_root / "examples/m9-ruin-altar-scene-delta-plan.json"
        self.capabilities_path = self.repo_root / "examples/m9-capability-attestations.json"
        self.lifecycle_root = self.repo_root / "artifacts/goal/m9-s3-correction-release"
        self._assert_fixed_evidence()

    def twin_resource(self) -> str:
        twin, raw_sha = self._load_twin()
        payload = twin.model_dump(mode="json")
        payload["artifact_sha256"] = raw_sha
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def lifecycle_resource(self) -> str:
        events = SceneLifecycleLedger(self.lifecycle_root / "lifecycle.sqlite3").events()
        return json.dumps(
            [item.model_dump(mode="json") for item in events], ensure_ascii=False, indent=2
        )

    def verification_resource(self) -> str:
        path = self.lifecycle_root / "verification.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("status") != "verified":
            raise ValueError("registered M9 verification is not terminal and verified")
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def summarize_twin(self, twin_sha256: str) -> SceneTwinSummary:
        twin, raw_sha = self._load_twin()
        if twin_sha256 != raw_sha:
            raise ValueError("unknown or stale Scene Digital Twin fingerprint")
        return SceneTwinSummary(
            twin_id=twin.twin_id,
            twin_sha256=raw_sha,
            scene_path=twin.scene_path,
            actor_count=len(twin.actors),
            editable_actor_ids=sorted(item.actor_id for item in twin.actors if item.editable),
            protected_actor_ids=sorted(item.actor_id for item in twin.actors if item.protected),
            light_actor_ids=sorted(item.actor_id for item in twin.actors if item.light is not None),
            pcg_component_ids=sorted(
                component.component_id
                for actor in twin.actors
                for component in actor.pcg_components
            ),
            available_staging_strategies=sorted(
                item.strategy for item in twin.staging_capabilities if item.available
            ),
        )

    def compile_registered_plan(self, plan_sha256: str) -> MultiDomainDryRunReceipt:
        plan = MultiDomainSceneDeltaPlan.model_validate_json(
            self.plan_path.read_text(encoding="utf-8")
        )
        if plan_sha256 != plan.canonical_sha256():
            raise ValueError("unknown plan fingerprint; arbitrary plan payloads are not accepted")
        capabilities = [
            CapabilityAttestation.model_validate(item)
            for item in json.loads(self.capabilities_path.read_text(encoding="utf-8"))
        ]
        observed = {
            target_id: fingerprint
            for operation in plan.operations
            for target_id, fingerprint in operation.expected_source_fingerprints.items()
        }
        return compile_multi_domain_dry_run(plan, capabilities, observed)

    def inspect_correction(self, evaluation_sha256: str) -> CorrectionInspection:
        evaluation = SceneDeltaEvaluation.model_validate_json(
            (self.lifecycle_root / "failure-evaluation.json").read_text(encoding="utf-8")
        )
        correction = DomainCorrectionPlan.model_validate_json(
            (self.lifecycle_root / "correction-plan.json").read_text(encoding="utf-8")
        )
        if evaluation_sha256 != evaluation.evaluation_sha256:
            raise ValueError("unknown evaluation fingerprint")
        if correction.evaluation_sha256 != evaluation.evaluation_sha256:
            raise ValueError("registered correction does not bind the evaluation")
        if correction.lighting is None:
            raise ValueError("registered correction has no bounded lighting patch")
        return CorrectionInspection(
            evaluation_sha256=evaluation.evaluation_sha256,
            correction_plan_sha256=correction.plan_sha256,
            failed_domains=list(evaluation.failed_domains),
            rerun_domains=list(correction.rerun_domains),
            preserved_domains=sorted(correction.preserved_domain_evidence),
            requested_lighting_intensity=correction.lighting.intensity,
        )

    def verify_disposition(self, disposition_id: str) -> DispositionVerification:
        request = VerifiedDispositionRequest.model_validate_json(
            (self.lifecycle_root / "disposition-request.json").read_text(encoding="utf-8")
        )
        receipt = VerifiedDispositionReceipt.model_validate_json(
            (self.lifecycle_root / "disposition-receipt.json").read_text(encoding="utf-8")
        )
        if disposition_id != request.disposition_id or receipt.disposition_id != disposition_id:
            raise ValueError("unknown disposition identity")
        if receipt.evaluation_sha256 != request.evaluation_sha256:
            raise ValueError("disposition receipt is not bound to its verified evaluation")
        published = self._unreal_package_file(receipt.published_scene_path)
        source = self._unreal_package_file("/Game/ArtFlowDemo")
        if file_sha256(published) != receipt.published_scene_sha256:
            raise ValueError("published Unreal package bytes no longer match the receipt")
        if file_sha256(source) != receipt.source_scene_sha256_after:
            raise ValueError("source Unreal package changed after disposition")
        return DispositionVerification(
            disposition_id=receipt.disposition_id,
            published_scene_path=receipt.published_scene_path,
            published_scene_sha256=receipt.published_scene_sha256,
        )

    def _load_twin(self) -> tuple[SceneDigitalTwin, str]:
        with zipfile.ZipFile(self.twin_package) as archive:
            raw = archive.read("scene-digital-twin.json")
        return SceneDigitalTwin.model_validate_json(raw), hashlib.sha256(raw).hexdigest()

    def _unreal_package_file(self, object_path: str | None) -> Path:
        if object_path is None or not object_path.startswith("/Game/"):
            raise ValueError("only fixed project Unreal package paths are supported")
        relative = object_path.removeprefix("/Game/") + ".umap"
        return self.repo_root / "integrations/unreal/ArtFlowBridgeHost/Content" / relative

    def _assert_fixed_evidence(self) -> None:
        required = [
            self.twin_package,
            self.plan_path,
            self.capabilities_path,
            self.lifecycle_root / "lifecycle.sqlite3",
            self.lifecycle_root / "verification.json",
            self.lifecycle_root / "failure-evaluation.json",
            self.lifecycle_root / "correction-plan.json",
            self.lifecycle_root / "disposition-request.json",
            self.lifecycle_root / "disposition-receipt.json",
        ]
        missing = [path.relative_to(self.repo_root).as_posix() for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError("ArtFlow MCP evidence is incomplete: " + ", ".join(missing))


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "artifacts/goal/m9-s3-correction-release/verification.json"
        ).is_file():
            return candidate
    raise RuntimeError("ArtFlow MCP must be started from the checked-out ArtFlow repository")


def build_mcp_server(repo_root: Path) -> MCPServer:
    facade = ArtFlowMCPFacade(repo_root)
    server = MCPServer(
        "ArtFlow Agent",
        title="ArtFlow Unreal 场景变更 Agent",
        description="读取真实场景证据并调用现有有界规划、纠错与发布验证能力。",
        instructions=(
            "只使用内容哈希或 ArtFlow ID 调用工具。此 MCP Server 不执行任意代码、不接受文件路径，"
            "也不拥有 Agent 状态机。"
        ),
        version="0.10.0",
        log_level="WARNING",
    )

    @server.resource(
        MCP_RESOURCE_URIS["twin"],
        name="current_scene_twin",
        title="当前 Unreal Scene Digital Twin",
        description="M7 实机导出的相机、Actor、材质、灯光、PCG、边界与保护关系。",
        mime_type="application/json",
    )
    def current_scene_twin() -> str:
        return facade.twin_resource()

    @server.resource(
        MCP_RESOURCE_URIS["lifecycle"],
        name="m9_lifecycle",
        title="M9 持久生命周期",
        description="M9 评价、单域纠正、恢复和发布的九个 append-only 事件。",
        mime_type="application/json",
    )
    def m9_lifecycle() -> str:
        return facade.lifecycle_resource()

    @server.resource(
        MCP_RESOURCE_URIS["verification"],
        name="m9_verification",
        title="M9 独立验证报告",
        description="单域纠正、无重提恢复与内容寻址发布的独立验证摘要。",
        mime_type="application/json",
    )
    def m9_verification() -> str:
        return facade.verification_resource()

    read_only = types.ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    @server.tool(
        name="scene.twin.summarize",
        title="核验场景数字孪生",
        description="按 SHA-256 读取固定 Scene Twin，返回受保护对象和可用暂存策略摘要。",
        annotations=read_only,
        structured_output=True,
    )
    def summarize_twin(
        twin_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)],
    ) -> SceneTwinSummary:
        return facade.summarize_twin(twin_sha256)

    @server.tool(
        name="scene.delta.compile_registered",
        title="编译已注册 Scene Delta",
        description="只接受仓库已注册计划的内容哈希，并调用 ArtFlow 原有 DAG 编译与能力路由。",
        annotations=read_only,
        structured_output=True,
    )
    def compile_registered_plan(
        plan_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)],
    ) -> MultiDomainDryRunReceipt:
        return facade.compile_registered_plan(plan_sha256)

    @server.tool(
        name="scene.correction.inspect",
        title="核验失败域纠正范围",
        description="按评价哈希读取持久证据，证明纠正只重跑失败域并锁定成功域。",
        annotations=read_only,
        structured_output=True,
    )
    def inspect_correction(
        evaluation_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)],
    ) -> CorrectionInspection:
        return facade.inspect_correction(evaluation_sha256)

    @server.tool(
        name="scene.disposition.verify",
        title="验证 Unreal 发布结果",
        description="按 disposition ID 复检真实已发布关卡、来源回执和源关卡不变式。",
        annotations=read_only,
        structured_output=True,
    )
    def verify_disposition(
        disposition_id: Annotated[str, Field(pattern=r"^m9-disposition-[0-9a-f]{20}$")],
    ) -> DispositionVerification:
        return facade.verify_disposition(disposition_id)

    # MCP SDK 2.1 derives a permissive Pydantic model for function arguments. Close the
    # generated top-level schema and validator so unknown keys cannot be silently discarded.
    # The dependency is minor-version bounded because this is intentionally fail-closed.
    for registered_tool in server._tool_manager._tools.values():
        argument_model = registered_tool.fn_metadata.arg_model
        argument_model.model_config["extra"] = "forbid"
        argument_model.model_rebuild(force=True)
        registered_tool.parameters = argument_model.model_json_schema(by_alias=True)

    return server


def default_mcp_server() -> MCPServer:
    return build_mcp_server(find_repo_root())
