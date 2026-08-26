from pathlib import Path

from artflow_agent.batch import run_batch
from artflow_agent.domain import (
    ArtBrief,
    EnvironmentSnapshot,
    OutputArtifact,
    QueuedJob,
    UploadedInput,
)
from artflow_agent.planning import DeterministicPlanner
from artflow_agent.providers import ComfyRecipeProvider
from artflow_agent.recipes import RecipeCatalog
from artflow_agent.run_store import RunStore


class FakeGateway:
    def __init__(self, snapshot: EnvironmentSnapshot) -> None:
        self.snapshot = snapshot
        self.count = 0

    def inspect(self) -> EnvironmentSnapshot:
        return self.snapshot

    def upload_image(self, path: Path, *, subfolder: str) -> UploadedInput:
        assert path.exists()
        return UploadedInput(name=path.name, subfolder=subfolder)

    def queue(self, workflow) -> QueuedJob:
        self.count += 1
        assert workflow["4"]["inputs"]["image"].startswith("ArtFlow/run/")
        return QueuedJob(prompt_id=f"prompt-{self.count}", client_id="client")

    def validate_workflow(self, workflow) -> list[str]:
        return []

    def wait(self, prompt_id: str, *, timeout_seconds: float):
        return {"outputs": {"18": {"images": [{"filename": f"{prompt_id}.png"}]}}}

    def collect_outputs(self, history) -> list[OutputArtifact]:
        item = history["outputs"]["18"]["images"][0]
        return [OutputArtifact(filename=item["filename"], node_id="18")]

    def download_output(self, artifact: OutputArtifact, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"generated")
        return destination


def test_batch_executes_all_directions_and_enters_review(tmp_path) -> None:
    brief = ArtBrief(
        project_name="fixture",
        source_image="source.png",
        intent="Create two controlled environment lighting variants.",
        preserve=["composition"],
        avoid=["characters"],
        variant_count=2,
    )
    store = RunStore(tmp_path / "runs")
    store.create(brief, DeterministicPlanner().create_plan(brief), run_id="run")
    store.approve("run")
    source = tmp_path / "source.png"
    source.write_bytes(b"source")
    catalog = RecipeCatalog.bundled()
    definition = catalog.get("composition-preserving-v1").definition
    gateway = FakeGateway(
        EnvironmentSnapshot(
            comfy_url="http://comfy.test",
            reachable=True,
            nodes=definition.required_nodes,
            models=definition.required_models,
            vram_mb=16384,
        )
    )
    values = {
        "denoise": 0.4,
        "width": 1024,
        "height": 1024,
        "seed": 42,
    }

    state = run_batch(store, "run", ComfyRecipeProvider(gateway), catalog, source, values)

    assert state.status == "review"
    assert len(state.candidates) == 2
    assert all(item.status == "completed" for item in state.direction_runs)
    assert gateway.count == 2
