from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from agents.service import InvestigationService
from api.dependencies import get_repository, require_mutation_token
from api.schemas.incidents import ScenarioRunIn
from persistence.repository import SentinelRepository
from runtime.state import RuntimeState
from simulator.catalog import build_catalog
from simulator.engine import IncidentSimulator

router = APIRouter(
    prefix="/v1/simulator",
    tags=["simulator"],
)
simulator = IncidentSimulator()
Repository = Annotated[SentinelRepository, Depends(get_repository)]


@router.get("/scenarios")
def scenarios() -> list[dict[str, object]]:
    return [scenario.model_dump(mode="json") for scenario in build_catalog()]


@router.post("/run", dependencies=[Depends(require_mutation_token)])
async def run_scenario(request: ScenarioRunIn, repository: Repository) -> RuntimeState:
    return await InvestigationService(repository).run_scenario(request.scenario_id)


@router.post("/reset", dependencies=[Depends(require_mutation_token)])
def reset() -> dict[str, str]:
    simulator.reset()
    return {"status": "reset"}
