from __future__ import annotations

import json
from glob import glob
from pathlib import Path
from typing import Annotated, Literal

import typer

from .agent_harness import OfflineCoordinator, build_offline_registry
from .agent_runtime import AgentBudget, AgentEventStore
from .attestation import attest_local_capability
from .batch import run_batch
from .comfy import ComfyGateway, inspect_environment
from .delivery import package_run
from .domain import ArtBrief, Candidate
from .evaluation import PydanticAIVisualEvaluator, evaluate_candidate
from .execution import execute_recipe
from .planning import DeterministicPlanner, PydanticAIPlanner
from .providers import ComfyRecipeProvider
from .recipes import RecipeCatalog
from .review import create_contact_sheet, evaluate_trajectory
from .routing import ProviderRouteCandidate, RoutePolicyRequest, route_scene_package
from .run_store import RunStore
from .scene_packages import ScenePackageArchive, ScenePackagePreview

app = typer.Typer(no_args_is_help=True, help="ArtFlow Agent development CLI.")


def _read_brief(path: Path) -> ArtBrief:
    return ArtBrief.model_validate_json(path.read_text(encoding="utf-8"))


@app.command("validate-brief")
def validate_brief(path: Path) -> None:
    """Validate an art brief and print its normalized form."""
    brief = _read_brief(path)
    typer.echo(brief.model_dump_json(indent=2))


@app.command("inspect-scene-package")
def inspect_scene_package(path: Path) -> None:
    """Read and verify an atomic Unreal-originated scene package without extracting it."""
    preview = ScenePackageArchive().inspect(path)
    typer.echo(preview.model_dump_json(indent=2))


@app.command("create-agent-run")
def create_agent_run(
    run_id: str,
    database: Path = Path("runs/agent-events.sqlite3"),
    max_iterations: int = 12,
    max_tool_calls: int = 24,
    max_retries: int = 3,
    max_cost_usd: float | None = None,
) -> None:
    """Create the durable, event-sourced shell for an ArtFlow Agent run."""
    state = AgentEventStore(database).create_run(
        run_id,
        budgets=AgentBudget(
            max_iterations=max_iterations,
            max_tool_calls=max_tool_calls,
            max_retries=max_retries,
            max_cost_usd=max_cost_usd,
        ),
    )
    typer.echo(state.model_dump_json(indent=2))


@app.command("attach-scene-package")
def attach_scene_package(
    run_id: str,
    path: Path,
    database: Path = Path("runs/agent-events.sqlite3"),
    expected_archive_sha256: str | None = None,
) -> None:
    """Verify and atomically bind a Scene Package to a durable Agent run."""
    preview = ScenePackageArchive().inspect(path)
    state = AgentEventStore(database).attach_scene(
        run_id,
        preview,
        expected_archive_sha256=expected_archive_sha256,
    )
    typer.echo(state.model_dump_json(indent=2))


@app.command("agent-status")
def agent_status(
    run_id: str,
    database: Path = Path("runs/agent-events.sqlite3"),
) -> None:
    """Rebuild an Agent run from events and print its code-generated status bar."""
    status = AgentEventStore(database).load(run_id).status_bar()
    typer.echo(status.model_dump_json(indent=2))


@app.command("run-offline-agent-step")
def run_offline_agent_step(
    run_id: str,
    database: Path = Path("runs/agent-events.sqlite3"),
) -> None:
    """Run one deterministic, network-free Agent capability loop for inspection."""
    store = AgentEventStore(database)
    result = OfflineCoordinator(store, build_offline_registry()).run_once(run_id)
    typer.echo(result.model_dump_json(indent=2))


