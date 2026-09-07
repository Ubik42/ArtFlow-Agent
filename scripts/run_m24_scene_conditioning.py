from __future__ import annotations

import hashlib
import json
import subprocess
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
from artflow_agent.scene_conditioning import compile_scene_conditioning_request
from artflow_agent.scene_packages import ScenePackageArchive

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / (
    "artifacts/goal/m19-s1-candidate-work/.agent-artifacts/scene-packages/"
    "ca79f77b487ea5080876017d513f815c37846eb80edea2b33c4d990b7f07ecf6.zip"
)
OUTPUT = ROOT / "artifacts/goal/m24-s1-scene-conditioning"
COMFY_URL = "http://127.0.0.1:8190"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    preview = ScenePackageArchive().inspect(ARCHIVE)
    depth = next(item for item in preview.package.passes if item.kind == "depth")
    beauty = next(item for item in preview.package.passes if item.kind == "beauty")
    source = OUTPUT / "depth.exr"
    with ZipFile(ARCHIVE) as archive:
        source.write_bytes(archive.read(depth.artifact.path))
        (OUTPUT / "beauty.png").write_bytes(archive.read(beauty.artifact.path))
    if hashlib.sha256(source.read_bytes()).hexdigest() != depth.artifact.sha256:
        raise RuntimeError("extracted Unreal depth pass identity changed")
    blender = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
    subprocess.run(
        [
            str(blender),
            "--background",
            "--python",
            str(ROOT / "integrations/blender/normalize_unreal_depth.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    source = OUTPUT / "scene-conditioning.png"
    request = compile_scene_conditioning_request(
        scene_package_sha256=preview.archive_sha256,
        reference_beauty_sha256=beauty.artifact.sha256,
        conditioning_pass_sha256=depth.artifact.sha256,
        conditioning_input_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        prompt=(
            "cinematic rain-breakthrough shrine courtyard, weathered stone, wet reflective ground, "
            "warm key light through cold storm atmosphere, preserve the supplied depth silhouette"
        ),
        negative_prompt="characters, text, logo, camera drift, silhouette redesign, floating geometry",
        seed=20260907,
    )
    (OUTPUT / "conditioning-request.json").write_text(
        request.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )

    run_id = f"m24-{request.request_sha256[:20]}"
    execution_id = f"exec-{request.request_sha256[:20]}"
    idempotency_key = f"comfy:{execution_id}:{request.recipe_id}"
    store = AgentEventStore(OUTPUT / "agent-events.sqlite3")
    try:
        store.load(run_id)
    except AgentRuntimeError:
        store.create_run(run_id)
        store.attach_scene(run_id, preview, expected_archive_sha256=preview.archive_sha256)
    candidates = [
        ProviderRouteCandidate.model_validate(item)
        for item in json.loads(
            (ROOT / "examples/provider-route-candidates.example.json").read_text(encoding="utf-8")
        )
        if item["manifest"]["execution_kind"] == "local"
    ]
    decision = route_scene_package(
        preview,
        candidates,
        RoutePolicyRequest(
            decision_id=f"route-{request.request_sha256[:16]}",
            output_width=request.width,
            output_height=request.height,
        ),
    ).decision
    state = store.load(run_id)
    if state.route_decision is None:
        store.propose_route(run_id, decision)
    recipe = RecipeCatalog.bundled().get(request.recipe_id)
    with ComfyGateway(COMFY_URL) as gateway:
        snapshot = gateway.inspect()
        attestation = attest_local_capability(
            snapshot, candidates[0].manifest, candidates[0].model_id, recipe.definition
        )
        if attestation.status != "supported":
            raise RuntimeError("local ComfyUI capability drifted: " + ", ".join(attestation.reasons))
        store.record_capability_attestation(run_id, attestation)
        store.reserve_provider_execution(run_id, execution_id, idempotency_key, decision)
        compiled = ComfyWorkflowCompiler(store).compile(
            run_id,
            execution_id,
            request.recipe_id,
            {
                "source_image": f"ArtFlow/{execution_id}/scene-conditioning.png",
                "positive_prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "seed": request.seed,
                "denoise": request.denoise,
                "width": request.width,
                "height": request.height,
                "filename_prefix": f"ArtFlow/{execution_id}/composition",
            },
            source_pass="depth",
            prepared_source_name="scene-conditioning.png",
            prepared_source_sha256=request.conditioning_input_sha256,
        )
        problems = gateway.validate_workflow(compiled.workflow)
        if problems:
            raise RuntimeError("live workflow validation failed: " + "; ".join(problems))
        provider = ComfyProviderAdapter(
            compiled,
            adapter=BoundedComfyAdapter(gateway),
            source_path=source,
            idempotency_key=idempotency_key,
            observation_timeout_seconds=600,
        )
        final = ProviderExecutionCoordinator(store, provider).run_or_reconcile(
            run_id, execution_id, idempotency_key, decision
        )
        execution = next(item for item in final.provider_executions if item.execution_id == execution_id)
        if execution.status != "succeeded" or execution.receipt is None:
            raise RuntimeError(f"ComfyUI conditioning stopped at {execution.status}")
        artifact = execution.receipt.artifacts[0]
        content = provider.fetch_artifact(
            execution.receipt.provider_request_id or "", artifact.path
        )
        candidate = OUTPUT / "depth-guided-candidate.png"
        candidate.write_bytes(content)
        if hashlib.sha256(content).hexdigest() != artifact.sha256:
            raise RuntimeError("persisted scene-conditioned candidate identity changed")
        history = gateway.history(execution.receipt.provider_request_id or "") or {}
        timestamps = [
            message[1]["timestamp"]
            for message in (history.get("status") or {}).get("messages", [])
            if message[0] in {"execution_start", "execution_success"}
        ]
        elapsed_seconds = (
            round((max(timestamps) - min(timestamps)) / 1000.0, 3)
            if len(timestamps) >= 2
            else 0.001
        )
        result = {
            "schema_id": "artflow-scene-conditioning-receipt/1",
            "request_id": request.request_id,
            "request_sha256": request.request_sha256,
            "status": "succeeded",
            "comfyui_version": snapshot.comfyui_version,
            "device": snapshot.device_name,
            "observed_node_count": len(snapshot.nodes),
            "production_nodes": sorted(
                node for node in snapshot.nodes if node.startswith("Production")
            ),
            "provider_request_id": execution.receipt.provider_request_id,
            "workflow_sha256": compiled.workflow_sha256,
            "artifact_path": candidate.name,
            "artifact_sha256": artifact.sha256,
            "elapsed_seconds": elapsed_seconds,
            "downstream_consumer": request.downstream_consumer,
        }
        (OUTPUT / "conditioning-receipt.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
