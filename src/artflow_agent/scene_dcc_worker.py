from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .agent_runtime import AgentEventStore, AgentRuntimeError
from .blender_set_dressing import (
    BlenderSetDressingReceipt,
    BlenderSetDressingRequest,
    verify_set_dressing,
)
from .blender_surface import BlenderSurfaceRequest
from .lookdev_handoff import SceneLookdevRequest
from .scene_dcc_work import SceneDccWorkDefinition, SceneDccWorkProgressRequest
from .surface_detail import (
    BlenderSurfaceDetailReceipt,
    ComfySurfaceDetailReceipt,
    SurfaceDetailRequest,
    verify_surface_detail_artifacts,
)

WORKER_ID = "artflow-local-blender-worker-v1"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _load_receipt(path: Path, *, expected_sha256: str) -> dict[str, object]:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    recorded = receipt.get("receipt_sha256")
    payload = dict(receipt)
    payload.pop("receipt_sha256", None)
    if recorded != expected_sha256 or _canonical_sha256(payload) != expected_sha256:
        raise ValueError(f"DCC receipt identity changed: {path.name}")
    return receipt


def _verify_artifacts(root: Path, receipt: dict[str, object]) -> None:
    artifacts = receipt.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise TypeError("DCC receipt artifacts must be a list")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise TypeError("DCC artifact entry must be an object")
        path = (root / str(artifact["relative_path"])).resolve()
        if root.resolve() not in path.parents:
            raise ValueError("DCC artifact escaped its registered root")
        if not path.is_file() or _file_sha256(path) != artifact["sha256"]:
            raise ValueError(f"DCC artifact identity changed: {path.name}")


