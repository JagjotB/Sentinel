from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from mcp.contracts import PermissionClass
from runtime.permissions import PermissionPolicy
from safety.validators import validate_action_payload


class ActionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str = Field(min_length=2, max_length=120)
    permission: PermissionClass
    target: str = Field(min_length=1, max_length=300)
    payload: dict[str, object] = Field(default_factory=dict)
    generated_by_model: bool = True


class SafetyDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    allowed: bool
    requires_approval: bool
    reasons: list[str]
    policy_version: str = "2026-09-01"


class SafetyPolicy:
    def __init__(self) -> None:
        self.permissions = PermissionPolicy()

    def evaluate(self, action: ActionRequest, *, approved: bool = False) -> SafetyDecision:
        permission = self.permissions.evaluate(action.permission, approved=approved)
        reasons = [permission.reason]
        try:
            validate_action_payload(action.payload)
        except ValueError as exc:
            reasons.append(str(exc))
            return SafetyDecision(allowed=False, requires_approval=False, reasons=reasons)
        return SafetyDecision(
            allowed=permission.allowed,
            requires_approval=permission.requires_approval,
            reasons=reasons,
        )
