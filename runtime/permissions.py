from __future__ import annotations

from dataclasses import dataclass

from mcp.contracts import PermissionClass


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    requires_approval: bool
    reason: str


class PermissionPolicy:
    def evaluate(
        self, permission: PermissionClass, *, approved: bool = False
    ) -> PermissionDecision:
        if permission is PermissionClass.DESTRUCTIVE:
            return PermissionDecision(False, False, "destructive actions are forbidden")
        if permission is PermissionClass.LOW_RISK_WRITE and not approved:
            return PermissionDecision(False, True, "explicit human approval required")
        return PermissionDecision(True, False, "allowed by least-privilege policy")
