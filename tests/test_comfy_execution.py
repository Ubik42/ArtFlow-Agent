import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from artflow_agent.comfy import ComfyGateway
from artflow_agent.comfy_execution import (
    BoundedComfyAdapter,
    ComfyExecutionBoundaryError,
    ComfyWorkflowCompiler,
    CompiledComfyRequest,
)
from artflow_agent.contracts import RouteDecision, SceneConstraintPackage
from artflow_agent.domain import OutputArtifact, QueuedJob, UploadedInput
from artflow_agent.scene_packages import ScenePackagePreview, VerifiedSceneArtifact


def _compiled_request() -> CompiledComfyRequest:
    return CompiledComfyRequest(
        run_id="run-001",
        execution_id="execution-001",
        route_decision_id="route-001",
        route_fingerprint="a" * 64,
        provider_id="comfy-local",
        model_id="flux-local",
        scene_package_id="scene-001",
        scene_package_sha256="b" * 64,
        attestation_environment_sha256="c" * 64,
        recipe_id="composition-preserving-v1",
        recipe_version="1.1.0",
        workflow_sha256="d" * 64,
        source_artifact_path="passes/beauty.png",
        source_artifact_sha256="e" * 64,
        workflow={"1": {"class_type": "Fixture", "inputs": {}}},
    )


class _FixtureTransport:
    def __init__(self) -> None:
        self.uploads = 0
        self.queues = 0

    def upload_image(self, path: Path, *, subfolder: str) -> UploadedInput:
        self.uploads += 1
        return UploadedInput(name=path.name, subfolder=subfolder)

    def queue(self, workflow, client_id=None) -> QueuedJob:
        self.queues += 1
        return QueuedJob(prompt_id="prompt-fixture", client_id=client_id)

    def history(self, prompt_id: str):
        assert prompt_id == "prompt-fixture"
        return {
            "status": {"completed": True},
            "outputs": {"18": {"images": [{"filename": "result.png", "subfolder": "ArtFlow"}]}},
        }

    def collect_outputs(self, history):
        item = history["outputs"]["18"]["images"][0]
        return [OutputArtifact(filename=item["filename"], subfolder=item["subfolder"])]

    def fetch_output_bytes(self, artifact: OutputArtifact) -> bytes:
        assert artifact.filename == "result.png"
        return b"fixture-result"


def test_invalid_source_hash_has_no_local_side_effect(tmp_path) -> None:
    request = _compiled_request()
    transport = _FixtureTransport()
    adapter = BoundedComfyAdapter(transport)
    source = tmp_path / "beauty.png"
    source.write_bytes(b"wrong-for-this-request")

    with pytest.raises(ComfyExecutionBoundaryError, match="Source artifact hash"):
        adapter.submit(request, source)
    assert (transport.uploads, transport.queues) == (0, 0)


def test_bounded_local_adapter_submits_compiled_request(tmp_path) -> None:
    content = b"verified-source"
    request = _compiled_request().model_copy(
        update={"source_artifact_sha256": __import__("hashlib").sha256(content).hexdigest()}
    )
    source = tmp_path / "beauty.png"
    source.write_bytes(content)
    transport = _FixtureTransport()
    adapter = BoundedComfyAdapter(transport)
    job = adapter.submit(request, source)
    assert job.prompt_id == "prompt-fixture"
    receipt = adapter.normalize_terminal_receipt(request, job.prompt_id)
    assert receipt is not None
    assert receipt.status == "succeeded"
    assert receipt.artifacts[0].path == "ArtFlow/result.png"
    assert (transport.uploads, transport.queues) == (1, 1)


