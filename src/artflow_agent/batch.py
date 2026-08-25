from __future__ import annotations

from pathlib import Path
from typing import Any

from .comfy import ComfyError, ComfyGateway
from .domain import Candidate, RunState
from .execution import execute_recipe
from .recipes import RecipeCatalog
from .run_store import RunStateError, RunStore


def run_batch(
    store: RunStore,
    run_id: str,
    gateway: ComfyGateway,
    catalog: RecipeCatalog,
    source_path: Path,
    base_values: dict[str, Any],
    mask_path: Path | None = None,
) -> RunState:
    """Execute pending/failed directions and preserve completed work across retries."""
    state = store.load(run_id)
    if state.status not in {"approved", "running"}:
        raise RunStateError(f"Batch requires an approved or running run, not {state.status}")

    snapshot = gateway.inspect()
    recipes = {
        direction.recipe_id: catalog.get(direction.recipe_id) for direction in state.plan.directions
    }
    problems = {
        recipe_id: recipe.validate_environment(snapshot) for recipe_id, recipe in recipes.items()
    }
    incompatible = [
        f"{recipe_id}: {'; '.join(items)}" for recipe_id, items in problems.items() if items
    ]
    if incompatible:
        raise ComfyError(" | ".join(incompatible))

    uploaded = gateway.upload_image(source_path, subfolder=f"ArtFlow/{run_id}")
    remote_source = "/".join(part for part in (uploaded.subfolder, uploaded.name) if part)
    remote_mask: str | None = None
    needs_mask = any(
        slot.name == "mask_image" for recipe in recipes.values() for slot in recipe.definition.slots
    )
    if needs_mask:
        if mask_path is None:
            raise RunStateError("The approved masked-refinement recipe requires a mask image")
        uploaded_mask = gateway.upload_image(mask_path, subfolder=f"ArtFlow/{run_id}")
        remote_mask = "/".join(
            part for part in (uploaded_mask.subfolder, uploaded_mask.name) if part
        )
    if state.status == "approved":
        state = store.mark_running(run_id)

    direction_by_name = {direction.name: direction for direction in state.plan.directions}
    for index, progress in enumerate(state.direction_runs):
        if progress.status == "completed":
            continue
        direction = direction_by_name[progress.direction_name]
        recipe = recipes[direction.recipe_id]
        values = dict(base_values)
        values.update(
            {
                "source_image": remote_source,
                "positive_prompt": _direction_prompt(state, direction.name),
                "negative_prompt": ", ".join(state.brief.avoid),
                "seed": int(base_values.get("seed", 0)) + index,
                "filename_prefix": f"ArtFlow/{run_id}/{direction.name}",
            }
        )
        if remote_mask is not None:
            values["mask_image"] = remote_mask
        store.begin_direction(run_id, direction.name)
        try:
            receipt = execute_recipe(gateway, recipe, values, environment=snapshot)
            if not receipt.outputs:
                raise ComfyError(f"Direction {direction.name} completed without image outputs")
            output_dir = store.root / run_id / "artifacts" / direction.name
            candidates: list[Candidate] = []
            for output_index, artifact in enumerate(receipt.outputs, start=1):
                destination = output_dir / Path(artifact.filename).name
                gateway.download_output(artifact, destination)
                artifact.local_path = str(destination.resolve())
                candidates.append(
                    Candidate(
                        candidate_id=f"{direction.name}-{output_index:02d}",
                        direction_name=direction.name,
                        image_path=str(destination.resolve()),
                    )
                )
            receipt_path = store.save_receipt(run_id, receipt)
            for candidate in candidates:
                candidate.receipt_path = str(receipt_path.resolve())
            store.complete_direction(run_id, direction.name, receipt, receipt_path, candidates)
        except Exception as exc:
            store.fail_direction(run_id, direction.name, str(exc))
            raise

    completed = store.load(run_id)
    candidates = [
        candidate for direction in completed.direction_runs for candidate in direction.candidates
    ]
    return store.set_candidates(run_id, candidates)


def _direction_prompt(state: RunState, direction_name: str) -> str:
    direction = next(item for item in state.plan.directions if item.name == direction_name)
    preserve = ", ".join(state.brief.preserve)
    avoid = ", ".join(state.brief.avoid)
    return (
        f"{state.brief.intent} Direction: {direction.visual_goal}. {direction.prompt_delta}. "
        f"Preserve exactly: {preserve}. Do not introduce or alter: {avoid}."
    )
