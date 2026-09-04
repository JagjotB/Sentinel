from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from agents.service import InvestigationService
from api.dependencies import get_repository, require_mutation_token
from api.schemas.incidents import ScenarioRunIn
from api.settings import get_settings
from mcp.factory import ToolProviderConfig
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetPolicy
from runtime.model_router import build_model_router
from runtime.state import RuntimeState
from simulator.catalog import build_catalog
from simulator.engine import IncidentSimulator
from simulator.faults.kubernetes import FaultReceipt, KubernetesFaultController

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
    return await _investigation_service(repository).run_scenario(request.scenario_id)


@router.post("/cluster/investigate", dependencies=[Depends(require_mutation_token)])
async def investigate_cluster(request: ScenarioRunIn, repository: Repository) -> RuntimeState:
    return await _investigation_service(repository, live=True).run_scenario(request.scenario_id)


def _investigation_service(
    repository: SentinelRepository, *, live: bool = False
) -> InvestigationService:
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
    mode = "live" if live else settings.tool_provider
    tools = ToolProviderConfig(
        mode=mode,
        namespace=settings.kubernetes_namespace,
        kubectl_context=settings.kubectl_context,
        prometheus_url=settings.prometheus_url,
        tempo_url=settings.tempo_url,
        git_repository_path=Path(settings.git_repository_path),
        github_repository=settings.github_repository,
        github_token=settings.github_token,
    )
    return InvestigationService(repository, budget, model_router, tools)


@router.post("/reset", dependencies=[Depends(require_mutation_token)])
def reset() -> dict[str, str]:
    simulator.reset()
    return {"status": "reset"}


@router.post(
    "/cluster/inject",
    dependencies=[Depends(require_mutation_token)],
    response_model=FaultReceipt,
)
def inject_cluster(request: ScenarioRunIn) -> FaultReceipt:
    return KubernetesFaultController().inject(request.scenario_id)


@router.post("/cluster/reset", dependencies=[Depends(require_mutation_token)])
def reset_cluster() -> dict[str, object]:
    operations = KubernetesFaultController().reset()
    return {"status": "reset", "operations": operations}
