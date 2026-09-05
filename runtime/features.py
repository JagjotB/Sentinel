from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InvestigationFeatures:
    """Explicit runtime switches used for controlled, independently executed ablations."""

    verifier: bool = True
    deep_learning: bool = True
    retrieval: bool = True
    context_engineering: bool = True
    subagents: bool = True
