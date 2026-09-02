from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from mcp.contracts import PermissionClass
from runtime.context_manager import ContextManager
from runtime.state import Evidence
from safety.approvals import ApprovalClaims, ApprovalTokenError, ApprovalTokenManager
from safety.policy import ActionRequest, SafetyPolicy
from safety.validators import scan_paths


def test_destructive_action_is_forbidden_even_with_approval() -> None:
    decision = SafetyPolicy().evaluate(
        ActionRequest(
            name="delete_namespace",
            permission=PermissionClass.DESTRUCTIVE,
            target="sentinel-demo",
        ),
        approved=True,
    )
    assert not decision.allowed
    assert "forbidden" in " ".join(decision.reasons)


def test_arbitrary_command_injection_is_rejected() -> None:
    decision = SafetyPolicy().evaluate(
        ActionRequest(
            name="patch",
            permission=PermissionClass.LOW_RISK_WRITE,
            target="config/service.yaml",
            payload={"patch": "value: ok; powershell -Command whoami"},
        ),
        approved=True,
    )
    assert not decision.allowed
    assert any("shell" in reason for reason in decision.reasons)


def test_prompt_injection_fixtures_are_treated_as_untrusted_data() -> None:
    fixture = Path(__file__).parent / "fixtures" / "prompt_injection_logs.json"
    messages = json.loads(fixture.read_text(encoding="utf-8"))
    evidence = [
        Evidence(
            id=f"ev_{index}",
            source="logs",
            kind="raw",
            summary=row["message"],
            raw_reference=f"fixture://{index}",
            payload={},
        )
        for index, row in enumerate(messages)
    ]
    context = ContextManager().build(evidence, "payment timeout")
    assert "rm -rf" not in context.text
    assert "attacker.invalid" not in context.text
    assert "payment timeout" in context.text


def test_approval_tokens_are_scoped_expiring_and_tamper_evident() -> None:
    manager = ApprovalTokenManager("unit-test-secret-material")
    now = int(time.time())
    claims = ApprovalClaims(
        incident_id="inc_1",
        remediation_id="rem_1",
        actor="oncall@example.com",
        expires_at=now + 60,
        nonce="nonce-1",
    )
    token = manager.issue(claims)
    assert (
        manager.verify(
            token,
            incident_id="inc_1",
            remediation_id="rem_1",
            actor="oncall@example.com",
            now=now,
        )
        == claims
    )
    with pytest.raises(ApprovalTokenError):
        manager.verify(
            token + "tampered",
            incident_id="inc_1",
            remediation_id="rem_1",
            actor="oncall@example.com",
            now=now,
        )
    with pytest.raises(ApprovalTokenError, match="expired"):
        manager.verify(
            token,
            incident_id="inc_1",
            remediation_id="rem_1",
            actor="oncall@example.com",
            now=now + 120,
        )


def test_repository_source_contains_no_credential_shaped_secrets() -> None:
    root = Path(__file__).resolve().parents[2]
    paths = [
        path
        for folder in ("api", "agents", "mcp", "runtime", "safety")
        for path in (root / folder).rglob("*.py")
    ]
    assert scan_paths(paths) == []
