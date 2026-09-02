from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from pydantic import BaseModel, ConfigDict


class ApprovalClaims(BaseModel):
    model_config = ConfigDict(frozen=True)
    incident_id: str
    remediation_id: str
    actor: str
    expires_at: int
    nonce: str


class ApprovalTokenError(ValueError):
    pass


class ApprovalTokenManager:
    def __init__(self, secret: str) -> None:
        if len(secret) < 16:
            raise ValueError("approval secret must be at least 16 characters")
        self.secret = secret.encode()

    def issue(self, claims: ApprovalClaims) -> str:
        payload = json.dumps(claims.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        signature = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"

    def verify(
        self,
        token: str,
        *,
        incident_id: str,
        remediation_id: str,
        actor: str,
        now: int | None = None,
    ) -> ApprovalClaims:
        try:
            encoded, signature = token.split(".", 1)
            expected = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ApprovalTokenError("approval token signature is invalid")
            padded = encoded + "=" * (-len(encoded) % 4)
            claims = ApprovalClaims.model_validate_json(base64.urlsafe_b64decode(padded))
        except (ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, ApprovalTokenError):
                raise
            raise ApprovalTokenError("approval token is malformed") from exc
        current = int(time.time()) if now is None else now
        if claims.expires_at < current:
            raise ApprovalTokenError("approval token expired")
        if (
            claims.incident_id != incident_id
            or claims.remediation_id != remediation_id
            or claims.actor != actor
        ):
            raise ApprovalTokenError("approval token scope does not match request")
        return claims