@app.command("propose-offline-route")
def propose_offline_route(
    run_id: str,
    candidates_path: Path,
    decision_id: str,
    database: Path = Path("runs/agent-events.sqlite3"),
    privacy_ceiling: Literal[
        "local_only", "provider_processed", "provider_retained"
    ] = "local_only",
    max_cost_usd: float = 0,
) -> None:
    """Evaluate provider manifests and persist an approval-bound route without execution."""
    store = AgentEventStore(database)
    state = store.load(run_id)
    if state.scene is None:
        raise typer.BadParameter("The Agent run has no attached Scene Package")
    payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidates = [ProviderRouteCandidate.model_validate(item) for item in payload]
    preview = ScenePackagePreview(
        package=state.scene.package,
        archive_sha256=state.scene.archive_sha256,
        artifacts=state.scene.artifacts,
    )
    result = route_scene_package(
        preview,
        candidates,
        RoutePolicyRequest(
            decision_id=decision_id,
            privacy_ceiling=privacy_ceiling,
            max_cost_usd=max_cost_usd,
        ),
    )
    proposed = store.propose_route(run_id, result.decision)
    typer.echo(
        json.dumps(
            {
                "route": result.decision.model_dump(mode="json"),
                "status": proposed.status_bar().model_dump(mode="json"),
            },
            indent=2,
        )
    )


@app.command("attest-local-provider")
def attest_local_provider(
    candidates_path: Path,
    provider_id: str,
    model_id: str,
    recipe_id: str,
    output: Path,
    comfy_url: str = "http://127.0.0.1:8188",
    run_id: str | None = None,
    database: Path = Path("runs/agent-events.sqlite3"),
) -> None:
    """Read ComfyUI facts and save a bounded capability attestation; never queue work."""
    payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    candidates = [ProviderRouteCandidate.model_validate(item) for item in payload]
    candidate = next(
        (
            item
            for item in candidates
            if item.manifest.provider_id == provider_id and item.model_id == model_id
        ),
        None,
    )
    if candidate is None:
        raise typer.BadParameter("Provider/model pair is absent from the candidate manifest")
    recipe = RecipeCatalog.bundled().get(recipe_id).definition
    snapshot = inspect_environment(comfy_url)
    attestation = attest_local_capability(
        snapshot,
        candidate.manifest,
        model_id,
        recipe,
    )
    attestation.save(output)
    if run_id is not None:
        AgentEventStore(database).record_capability_attestation(run_id, attestation)
    typer.echo(attestation.model_dump_json(indent=2))


@app.command()
def plan(
    path: Path, model: str | None = typer.Option(None, help="Optional PydanticAI model.")
) -> None:
    """Create a reviewable plan; deterministic by default and model-backed on request."""
    brief = _read_brief(path)
    planner = PydanticAIPlanner(model) if model else DeterministicPlanner()
    run_plan = planner.create_plan(brief)
    typer.echo(run_plan.model_dump_json(indent=2))


@app.command()
def doctor(comfy_url: str = "http://127.0.0.1:8188") -> None:
    """Check whether the configured local ComfyUI runtime is reachable."""
    snapshot = inspect_environment(comfy_url)
    typer.echo(json.dumps(snapshot.model_dump(mode="json"), indent=2, ensure_ascii=False))
    if not snapshot.reachable:
        raise typer.Exit(code=1)


@app.command("list-recipes")
def list_recipes(task_type: str | None = None) -> None:
    """List reviewed workflows available to the agent."""
    definitions = RecipeCatalog.bundled().list(task_type)
    typer.echo(json.dumps([item.model_dump() for item in definitions], indent=2))


@app.command("create-run")
def create_run(
    path: Path,
    runs_dir: Path = Path("runs"),
    model: str | None = typer.Option(None, help="Optional PydanticAI model."),
) -> None:
    """Persist a planned run awaiting human approval."""
    brief = _read_brief(path)
    planner = PydanticAIPlanner(model) if model else DeterministicPlanner()
    state = RunStore(runs_dir).create(brief, planner.create_plan(brief))
    typer.echo(state.model_dump_json(indent=2))


@app.command("create-revision")
def create_revision(
    parent_run_id: str,
    path: Path,
    runs_dir: Path = Path("runs"),
    model: str | None = typer.Option(None, help="Optional PydanticAI model."),
) -> None:
    """Create an approval-gated masked revision from a human-selected candidate."""
    brief = _read_brief(path)
    planner = PydanticAIPlanner(model) if model else DeterministicPlanner()
    plan = planner.create_plan(brief)
    state = RunStore(runs_dir).create_revision(parent_run_id, brief, plan)
    typer.echo(state.model_dump_json(indent=2))


