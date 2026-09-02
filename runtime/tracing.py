from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from prometheus_client import Counter, Histogram

if not isinstance(trace.get_tracer_provider(), TracerProvider):
    trace.set_tracer_provider(TracerProvider())

TRACER = trace.get_tracer("sentinel.runtime")
INCIDENTS = Counter("sentinel_incidents_total", "Incidents processed", ["status"])
TOOL_CALLS = Counter("sentinel_tool_calls_total", "Tool calls", ["tool", "status"])
MODEL_TOKENS = Counter("sentinel_model_tokens_total", "Model tokens", ["provider", "model"])
DIAGNOSIS_LATENCY = Histogram("sentinel_diagnosis_seconds", "Diagnosis latency")
HTTP_REQUESTS = Counter(
    "sentinel_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "sentinel_http_request_seconds", "HTTP request latency", ["method", "route"]
)
LOGGER = logging.getLogger("sentinel")


def structured_log(event: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"event": event, **fields}, sort_keys=True, default=str))


@contextmanager
def span(name: str, **attributes: str | int | float | bool) -> Iterator[None]:
    started = time.perf_counter()
    with TRACER.start_as_current_span(name, attributes=attributes):
        try:
            yield
        finally:
            structured_log(name, duration_ms=(time.perf_counter() - started) * 1000, **attributes)
