from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.current_variant_lifecycle import compile_current_inspection_request
from artflow_agent.web_api import create_app

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/goal/m61-s1-routed-dcc-publish'
RUN='unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e'

def test_inspection_resolves_existing_adoption_without_loading_facts(monkeypatch):
    state=AgentEventStore(OUT/'agent-events.sqlite3').load(RUN)
    def forbidden(*args): raise AssertionError('Preflight must not depend on the missing native facts')
    monkeypatch.setattr('artflow_agent.current_variant_lifecycle.load_routed_publish_facts',forbidden)
    request=compile_current_inspection_request(ROOT,state)
    assert request['required'] is True
    assert request['decision']==state.scene_candidate_adoption.decision.model_dump(mode='json')

def test_changed_scene_bytes_rejected_before_native_execution(monkeypatch):
    state=AgentEventStore(OUT/'agent-events.sqlite3').load(RUN)
    monkeypatch.setattr('artflow_agent.current_variant_lifecycle.file_sha256',lambda path:'0'*64)
    with pytest.raises(ValueError,match='bytes changed'):
        compile_current_inspection_request(ROOT,state)

def test_inspection_endpoint_is_loopback_only():
    client=TestClient(create_app(runs_dir=OUT,agent_database=OUT/'agent-events.sqlite3',project_root=ROOT),client=('203.0.113.8',55000))
    assert client.get(f'/api/agent/runs/{RUN}/current-variant/inspection-request').status_code==403
