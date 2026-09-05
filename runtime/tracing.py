from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.trace import NonRecordingSpan, Span, SpanContext, TraceFlags
from opentelemetry.trace.propagation import set_span_in_context
from prometheus_client import Counter, Histogram

INCIDENTS = Counter("sentinel_incidents_total", "Incidents processed", ["status"])
INCIDENT_LATENCY = Histogram(
    "sentinel_incident_seconds", "End-to-end incident workflow latency", ["operation"]
)
TOOL_CALLS = Counter("sentinel_tool_calls_total", "Tool calls", ["tool", "status"])
TOOL_LATENCY = Histogram(
    "sentinel_tool_call_seconds", "Tool call latency", ["tool", "status"]
)
MODEL_CALLS = Counter(
    "sentinel_model_calls_total", "Model calls", ["provider", "model", "purpose", "status"]
)
MODEL_TOKENS = Counter("sentinel_model_tokens_total", "Model tokens", ["provider", "model"])
MODEL_COST_USD = Counter(
    "sentinel_model_cost_usd_total", "Estimated model cost in USD", ["provider", "model"]
)
MODEL_LATENCY = Histogram(
    "sentinel_model_call_seconds", "Model call latency", ["provider", "model", "purpose"]
)
DIAGNOSIS_LATENCY = Histogram("sentinel_diagnosis_seconds", "Diagnosis node latency")
RETRIES = Counter("sentinel_retries_total", "Retries", ["component", "name"])
APPROVALS = Counter(
    "sentinel_approvals_total", "Approval workflow events", ["event", "decision"]
)
ERRORS = Counter("sentinel_errors_total", "Errors", ["component", "code"])
WORK_ITEMS = Counter("sentinel_work_items_total", "Durable work-item events", ["event"])
ABSTENTIONS = Counter("sentinel_abstentions_total", "Safe abstentions", ["reason"])
HTTP_REQUESTS = Counter(
    "sentinel_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "sentinel_http_request_seconds", "HTTP request latency", ["method", "route"]
)
LOGGER = logging.getLogger("sentinel")
_CONFIG_LOCK = threading.Lock()
_PROCESSOR_KEYS: set[str] = set()


def configure_telemetry(
    service_name: str,
    endpoint: str = "",
    *,
    exporter: SpanExporter | None = None,
) -> TracerProvider:
    """Configure one process-wide provider and optionally attach an OTLP/test exporter."""
    with _CONFIG_LOCK:
        provider = trace.get_tracer_provider()
        if not isinstance(provider, TracerProvider):
            provider = TracerProvider(
                resource=Resource.create(
                    {
                        "service.name": service_name,
                        "service.namespace": "sentinel",
                    }
                )
            )
            trace.set_tracer_provider(provider)

        key = f"exporter:{id(exporter)}" if exporter is not None else f"otlp:{endpoint}"
        if key in _PROCESSOR_KEYS or (exporter is None and not endpoint):
            return provider
        if exporter is not None:
            provider.add_span_processor(SimpleSpanProcessor(exporter))
        else:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, timeout=10))
            )
        _PROCESSOR_KEYS.add(key)
        return provider


def force_flush_telemetry(timeout_millis: int = 10_000) -> bool:
    provider = trace.get_tracer_provider()
    return not isinstance(provider, TracerProvider) or provider.force_flush(timeout_millis)


def trace_id_for(span_instance: Span) -> str:
    context = span_instance.get_span_context()
    if not context.is_valid:
        return secrets.token_hex(16)
    return f"{context.trace_id:032x}"


def current_trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    return f"{context.trace_id:032x}" if context.is_valid else None


def _parent_context(parent_trace_id: str | None) -> Context | None:
    if not parent_trace_id:
        return None
    try:
        trace_id = int(parent_trace_id, 16)
    except ValueError:
        return None
    current = trace.get_current_span().get_span_context()
    if current.is_valid and current.trace_id == trace_id:
        return None
    parent = SpanContext(
        trace_id=trace_id,
        span_id=secrets.randbits(64) or 1,
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
    )
    if not parent.is_valid:
        return None
    return set_span_in_context(NonRecordingSpan(parent))


def structured_log(event: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


@contextmanager
def span(
    name: str,
    *,
    parent_trace_id: str | None = None,
    **attributes: str | int | float | bool,
) -> Iterator[Span]:
    started = time.perf_counter()
    tracer = trace.get_tracer("sentinel.runtime")
    with tracer.start_as_current_span(
        name,
        context=_parent_context(parent_trace_id),
        attributes=attributes,
        record_exception=True,
        set_status_on_exception=True,
    ) as current:
        try:
            yield current
        finally:
            structured_log(name, duration_ms=(time.perf_counter() - started) * 1000, **attributes)
