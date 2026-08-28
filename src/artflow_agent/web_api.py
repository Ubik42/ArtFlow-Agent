from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from zipfile import ZipFile

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent_projection import (
    AgentRunProjection,
    AgentRunSummary,
    list_agent_runs,
    project_agent_run,
    project_stream_event,
    project_stream_snapshot,
)
from .agent_runtime import AgentEventStore, AgentRuntimeError
from .batch import run_batch
from .comfy import ComfyError, ComfyGateway, inspect_environment
from .comparison import (
    ComparisonAuthorizationDecision,
    ProviderComparisonPlan,
)
from .providers import ComfyRecipeProvider
from .recipes import RecipeCatalog
from .review import create_contact_sheet
from .run_store import RunStateError, RunStore
from .scene_packages import ScenePackageArchive, ScenePackageImportError

MAX_UI_SCENE_PACKAGE_BYTES = 64 * 1024 * 1024

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ExecuteRequest(BaseModel):
    mask_path: str | None = None


class JobSnapshot(BaseModel):
    run_id: str
    active: bool
    error: str | None = None


class ResolveAgentApprovalRequest(BaseModel):
    resolution: Literal["approved", "rejected"]


class AuthorizeComparisonRequest(BaseModel):
    approved_by: str = Field(min_length=1, max_length=120)


class JobRegistry:
    def __init__(self) -> None:
        self._threads: dict[str, threading.Thread] = {}
        self._errors: dict[str, str] = {}
        self._lock = threading.Lock()

    def start(self, run_id: str, target: Callable[[], None]) -> None:
        with self._lock:
            current = self._threads.get(run_id)
            if current is not None and current.is_alive():
                raise RuntimeError("This run is already executing")
            self._errors.pop(run_id, None)

            def guarded_target() -> None:
                try:
                    target()
                except (ComfyError, RunStateError, OSError, ValueError, TimeoutError) as exc:
                    with self._lock:
                        self._errors[run_id] = str(exc)

            thread = threading.Thread(target=guarded_target, name=f"artflow-{run_id}", daemon=True)
            self._threads[run_id] = thread
            thread.start()

    def snapshot(self, run_id: str) -> JobSnapshot:
        with self._lock:
            thread = self._threads.get(run_id)
            return JobSnapshot(
                run_id=run_id,
                active=thread is not None and thread.is_alive(),
                error=self._errors.get(run_id),
            )


