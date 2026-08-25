from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .comfy import ComfyError, ComfyGateway
from .domain import EnvironmentFingerprint, EnvironmentSnapshot, GenerationReceipt
from .recipes import Recipe


def execute_recipe(
    gateway: ComfyGateway,
    recipe: Recipe,
    values: dict[str, Any],
    *,
    timeout_seconds: float = 300,
    environment: EnvironmentSnapshot | None = None,
) -> GenerationReceipt:
    """Instantiate, queue, await, and receipt one reviewed workflow."""
    snapshot = environment or gateway.inspect()
    compatibility_problems = recipe.validate_environment(snapshot)
    if compatibility_problems:
        raise ComfyError("Environment preflight failed: " + "; ".join(compatibility_problems))
    workflow = recipe.instantiate(values)
    problems = gateway.validate_workflow(workflow)
    if problems:
        raise ComfyError("Workflow preflight failed: " + "; ".join(problems))
    canonical = json.dumps(workflow, sort_keys=True, separators=(",", ":")).encode()
    queued_at = datetime.now(UTC)
    job = gateway.queue(workflow)
    history = gateway.wait(job.prompt_id, timeout_seconds=timeout_seconds)
    completed_at = datetime.now(UTC)
    return GenerationReceipt(
        prompt_id=job.prompt_id,
        recipe_id=recipe.definition.recipe_id,
        recipe_version=recipe.definition.version,
        workflow_sha256=hashlib.sha256(canonical).hexdigest(),
        queued_at=queued_at,
        completed_at=completed_at,
        environment=EnvironmentFingerprint(
            comfy_url=snapshot.comfy_url,
            comfyui_version=snapshot.comfyui_version,
            python_version=snapshot.python_version,
            pytorch_version=snapshot.pytorch_version,
            device_name=snapshot.device_name,
            vram_mb=snapshot.vram_mb,
            verified_models=recipe.definition.required_models,
            verified_nodes=recipe.definition.required_nodes,
        ),
        resolved_inputs=values,
        outputs=gateway.collect_outputs(history),
    )
