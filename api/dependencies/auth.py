from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from api.settings import get_settings


def require_mutation_token(authorization: str | None = Header(default=None)) -> str:
    expected = f"Bearer {get_settings().api_token}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API token")
    return "api-user"