def test_recorded_http_boundary_normalizes_comfy_receipt(tmp_path) -> None:
    content = b"verified-source"
    result = b"generated-result"
    request = _compiled_request().model_copy(
        update={"source_artifact_sha256": __import__("hashlib").sha256(content).hexdigest()}
    )
    source = tmp_path / "beauty.png"
    source.write_bytes(content)
    observed: list[str] = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        observed.append(f"{http_request.method} {http_request.url.path}")
        if http_request.url.path == "/upload/image":
            return httpx.Response(
                200,
                json={
                    "name": "beauty.png",
                    "subfolder": "ArtFlow/execution-001",
                    "type": "input",
                },
            )
        if http_request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "prompt-fixture", "number": 1})
        if http_request.url.path == "/history/prompt-fixture":
            return httpx.Response(
                200,
                json={
                    "prompt-fixture": {
                        "status": {"completed": True},
                        "outputs": {
                            "18": {
                                "images": [
                                    {"filename": "result.png", "subfolder": "ArtFlow"}
                                ]
                            }
                        },
                    }
                },
            )
        if http_request.url.path == "/view":
            return httpx.Response(200, content=result)
        raise AssertionError(http_request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://comfy.test")
    gateway = ComfyGateway("http://comfy.test", client=client)
    adapter = BoundedComfyAdapter(gateway)
    job = adapter.submit(request, source)
    receipt = adapter.normalize_terminal_receipt(request, job.prompt_id)

    assert receipt is not None
    assert receipt.artifacts[0].sha256 == __import__("hashlib").sha256(result).hexdigest()
    assert observed == [
        "POST /upload/image",
        "POST /prompt",
        "GET /history/prompt-fixture",
        "GET /view",
    ]


def test_compiler_binds_reviewed_recipe_to_route_scene_and_attestation() -> None:
    root = Path(__file__).parents[1]
    package = SceneConstraintPackage.model_validate_json(
        (root / "examples" / "scene-constraint-package.example.json").read_text(
            encoding="utf-8"
        )
    )
    preview = ScenePackagePreview(
        package=package,
        archive_sha256="a" * 64,
        artifacts=[
            VerifiedSceneArtifact(path=item.artifact.path, sha256=item.artifact.sha256, size_bytes=1)
            for item in package.passes
        ],
    )
    decision = RouteDecision(
        decision_id="route-compiler-001",
        scene_package_id=package.package_id,
        scene_package_sha256=preview.archive_sha256,
        task="scene_direction",
        selected={
            "provider_id": "comfy-local",
            "model_id": "flux-local",
            "execution_kind": "local",
            "privacy_class": "local_only",
            "cost_class": "local_compute",
        },
        execution_intent={
            "required_controls": ["reference_image"],
            "evaluation_evidence": ["depth"],
            "width": package.camera.width,
            "height": package.camera.height,
            "delivery_format": "png",
            "intent_sha256": "b" * 64,
        },
        privacy_ceiling="local_only",
        max_cost_usd=0,
        requires_explicit_approval=True,
        rationale="fixture",
    )
    state = SimpleNamespace(
        scene=preview,
        route_decision=decision,
        provider_executions=[
            SimpleNamespace(
                execution_id="execution-001",
                status="reserved",
                route_fingerprint=decision.approval_fingerprint(),
                attestation_environment_sha256="c" * 64,
            )
        ],
        capability_attestations=[
            SimpleNamespace(
                environment_sha256="c" * 64,
                status="supported",
                recipe_id="composition-preserving-v1",
            )
        ],
    )
    compiler = ComfyWorkflowCompiler(SimpleNamespace(load=lambda _: state))
    values = json.loads((root / "examples" / "composition-values.example.json").read_text())
    values.update(
        {
            "source_image": "ArtFlow/execution-001/beauty.png",
            "filename_prefix": "ArtFlow/execution-001/composition",
            "width": package.camera.width,
            "height": package.camera.height,
        }
    )
    compiled = compiler.compile(
        "run-001", "execution-001", "composition-preserving-v1", values
    )
    assert compiled.workflow["4"]["inputs"]["image"] == values["source_image"]
    assert compiled.route_fingerprint == decision.approval_fingerprint()

    with pytest.raises(ComfyExecutionBoundaryError, match="dimensions"):
        compiler.compile(
            "run-001",
            "execution-001",
            "composition-preserving-v1",
            {**values, "width": package.camera.width + 1},
        )
