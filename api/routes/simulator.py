from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from agents.service import InvestigationService
from api.dependencies import get_repository, require_mutation_token
from api.schemas.incidents import ScenarioRunIn
from api.settings import get_settings
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetPolicy
from runtime.model_router import build_model_router
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
    settings = get_settings()
    budget = BudgetPolicy(
        max_runtime_seconds=settings.max_runtime_seconds,
        max_model_tokens=settings.max_model_tokens,
        max_tool_calls=settings.max_tool_calls,
        max_subagents=settings.max_subagents,
        max_identical_tool_calls=settings.max_identical_tool_calls,
        max_cost_usd=settings.max_cost_usd,
    )
    model_router = build_model_router(settings.model_provider, settings.model_name)
    return await InvestigationService(repository, budget, model_router).run_scenario(
        request.scenario_id
    )


@router.post("/reset", dependencies=[Depends(require_mutation_token)])
def reset() -> dict[str, str]:
    simulator.reset()
    return {"status": "reset"}
