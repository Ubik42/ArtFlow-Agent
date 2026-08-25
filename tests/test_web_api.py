from fastapi.testclient import TestClient

from artflow_agent.domain import ArtBrief
from artflow_agent.planning import DeterministicPlanner
from artflow_agent.run_store import RunStore
from artflow_agent.web_api import create_app


def test_web_api_preserves_approval_gate(tmp_path) -> None:
    brief = ArtBrief(
        project_name="fixture",
        source_image="examples/assets/coastal-ruins-graybox.png",
        intent="Create one controlled environment lighting direction.",
        variant_count=1,
    )
    store = RunStore(tmp_path)
    store.create(brief, DeterministicPlanner().create_plan(brief), run_id="run")
    client = TestClient(create_app(runs_dir=tmp_path))

    assert client.get("/api/runs").json()[0]["run_id"] == "run"
    blocked = client.post("/api/runs/run/execute", json={})
    assert blocked.status_code == 409
    assert "requires approval" in blocked.json()["detail"]

    approved = client.post("/api/runs/run/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
