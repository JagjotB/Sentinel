from __future__ import annotations

from pathlib import Path

import pytest

from agents.service import InvestigationService
from persistence.repository import SentinelRepository
from runtime.state import ExecutionStatus


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("scenario_id", "root_cause"),
    [
        ("oom_killed_001", "oom_killed"),
        ("bad_configmap_002", "bad_configmap"),
        ("dependency_timeout_001", "dependency_timeout"),
        ("db_pool_exhaustion_001", "db_pool_exhaustion"),
        ("queue_saturation_001", "queue_saturation"),
    ],
)
async def test_representative_incident_reaches_safe_approval_gate(
    tmp_path: Path, scenario_id: str, root_cause: str
) -> None:
    database = tmp_path / f"{scenario_id}.db"
    repository = SentinelRepository(f"sqlite:///{database}")
    state = await InvestigationService(repository).run_scenario(scenario_id)
    assert state.status is ExecutionStatus.WAITING_APPROVAL
    assert state.diagnosis is not None
    assert state.diagnosis.root_cause == root_cause
    assert state.diagnosis.evidence_ids
    assert state.remediation is not None
    assert state.remediation["status"] == "pending_approval"

