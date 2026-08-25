from artflow_agent.domain import EnvironmentSnapshot, OutputArtifact, QueuedJob
from artflow_agent.execution import execute_recipe
from artflow_agent.recipes import RecipeCatalog


class FakeGateway:
    def validate_workflow(self, workflow):
        return []

    def queue(self, workflow):
        assert workflow["12"]["inputs"]["noise_seed"] == 42
        return QueuedJob(prompt_id="prompt-1", client_id="client-1")

    def wait(self, prompt_id, *, timeout_seconds):
        assert prompt_id == "prompt-1"
        assert timeout_seconds == 30
        return {"outputs": {"8": {"images": [{"filename": "candidate.png"}]}}}

    def collect_outputs(self, history):
        assert history["outputs"]
        return [OutputArtifact(filename="candidate.png", node_id="8")]


def test_execute_recipe_returns_reproducible_receipt() -> None:
    recipe = RecipeCatalog.bundled().get("composition-preserving-v1")
    snapshot = EnvironmentSnapshot(
        comfy_url="http://comfy.test",
        reachable=True,
        comfyui_version="0.28.0",
        python_version="3.12.13",
        pytorch_version="2.13.0+cu130",
        device_name="NVIDIA GeForce RTX 4080",
        vram_mb=16375,
        models=recipe.definition.required_models,
        nodes=recipe.definition.required_nodes,
    )
    receipt = execute_recipe(
        FakeGateway(),
        recipe,
        {
            "source_image": "source.png",
            "positive_prompt": "cold dawn",
            "negative_prompt": "text",
            "seed": 42,
            "denoise": 0.4,
            "width": 1024,
            "height": 1024,
            "filename_prefix": "ArtFlow/test",
        },
        timeout_seconds=30,
        environment=snapshot,
    )
    assert receipt.prompt_id == "prompt-1"
    assert receipt.recipe_version == "1.1.0"
    assert len(receipt.workflow_sha256) == 64
    assert receipt.outputs[0].filename == "candidate.png"
    assert receipt.environment is not None
    assert receipt.environment.comfyui_version == "0.28.0"
    assert receipt.environment.device_name == "NVIDIA GeForce RTX 4080"
    assert receipt.environment.verified_models == recipe.definition.required_models
    assert receipt.environment.verified_nodes == recipe.definition.required_nodes
    assert receipt.resolved_inputs["seed"] == 42
    assert receipt.resolved_inputs["source_image"] == "source.png"
    assert receipt.resolved_inputs["denoise"] == 0.4
