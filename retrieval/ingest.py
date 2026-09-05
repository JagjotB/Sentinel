from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from simulator.catalog import build_catalog
from simulator.models import Scenario


class Document(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    source_type: str
    title: str
    body: str
    source_uri: str
    metadata: dict[str, str]


class AlertQuery(Protocol):
    service: str
    title: str


def build_corpus(
    scenarios: Iterable[Scenario] | None = None,
    *,
    exclude_scenario_ids: set[str] | None = None,
) -> list[Document]:
    selected = list(build_catalog() if scenarios is None else scenarios)
    excluded = exclude_scenario_ids or set()
    documents: list[Document] = []
    seen_runbooks: set[str] = set()
    for scenario in selected:
        if scenario.id in excluded:
            continue
        incident_body = (
            f"Service {scenario.service}. Root cause {scenario.root_cause}. "
            f"Evidence: {', '.join(scenario.expected_evidence)}. "
            f"Resolution: {', '.join(scenario.acceptable_remediations)}."
        )
        documents.append(
            Document(
                id=f"incident_{scenario.id}",
                source_type="historical_incident",
                title=scenario.title,
                body=incident_body,
                source_uri=f"simulator://scenarios/{scenario.id}",
                metadata={
                    "root_cause": scenario.root_cause,
                    "service": scenario.service,
                    "difficulty": scenario.difficulty,
                },
            )
        )
        if scenario.root_cause not in seen_runbooks:
            seen_runbooks.add(scenario.root_cause)
            documents.append(
                Document(
                    id=f"runbook_{scenario.root_cause}",
                    source_type="runbook",
                    title=f"Recovery runbook: {scenario.root_cause}",
                    body=(
                        f"Verify {', '.join(scenario.expected_evidence)}. "
                        "Approved responses include "
                        f"{', '.join(scenario.acceptable_remediations)}. "
                        "All writes require approval and destructive changes are forbidden."
                    ),
                    source_uri=f"runbook://{scenario.root_cause}",
                    metadata={"root_cause": scenario.root_cause, "service": scenario.service},
                )
            )
    return documents


def query_from_alert(scenario: AlertQuery) -> str:
    """Build a retrieval query from fields observable at incident-ingestion time."""
    return f"{scenario.service} {scenario.title}"


def corpus_checksum(documents: list[Document]) -> str:
    value = "|".join(f"{item.id}:{item.title}:{item.body}" for item in documents)
    return hashlib.sha256(value.encode()).hexdigest()
