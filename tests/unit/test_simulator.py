import importlib
import json
from pathlib import Path

import pytest
import yaml

from simulator.catalog import FAULT_SPECS, build_catalog
from simulator.engine import IncidentSimulator
from simulator.faults.kubernetes import CommandResult, KubernetesFaultController


def test_catalog_has_portfolio_scale_and_diverse_root_causes() -> None:
    scenarios = build_catalog()
    assert len(scenarios) >= 30
    assert len({scenario.root_cause for scenario in scenarios}) >= 10
    assert len({scenario.id for scenario in scenarios}) == len(scenarios)


def test_injection_is_deterministic_and_resettable() -> None:
    simulator = IncidentSimulator()
    first = simulator.inject("oom_killed_001")
    simulator.reset()
    second = simulator.inject("oom_killed_001")
    assert first.telemetry == second.telemetry
    assert first.logs == second.logs
    assert max(point.memory for point in first.telemetry[-20:]) > max(
        point.memory for point in first.telemetry[:20]
    )


def test_runtime_snapshot_excludes_evaluator_labels() -> None:
    snapshot = IncidentSimulator().inject("oom_killed_001")
    runtime_fields = snapshot.scenario.model_dump()
    assert "root_cause" not in runtime_fields
    assert "expected_evidence" not in runtime_fields
    assert "acceptable_remediations" not in runtime_fields
    assert "forbidden_actions" not in runtime_fields
    assert all("oom_killed" not in str(item).lower() for item in snapshot.runbooks)


class RecordingRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> CommandResult:
        del input_text, timeout_seconds
        self.calls.append(args)
        output = '{"items": []}' if "get" in args else ""
        return CommandResult(args=args, returncode=0, stdout=output)


class OOMEvidenceRunner(RecordingRunner):
    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> CommandResult:
        del input_text, timeout_seconds
        self.calls.append(args)
        payload = {
            "items": [
                {
                    "metadata": {"name": "payments-abc"},
                    "status": {
                        "containerStatuses": [
                            {
                                "restartCount": 1,
                                "lastState": {
                                    "terminated": {"reason": "OOMKilled", "exitCode": 137}
                                },
                            }
                        ]
                    },
                }
            ]
        }
        return CommandResult(args=args, returncode=0, stdout=json.dumps(payload))


class ReadinessEvidenceRunner(RecordingRunner):
    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> CommandResult:
        del input_text, timeout_seconds
        self.calls.append(args)
        payload = {
            "items": [
                {
                    "metadata": {"name": "checkout-unready"},
                    "spec": {
                        "containers": [
                            {
                                "env": [
                                    {
                                        "name": "SENTINEL_SCENARIO_ID",
                                        "value": "bad_readiness_probe_001",
                                    }
                                ]
                            }
                        ]
                    },
                    "status": {
                        "containerStatuses": [
                            {"ready": False, "state": {"running": {"startedAt": "now"}}}
                        ]
                    },
                }
            ]
        }
        return CommandResult(args=args, returncode=0, stdout=json.dumps(payload))


class EmptyEndpointsRunner(RecordingRunner):
    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> CommandResult:
        del input_text, timeout_seconds
        self.calls.append(args)
        return CommandResult(
            args=args,
            returncode=0,
            stdout=json.dumps({"metadata": {"name": "frontend"}, "subsets": []}),
        )


class RestartCollisionRunner(RecordingRunner):
    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout_seconds: float = 60.0,
    ) -> CommandResult:
        del input_text, timeout_seconds
        self.calls.append(args)
        if len(self.calls) == 1:
            return CommandResult(
                args=args,
                returncode=1,
                stderr=(
                    "if restart has already been triggered within the past second, "
                    "please wait before attempting to trigger another"
                ),
            )
        return CommandResult(args=args, returncode=0)