def reconcile_registered_chain(project_root: Path, work: SceneDccWorkDefinition) -> str:
    roots = {
        "model": project_root / "artifacts/goal/m23-s1-blender-modeling",
        "pbr": project_root / "artifacts/goal/m23-s2-blender-pbr",
        "layout": project_root / "artifacts/goal/m23-s4-geometry-layout",
        "shot": project_root / "artifacts/goal/m23-s5-camera-light",
        "conditioning": project_root / "artifacts/goal/m24-s1-scene-conditioning",
        "lookdev": project_root / "artifacts/goal/m24-s2-scene-lookdev",
        "surface": project_root / "artifacts/goal/m26-s1-surface-bake",
        "dressing": project_root / "artifacts/goal/m28-s1-set-dressing",
        "detail": project_root / "artifacts/goal/m30-s1-surface-detail",
    }
    model_request = json.loads(
        (roots["model"] / "modeling-request.json").read_text(encoding="utf-8")
    )
    pbr_request = json.loads(
        (roots["pbr"] / "pbr-assembly-request.json").read_text(encoding="utf-8")
    )
    if model_request["request_sha256"] != work.modeling_request_sha256:
        raise ValueError("registered modeling request changed")
    if pbr_request["request_sha256"] != work.pbr_request_sha256:
        raise ValueError("registered PBR request changed")

    if work.layout_request_sha256 is not None:
        layout_request = json.loads(
            (roots["layout"] / "layout-request.json").read_text(encoding="utf-8")
        )
        if layout_request["request_sha256"] != work.layout_request_sha256:
            raise ValueError("registered Geometry Nodes request changed")
        layout_receipt = _load_receipt(
            roots["layout"] / "layout-receipt.json",
            expected_sha256=str(work.layout_receipt_sha256),
        )
        _verify_artifacts(roots["layout"], layout_receipt)

    if work.shot_request_sha256 is not None:
        shot_request = json.loads((roots["shot"] / "shot-request.json").read_text(encoding="utf-8"))
        if shot_request["request_sha256"] != work.shot_request_sha256:
            raise ValueError("registered camera-light request changed")
        shot_receipt = _load_receipt(
            roots["shot"] / "shot-receipt.json",
            expected_sha256=str(work.shot_receipt_sha256),
        )
        _verify_artifacts(roots["shot"], shot_receipt)
        unreal_receipt = _load_receipt(
            roots["shot"] / "unreal-shot-return-receipt.json",
            expected_sha256=str(work.unreal_shot_return_receipt_sha256),
        )
        if (
            work.lookdev_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal shot candidate changed")
        screenshot = roots["shot"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal shot screenshot identity changed")

    if work.lookdev_request_sha256 is not None:
        lookdev_request = SceneLookdevRequest.model_validate_json(
            (roots["lookdev"] / "lookdev-request.json").read_text(encoding="utf-8")
        )
        if lookdev_request.request_sha256 != work.lookdev_request_sha256:
            raise ValueError("registered scene-conditioned lookdev request changed")
        if lookdev_request.accepted_artifact_sha256 != work.accepted_visual_target_sha256:
            raise ValueError("registered visual target identity changed")
        target = roots["conditioning"] / "depth-guided-candidate.png"
        if _file_sha256(target) != work.accepted_visual_target_sha256:
            raise ValueError("accepted visual target bytes changed")
        lookdev_receipt = _load_receipt(
            roots["lookdev"] / "lookdev-receipt.json",
            expected_sha256=str(work.lookdev_receipt_sha256),
        )
        _verify_artifacts(roots["lookdev"], lookdev_receipt)
        unreal_receipt = _load_receipt(
            roots["lookdev"] / "unreal-lookdev-return-receipt.json",
            expected_sha256=str(work.unreal_lookdev_return_receipt_sha256),
        )
        if (
            work.surface_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal lookdev candidate changed")
        shot_return = json.loads(
            (roots["shot"] / "unreal-shot-return-receipt.json").read_text(encoding="utf-8")
        )
        if unreal_receipt.get("source_candidate_scene_path") != shot_return.get(
            "candidate_scene_path"
        ):
            raise ValueError("Unreal lookdev candidate no longer derives from the registered shot")
        screenshot = roots["lookdev"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal lookdev screenshot identity changed")

    if work.surface_request_sha256 is not None:
        surface_request = BlenderSurfaceRequest.model_validate_json(
            (roots["surface"] / "surface-request.json").read_text(encoding="utf-8")
        )
        if surface_request.request_sha256 != work.surface_request_sha256:
            raise ValueError("registered surface request changed")
        surface_receipt = _load_receipt(
            roots["surface"] / "surface-receipt.json",
            expected_sha256=str(work.surface_receipt_sha256),
        )
        _verify_artifacts(roots["surface"], surface_receipt)
        unreal_receipt = _load_receipt(
            roots["surface"] / "unreal-surface-return-receipt.json",
            expected_sha256=str(work.unreal_surface_return_receipt_sha256),
        )
        if (
            work.set_dressing_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal surface candidate changed")
        lookdev_return = json.loads(
            (roots["lookdev"] / "unreal-lookdev-return-receipt.json").read_text(encoding="utf-8")
        )
        if unreal_receipt.get("source_candidate_scene_path") != lookdev_return.get(
            "candidate_scene_path"
        ):
            raise ValueError("Unreal surface candidate no longer derives from lookdev")
        screenshot = roots["surface"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal surface screenshot identity changed")

    if work.set_dressing_request_sha256 is not None:
        request = BlenderSetDressingRequest.model_validate_json(
            (roots["dressing"] / "set-dressing-request.json").read_text(encoding="utf-8")
        )
        receipt = BlenderSetDressingReceipt.model_validate_json(
            (roots["dressing"] / "set-dressing-receipt.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.set_dressing_request_sha256:
            raise ValueError("registered set-dressing request changed")
        if receipt.receipt_sha256 != work.set_dressing_receipt_sha256:
            raise ValueError("registered set-dressing receipt changed")
        verify_set_dressing(request, receipt, roots["dressing"])
        manifest_artifact = next(
            item for item in receipt.artifacts if item.kind == "transform_manifest"
        )
        if manifest_artifact.sha256 != work.set_dressing_manifest_sha256:
            raise ValueError("registered transform manifest changed")
        unreal_receipt = _load_receipt(
            roots["dressing"] / "unreal-set-dressing-return-receipt.json",
            expected_sha256=str(work.unreal_set_dressing_return_receipt_sha256),
        )
        if (
            work.surface_detail_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal set-dressing candidate changed")
        surface_return = json.loads(
            (roots["surface"] / "unreal-surface-return-receipt.json").read_text(encoding="utf-8")
        )
        if unreal_receipt.get("source_candidate_scene_path") != surface_return.get(
            "candidate_scene_path"
        ):
            raise ValueError("Unreal set-dressing candidate no longer derives from surface")
        screenshot = roots["dressing"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal set-dressing screenshot identity changed")

    if work.surface_detail_request_sha256 is not None:
        request = SurfaceDetailRequest.model_validate_json(
            (roots["detail"] / "surface-detail-request.json").read_text(encoding="utf-8")
        )
        comfy_receipt = ComfySurfaceDetailReceipt.model_validate_json(
            (roots["detail"] / "comfy-surface-detail-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        blender_receipt = BlenderSurfaceDetailReceipt.model_validate_json(
            (roots["detail"] / "blender-surface-detail-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        if request.request_sha256 != work.surface_detail_request_sha256:
            raise ValueError("registered surface-detail request changed")
        if comfy_receipt.receipt_sha256 != work.comfy_surface_detail_receipt_sha256:
            raise ValueError("registered Comfy surface-detail receipt changed")
        if blender_receipt.receipt_sha256 != work.blender_surface_detail_receipt_sha256:
            raise ValueError("registered Blender surface-detail receipt changed")
        verify_surface_detail_artifacts(request, comfy_receipt, blender_receipt, roots["detail"])
        unreal_receipt = _load_receipt(
            roots["detail"] / "unreal-surface-detail-return-receipt.json",
            expected_sha256=str(work.unreal_surface_detail_return_receipt_sha256),
        )
        if unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path:
            raise ValueError("Unreal surface-detail candidate changed")
        dressing_return = json.loads(
            (roots["dressing"] / "unreal-set-dressing-return-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        if unreal_receipt.get("source_candidate_scene_path") != dressing_return.get(
            "candidate_scene_path"
        ):
            raise ValueError("surface-detail candidate no longer derives from set dressing")
        screenshot = roots["detail"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal surface-detail screenshot identity changed")

    return work.unreal_return_receipt_sha256


class SceneDccWorker:
    def __init__(self, store: AgentEventStore, project_root: Path) -> None:
        self._store = store
        self._project_root = project_root.resolve()

    def run_once(self, run_id: str) -> None:
        state = self._store.load(run_id)
        work = state.scene_dcc_work
        if work is None:
            raise AgentRuntimeError("current Scene Session has no DCC work")
        if work.status == "succeeded":
            return
        if work.status == "failed":
            raise AgentRuntimeError("DCC work has failed and requires a new work identity")
        if work.status == "queued":
            self._store.claim_scene_dcc_work(
                run_id,
                work_sha256=work.definition.work_sha256,
                worker_id=WORKER_ID,
            )
            work = self._store.load(run_id).scene_dcc_work
            assert work is not None
        if work.worker_id != WORKER_ID:
            raise AgentRuntimeError("DCC work is owned by another worker")

        try:
            if work.status == "claimed":
                self._progress(run_id, work.definition, "executing", "正在核对固定 DCC 能力链")
                work = self._store.load(run_id).scene_dcc_work
                assert work is not None
            outcome = reconcile_registered_chain(self._project_root, work.definition)
            if work.status == "executing":
                self._progress(
                    run_id, work.definition, "reconciling", "正在对账 Blender 与 Unreal 回执"
                )
            work = self._store.load(run_id).scene_dcc_work
            assert work is not None
            if work.status == "reconciling":
                self._progress(
                    run_id,
                    work.definition,
                    "succeeded",
                    "建模、PBR、Geometry Nodes、镜头灯光、Lookdev、Surface、物理布景与表面细节已回流",
                    outcome_sha256=outcome,
                )
        except (OSError, TypeError, ValueError) as exc:
            current = self._store.load(run_id).scene_dcc_work
            if current is not None and current.status in {"claimed", "executing", "reconciling"}:
                self._progress(run_id, current.definition, "failed", str(exc)[:500])
            raise

    def _progress(
        self,
        run_id: str,
        definition: SceneDccWorkDefinition,
        status: str,
        message: str,
        *,
        outcome_sha256: str | None = None,
    ) -> None:
        self._store.progress_scene_dcc_work(
            run_id,
            SceneDccWorkProgressRequest(
                work_sha256=definition.work_sha256,
                worker_id=WORKER_ID,
                status=status,
                action_id=f"{definition.work_id}-{status}",
                outcome_sha256=outcome_sha256,
                message=message,
            ),
        )
