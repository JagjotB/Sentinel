from __future__ import annotations

from functools import lru_cache

from api.settings import get_settings
from persistence.repository import SentinelRepository


@lru_cache
def get_repository() -> SentinelRepository:
    return SentinelRepository(get_settings().database_url)