@pytest.mark.parametrize("cause", [spec[1] for spec in FAULT_SPECS])
def test_every_catalog_fault_has_a_real_kubectl_strategy(cause: str) -> None:
    runner = RecordingRunner()
    root = Path(__file__).resolve().parents[2]
    controller = KubernetesFaultController(runner, repository_root=root)
    receipt = controller.inject(f"{cause}_001")
    assert receipt.root_cause == cause
    assert receipt.operations
    assert all(call[0] == "kubectl" and "--namespace" in call for call in runner.calls)
    assert any(action in call for call in runner.calls for action in ("patch", "set", "apply"))


def test_oom_wait_requires_kubernetes_termination_evidence() -> None:
    runner = OOMEvidenceRunner()
    controller = KubernetesFaultController(runner)

    evidence = controller.wait_for_oom_killed("oom_killed_001")

    assert evidence.reason == "OOMKilled"
    assert evidence.pod == "payments-abc"
    assert evidence.restart_count == 1
    assert any("app=payments" in call for call in runner.calls)


def test_oom_wait_rejects_non_oom_scenarios() -> None:
    with pytest.raises(ValueError, match="not an OOM fault"):
        KubernetesFaultController(RecordingRunner()).wait_for_oom_killed(
            "cpu_throttling_001"
        )


def test_readiness_wait_requires_running_unready_scenario_pod() -> None:
    runner = ReadinessEvidenceRunner()
    controller = KubernetesFaultController(runner)

    evidence = controller.wait_for_bad_readiness("bad_readiness_probe_001")

    assert evidence.resource == "pod/checkout-unready"
    assert evidence.condition == "Ready"
    assert evidence.observed_value == "False"
    assert any("app=checkout" in call for call in runner.calls)


def test_selector_wait_requires_zero_service_endpoints() -> None:
    runner = EmptyEndpointsRunner()
    controller = KubernetesFaultController(runner)

    evidence = controller.wait_for_selector_mismatch("selector_mismatch_001")

    assert evidence.resource == "service/frontend"
    assert evidence.condition == "ReadyEndpoints"
    assert evidence.observed_value == "0"
    assert any("endpoints" in call for call in runner.calls)


@pytest.mark.parametrize(
    ("method_name", "scenario_id", "message"),
    [
        ("wait_for_bad_readiness", "oom_killed_001", "not a readiness fault"),
        ("wait_for_selector_mismatch", "oom_killed_001", "not a selector fault"),
    ],
)
def test_kubernetes_condition_waits_reject_wrong_fault_classes(
    method_name: str, scenario_id: str, message: str
) -> None:
    controller = KubernetesFaultController(RecordingRunner())

    with pytest.raises(ValueError, match=message):
        getattr(controller, method_name)(scenario_id)


def test_rollout_restart_retries_timestamp_collision(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = RestartCollisionRunner()
    controller = KubernetesFaultController(runner)
    monkeypatch.setattr("simulator.faults.kubernetes.time.sleep", lambda _: None)

    controller._restart_rollout("deployment/traffic-generator")

    assert len(runner.calls) == 2
    expected = ["rollout", "restart", "deployment/traffic-generator"]
    assert all(call[1:4] == expected for call in runner.calls)


def test_catalog_fault_injector_references_resolve() -> None:
    for scenario in build_catalog():
        module_name, function_name = scenario.fault_injector.split(":", maxsplit=1)
        module = importlib.import_module(module_name)
        assert callable(getattr(module, function_name))


def test_kubernetes_manifest_defines_buildable_networked_demo() -> None:
    root = Path(__file__).resolve().parents[2]
    manifest = root / "infrastructure" / "kubernetes" / "demo-services.yaml"
    resources = [item for item in yaml.safe_load_all(manifest.read_text()) if item]
    kinds = [item["kind"] for item in resources]
    assert kinds.count("Deployment") == 5
    assert kinds.count("Service") == 5
    assert "StatefulSet" in kinds
    images = {
        container["image"]
        for item in resources
        if item["kind"] in {"Deployment", "StatefulSet"}
        for container in item["spec"]["template"]["spec"]["containers"]
    }
    assert "sentinel/demo-service:local" in images
    assert "sentinel/traffic-generator:local" in images
    assert (root / "infrastructure" / "docker" / "demo-service.Dockerfile").exists()
    assert (root / "infrastructure" / "docker" / "traffic.Dockerfile").exists()
