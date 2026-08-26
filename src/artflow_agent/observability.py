from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)
from opentelemetry.trace import Span, Status, StatusCode, Tracer
from pydantic import BaseModel, Field, model_validator

TRACE_ATTRIBUTE_ALLOWLIST = frozenset(
    {
        "artflow.run_id",
        "artflow.execution_id",
        "artflow.capability_id",
        "artflow.phase",
        "artflow.outcome",
        "artflow.event_sequence",
        "artflow.retry_suppressed",
        "artflow.recovery_action",
        "artflow.side_effect_count",
        "artflow.idempotency_key_sha256",
        "artflow.provider_request_id_sha256",
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.request.model",
    }
)

FORBIDDEN_TRACE_TERMS = (
    "prompt",
    "credential",
    "authorization",
    "api_key",
    "chain_of_thought",
    "reasoning",
)


class PersistedSpan(BaseModel):
    trace_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    span_id: str = Field(pattern=r"^[a-f0-9]{16}$")
    parent_span_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{16}$")
    traceparent: str = Field(pattern=r"^00-[a-f0-9]{32}-[a-f0-9]{16}-0[01]$")
    name: str
    kind: str
    start_time_unix_nano: int = Field(ge=0)
    end_time_unix_nano: int = Field(ge=0)
    duration_ms: float = Field(ge=0)
    status: str
    attributes: dict[str, str | int | float | bool]

    @model_validator(mode="after")
    def reject_sensitive_trace_content(self) -> PersistedSpan:
        encoded = json.dumps(self.attributes, sort_keys=True).casefold()
        if any(term in encoded for term in FORBIDDEN_TRACE_TERMS):
            raise ValueError("Trace contains forbidden prompt, media, credential or reasoning data")
        if not set(self.attributes).issubset(TRACE_ATTRIBUTE_ALLOWLIST):
            raise ValueError("Trace contains an attribute outside the privacy allowlist")
        return self


class LocalTraceDocument(BaseModel):
    schema_id: str = "artflow-otel-trace/1"
    service_name: str = "artflow-agent"
    telemetry_sdk: str = "opentelemetry-python"
    spans: list[PersistedSpan]


class AllowlistedJsonSpanExporter(SpanExporter):
    """Local exporter that persists only explicitly allowed scalar attributes."""

    def __init__(self, output_path: Path) -> None:
        self.output_path = output_path
        self._lock = Lock()
        self._spans: dict[str, PersistedSpan] = {}

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        with self._lock:
            for span in spans:
                persisted = _persisted_span(span)
                self._spans[persisted.span_id] = persisted
            self._write()
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        with self._lock:
            self._write()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        del timeout_millis
        with self._lock:
            self._write()
        return True

    @property
    def spans(self) -> list[PersistedSpan]:
        with self._lock:
            return sorted(self._spans.values(), key=lambda item: item.start_time_unix_nano)

    def _write(self) -> None:
        document = LocalTraceDocument(spans=self.spans_unlocked())
        payload = document.model_dump_json(indent=2) + "\n"
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output_path.with_suffix(self.output_path.suffix + ".partial")
        temporary.write_text(payload, encoding="utf-8")
        os.replace(temporary, self.output_path)

    def spans_unlocked(self) -> list[PersistedSpan]:
        return sorted(self._spans.values(), key=lambda item: item.start_time_unix_nano)


class TraceRecorder:
    def __init__(self, output_path: Path) -> None:
        self.exporter = AllowlistedJsonSpanExporter(output_path)
        self.provider = TracerProvider(
            resource=Resource.create(
                {
                    "service.name": "artflow-agent",
                    "service.version": "0.1.0",
                }
            )
        )
        self.provider.add_span_processor(SimpleSpanProcessor(self.exporter))
        self.tracer: Tracer = self.provider.get_tracer(
            "artflow-agent.harness", "1.0.0"
        )

    @contextmanager
    def span(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[Span]:
        safe = _allowlisted_attributes(attributes or {})
        with self.tracer.start_as_current_span(
            name,
            attributes=safe,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                yield span
            except Exception:
                span.set_status(Status(StatusCode.ERROR))
                raise

    def flush(self) -> None:
        self.provider.force_flush()

    def shutdown(self) -> None:
        self.provider.shutdown()


def hashed_trace_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def set_safe_attributes(span: Span, attributes: Mapping[str, Any]) -> None:
    for key, value in _allowlisted_attributes(attributes).items():
        span.set_attribute(key, value)


def _allowlisted_attributes(
    attributes: Mapping[str, Any],
) -> dict[str, str | int | float | bool]:
    unknown = set(attributes) - TRACE_ATTRIBUTE_ALLOWLIST
    if unknown:
        raise ValueError(f"Trace attributes are not allowlisted: {sorted(unknown)}")
    result: dict[str, str | int | float | bool] = {}
    for key, value in attributes.items():
        if not isinstance(value, (str, int, float, bool)):
            raise TypeError(f"Trace attribute {key} must be scalar")
        result[key] = value
    return result


def _persisted_span(span: ReadableSpan) -> PersistedSpan:
    context = span.context
    if context is None or span.start_time is None or span.end_time is None:
        raise ValueError("Ended OpenTelemetry span is missing identity or timestamps")
    trace_id = f"{context.trace_id:032x}"
    span_id = f"{context.span_id:016x}"
    parent_span_id = f"{span.parent.span_id:016x}" if span.parent is not None else None
    sampled = "01" if context.trace_flags.sampled else "00"
    attributes = _allowlisted_attributes(dict(span.attributes or {}))
    return PersistedSpan(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        traceparent=f"00-{trace_id}-{span_id}-{sampled}",
        name=span.name,
        kind=span.kind.name,
        start_time_unix_nano=span.start_time,
        end_time_unix_nano=span.end_time,
        duration_ms=(span.end_time - span.start_time) / 1_000_000,
        status=span.status.status_code.name,
        attributes=attributes,
    )
