from simulator.catalog import build_catalog
from simulator.engine import IncidentSimulator


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
