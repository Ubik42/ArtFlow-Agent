import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pydantic import BaseModel

from artflow_agent.agent_harness import (
    CapabilityAuthority,
    CapabilityDescription,
    CapabilityError,
    CapabilityRegistry,
    CapabilitySpec,
    ContextAssembler,
    OfflineCoordinator,
    build_offline_registry,
)
from artflow_agent.agent_runtime import AgentBudget, AgentEventStore, AgentRuntimeError
from artflow_agent.scene_packages import ScenePackageArchive


def _attached_store(tmp_path: Path, *, budget: AgentBudget | None = None) -> AgentEventStore:
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "examples" / "scene-constraint-package.example.json").read_text(
            encoding="utf-8"
        )
    )
    artifacts = {
        "passes/beauty.png": b"beauty",
        "passes/depth.exr": b"depth",
        "passes/world-normal.exr": b"world-normal",
        "passes/object-id.png": b"object-id",
    }
    for item in manifest["passes"]:
        item["artifact"]["sha256"] = hashlib.sha256(
            artifacts[item["artifact"]["path"]]
        ).hexdigest()
    archive_path = tmp_path / "scene-package.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("scene-package.json", json.dumps(manifest))
        for name, content in artifacts.items():
            archive.writestr(name, content)

    store = AgentEventStore(tmp_path / "events.sqlite3")
    store.create_run("agent-harness-run", budgets=budget)
    store.attach_scene("agent-harness-run", ScenePackageArchive().inspect(archive_path))
    return store


def test_context_separates_stable_rules_from_compact_dynamic_facts(tmp_path) -> None:
    store = _attached_store(tmp_path)
    context = ContextAssembler().assemble(
        store.load("agent-harness-run"), build_offline_registry()
    )

    assert context.stable.protocol == "artflow-agent-context/1"
    assert context.dynamic.package_id == "coastal-ruins-ue-capture-001"
    assert context.dynamic.protected_regions == ["main-ruin"]
    assert context.dynamic.editable_regions == ["arch-repair"]
    assert len(context.dynamic.artifact_citations) == 4
    serialized = context.model_dump_json()
    assert "beauty" in serialized
    assert "world-normal" in serialized
    assert "data:image" not in serialized
    assert len(serialized) < 30_000


def test_registry_rejects_unknown_duplicate_and_unavailable_before_execution() -> None:
    class EmptyInput(BaseModel):
        pass

    class EmptyOutput(BaseModel):
        ok: bool

    calls = 0

    def execute(value: EmptyInput, state) -> EmptyOutput:
        nonlocal calls
        calls += 1
        return EmptyOutput(ok=True)

    spec = CapabilitySpec(
        description=CapabilityDescription(
            capability_id="test.unavailable",
            version="1.0.0",
            input_schema=EmptyInput.model_json_schema(),
            output_schema=EmptyOutput.model_json_schema(),
            authority=CapabilityAuthority(reads=[], writes=[], external_side_effects=False),
            availability="unavailable",
            risk="R0",
            idempotency="read_only",
            timeout_seconds=1,
            max_observation_bytes=1024,
            verification_signal="Fixture verifier",
        ),
        input_type=EmptyInput,
        output_type=EmptyOutput,
        execute=execute,
        verify=lambda value, output, state: output.ok,
        summarize=lambda output: "ok",
    )
    registry = CapabilityRegistry()
    registry.register(spec)

    with pytest.raises(CapabilityError, match="Duplicate"):
        registry.register(spec)
    with pytest.raises(CapabilityError, match="Unknown"):
        registry.prepare("test.unknown", {})
    with pytest.raises(CapabilityError, match="unavailable"):
        registry.prepare("test.unavailable", {})
    assert calls == 0


def test_offline_loop_persists_verified_observation_and_budgets(tmp_path) -> None:
    store = _attached_store(
        tmp_path,
        budget=AgentBudget(max_iterations=2, max_tool_calls=2, max_retries=0),
    )
    result = OfflineCoordinator(store, build_offline_registry()).run_once(
        "agent-harness-run"
    )

    assert result.verified is True
    assert result.output["package_id"] == "coastal-ruins-ue-capture-001"
    reopened = AgentEventStore(tmp_path / "events.sqlite3").load("agent-harness-run")
    assert reopened.budgets.used_iterations == 1
    assert reopened.budgets.used_tool_calls == 1
    assert reopened.status_bar().pending_tool_call_count == 0
    assert len(reopened.observations) == 1
    assert reopened.observations[0].verified is True


def test_iteration_and_tool_budgets_fail_closed_after_replay(tmp_path) -> None:
    store = _attached_store(
        tmp_path,
        budget=AgentBudget(max_iterations=1, max_tool_calls=1, max_retries=0),
    )
    OfflineCoordinator(store, build_offline_registry()).run_once("agent-harness-run")
    reopened = AgentEventStore(tmp_path / "events.sqlite3")

    with pytest.raises(AgentRuntimeError, match="iteration budget is exhausted"):
        reopened.begin_iteration("agent-harness-run", "iteration-second")
    with pytest.raises(AgentRuntimeError, match="tool-call budget is exhausted"):
        reopened.start_tool_call(
            "agent-harness-run",
            "call-second",
            "scene.inspect_constraints",
            "a" * 64,
        )
