from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies import require_mutation_token
from api.schemas.incidents import ScenarioRunIn
from simulator.catalog import build_catalog
from simulator.engine import IncidentSimulator

router = APIRouter(
    prefix="/v1/simulator",
    tags=["simulator"],
    dependencies=[Depends(require_mutation_token)],
)
simulator = IncidentSimulator()


@router.get("/scenarios")
def scenarios() -> list[dict[str, object]]:
    return [scenario.model_dump(mode="json") for scenario in build_catalog()]


@router.post("/run")
def run_scenario(request: ScenarioRunIn) -> dict[str, object]:
    snapshot = simulator.inject(request.scenario_id)
    return {
        "scenario": snapshot.scenario.model_dump(mode="json"),
        "telemetry_points": len(snapshot.telemetry),
        "log_count": len(snapshot.logs),
        "injected_at": snapshot.injected_at,
    }


@router.post("/reset")
def reset() -> dict[str, str]:
    simulator.reset()
    return {"status": "reset"}