@app.command()
def approve(run_id: str, runs_dir: Path = Path("runs")) -> None:
    """Explicitly approve a plan before any generation is allowed."""
    state = RunStore(runs_dir).approve(run_id)
    typer.echo(state.model_dump_json(indent=2))


@app.command("execute-recipe")
def execute_recipe_command(
    run_id: str,
    recipe_id: str,
    values_path: Path,
    comfy_url: str = "http://127.0.0.1:8188",
    runs_dir: Path = Path("runs"),
    source: Annotated[
        Path | None, typer.Option("--source", help="Upload this source image first.")
    ] = None,
    mask: Annotated[
        Path | None, typer.Option("--mask", help="Upload this refinement mask first.")
    ] = None,
) -> None:
    """Execute one reviewed recipe for an approved run and persist its receipt."""
    store = RunStore(runs_dir)
    state = store.load(run_id)
    allowed_recipe_ids = {direction.recipe_id for direction in state.plan.directions}
    if recipe_id not in allowed_recipe_ids:
        raise typer.BadParameter(f"Recipe {recipe_id!r} is not part of the approved run plan")
    if state.status not in {"approved", "running"}:
        raise typer.BadParameter(f"Run must be approved or running, not {state.status}")
    if state.status == "approved":
        store.mark_running(run_id)
    recipe = RecipeCatalog.bundled().get(recipe_id)
    values = json.loads(values_path.read_text(encoding="utf-8"))
    with ComfyGateway(comfy_url) as gateway:
        problems = recipe.validate_environment(gateway.inspect())
        if problems:
            raise typer.BadParameter("; ".join(problems))
        if source is not None:
            uploaded = gateway.upload_image(source, subfolder=f"ArtFlow/{run_id}")
            values["source_image"] = "/".join(
                part for part in (uploaded.subfolder, uploaded.name) if part
            )
        if mask is not None:
            uploaded_mask = gateway.upload_image(mask, subfolder=f"ArtFlow/{run_id}")
            values["mask_image"] = "/".join(
                part for part in (uploaded_mask.subfolder, uploaded_mask.name) if part
            )
        receipt = execute_recipe(gateway, recipe, values)
        output_dir = runs_dir / run_id / "artifacts" / receipt.prompt_id
        for artifact in receipt.outputs:
            destination = output_dir / Path(artifact.filename).name
            gateway.download_output(artifact, destination)
            artifact.local_path = str(destination.resolve())
    receipt_path = store.save_receipt(run_id, receipt)
    typer.echo(str(receipt_path))


@app.command("record-candidates")
def record_candidates(run_id: str, path: Path, runs_dir: Path = Path("runs")) -> None:
    """Attach generated candidates and move the run into human review."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = [Candidate.model_validate(item) for item in payload]
    state = RunStore(runs_dir).set_candidates(run_id, candidates)
    typer.echo(state.model_dump_json(indent=2))


@app.command("run-batch")
def run_batch_command(
    run_id: str,
    values_path: Path,
    source: Path | None = None,
    comfy_url: str = "http://127.0.0.1:8188",
    runs_dir: Path = Path("runs"),
    mask: Annotated[Path | None, typer.Option("--mask")] = None,
) -> None:
    """Run or resume all unfinished directions in an approved plan."""
    values = json.loads(values_path.read_text(encoding="utf-8"))
    store = RunStore(runs_dir)
    resolved_source = source or Path(store.load(run_id).brief.source_image)
    with ComfyGateway(comfy_url) as gateway:
        provider = ComfyRecipeProvider(gateway)
        state = run_batch(
            store,
            run_id,
            provider,
            RecipeCatalog.bundled(),
            resolved_source,
            values,
            mask,
        )
    typer.echo(state.model_dump_json(indent=2))


@app.command("run-status")
def run_status(run_id: str, runs_dir: Path = Path("runs")) -> None:
    """Print persisted run state."""
    typer.echo(RunStore(runs_dir).load(run_id).model_dump_json(indent=2))


@app.command("make-contact-sheet")
def make_contact_sheet(
    run_id: str,
    output: Path | None = None,
    runs_dir: Path = Path("runs"),
) -> None:
    """Build a labeled sheet from the run's candidate images."""
    state = RunStore(runs_dir).load(run_id)
    resolved_output = output or runs_dir / run_id / "artifacts" / "contact-sheet.jpg"
    create_contact_sheet(state.candidates, resolved_output)
    typer.echo(str(resolved_output))


