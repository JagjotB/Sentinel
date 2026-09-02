from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from runtime.state import Evidence

INJECTION_PATTERNS = re.compile(
    r"(?i)(ignore (all|previous) instructions|system prompt|developer message|execute\s+shell|"
    r"curl\s+https?://|powershell\s+-|rm\s+-rf)"
)


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
        for item in ranked:
            summary = INJECTION_PATTERNS.sub("[untrusted-instruction-redacted]", item.summary)
            line = f"[{item.id}] {item.source}/{item.kind}: {summary[: self.max_item_chars]}"
            if sum(len(part) for part in lines) + len(line) > characters:
                break
            lines.append(line)
            ids.append(item.id)
        text = "\n".join(lines)
        return ContextWindow(
            text=text,
            evidence_ids=tuple(ids),
            estimated_tokens=(len(text) + 3) // 4,
            dropped_count=len(evidence) - len(ids),
        )
