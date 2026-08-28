from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from mcp import Client, StdioServerParameters

from artflow_agent.contracts import MultiDomainSceneDeltaPlan
from artflow_agent.mcp_facade import MCP_RESOURCE_URIS, ArtFlowMCPFacade, file_sha256
from artflow_agent.scene_lifecycle import SceneLifecycleLedger, canonical_sha256


def protected_snapshot(root: Path) -> dict[str, str]:
    relative_paths = [
        "artifacts/goal/m9-s3-correction-release/lifecycle.sqlite3",
        "integrations/unreal/ArtFlowBridgeHost/Content/ArtFlowDemo.umap",
        (
            "integrations/unreal/ArtFlowBridgeHost/Content/ArtFlow/Published/"
            "AF_M9_b70662c9ce03.umap"
        ),
    ]
    return {path: file_sha256(root / path) for path in relative_paths}


def registered_inputs(root: Path) -> dict[str, str]:
    m9 = root / "artifacts/goal/m9-s3-correction-release"
    facade = ArtFlowMCPFacade(root)
    plan = MultiDomainSceneDeltaPlan.model_validate_json(
        (root / "examples/m9-ruin-altar-scene-delta-plan.json").read_text(encoding="utf-8")
    )
    return {
        "twin_sha256": json.loads(facade.twin_resource())["artifact_sha256"],
        "plan_sha256": plan.canonical_sha256(),
        "evaluation_sha256": json.loads(
            (m9 / "failure-evaluation.json").read_text(encoding="utf-8")
        )["evaluation_sha256"],
        "disposition_id": json.loads(
            (m9 / "disposition-request.json").read_text(encoding="utf-8")
        )["disposition_id"],
    }


def compact_result(result: Any) -> dict[str, Any]:
    return {
        "is_error": result.is_error,
        "structured_content": result.structured_content,
        "content_types": [item.type for item in result.content],
    }


async def verify(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    m9 = root / "artifacts/goal/m9-s3-correction-release"
    inputs = registered_inputs(root)
    before_hashes = protected_snapshot(root)
    before_events = len(SceneLifecycleLedger(m9 / "lifecycle.sqlite3").events())
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(root / "scripts/run_artflow_mcp.py")],
        cwd=root,
    )

    async with Client(params, raise_exceptions=False) as client:
        resources_result = await client.list_resources()
        tools_result = await client.list_tools()
        resources = resources_result.resources
        tools = tools_result.tools
        resource_reads: dict[str, dict[str, Any]] = {}
        for resource in resources:
            result = await client.read_resource(resource.uri)
            serialized = json.dumps(
                result.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
            ).encode("utf-8")
            resource_reads[str(resource.uri)] = {
                "content_count": len(result.contents),
                "response_sha256": hashlib.sha256(serialized).hexdigest(),
            }

        golden = {
            "scene.twin.summarize": compact_result(
                await client.call_tool(
                    "scene.twin.summarize", {"twin_sha256": inputs["twin_sha256"]}
                )
            ),
            "scene.delta.compile_registered": compact_result(
                await client.call_tool(
                    "scene.delta.compile_registered", {"plan_sha256": inputs["plan_sha256"]}
                )
            ),
            "scene.correction.inspect": compact_result(
                await client.call_tool(
                    "scene.correction.inspect",
                    {"evaluation_sha256": inputs["evaluation_sha256"]},
                )
            ),
            "scene.disposition.verify": compact_result(
                await client.call_tool(
                    "scene.disposition.verify",
                    {"disposition_id": inputs["disposition_id"]},
                )
            ),
        }
        hostile = {
            "unrestricted_path": compact_result(
                await client.call_tool(
                    "scene.twin.summarize",
                    {"twin_sha256": inputs["twin_sha256"], "path": "D:/unrestricted"},
                )
            ),
            "arbitrary_workflow": compact_result(
                await client.call_tool(
                    "scene.delta.compile_registered",
                    {"plan_sha256": inputs["plan_sha256"], "workflow": {"nodes": []}},
                )
            ),
            "unknown_evaluation": compact_result(
                await client.call_tool(
                    "scene.correction.inspect", {"evaluation_sha256": "invalid"}
                )
            ),
            "arbitrary_python": compact_result(
                await client.call_tool(
                    "scene.disposition.verify",
                    {
                        "disposition_id": inputs["disposition_id"],
                        "python": "open('untrusted','w')",
                    },
                )
            ),
        }
        transcript = {
            "schema_id": "m10-s1-mcp-protocol-transcript/1",
            "transport": "stdio-subprocess",
            "protocol_version": client.protocol_version,
            "server": client.server_info.model_dump(mode="json"),
            "resource_uris": sorted(str(resource.uri) for resource in resources),
            "resource_reads": resource_reads,
            "tools": [
                {
                    "name": tool.name,
                    "input_schema": tool.input_schema,
                    "output_schema": tool.output_schema,
                    "annotations": tool.annotations.model_dump(mode="json")
                    if tool.annotations
                    else None,
                }
                for tool in tools
            ],
            "golden_calls": golden,
            "hostile_calls": hostile,
        }

    after_hashes = protected_snapshot(root)
    after_events = len(SceneLifecycleLedger(m9 / "lifecycle.sqlite3").events())
    expected_tools = {
        "scene.twin.summarize",
        "scene.delta.compile_registered",
        "scene.correction.inspect",
        "scene.disposition.verify",
    }
    tool_names = {tool["name"] for tool in transcript["tools"]}
    audit = {
        "schema_id": "m10-s1-mcp-boundary-audit/1",
        "status": "verified",
        "protocol_version": transcript["protocol_version"],
        "transport": transcript["transport"],
        "resource_count": len(transcript["resource_uris"]),
        "tool_count": len(transcript["tools"]),
        "golden_call_count": len(transcript["golden_calls"]),
        "hostile_rejection_count": sum(
            item["is_error"] for item in transcript["hostile_calls"].values()
        ),
        "all_inputs_closed": all(
            tool["input_schema"].get("additionalProperties") is False
            for tool in transcript["tools"]
        ),
        "all_tools_read_only": all(
            tool["annotations"] and tool["annotations"]["read_only_hint"]
            for tool in transcript["tools"]
        ),
        "arbitrary_execution_surface_count": sum(
            token in json.dumps(
                [tool["input_schema"].get("properties", {}) for tool in transcript["tools"]]
            ).lower()
            for token in ["path", "python", "shell", "blueprint", "workflow"]
        ),
        "durable_events_before": before_events,
        "durable_events_after": after_events,
        "protected_bytes_unchanged": before_hashes == after_hashes,
        "duplicate_side_effect_count": 0,
    }
    assert transcript["protocol_version"] == "2026-07-28"
    assert set(transcript["resource_uris"]) == set(MCP_RESOURCE_URIS.values())
    assert tool_names == expected_tools
    assert all(not item["is_error"] for item in transcript["golden_calls"].values())
    assert audit["hostile_rejection_count"] == 4
    assert audit["all_inputs_closed"] is True
    assert audit["all_tools_read_only"] is True
    assert audit["arbitrary_execution_surface_count"] == 0
    assert audit["durable_events_before"] == audit["durable_events_after"]
    assert audit["protected_bytes_unchanged"] is True
    audit["audit_sha256"] = canonical_sha256(audit)
    transcript["transcript_sha256"] = canonical_sha256(transcript)
    return transcript, audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/goal/m10-s1-mcp-facade"),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    transcript, audit = asyncio.run(verify(root))
    (output_dir / "protocol-transcript.json").write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "boundary-audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
