from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from api.dependencies.repository import get_repository
from api.main import app
from api.settings import get_settings
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
    assert len(work.json()["parent_trace_id"]) == 32
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
    missing = client.get("/v1/incidents/missing-observability-id")
    metrics = client.get("/metrics")
    assert health.status_code == 200
    assert health.headers["X-Request-ID"]
    assert health.headers["X-Trace-ID"]
    assert missing.status_code == 404
    assert metrics.status_code == 200
    assert "sentinel_http_requests_total" in metrics.text
    assert 'route="/v1/incidents/{incident_id}"' in metrics.text
    assert 'route="/v1/incidents/missing-observability-id"' not in metrics.text


def test_latest_benchmark_summary_is_served(client: TestClient) -> None:
    response = client.get("/v1/benchmarks/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["manifest"]["scenario_count"] == 36
    assert payload["manifest"]["protocol_version"] == "independent-v2"
    assert payload["manifest"]["independent_trial_count"] == 324
    assert payload["metrics"]["sentinel_full"]["root_cause_accuracy"] == pytest.approx(
        28 / 36
    )


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
        connection.execute(
            text(
                "CREATE TABLE approvals ("
                "id VARCHAR(40) PRIMARY KEY, incident_id VARCHAR(40), "
                "remediation_id VARCHAR(40), decision VARCHAR(20), actor VARCHAR(120), "
                "reason TEXT, idempotency_key VARCHAR(160), created_at TIMESTAMP)"
            )
        )

    run_migrations(engine)

    assert inspect(engine).has_table("work_items")
    assert inspect(engine).has_table("approval_nonces")
    assert "request_hash" in {
        item["name"] for item in inspect(engine).get_columns("approvals")
    }
    assert "parent_trace_id" in {
        item["name"] for item in inspect(engine).get_columns("work_items")
    }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar() == 4


def test_approved_remediation_materializes_one_governed_patch(
    client: TestClient,
    repository: SentinelRepository,
    tmp_path: Path,
) -> None:
    settings = get_settings()
    original_repository_path = settings.git_repository_path
    settings.git_repository_path = str(tmp_path)
    try:
        investigation = client.post(
            "/v1/simulator/run",
            json={"scenario_id": "oom_killed_002"},
            headers={"Authorization": "Bearer sentinel-local-token"},
        )
        assert investigation.status_code == 200
        state = investigation.json()
        incident_id = state["incident_id"]
        remediation_id = state["remediation"]["id"]
        token = client.post(
            f"/v1/incidents/{incident_id}/remediations/{remediation_id}/approval-token",
            params={"actor": "oncall@example.com"},
            headers={"Authorization": "Bearer sentinel-local-token"},
        )
        assert token.status_code == 200
        decision_headers = {
            "Authorization": "Bearer sentinel-local-token",
            "X-Approval-Token": token.json()["token"],
            "Idempotency-Key": "approve-remediation-001",
        }
        decision = client.post(
            f"/v1/incidents/{incident_id}/remediations/{remediation_id}/approval",
            json={
                "decision": "approved",
                "actor": "oncall@example.com",
                "reason": "Evidence and patch scope independently reviewed",
            },
            headers=decision_headers,
        )
        replay = client.post(
            f"/v1/incidents/{incident_id}/remediations/{remediation_id}/approval",
            json={
                "decision": "approved",
                "actor": "oncall@example.com",
                "reason": "Evidence and patch scope independently reviewed",
            },
            headers=decision_headers,
        )

        assert decision.status_code == 200
        assert replay.status_code == 200
        assert replay.json()["id"] == decision.json()["id"]
        remediation = repository.get_remediation(remediation_id)
        assert remediation.status == "proposal_materialized"
        artifact = tmp_path / remediation.validation["execution"]["artifact"]
        assert artifact.is_file()
        assert artifact.read_text(encoding="utf-8") == remediation.plan["patch"]
        patch_calls = [
            call
            for call in repository.list_tool_calls(incident_id)
            if call.tool_name == "create_proposed_patch_or_pr"
        ]
        assert len(patch_calls) == 1

        replay_with_new_key = client.post(
            f"/v1/incidents/{incident_id}/remediations/{remediation_id}/approval",
            json={
                "decision": "approved",
                "actor": "oncall@example.com",
                "reason": "Evidence and patch scope independently reviewed",
            },
            headers={**decision_headers, "Idempotency-Key": "approve-remediation-002"},
        )
        assert replay_with_new_key.status_code == 403
    finally:
        settings.git_repository_path = original_repository_path