def create_app(
    *,
    runs_dir: Path | None = None,
    agent_database: Path | None = None,
    comfy_url: str = "http://127.0.0.1:8188",
    delivery_artifact_root: Path | None = None,
) -> FastAPI:
    resolved_runs = (runs_dir or PROJECT_ROOT / "runs").resolve()
    store = RunStore(resolved_runs)
    resolved_agent_database = (agent_database or resolved_runs / "agent-events.sqlite3").resolve()
    agent_store = AgentEventStore(resolved_agent_database)
    scene_archive_root = resolved_runs / ".agent-artifacts" / "scene-packages"
    provider_artifact_root = (
        resolved_agent_database.parent / ".agent-artifacts" / "provider-outputs"
    )
    revision_artifact_root = PROJECT_ROOT / "artifacts" / "goal" / "m4-s3-bounded-revision"
    resolved_delivery_artifact_root = (
        delivery_artifact_root
        or PROJECT_ROOT / "artifacts" / "goal" / "m6-s1-unreal-return"
    ).resolve()
    jobs = JobRegistry()
    app = FastAPI(title="ArtFlow Agent", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        snapshot = inspect_environment(comfy_url)
        return {
            "reachable": snapshot.reachable,
            "vram_mb": snapshot.vram_mb,
            "model_inventory": snapshot.model_inventory,
            "node_count": len(snapshot.nodes),
        }

    @app.get("/api/runs")
    def list_runs():
        return store.list()

    @app.get("/api/agent/runs", response_model=list[AgentRunSummary])
    def list_durable_agent_runs():
        try:
            return list_agent_runs(agent_store)
        except AgentRuntimeError as exc:
            raise HTTPException(status_code=409, detail=f"Agent event store is corrupt: {exc}") from exc

    @app.get("/api/agent/runs/{run_id}", response_model=AgentRunProjection)
    def get_durable_agent_run(run_id: str):
        try:
            return project_agent_run(agent_store, run_id)
        except AgentRuntimeError as exc:
            status_code = 404 if str(exc).startswith("Unknown Agent run") else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/agent/scene-packages/import", response_model=AgentRunProjection)
    async def import_scene_package(request: Request):
        content_type = request.headers.get("content-type", "").split(";", 1)[0].casefold()
        if content_type not in {"application/zip", "application/octet-stream"}:
            raise HTTPException(status_code=415, detail="Scene import requires raw ZIP bytes")
        declared_size = request.headers.get("content-length")
        if declared_size:
            try:
                if int(declared_size) > MAX_UI_SCENE_PACKAGE_BYTES:
                    raise HTTPException(status_code=413, detail="Scene Package exceeds the 64 MiB UI limit")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid Content-Length") from exc
        payload = await request.body()
        if not payload:
            raise HTTPException(status_code=400, detail="Scene Package body is empty")
        if len(payload) > MAX_UI_SCENE_PACKAGE_BYTES:
            raise HTTPException(status_code=413, detail="Scene Package exceeds the 64 MiB UI limit")

        expected_sha256 = request.headers.get("x-scene-package-sha256")
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if expected_sha256 is not None and expected_sha256.casefold() != actual_sha256:
            raise HTTPException(status_code=409, detail="Scene Package upload hash does not match")

        scene_archive_root.mkdir(parents=True, exist_ok=True)
        temporary_path = scene_archive_root / f".{uuid.uuid4().hex}.uploading"
        temporary_path.write_bytes(payload)
        try:
            preview = ScenePackageArchive().inspect(temporary_path)
            final_path = scene_archive_root / f"{preview.archive_sha256}.zip"
            if final_path.exists():
                ScenePackageArchive().inspect(final_path)
                temporary_path.unlink()
            else:
                os.replace(temporary_path, final_path)

            run_id = (
                f"unreal-{preview.package.package_id[:88]}-{preview.archive_sha256[:12]}"
            )
            agent_store.create_run(run_id)
            agent_store.attach_scene(
                run_id,
                preview,
                expected_archive_sha256=actual_sha256,
            )
            return project_agent_run(agent_store, run_id)
        except ScenePackageImportError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AgentRuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        finally:
            temporary_path.unlink(missing_ok=True)

    @app.get("/api/agent/runs/{run_id}/scene/passes/{pass_kind}")
    def get_scene_pass(run_id: str, pass_kind: str):
        try:
            state = agent_store.load(run_id)
            if state.scene is None:
                raise HTTPException(status_code=404, detail="Run has no Scene Package")
            matches = [item for item in state.scene.package.passes if item.kind == pass_kind]
            if len(matches) != 1:
                raise HTTPException(status_code=404, detail="Scene pass not found")
            archive_path = scene_archive_root / f"{state.scene.archive_sha256}.zip"
            preview = ScenePackageArchive().inspect(archive_path)
            if preview.archive_sha256 != state.scene.archive_sha256:
                raise ScenePackageImportError("Persisted Scene Package identity changed")
            with ZipFile(archive_path) as archive:
                content = archive.read(matches[0].artifact.path)
            return Response(
                content=content,
                media_type=matches[0].artifact.media_type,
                headers={
                    "Cache-Control": "public, immutable, max-age=31536000",
                    "X-Content-SHA256": matches[0].artifact.sha256,
                },
            )
        except AgentRuntimeError as exc:
            status_code = 404 if str(exc).startswith("Unknown Agent run") else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

        except ScenePackageImportError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Persisted Scene Package failed verification: {exc}",
            ) from exc

    @app.get(
        "/api/agent/runs/{run_id}/executions/{execution_id}/artifacts/{artifact_sha256}"
    )
    def get_provider_artifact(run_id: str, execution_id: str, artifact_sha256: str):
        try:
            state = agent_store.load(run_id)
            execution = next(
                item
                for item in state.provider_executions
                if item.execution_id == execution_id
            )
            if execution.receipt is None or execution.status != "succeeded":
                raise AgentRuntimeError("Provider execution has no verified successful receipt")
            artifact = next(
                item
                for item in execution.receipt.artifacts
                if item.sha256 == artifact_sha256
            )
            path = provider_artifact_root / f"{artifact.sha256}.png"
            if not path.is_file():
                raise AgentRuntimeError("Verified provider artifact is not persisted locally")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != artifact.sha256:
                raise AgentRuntimeError("Persisted provider artifact hash does not match receipt")
            return Response(
                content=content,
                media_type=artifact.media_type,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-Content-SHA256": artifact.sha256,
                },
            )
        except (AgentRuntimeError, StopIteration) as exc:
            message = str(exc) or "Unknown provider execution artifact"
            status_code = 404 if "Unknown" in message or "not persisted" in message else 409
            raise HTTPException(status_code=status_code, detail=message) from exc

    @app.get(
        "/api/agent/runs/{run_id}/codex-candidates/{candidate_id}/artifacts/{artifact_sha256}"
    )
    def get_codex_candidate_artifact(
        run_id: str,
        candidate_id: str,
        artifact_sha256: str,
    ):
        try:
            state = agent_store.load(run_id)
            record = next(
                item
                for item in state.codex_image_candidates
                if item.receipt.candidate_id == candidate_id
            )
            artifact = record.receipt.artifact
            if artifact.sha256 != artifact_sha256:
                raise AgentRuntimeError("Codex candidate artifact identity does not match receipt")
            path = provider_artifact_root / f"{artifact.sha256}.png"
            if not path.is_file():
                raise AgentRuntimeError("Codex candidate artifact is not persisted locally")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != artifact.sha256:
                raise AgentRuntimeError("Persisted Codex candidate hash does not match receipt")
            return Response(
                content=content,
                media_type=artifact.media_type,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-Content-SHA256": artifact.sha256,
                },
            )
        except (AgentRuntimeError, StopIteration) as exc:
            message = str(exc) or "Unknown Codex image candidate"
            status_code = 404 if "Unknown" in message or "not persisted" in message else 409
            raise HTTPException(status_code=status_code, detail=message) from exc

    @app.get(
        "/api/agent/runs/{run_id}/negative-controls/{control_id}/artifacts/{artifact_sha256}"
    )
    def get_negative_control_artifact(
        run_id: str,
        control_id: str,
        artifact_sha256: str,
    ):
        try:
            state = agent_store.load(run_id)
            record = next(
                item
                for item in state.negative_controls
                if item.receipt.control_id == control_id
            )
            artifact = record.receipt.artifact
            if artifact.sha256 != artifact_sha256:
                raise AgentRuntimeError("Negative-control artifact identity mismatch")
            path = provider_artifact_root / f"{artifact.sha256}.png"
            if not path.is_file():
                raise AgentRuntimeError("Negative-control artifact is not persisted locally")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != artifact.sha256:
                raise AgentRuntimeError("Persisted negative-control hash does not match receipt")
            return Response(
                content=content,
                media_type=artifact.media_type,
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-Content-SHA256": artifact.sha256,
                },
            )
        except (AgentRuntimeError, StopIteration) as exc:
            message = str(exc) or "Unknown negative control"
            status_code = 404 if "Unknown" in message or "not persisted" in message else 409
            raise HTTPException(status_code=status_code, detail=message) from exc

    @app.get(
        "/api/agent/runs/{run_id}/bounded-revisions/{revision_id}/artifacts/{kind}/{artifact_sha256}"
    )
    def get_bounded_revision_artifact(
        run_id: str,
        revision_id: str,
        kind: Literal["mask", "raw", "composite"],
        artifact_sha256: str,
    ):
        try:
            state = agent_store.load(run_id)
            request = state.bounded_revision_request
            result = state.bounded_revision_result
            if request is None or request.revision_id != revision_id:
                raise AgentRuntimeError("Unknown bounded revision request")
            if kind == "mask":
                expected_sha = request.mask.artifact_sha256
                relative_path = request.mask.artifact_path
            else:
                if result is None or result.revision_id != revision_id:
                    raise AgentRuntimeError("Bounded revision has no verified result")
                if kind == "raw":
                    expected_sha = result.receipt.raw_artifact_sha256
                    relative_path = result.receipt.raw_artifact_path
                else:
                    expected_sha = result.composite_artifact_sha256
                    relative_path = result.composite_artifact_path
            if artifact_sha256 != expected_sha:
                raise AgentRuntimeError("Bounded revision artifact identity mismatch")
            path = (revision_artifact_root / relative_path).resolve()
            if revision_artifact_root.resolve() not in path.parents or not path.is_file():
                raise AgentRuntimeError("Bounded revision artifact is not persisted locally")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != expected_sha:
                raise AgentRuntimeError("Persisted bounded revision hash does not match state")
            return Response(
                content=content,
                media_type="image/png",
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-Content-SHA256": expected_sha,
                },
            )
        except AgentRuntimeError as exc:
            message = str(exc)
            status_code = 404 if "Unknown" in message or "not persisted" in message else 409
            raise HTTPException(status_code=status_code, detail=message) from exc

    @app.get(
        "/api/agent/runs/{run_id}/verified-deliveries/{delivery_sha256}/visible/{artifact_sha256}"
    )
    def get_verified_delivery_visible_evidence(
        run_id: str,
        delivery_sha256: str,
        artifact_sha256: str,
    ):
        try:
            state = agent_store.load(run_id)
            delivery = state.verified_delivery
            if delivery is None or delivery.delivery_sha256 != delivery_sha256:
                raise AgentRuntimeError("Unknown verified delivery")
            if delivery.visible_evidence_sha256 != artifact_sha256:
                raise AgentRuntimeError("Verified-delivery artifact identity mismatch")
            path = resolved_delivery_artifact_root / "unreal-return-visible.png"
            if not path.is_file():
                raise AgentRuntimeError("Verified-delivery evidence is not persisted locally")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != artifact_sha256:
                raise AgentRuntimeError("Persisted verified-delivery evidence hash mismatch")
            return Response(
                content=content,
                media_type="image/png",
                headers={
                    "Cache-Control": "public, max-age=31536000, immutable",
                    "X-Content-SHA256": artifact_sha256,
                },
            )
        except AgentRuntimeError as exc:
            message = str(exc)
            status_code = 404 if "Unknown" in message or "not persisted" in message else 409
            raise HTTPException(status_code=status_code, detail=message) from exc

    @app.get("/api/agent/runs/{run_id}/stream")
    async def stream_durable_agent_run(
        run_id: str,
        request: Request,
        after: int = 0,
        follow: bool = True,
    ):
        if after < 0:
            raise HTTPException(status_code=400, detail="after must be zero or greater")
        try:
            agent_store.load(run_id)
        except AgentRuntimeError as exc:
            status_code = 404 if str(exc).startswith("Unknown Agent run") else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

        async def event_stream():
            cursor = after
            heartbeat = 0
            last_snapshot_sequence: int | None = None
            while True:
                events = agent_store.events(run_id)
                for event in events:
                    if event.sequence <= cursor:
                        continue
                    envelope = project_stream_event(event)
                    yield _sse_message("run.event", envelope.model_dump_json(), str(event.sequence))
                    cursor = event.sequence
                if last_snapshot_sequence != events[-1].sequence:
                    snapshot = project_stream_snapshot(agent_store, run_id)
                    yield _sse_message(snapshot.kind, snapshot.model_dump_json())
                    last_snapshot_sequence = events[-1].sequence
                if not follow or await request.is_disconnected():
                    break
                heartbeat += 1
                if heartbeat % 20 == 0:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.75)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/agent/runs/{run_id}/approvals/{decision_id}")
    def resolve_durable_agent_approval(
        run_id: str,
        decision_id: str,
        payload: ResolveAgentApprovalRequest,
    ):
        try:
            return agent_store.resolve_route_approval(
                run_id,
                decision_id,
                payload.resolution,
            ).status_bar()
        except AgentRuntimeError as exc:
            status_code = 404 if str(exc).startswith("Unknown Agent run") else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/agent/runs/{run_id}/comparison/authorize")
    def authorize_provider_comparison(
        run_id: str,
        payload: AuthorizeComparisonRequest,
    ):
        try:
            state = agent_store.load(run_id)
            if state.comparison_plan is None:
                raise AgentRuntimeError("Run has no pending provider comparison")
            if state.comparison_authorization is not None:
                return project_agent_run(agent_store, run_id)
            plan = ProviderComparisonPlan.model_validate(state.comparison_plan)
            authorization = ComparisonAuthorizationDecision(
                dossier_id=plan.dossier_id,
                dossier_sha256=plan.dossier_sha256,
                comparison_binding_sha256=plan.approval_binding(),
                resolution="approved",
                approved_by=payload.approved_by,
                approved_at=datetime.now(UTC),
                authorized_action_ids=[
                    child.action_id for child in plan.children if child.role == "hosted"
                ],
            )
            return project_agent_run(
                agent_store,
                agent_store.record_comparison_authorization(
                    run_id, authorization
                ).run_id,
            )
        except (AgentRuntimeError, ValueError) as exc:
            status_code = 404 if str(exc).startswith("Unknown Agent run") else 409
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        return _load_or_404(store, run_id)

    @app.get("/api/runs/{run_id}/job")
    def get_job(run_id: str):
        _load_or_404(store, run_id)
        return jobs.snapshot(run_id)

    @app.post("/api/runs/{run_id}/approve")
    def approve_run(run_id: str):
        try:
            return store.approve(run_id)
        except RunStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/execute", status_code=202)
    def execute_run(run_id: str, request: ExecuteRequest):
        state = _load_or_404(store, run_id)
        if state.status not in {"approved", "running"}:
            raise HTTPException(status_code=409, detail="Run requires approval before execution")
        source = _resolve_project_path(state.brief.source_image)
        values_file = (
            PROJECT_ROOT / "examples" / "masked-values.example.json"
            if state.brief.task_type == "masked_refinement"
            else PROJECT_ROOT / "examples" / "composition-values.example.json"
        )
        values = json.loads(values_file.read_text(encoding="utf-8"))
        mask = _resolve_project_path(request.mask_path) if request.mask_path else None

        def worker() -> None:
            with ComfyGateway(comfy_url) as gateway:
                run_batch(
                    RunStore(resolved_runs),
                    run_id,
                    ComfyRecipeProvider(gateway),
                    RecipeCatalog.bundled(),
                    source,
                    values,
                    mask,
                )

        try:
            jobs.start(run_id, worker)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return jobs.snapshot(run_id)

    @app.post("/api/runs/{run_id}/contact-sheet")
    def contact_sheet(run_id: str):
        state = _load_or_404(store, run_id)
        if not state.candidates:
            raise HTTPException(status_code=409, detail="No candidates are ready")
        path = resolved_runs / run_id / "artifacts" / "contact-sheet.jpg"
        create_contact_sheet(state.candidates, path)
        return {"url": f"/api/runs/{run_id}/contact-sheet"}

    @app.get("/api/runs/{run_id}/contact-sheet")
    def get_contact_sheet(run_id: str):
        path = _safe_run_file(resolved_runs, run_id, "artifacts/contact-sheet.jpg")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Contact sheet not found")
        return FileResponse(path)

    @app.post("/api/runs/{run_id}/select/{candidate_id}")
    def select_candidate(run_id: str, candidate_id: str):
        try:
            return store.select(run_id, candidate_id)
        except RunStateError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}/source")
    def get_source(run_id: str):
        state = _load_or_404(store, run_id)
        path = _resolve_project_path(state.brief.source_image)
        return FileResponse(path)

    @app.get("/api/runs/{run_id}/candidates/{candidate_id}")
    def get_candidate(run_id: str, candidate_id: str):
        state = _load_or_404(store, run_id)
        candidate = next(
            (item for item in state.candidates if item.candidate_id == candidate_id), None
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="Candidate not found")
        path = _resolve_run_artifact(resolved_runs, run_id, candidate.image_path)
        return FileResponse(path)

    @app.get("/api/showcase/image-to-3d/{asset_name}")
    @app.get("/api/showcase/production/{asset_name}")
    def image_to_3d_showcase_asset(asset_name: str) -> Response:
        """Serve a fixed project-owned proof set without accepting host paths."""
        goal_root = PROJECT_ROOT / "artifacts" / "goal"
        evidence_root = goal_root / "m10-s2-image-to-3d"
        allowed = {
            "reference": evidence_root / "altar-reference.png",
            "unreal": evidence_root / "unreal-generated-altar-v3.png",
            "pbr-source": goal_root
            / "m8-s2-pbr-material"
            / "validated"
            / "ruin_altar_basalt_base_color.png",
            "pbr-unreal": goal_root
            / "m8-s2-pbr-material"
            / "candidate-material-beauty.png",
            "scene-authored": goal_root
            / "m9-s2-unreal-multi-domain"
            / "authored-camera.png",
            "scene-validation": goal_root
            / "m9-s2-unreal-multi-domain"
            / "validation-camera.png",
            "lighting-failure": goal_root
            / "m9-s3-correction-release"
            / "failure-authored-camera.png",
            "lighting-corrected": goal_root
            / "m9-s3-correction-release"
            / "corrected-authored-camera.png",
        }
        path = allowed.get(asset_name)
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail="展示资产不存在")
        content = path.read_bytes()
        return Response(
            content=content,
            media_type="image/png",
            headers={"X-Content-SHA256": hashlib.sha256(content).hexdigest()},
        )

    source_web_dist = PROJECT_ROOT / "web" / "dist"
    packaged_web_dist = Path(__file__).resolve().parent / "web"
    web_dist = source_web_dist if source_web_dist.is_dir() else packaged_web_dist
    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app


