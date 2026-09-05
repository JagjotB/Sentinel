from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from runtime.state import Evidence

INJECTION_PATTERNS = re.compile(
    r"(?i)(ignore (all|previous) instructions|system prompt|developer message|execute\s+shell|"
    r"curl\s+https?://|powershell\s+-|rm\s+-rf)"
)
SECRET_KEY_PATTERN = re.compile(
    r"(?i)^(api[_-]?key|access[_-]?token|authorization|token|password|secret)$"
)
INLINE_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret)\s*([=:])\s*[^\s,;]+"
)
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}=*")


def _redact_text(value: str) -> str:
    value = BEARER_PATTERN.sub("Bearer [redacted]", value)
    return INLINE_SECRET_PATTERN.sub(r"\1\2[redacted]", value)


def _redact_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted]"
                if SECRET_KEY_PATTERN.fullmatch(str(key))
                else _redact_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


@dataclass(frozen=True)
class ContextWindow:
    text: str
    evidence_ids: tuple[str, ...]
    estimated_tokens: int
    dropped_count: int


class ContextManager:
    def __init__(self, max_tokens: int = 4_000, max_item_chars: int = 1_200) -> None:
        self.max_tokens = max_tokens
        self.max_item_chars = max_item_chars

    def build(self, evidence: list[Evidence], query: str) -> ContextWindow:
        query_terms = set(re.findall(r"[a-z0-9_]+", query.lower()))
        unique: dict[str, Evidence] = {}
        for item in evidence:
            digest = hashlib.sha256(
                f"{item.source}|{item.kind}|{item.summary}".lower().encode()
            ).hexdigest()
            previous = unique.get(digest)
            if previous is None or item.relevance > previous.relevance:
                unique[digest] = item
        ranked = sorted(
            unique.values(),
            key=lambda item: (
                item.relevance
                + 0.04 * len(query_terms & set(re.findall(r"[a-z0-9_]+", item.summary.lower())))
            ),
            reverse=True,
        )
        lines: list[str] = []
        ids: list[str] = []
        characters = self.max_tokens * 4
        used_characters = 0
        for item in ranked:
            rendered = (
                "[untrusted-instruction-redacted]"
                if INJECTION_PATTERNS.search(
                    f"{item.summary} {json.dumps(item.payload, default=str)}"
                )
                else (
                    f"{_redact_text(item.summary)}; data="
                    f"{json.dumps(_redact_value(item.payload), sort_keys=True, default=str)}"
                )
            )
            line = f"[{item.id}] {item.source}/{item.kind}: {rendered[: self.max_item_chars]}"
            extra = len(line) + (1 if lines else 0)
            if used_characters + extra > characters:
                break
            lines.append(line)
            ids.append(item.id)
            used_characters += extra
        text = "\n".join(lines)
        return ContextWindow(
            text=text,
            evidence_ids=tuple(ids),
            estimated_tokens=(len(text) + 3) // 4,
            dropped_count=len(evidence) - len(ids),
        )