@app.command()
def select(run_id: str, candidate_id: str, runs_dir: Path = Path("runs")) -> None:
    """Record the human-selected candidate and complete a run."""
    state = RunStore(runs_dir).select(run_id, candidate_id)
    typer.echo(state.model_dump_json(indent=2))


@app.command()
def evaluate(run_id: str, runs_dir: Path = Path("runs")) -> None:
    """Evaluate safety and reproducibility properties of a recorded trajectory."""
    store = RunStore(runs_dir)
    state = store.load(run_id)
    event_types = [event.event_type for event in store.events(run_id)]
    receipt_count = len(glob(str(runs_dir / run_id / "receipts" / "*.json")))
    result = evaluate_trajectory(state, event_types, receipt_count)
    _write_run_artifact(
        runs_dir, run_id, "evaluation-trajectory.json", result.model_dump_json(indent=2)
    )
    typer.echo(result.model_dump_json(indent=2))
    if not result.passed:
        raise typer.Exit(code=1)


@app.command("evaluate-assets")
def evaluate_assets(
    run_id: str,
    runs_dir: Path = Path("runs"),
    mask: Annotated[Path | None, typer.Option("--mask")] = None,
) -> None:
    """Run deterministic technical checks on every generated candidate."""
    state = RunStore(runs_dir).load(run_id)
    source = Path(state.brief.source_image)
    results = [
        evaluate_candidate(
            candidate.candidate_id,
            source,
            Path(candidate.image_path),
            mask_path=mask,
        )
        for candidate in state.candidates
    ]
    payload = json.dumps([result.model_dump() for result in results], indent=2)
    _write_run_artifact(runs_dir, run_id, "evaluation-assets.json", payload)
    typer.echo(payload)
    if not results or not all(result.passed for result in results):
        raise typer.Exit(code=1)


@app.command("evaluate-visual")
def evaluate_visual(
    run_id: str,
    model: Annotated[str, typer.Option("--model", help="A visual-capable PydanticAI model.")],
    runs_dir: Path = Path("runs"),
) -> None:
    """Opt in to model-backed visual judgment after deterministic checks."""
    state = RunStore(runs_dir).load(run_id)
    evaluator = PydanticAIVisualEvaluator(model)
    direction_by_name = {direction.name: direction for direction in state.plan.directions}
    results = [
        evaluator.evaluate(
            candidate.candidate_id,
            state.brief,
            direction_by_name[candidate.direction_name],
            Path(state.brief.source_image),
            Path(candidate.image_path),
        )
        for candidate in state.candidates
    ]
    payload = json.dumps([result.model_dump() for result in results], indent=2)
    _write_run_artifact(runs_dir, run_id, "evaluation-visual.json", payload)
    typer.echo(payload)


@app.command("package-run")
def package_run_command(
    run_id: str,
    output: Path | None = None,
    runs_dir: Path = Path("runs"),
) -> None:
    """Create a checksummed delivery package for a completed selected run."""
    path = package_run(
        RunStore(runs_dir),
        run_id,
        output or Path("outputs") / f"{run_id}.zip",
    )
    typer.echo(str(path))


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8787,
    reload: bool = False,
    runs_dir: Path = Path("runs"),
    agent_database: Path | None = None,
) -> None:
    """Serve the local portfolio workbench and typed run API."""
    import uvicorn

    from .web_api import create_app

    uvicorn.run(
        create_app(runs_dir=runs_dir, agent_database=agent_database),
        host=host,
        port=port,
        reload=reload,
    )


def _write_run_artifact(runs_dir: Path, run_id: str, name: str, content: str) -> Path:
    root = (runs_dir / run_id / "artifacts").resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content + "\n", encoding="utf-8")
    temporary.replace(path)
    return path
