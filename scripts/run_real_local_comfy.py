from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from artflow_agent.agent_runtime import AgentEventStore, AgentRuntimeError
from artflow_agent.attestation import attest_local_capability
from artflow_agent.comfy import ComfyGateway
from artflow_agent.comfy_execution import (
    BoundedComfyAdapter,
    ComfyProviderAdapter,
    ComfyWorkflowCompiler,
)
from artflow_agent.provider_execution import ProviderExecutionCoordinator
from artflow_agent.recipes import RecipeCatalog
from artflow_agent.routing import ProviderRouteCandidate, RoutePolicyRequest, route_scene_package
from artflow_agent.scene_packages import ScenePackageArchive


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one verified Unreal package locally")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/goal/m3-s11-local-run"))
    parser.add_argument("--comfy-url", default="http://127.0.0.1:8188")
    args = parser.parse_args()

    preview = ScenePackageArchive().inspect(args.archive)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    scene_root = output / ".agent-artifacts" / "scene-packages"
    scene_root.mkdir(parents=True, exist_ok=True)
    (scene_root / f"{preview.archive_sha256}.zip").write_bytes(args.archive.read_bytes())
    source = output / "beauty.png"
    with ZipFile(args.archive) as archive:
        source.write_bytes(archive.read("passes/beauty.png"))

    run_id = f"local-{preview.package.package_id}-{preview.archive_sha256[:12]}"
    execution_id = f"exec-{preview.archive_sha256[:20]}"
    idempotency_key = f"comfy:{execution_id}:composition-preserving-v1"
    store = AgentEventStore(output / "agent-events.sqlite3")
    try:
        state = store.load(run_id)
    except AgentRuntimeError:
        store.create_run(run_id)
        store.attach_scene(run_id, preview, expected_archive_sha256=preview.archive_sha256)
        state = store.load(run_id)

    candidates = [
        ProviderRouteCandidate.model_validate(item)
        for item in json.loads(
            Path("examples/provider-route-candidates.example.json").read_text(encoding="utf-8")
        )
    ]
    local_candidates = [item for item in candidates if item.manifest.execution_kind == "local"]
    decision = route_scene_package(
        preview,
        local_candidates,
        RoutePolicyRequest(
            decision_id=f"route-{preview.archive_sha256[:16]}",
            output_width=1024,
            output_height=576,
        ),
    ).decision
    if state.route_decision is None:
        store.propose_route(run_id, decision)

    state = store.load(run_id)
    existing_execution = next(
        (
            item
            for item in state.provider_executions
            if item.execution_id == execution_id
        ),
        None,
    )
    if (
        existing_execution is not None
        and existing_execution.status == "succeeded"
        and existing_execution.receipt is not None
    ):
        artifact_root = output / ".agent-artifacts" / "provider-outputs"
        for artifact in existing_execution.receipt.artifacts:
            path = artifact_root / f"{artifact.sha256}.png"
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
                raise RuntimeError("Terminal receipt artifact is missing or corrupt")
        (output / "final-state.json").write_text(
            state.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        print(state.model_dump_json(indent=2))
        return

    recipe = RecipeCatalog.bundled().get("composition-preserving-v1")
    with ComfyGateway(args.comfy_url) as gateway:
        snapshot = gateway.inspect()
        attestation = attest_local_capability(
            snapshot,
            local_candidates[0].manifest,
            local_candidates[0].model_id,
            recipe.definition,
        )
        if attestation.status != "supported":
            raise RuntimeError("Local capability drifted: " + ", ".join(attestation.reasons))
        store.record_capability_attestation(run_id, attestation)
        store.reserve_provider_execution(run_id, execution_id, idempotency_key, decision)
        values = {
            "source_image": f"ArtFlow/{execution_id}/beauty.png",
            "positive_prompt": (
                preview.package.art_intent.goal
                + " Preserve: "
                + "; ".join(preview.package.art_intent.preserve)
            ),
            "negative_prompt": "; ".join(preview.package.art_intent.prohibit),
            "seed": 20260825,
            "denoise": 0.35,
            "width": 1024,
            "height": 576,
            "filename_prefix": f"ArtFlow/{execution_id}/composition",
        }
        compiled = ComfyWorkflowCompiler(store).compile(
            run_id, execution_id, recipe.definition.recipe_id, values
        )
        problems = gateway.validate_workflow(compiled.workflow)
        if problems:
            raise RuntimeError("Live workflow validation failed: " + "; ".join(problems))
        existing = next(
            item for item in store.load(run_id).provider_executions
            if item.execution_id == execution_id
        )
        adapter = BoundedComfyAdapter(gateway)
        provider = ComfyProviderAdapter(
            compiled,
            adapter=adapter,
            source_path=source,
            idempotency_key=idempotency_key,
            known_prompt_id=existing.provider_request_id,
            observation_timeout_seconds=600,
        )
        final = ProviderExecutionCoordinator(store, provider).run_or_reconcile(
            run_id, execution_id, idempotency_key, decision
        )
        execution = next(item for item in final.provider_executions if item.execution_id == execution_id)
        if execution.status == "succeeded" and execution.receipt is not None:
            artifact_root = output / ".agent-artifacts" / "provider-outputs"
            artifact_root.mkdir(parents=True, exist_ok=True)
            for artifact in execution.receipt.artifacts:
                content = provider.fetch_artifact(execution.receipt.provider_request_id or "", artifact.path)
                destination = output / Path(artifact.path).name
                destination.write_bytes(content)
                if hashlib.sha256(content).hexdigest() != artifact.sha256:
                    raise RuntimeError("Persisted candidate hash mismatch")
                (artifact_root / f"{artifact.sha256}.png").write_bytes(content)
        (output / "compiled-request.json").write_text(
            compiled.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (output / "final-state.json").write_text(
            final.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        print(final.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
