from __future__ import annotations

from pathlib import Path

from agents.base import InvestigationContext
from mcp.contracts import evidence_id
from ml.log_intelligence import LogIntelligence
from ml.telemetry_anomaly import AnomalyDetector
from runtime.state import Evidence


class TelemetryAgent:
    name = "telemetry"

    def __init__(self, artifact_path: Path | None = None) -> None:
        path = artifact_path or (
            Path(__file__).resolve().parents[1] / "ml" / "artifacts" / "telemetry_autoencoder.npz"
        )
        self.detector = AnomalyDetector.from_artifact(path)
        self.log_intelligence = LogIntelligence()

    async def run(self, context: InvestigationContext, task_id: str) -> list[Evidence]:
        scenario = context.snapshot.scenario
        evidence = await context.call_tool(
            "query_prometheus", {"query": f'service="{scenario.service}"'}, task_id
        )
        evidence.extend(
            await context.call_tool(
                "search_logs", {"service": scenario.service, "query": "", "limit": 200}, task_id
            )
        )
        anomaly = self.detector.predict(context.snapshot)
        anomaly_payload = anomaly.model_dump(mode="json")
        anomaly_evidence = Evidence(
            id=evidence_id("telemetry_anomaly_model", anomaly_payload),
            source="telemetry_anomaly_model",
            kind="learned_anomaly",
            summary=(
                f"Neural anomaly score {anomaly.anomaly_score:.3f}; dimensions "
                f"{', '.join(anomaly.anomalous_dimensions)}; onset {anomaly.onset_timestamp}"
            ),
            raw_reference=f"model://telemetry_autoencoder/{scenario.id}",
            payload=anomaly_payload,
            relevance=0.95,
        )
        log_payload = self.log_intelligence.evidence_payload(context.snapshot.logs)
        top_template = str(log_payload["clusters"][0]["template"])
        log_evidence = Evidence(
            id=evidence_id("log_intelligence", log_payload),
            source="log_intelligence",
            kind="learned_log_clusters",
            summary=f"Top rare log cluster: {top_template}",
            raw_reference=f"model://log_intelligence/{scenario.id}",
            payload=log_payload,
            relevance=0.9,
        )
        evidence.extend(
            [
                context.store_evidence(anomaly_evidence, task_id),
                context.store_evidence(log_evidence, task_id),
            ]
        )
        return evidence
