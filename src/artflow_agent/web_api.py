from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .batch import run_batch
from .comfy import ComfyError, ComfyGateway, inspect_environment
from .recipes import RecipeCatalog
from .review import create_contact_sheet
from .run_store import RunStateError, RunStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ExecuteRequest(BaseModel):
    mask_path: str | None = None


class JobSnapshot(BaseModel):
    run_id: str
    active: bool
    error: str | None = None


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
    comfy_url: str = "http://127.0.0.1:8188",
) -> FastAPI:
    resolved_runs = (runs_dir or PROJECT_ROOT / "runs").resolve()
    store = RunStore(resolved_runs)
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
                    gateway,
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
        path = Path(candidate.image_path).resolve()
        if not path.is_relative_to(resolved_runs) or not path.is_file():
            raise HTTPException(status_code=404, detail="Candidate artifact not found")
        return FileResponse(path)

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
