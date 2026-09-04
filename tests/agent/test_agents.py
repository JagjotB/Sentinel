from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agents.diagnosis import DiagnosisAgent
from agents.service import InvestigationService
from api.dependencies.repository import get_repository
from api.main import app
from persistence.repository import SentinelRepository
from runtime.state import Evidence, ExecutionStatus


async def test_hierarchical_workflow_produces_verified_evidence_and_remediation(
    tmp_path: Path,
) -> None:
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'agents.db'}")
    state = await InvestigationService(repository).run_scenario("oom_killed_001")
    assert state.status is ExecutionStatus.WAITING_APPROVAL
    assert state.diagnosis is not None
    assert state.diagnosis.status == "supported"
    assert state.diagnosis.root_cause == "oom_killed"
    assert state.remediation is not None
    assert state.remediation["plan"]["type"] == "patch_proposal"
    assert {task.agent for task in state.tasks} >= {
        "supervisor",
        "infrastructure",
        "telemetry",
        "diagnosis",
        "verifier",
        "remediation",
    }
    assert any(item.source == "telemetry_anomaly_model" for item in state.evidence)
    assert any(item.source == "log_intelligence" for item in state.evidence)
    assert state.metadata["orchestrator"] == "langgraph"
    assert state.metadata["graph_path"] == [
        "initialized",
        "evidence_collected",
        "diagnosed",
        "verified",
        "remediation_proposed",
    ]
    assert {step.agent for step in state.steps} == {"diagnosis", "verifier"}
    model_calls = repository.list_model_calls(state.incident_id)
    assert {call.prompt_version for call in model_calls} == {
        "diagnosis-v2",
        "verification-v2",
    }
    assert all(call.input_tokens > 0 and call.output_tokens > 0 for call in model_calls)


async def test_task_decomposition_is_dynamic(tmp_path: Path) -> None:
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'dynamic.db'}")
    state = await InvestigationService(repository).run_scenario("downstream_rate_limit_001")
    agents = {task.agent for task in state.tasks}
    assert "change_analysis" not in agents
    assert "infrastructure" in agents and "telemetry" in agents


def test_diagnosis_abstains_when_evidence_is_weak() -> None:
    weak = Evidence(
        id="ev_weak",
        source="unknown",
        kind="note",
        summary="service behavior is unclear",
        raw_reference="test://weak",
        payload={},
    )
    diagnosis, _ = DiagnosisAgent().run([weak])
    assert diagnosis.status == "insufficient_evidence"
    assert not diagnosis.evidence_ids


def test_simulator_api_runs_complete_investigation(tmp_path: Path) -> None:
    repository = SentinelRepository(f"sqlite:///{tmp_path / 'api-agents.db'}")
    app.dependency_overrides[get_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            response = client.post(
                "/v1/simulator/run",
                json={"scenario_id": "oom_killed_002"},
                headers={"Authorization": "Bearer sentinel-local-token"},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "waiting_approval"
        assert response.json()["diagnosis"]["root_cause"] == "oom_killed"
    finally:
        app.dependency_overrides.clear()
