import json

import pytest

from artflow_agent.observability import TraceRecorder, hashed_trace_value


def test_trace_recorder_persists_w3c_correlated_allowlisted_spans(tmp_path) -> None:
    output = tmp_path / "trace.json"
    recorder = TraceRecorder(output)
    with recorder.span(
        "invoke_agent",
        {
            "artflow.run_id": "run-001",
            "artflow.execution_id": "execution-001",
            "artflow.idempotency_key_sha256": hashed_trace_value("secret-idem"),
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.provider.name": "codex_image",
            "gen_ai.request.model": "gpt-image-2",
        },
    ) as root, recorder.span(
        "execute_tool",
        {
            "artflow.capability_id": "provider.execute",
            "artflow.phase": "provider_submission",
        },
    ):
        root.set_attribute("artflow.event_sequence", 7)
    recorder.shutdown()

    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["schema_id"] == "artflow-otel-trace/1"
    assert len(document["spans"]) == 2
    root_span = next(span for span in document["spans"] if span["name"] == "invoke_agent")
    child = next(span for span in document["spans"] if span["name"] == "execute_tool")
    assert child["trace_id"] == root_span["trace_id"]
    assert child["parent_span_id"] == root_span["span_id"]
    assert root_span["traceparent"].startswith(f"00-{root_span['trace_id']}-")
    assert len(root_span["trace_id"]) == 32
    assert len(root_span["span_id"]) == 16
    encoded = json.dumps(document).casefold()
    assert "secret-idem" not in encoded
    assert "prompt" not in encoded
    assert "reasoning" not in encoded


def test_trace_recorder_rejects_non_allowlisted_attributes(tmp_path) -> None:
    recorder = TraceRecorder(tmp_path / "trace.json")
    with pytest.raises(ValueError, match="not allowlisted"), recorder.span(
        "unsafe", {"user.prompt": "do not persist"}
    ):
        pass
    recorder.shutdown()
