from __future__ import annotations

from simulator.engine import IncidentSimulator, SimulationSnapshot


def inject(simulator: IncidentSimulator, scenario_id: str) -> SimulationSnapshot:
    """The only local mutation entry point; reset keeps evaluation trials idempotent."""
    simulator.reset()
    return simulator.inject(scenario_id)
