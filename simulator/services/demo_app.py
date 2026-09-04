from __future__ import annotations

import json
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import Engine, create_engine, text

LOGGER = logging.getLogger("sentinel.simulator.service")
SERVICE = os.getenv("SERVICE_NAME", "demo")
FAULT_MODE = os.getenv("SENTINEL_FAULT_MODE", "none")
SCENARIO_ID = os.getenv("SENTINEL_SCENARIO_ID", "baseline")
PAYMENTS_URL = os.getenv("PAYMENTS_URL", "http://payments:8080")
DATABASE_URL = os.getenv("DATABASE_URL", "")

REQUESTS = Counter(
    "sentinel_demo_requests_total",
    "Requests handled by Sentinel demo services",
    ["service", "route", "status", "fault"],
)
LATENCY = Histogram(
    "sentinel_demo_request_seconds",
    "Request latency in Sentinel demo services",
    ["service", "route", "fault"],
)
READY = Gauge("sentinel_demo_ready", "Readiness of a Sentinel demo service", ["service"])
QUEUE_DEPTH = Gauge("sentinel_demo_queue_depth", "Synthetic worker queue depth", ["service"])

_memory_leak: list[bytearray] = []
_request_times: deque[float] = deque(maxlen=1000)
_queue_depth = 0
_queue_lock = Lock()
_db_engine: Engine | None = None


class WorkRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=80)
    amount_cents: int = Field(default=1500, gt=0, le=1_000_000)
    schema_version: str = Field(default="v1", max_length=20)


def _structured_log(event: str, **fields: Any) -> None:
    LOGGER.info(
        json.dumps(
            {
                "event": event,
                "service": SERVICE,
                "fault": FAULT_MODE,
                "scenario_id": SCENARIO_ID,
                **fields,
            },
            sort_keys=True,
            default=str,
        )
    )


def _database_engine() -> Engine | None:
    global _db_engine
    if not DATABASE_URL:
        return None
    if _db_engine is None:
        pool_size = 1 if FAULT_MODE == "db_pool_exhaustion" else 5
        _db_engine = create_engine(
            DATABASE_URL,
            pool_size=pool_size,
            max_overflow=0,
            pool_timeout=0.25,
            pool_pre_ping=True,
        )
    return _db_engine


def _initialize_database() -> None:
    engine = _database_engine()
    if engine is None:
        return
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS sentinel_payments "
                        "(request_id TEXT PRIMARY KEY, amount_cents INTEGER NOT NULL)"
                    )
                )
            return
        except Exception as exc:
            _structured_log("database_not_ready", error=type(exc).__name__)
            time.sleep(1)


@asynccontextmanager
async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
    if SERVICE == "payments":
        _initialize_database()
    _structured_log("service_started")
    yield
    if _db_engine is not None:
        _db_engine.dispose()


app = FastAPI(title=f"Sentinel {SERVICE} demo service", lifespan=lifespan)


@app.middleware("http")
async def observe(request: Request, call_next):  # type: ignore[no-untyped-def]
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.url.path
        REQUESTS.labels(service=SERVICE, route=route, status=str(status), fault=FAULT_MODE).inc()
        LATENCY.labels(service=SERVICE, route=route, fault=FAULT_MODE).observe(
            time.perf_counter() - started
        )
        _structured_log(
            "request_completed",
            route=route,
            status=status,
            trace_id=request.headers.get("traceparent", ""),
        )


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE, "fault": FAULT_MODE}


@app.get("/")
def index() -> dict[str, str]:
    return {
        "service": SERVICE,
        "status": "ready",
        "message": "Sentinel Kubernetes incident simulator",
    }


@app.get("/readyz")
def ready() -> dict[str, str]:
    unavailable = FAULT_MODE in {"missing_secret", "bad_environment"}
    READY.labels(service=SERVICE).set(0 if unavailable else 1)
    if unavailable:
        raise HTTPException(status_code=503, detail=f"service blocked by {FAULT_MODE}")
    return {"status": "ready", "service": SERVICE}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/work")
