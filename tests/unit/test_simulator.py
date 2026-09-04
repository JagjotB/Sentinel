import importlib
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
