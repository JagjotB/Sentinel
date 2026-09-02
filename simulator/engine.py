from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

from simulator.catalog import by_id
from simulator.models import Scenario, StructuredLog, TelemetryPoint

FEATURES = (
    "cpu",
    "memory",
    "request_rate",
    "error_rate",
    "p95_latency",
    "queue_depth",
    "db_connections",
    "network_io",
)


@dataclass(frozen=True)
class SimulationSnapshot:
    scenario: Scenario
    telemetry: tuple[TelemetryPoint, ...]
    logs: tuple[StructuredLog, ...]
    kubernetes: dict[str, Any]
    deployment: dict[str, Any]
    runbooks: tuple[dict[str, str], ...]
    injected_at: float


class IncidentSimulator:
    """Generates reproducible telemetry and provider state for one injected fault."""

    def __init__(self) -> None:
        self._snapshot: SimulationSnapshot | None = None

    @property
    def active(self) -> SimulationSnapshot | None:
        return self._snapshot

    def reset(self) -> None:
        self._snapshot = None

    def inject(self, scenario_id: str) -> SimulationSnapshot:
        scenario = by_id(scenario_id)
        rng = np.random.default_rng(scenario.seed)
        rows = 120
        onset = 72 + scenario.seed % 8
        values = rng.normal(0.0, 0.035, size=(rows, len(FEATURES)))
        baseline = np.array([0.32, 0.41, 94.0, 0.012, 0.18, 8.0, 11.0, 42.0])
        scales = np.array([0.12, 0.15, 8.0, 0.006, 0.04, 2.0, 1.4, 8.0])
        values = baseline + values * scales
        self._apply_fault(values, onset, scenario.root_cause)
        now = 1_788_332_400.0 + scenario.seed
        telemetry = tuple(
            TelemetryPoint(timestamp=now + i, **dict(zip(FEATURES, row, strict=True)))
            for i, row in enumerate(values)
        )
        trace_id = hashlib.sha256(scenario.id.encode()).hexdigest()[:24]
        logs = self._logs(scenario, now, onset, trace_id, rng)
        kubernetes = self._kubernetes_state(scenario, onset)
        deployment = {
            "revision": "8f2c1a"
            if scenario.category in {"deployment", "resources", "kubernetes"}
            else "42b761",
            "deployed_at": now + onset - 42,
            "service": scenario.service,
            "diff": self._deployment_diff(scenario),
            "author": "release-bot",
        }
        runbooks = (
            {
                "id": f"rb_{scenario.root_cause}",
                "title": f"Recover {scenario.root_cause}",
                "body": (
                    f"Verify {', '.join(scenario.expected_evidence)} before "
                    f"{scenario.acceptable_remediations[0]}."
                ),
            },
            {
                "id": "rb_safe_changes",
                "title": "Safe incident changes",
                "body": (
                    "Require approval for all writes. Never delete a namespace during "
                    "incident diagnosis."
                ),
            },
        )
        self._snapshot = SimulationSnapshot(
            scenario, telemetry, logs, kubernetes, deployment, runbooks, now + onset
        )
        return self._snapshot

    @staticmethod
    def _apply_fault(values: np.ndarray, onset: int, cause: str) -> None:
        span = len(values) - onset
        ramp = np.linspace(0.0, 1.0, span)
        if cause in {"oom_killed", "memory_leak"}:
            values[onset:, 1] += 0.2 + ramp * 1.2
            values[onset:, 3] += ramp * 0.24
            values[onset:, 4] += ramp * 2.8
        elif cause in {"cpu_throttling"}:
            values[onset:, 0] += 0.75
            values[onset:, 4] += 2.4
            values[onset:, 3] += 0.14
        elif cause in {"db_pool_exhaustion", "slow_query_lock"}:
            values[onset:, 6] += 28.0
            values[onset:, 4] += 3.1
            values[onset:, 3] += 0.12
        elif cause in {"queue_saturation"}:
            values[onset:, 5] += 20.0 + ramp * 160.0
            values[onset:, 4] += ramp * 1.8
        elif cause in {"downstream_rate_limit"}:
            values[onset:, 2] += 70.0
            values[onset:, 3] += 0.28
            values[onset:, 4] += 1.4
        elif cause in {"dns_failure", "dependency_timeout", "network_policy_denied"}:
            values[onset:, 7] *= 0.15
            values[onset:, 3] += 0.32
            values[onset:, 4] += 3.4
        elif cause == "disk_pressure":
            values[onset:, 1] += 0.25
            values[onset:, 4] += 0.8
        else:
            values[onset:, 3] += 0.22
            values[onset:, 4] += 2.0

    @staticmethod
    def _logs(
        scenario: Scenario, now: float, onset: int, trace_id: str, rng: np.random.Generator
    ) -> tuple[StructuredLog, ...]:
        normal = [
            StructuredLog(
                timestamp=now + i * 5,
                service=scenario.service,
                level="INFO",
                message=f"request completed status=200 duration_ms={rng.integers(14, 90)}",
                trace_id=trace_id,
            )
            for i in range(14)
        ]
        incident_messages = {
            "oom_killed": "container terminated reason=OOMKilled exit_code=137",
            "memory_leak": "heap pressure high retained_buffers increasing",
            "cpu_throttling": "cgroup cpu throttled execution delayed",
            "bad_readiness_probe": "readiness probe failed status=404 path=/readyz",
            "bad_configmap": "upstream connection failed invalid host",
            "missing_secret": "startup failed missing secret key PAYMENT_TOKEN",
            "image_pull_failure": "pod pending ImagePullBackOff",
            "selector_mismatch": "service has zero ready endpoints",
            "dns_failure": "lookup payments.svc: no such host",
            "dependency_timeout": "bank gateway request deadline exceeded",
            "network_policy_denied": "egress connection denied by policy",
            "db_pool_exhaustion": "database pool acquire timeout",
            "slow_query_lock": "ledger update waiting on row lock",
            "bad_environment": "invalid feature flag value during startup",
            "dependency_regression": "legacy payload rejected UnsupportedSchema",
            "queue_saturation": "consumer lag above SLO queue saturated",
            "downstream_rate_limit": "bank gateway returned status=429 retry_after=2",
            "disk_pressure": "node condition DiskPressure pod eviction scheduled",
        }
        abnormal = [
            StructuredLog(
                timestamp=now + onset + i * 2,
                service=scenario.service,
                level="ERROR",
                message=incident_messages[scenario.root_cause],
                trace_id=trace_id,
            )
            for i in range(8)
        ]
        return tuple(sorted(normal + abnormal, key=lambda row: row.timestamp))

    @staticmethod
    def _kubernetes_state(scenario: Scenario, onset: int) -> dict[str, Any]:
        reason_by_cause = {
            "oom_killed": "OOMKilled",
            "image_pull_failure": "ImagePullBackOff",
            "bad_readiness_probe": "Unhealthy",
            "disk_pressure": "Evicted",
        }
        return {
            "namespace": "sentinel-demo",
            "pods": [
                {
                    "name": f"{scenario.service}-7fc8",
                    "ready": scenario.category not in {"kubernetes", "resources"},
                    "restarts": 4 if scenario.root_cause in {"oom_killed", "memory_leak"} else 0,
                }
            ],
            "events": [
                {
                    "reason": reason_by_cause.get(scenario.root_cause, "Degraded"),
                    "message": scenario.title,
                    "offset": onset,
                }
            ],
            "deployment": {"name": scenario.service, "generation": 12, "available_replicas": 1},
            "service": {
                "name": scenario.service,
                "endpoints": 0 if scenario.root_cause == "selector_mismatch" else 2,
            },
            "configmap": {
                "name": f"{scenario.service}-config",
                "valid": scenario.root_cause != "bad_configmap",
            },
            "resource_limits": {
                "cpu": "500m",
                "memory": "256Mi" if scenario.root_cause == "oom_killed" else "512Mi",
            },
        }

    @staticmethod
    def _deployment_diff(scenario: Scenario) -> str:
        diffs = {
            "oom_killed": "- memory: 512Mi\n+ memory: 256Mi",
            "bad_readiness_probe": "- path: /ready\n+ path: /readyz",
            "bad_configmap": "- PAYMENTS_URL: http://payments\n+ PAYMENTS_URL: http://payment",
            "missing_secret": "- key: PAYMENT_TOKEN\n+ key: PAYMENTS_TOKEN",
            "image_pull_failure": "- image: worker:stable\n+ image: worker:missing",
        }
        return diffs.get(
            scenario.root_cause, f"release change correlated with {scenario.root_cause}"
        )