async def work(payload: WorkRequest) -> dict[str, str | int | float]:
    if SERVICE == "checkout":
        return await _checkout(payload)
    if SERVICE == "payments":
        return await _payments(payload)
    if SERVICE == "worker":
        return await _worker(payload)
    return {"status": "rendered", "request_id": payload.request_id, "service": SERVICE}


async def _checkout(payload: WorkRequest) -> dict[str, str | int | float]:
    _apply_process_faults()
    if FAULT_MODE == "bad_environment":
        raise HTTPException(status_code=500, detail="invalid feature flag value")
    if FAULT_MODE == "dependency_regression" and payload.schema_version == "v1":
        raise HTTPException(status_code=422, detail="UnsupportedSchema: v1")
    timeout = 0.35 if FAULT_MODE in {"dependency_timeout", "dns_failure"} else 1.5
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{PAYMENTS_URL}/work", json=payload.model_dump())
            response.raise_for_status()
    except httpx.HTTPError as exc:
        _structured_log("dependency_call_failed", error=type(exc).__name__, target=PAYMENTS_URL)
        raise HTTPException(status_code=502, detail="payments dependency failed") from exc
    return {
        "status": "accepted",
        "request_id": payload.request_id,
        "amount_cents": payload.amount_cents,
        "service": SERVICE,
    }


async def _payments(payload: WorkRequest) -> dict[str, str | int | float]:
    _apply_process_faults()
    if FAULT_MODE == "dependency_timeout":
        await _sleep(2.0)
    if FAULT_MODE == "downstream_rate_limit":
        now = time.monotonic()
        _request_times.append(now)
        recent = sum(1 for item in _request_times if now - item < 1.0)
        if recent > 2:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
    engine = _database_engine()
    if engine is not None:
        delay = 1.5 if FAULT_MODE in {"db_pool_exhaustion", "slow_query_lock"} else 0.0
        try:
            with engine.begin() as connection:
                if delay:
                    connection.execute(text("SELECT pg_sleep(:delay)"), {"delay": delay})
                connection.execute(
                    text(
                        "INSERT INTO sentinel_payments(request_id, amount_cents) "
                        "VALUES (:request_id, :amount_cents) "
                        "ON CONFLICT (request_id) DO NOTHING"
                    ),
                    {"request_id": payload.request_id, "amount_cents": payload.amount_cents},
                )
        except Exception as exc:
            _structured_log("database_operation_failed", error=type(exc).__name__)
            raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {
        "status": "authorized",
        "request_id": payload.request_id,
        "amount_cents": payload.amount_cents,
        "service": SERVICE,
    }


async def _worker(payload: WorkRequest) -> dict[str, str | int | float]:
    global _queue_depth
    with _queue_lock:
        _queue_depth += 1
        current = _queue_depth
        QUEUE_DEPTH.labels(service=SERVICE).set(current)
    try:
        if FAULT_MODE == "queue_saturation" and current > 2:
            raise HTTPException(status_code=503, detail="worker queue saturated")
        await _sleep(0.7 if FAULT_MODE == "queue_saturation" else 0.03)
        return {"status": "processed", "request_id": payload.request_id, "queue_depth": current}
    finally:
        with _queue_lock:
            _queue_depth -= 1
            QUEUE_DEPTH.labels(service=SERVICE).set(_queue_depth)


def _apply_process_faults() -> None:
    if FAULT_MODE == "oom_killed":
        megabytes = int(os.getenv("OOM_ALLOCATION_MB", "192"))
        _memory_leak.append(bytearray(megabytes * 1024 * 1024))
    elif FAULT_MODE == "memory_leak":
        _memory_leak.append(bytearray(4 * 1024 * 1024))
    elif FAULT_MODE == "cpu_throttling":
        deadline = time.perf_counter() + 0.75
        while time.perf_counter() < deadline:
            pass
    elif FAULT_MODE == "disk_pressure":
        scratch = Path(os.getenv("SENTINEL_SCRATCH_DIR", "/tmp"))  # noqa: S108
        with (scratch / "sentinel-pressure.log").open("ab") as handle:
            handle.write(b"x" * 4 * 1024 * 1024)


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
