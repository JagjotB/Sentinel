from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from api.dependencies.repository import get_repository
from api.main import app
from persistence.migration_runner import run_migrations
from persistence.repository import ConflictError, SentinelRepository


@pytest.fixture
def repository(tmp_path: Path) -> SentinelRepository:
    return SentinelRepository(f"sqlite:///{tmp_path / 'test.db'}")


@pytest.fixture
def client(repository: SentinelRepository) -> TestClient:
    app.dependency_overrides[get_repository] = lambda: repository
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def alert() -> dict[str, object]:
    return {
        "title": "checkout error spike",
        "service": "checkout-api",
        "severity": "SEV-2",
        "labels": {"team": "payments"},
        "metrics": {"error_rate": 0.248},
        "scenario_id": "oom_killed_001",
    }


def test_alert_ingestion_is_idempotent(client: TestClient) -> None:
    headers = {
        "Authorization": "Bearer sentinel-local-token",
        "Idempotency-Key": "alert-unique-001",
    }
    first = client.post("/v1/alerts", json=alert(), headers=headers)
    second = client.post("/v1/alerts", json=alert(), headers=headers)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == "queued"
    work = client.get(f"/v1/incidents/{first.json()['id']}/work")
    assert work.status_code == 200
    assert work.json()["provider_mode"] == "simulator"
    assert work.json()["status"] == "queued"


def test_idempotency_key_rejects_different_payload(repository: SentinelRepository) -> None:
    values = {
        "title": "incident",
        "service": "checkout",
        "severity": "SEV-2",
        "idempotency_key": "same-key",
    }
    repository.create_incident(alert={"value": 1}, **values)
    with pytest.raises(ConflictError):
        repository.create_incident(alert={"value": 2}, **values)


def test_mutation_requires_authentication(client: TestClient) -> None:
    response = client.post(
        "/v1/alerts", json=alert(), headers={"Idempotency-Key": "alert-unique-002"}
    )
    assert response.status_code == 401
    assert "traceback" not in response.text.lower()


def test_health_requests_are_observable(client: TestClient) -> None:
    health = client.get("/healthz")
    metrics = client.get("/metrics")
    assert health.status_code == 200
    assert health.headers["X-Request-ID"]
    assert metrics.status_code == 200
    assert "sentinel_http_requests_total" in metrics.text


def test_latest_benchmark_summary_is_served(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["manifest"]["scenario_count"] == 36
    assert payload["metrics"]["sentinel_full"]["root_cause_accuracy"] > 0.8


def test_schema_v1_database_upgrades_to_durable_work_queue(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'upgrade.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO schema_migrations VALUES (1, CURRENT_TIMESTAMP)")
        )

    run_migrations(engine)

    assert inspect(engine).has_table("work_items")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar() == 2
