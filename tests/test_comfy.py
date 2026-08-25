import httpx

from artflow_agent.comfy import ComfyGateway
from artflow_agent.domain import OutputArtifact


def test_gateway_inspects_nodes_models_and_collects_outputs() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system_stats":
            return httpx.Response(
                200,
                json={
                    "system": {
                        "comfyui_version": "0.28.0",
                        "python_version": "3.12.13",
                        "pytorch_version": "2.13.0+cu130",
                    },
                    "devices": [
                        {"name": "Mock RTX", "vram_total": 8 * 1024**3}
                    ],
                },
            )
        if request.url.path == "/object_info":
            return httpx.Response(
                200,
                json={
                    "CheckpointLoaderSimple": {
                        "input": {"required": {"ckpt_name": [["checkpoint.safetensors"]]}}
                    },
                    "UNETLoader": {
                        "input": {
                            "required": {
                                "unet_name": [["model-b.safetensors", "model-a.safetensors"]]
                            }
                        }
                    },
                    "KSampler": {},
                },
            )
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://comfy.test")
    gateway = ComfyGateway("http://comfy.test", client=client)
    snapshot = gateway.inspect()

    assert snapshot.reachable is True
    assert snapshot.comfyui_version == "0.28.0"
    assert snapshot.python_version == "3.12.13"
    assert snapshot.pytorch_version == "2.13.0+cu130"
    assert snapshot.device_name == "Mock RTX"
    assert snapshot.vram_mb == 8192
    assert snapshot.models == [
        "checkpoint.safetensors",
        "model-a.safetensors",
        "model-b.safetensors",
    ]
    assert snapshot.model_inventory["checkpoints"] == ["checkpoint.safetensors"]
    assert snapshot.model_inventory["diffusion_models"] == [
        "model-a.safetensors",
        "model-b.safetensors",
    ]
    assert snapshot.nodes == ["CheckpointLoaderSimple", "KSampler", "UNETLoader"]
    assert (
        gateway.validate_workflow(
            {
                "1": {
                    "class_type": "CheckpointLoaderSimple",
                    "inputs": {"ckpt_name": "checkpoint.safetensors"},
                }
            }
        )
        == []
    )
    problems = gateway.validate_workflow(
        {
            "1": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "missing.safetensors", "extra": 1},
            }
        }
    )
    assert any("unavailable value" in problem for problem in problems)
    assert any("unknown input" in problem for problem in problems)
    artifacts = gateway.collect_outputs(
        {"outputs": {"8": {"images": [{"filename": "result.png", "subfolder": "ArtFlow"}]}}}
    )
    assert artifacts[0].filename == "result.png"
    assert artifacts[0].node_id == "8"


def test_gateway_queues_and_reads_completed_history() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "p-1", "number": 7})
        if request.url.path == "/history/p-1":
            return httpx.Response(
                200,
                json={"p-1": {"status": {"completed": True}, "outputs": {}}},
            )
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://comfy.test")
    gateway = ComfyGateway("http://comfy.test", client=client)
    job = gateway.queue({"1": {"class_type": "Example", "inputs": {}}}, client_id="client")

    assert job.prompt_id == "p-1"
    assert job.number == 7
    assert gateway.wait("p-1", timeout_seconds=0.1, poll_seconds=0) == {
        "status": {"completed": True},
        "outputs": {},
    }


def test_gateway_uploads_inputs_and_downloads_outputs(tmp_path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"fixture-image")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/image":
            assert b"fixture-image" in request.content
            return httpx.Response(
                200,
                json={"name": "source.png", "subfolder": "ArtFlow", "type": "input"},
            )
        if request.url.path == "/view":
            assert request.url.params["filename"] == "result.png"
            return httpx.Response(200, content=b"generated-image")
        raise AssertionError(request.url.path)

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://comfy.test")
    gateway = ComfyGateway("http://comfy.test", client=client)
    uploaded = gateway.upload_image(source)
    destination = tmp_path / "outputs" / "result.png"
    gateway.download_output(OutputArtifact(filename="result.png", subfolder="ArtFlow"), destination)

    assert uploaded.name == "source.png"
    assert destination.read_bytes() == b"generated-image"
