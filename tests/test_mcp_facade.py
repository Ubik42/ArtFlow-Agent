from __future__ import annotations

import asyncio
import functools
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp import Client

from artflow_agent.contracts import MultiDomainSceneDeltaPlan
from artflow_agent.mcp_facade import MCP_RESOURCE_URIS, ArtFlowMCPFacade, build_mcp_server
from artflow_agent.scene_lifecycle import SceneLifecycleLedger

ROOT = Path(__file__).resolve().parents[1]
M9 = ROOT / "artifacts/goal/m9-s3-correction-release"


def run_async(function: Callable[[], Any]) -> Callable[[], None]:
    @functools.wraps(function)
    def wrapper() -> None:
        asyncio.run(function())

    return wrapper


def _registered_inputs() -> dict[str, str]:
    facade = ArtFlowMCPFacade(ROOT)
    twin_sha256 = json.loads(facade.twin_resource())["artifact_sha256"]
    plan = MultiDomainSceneDeltaPlan.model_validate_json(
        (ROOT / "examples/m9-ruin-altar-scene-delta-plan.json").read_text(encoding="utf-8")
    )
    evaluation = json.loads((M9 / "failure-evaluation.json").read_text(encoding="utf-8"))
    disposition = json.loads((M9 / "disposition-request.json").read_text(encoding="utf-8"))
    return {
        "twin_sha256": twin_sha256,
        "plan_sha256": plan.canonical_sha256(),
        "evaluation_sha256": evaluation["evaluation_sha256"],
        "disposition_id": disposition["disposition_id"],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@run_async
async def test_official_client_discovers_fixed_resources_and_closed_tools() -> None:
    async with Client(build_mcp_server(ROOT), raise_exceptions=True) as client:
        assert client.protocol_version == "2026-07-28"
        resources = (await client.list_resources()).resources
        tools = (await client.list_tools()).tools

        assert {str(resource.uri) for resource in resources} == set(MCP_RESOURCE_URIS.values())
        assert {tool.name for tool in tools} == {
            "scene.twin.summarize",
            "scene.delta.compile_registered",
            "scene.correction.inspect",
            "scene.disposition.verify",
        }
        assert all(tool.input_schema["additionalProperties"] is False for tool in tools)
        assert all(tool.annotations and tool.annotations.read_only_hint for tool in tools)
        for resource in resources:
            result = await client.read_resource(resource.uri)
            assert result.contents


@run_async
async def test_registered_calls_reuse_existing_artflow_contracts() -> None:
    values = _registered_inputs()
    calls = [
        ("scene.twin.summarize", {"twin_sha256": values["twin_sha256"]}),
        ("scene.delta.compile_registered", {"plan_sha256": values["plan_sha256"]}),
        (
            "scene.correction.inspect",
            {"evaluation_sha256": values["evaluation_sha256"]},
        ),
        ("scene.disposition.verify", {"disposition_id": values["disposition_id"]}),
    ]
    async with Client(build_mcp_server(ROOT), raise_exceptions=True) as client:
        results = [await client.call_tool(name, arguments) for name, arguments in calls]

    assert all(not result.is_error and result.structured_content for result in results)
    assert results[1].structured_content["committed_mutation_count"] == 0
    assert results[2].structured_content["rerun_domains"] == ["lighting"]
    assert set(results[2].structured_content["preserved_domains"]) == {"asset", "material", "pcg"}
    assert results[3].structured_content["duplicate_side_effect_count"] == 0


@run_async
async def test_hostile_inputs_fail_closed_without_mutating_evidence() -> None:
    values = _registered_inputs()
    protected_files = [
        M9 / "lifecycle.sqlite3",
        ROOT / "integrations/unreal/ArtFlowBridgeHost/Content/ArtFlowDemo.umap",
        ROOT
        / "integrations/unreal/ArtFlowBridgeHost/Content/ArtFlow/Published/AF_M9_b70662c9ce03.umap",
    ]
    before_hashes = {path: _sha256(path) for path in protected_files}
    before_events = len(SceneLifecycleLedger(M9 / "lifecycle.sqlite3").events())

    async with Client(build_mcp_server(ROOT), raise_exceptions=False) as client:
        rejected = [
            await client.call_tool(
                "scene.twin.summarize",
                {"twin_sha256": values["twin_sha256"], "path": "D:/unrestricted"},
            ),
            await client.call_tool(
                "scene.delta.compile_registered",
                {"plan_sha256": values["plan_sha256"], "workflow": {"nodes": []}},
            ),
            await client.call_tool("scene.correction.inspect", {"evaluation_sha256": "invalid"}),
            await client.call_tool(
                "scene.disposition.verify",
                {"disposition_id": values["disposition_id"], "python": "open('x','w')"},
            ),
        ]

    assert all(result.is_error for result in rejected)
    assert len(SceneLifecycleLedger(M9 / "lifecycle.sqlite3").events()) == before_events
    assert {path: _sha256(path) for path in protected_files} == before_hashes