def _load_or_404(store: RunStore, run_id: str):
    try:
        return store.load(run_id)
    except RunStateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _resolve_project_path(value: str | None) -> Path:
    if not value:
        raise HTTPException(status_code=400, detail="A project-relative path is required")
    candidate = Path(value)
    path = (candidate if candidate.is_absolute() else PROJECT_ROOT / candidate).resolve()
    if not path.is_relative_to(PROJECT_ROOT) or not path.is_file():
        raise HTTPException(status_code=400, detail="Path must reference an existing project file")
    return path


def _safe_run_file(runs_dir: Path, run_id: str, relative_path: str) -> Path:
    root = (runs_dir / run_id).resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=400, detail="Invalid run artifact path")
    return path


def _resolve_run_artifact(runs_dir: Path, run_id: str, stored_path: str) -> Path:
    """Resolve both current paths and legacy absolute paths after a repository move."""

    root = (runs_dir / run_id).resolve()
    candidate = Path(stored_path)
    if candidate.is_absolute():
        current = candidate.resolve()
        if current.is_relative_to(root) and current.is_file():
            return current
        parts = candidate.parts
        matching = [index for index, part in enumerate(parts) if part == run_id]
        if not matching:
            raise HTTPException(status_code=404, detail="Candidate artifact not found")
        candidate = Path(*parts[matching[-1] + 1 :])
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Candidate artifact not found")
    return resolved


def _sse_message(event: str, data: str, event_id: str | None = None) -> str:
    if len(data.encode()) > 64 * 1024:
        raise AgentRuntimeError("Agent UI event exceeds the 64 KiB transport limit")
    parts = [f"event: {event}"]
    if event_id is not None:
        parts.append(f"id: {event_id}")
    parts.append(f"data: {data}")
    return "\n".join(parts) + "\n\n"
