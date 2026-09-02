from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from runtime.sandbox import SHELL_TOKENS
from runtime.state import Diagnosis, Evidence

SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|token|password)\s*[=:]\s*['\"][A-Za-z0-9+/=_-]{24,}"),
)


def validate_action_payload(payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, sort_keys=True, default=str)
    if SHELL_TOKENS.search(rendered):
        raise ValueError("action contains forbidden shell syntax")
    if any(pattern.search(rendered) for pattern in SECRET_PATTERNS):
        raise ValueError("action contains a credential-shaped value")
    if len(rendered) > 100_000:
        raise ValueError("action payload exceeds the policy size limit")


def validate_diagnosis(diagnosis: Diagnosis, evidence: list[Evidence]) -> None:
    diagnosis.validate_against({item.id for item in evidence})
    if diagnosis.status == "supported" and diagnosis.confidence < 0.5:
        raise ValueError("supported diagnosis confidence is below policy threshold")
    if diagnosis.risk_class == "destructive":
        raise ValueError("destructive remediation classification is forbidden")


def scan_paths(paths: list[Path]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file() or path.suffix.lower() in {".png", ".npz", ".lock"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if match := pattern.search(text):
                findings.append(
                    {"path": str(path), "offset": match.start(), "pattern": pattern.pattern}
                )
    return findings
