from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter

router = APIRouter(prefix="/v1/benchmarks", tags=["benchmarks"])
REPORT = Path(__file__).resolve().parents[2] / "evals" / "reports" / "latest" / "summary.json"


@lru_cache
def load_latest() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(REPORT.read_text(encoding="utf-8")))


@router.get("/latest")
def latest() -> dict[str, Any]:
    """Return the checked-in, reproducible portfolio evaluation summary."""
    return load_latest()
