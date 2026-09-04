from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.base import InvestigationContext
from agents.change_analysis import ChangeAnalysisAgent
from agents.diagnosis import DiagnosisAgent, Hypothesis
from agents.infrastructure import InfrastructureAgent
from agents.remediation import RemediationAgent
from agents.retrieval import RetrievalAgent
from agents.telemetry import TelemetryAgent
from agents.verifier import VerifierAgent
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetLedger
from runtime.checkpoints import CheckpointStore
from runtime.langchain_gateway import LangChainReasoner, ModelCallContext
from runtime.scheduler import TaskScheduler
from runtime.state import (
    AgentTask,
    Evidence,
    ExecutionStatus,
    RuntimeState,
    StepRecord,
    TaskStatus,
)
from runtime.tool_registry import ToolRegistry
from simulator.engine import SimulationSnapshot

EvidenceRunner = Callable[[InvestigationContext, str], Awaitable[list[Evidence]]]
GraphNode = Literal[
    "initialize", "collect_evidence", "diagnose", "verify", "remediate", "abstain"
]


class InvestigationGraphState(TypedDict):
    runtime: RuntimeState
    ledger: BudgetLedger
    scheduler: TaskScheduler
    context: InvestigationContext
    supervisor_id: str
    hypotheses: list[Hypothesis]
    verification: dict[str, object]


class SupervisorAgent:
    """LangGraph supervisor for the durable Sentinel investigation workflow."""

    name = "supervisor"

    def __init__(
        self,
        repository: SentinelRepository,
        tools: ToolRegistry,
        snapshot: SimulationSnapshot,
        checkpoints: CheckpointStore,
        reasoner: LangChainReasoner | None = None,
        *,
        use_snapshot_models: bool = True,
    ) -> None:
        self.repository = repository
        self.tools = tools
        self.snapshot = snapshot
        self.checkpoints = checkpoints
        self.reasoner = reasoner or LangChainReasoner(repository)
        self.use_snapshot_models = use_snapshot_models
        self.graph = self._build_graph()

    async def run(self, state: RuntimeState, ledger: BudgetLedger) -> RuntimeState:
        supervisor_id = self._supervisor_id(state)
        graph_input = InvestigationGraphState(
            runtime=state,
            ledger=ledger,
            scheduler=TaskScheduler(ledger),
            context=InvestigationContext(state, self.snapshot, self.repository, self.tools, ledger),
            supervisor_id=supervisor_id,
            hypotheses=[],
            verification={},
        )
        result = await self.graph.ainvoke(
            graph_input,
            config={
                "configurable": {"thread_id": state.execution_id},
                "tags": ["sentinel", "langgraph", "incident-investigation"],
                "metadata": {
                    "incident_id": state.incident_id,
                    "execution_id": state.execution_id,
                    "trace_id": state.trace_id,
                },
            },
        )
        return cast(RuntimeState, result["runtime"])

    def topology(self) -> set[str]:
        """Return compiled node names for tests, diagnostics, and operator APIs."""
        return set(self.graph.get_graph().nodes) - {START, END}

    def _build_graph(
        self,
    ) -> CompiledStateGraph[
        InvestigationGraphState, None, InvestigationGraphState, InvestigationGraphState
    ]:
        builder = StateGraph(InvestigationGraphState)
        builder.add_node("initialize", self._initialize_node)
        builder.add_node("collect_evidence", self._collect_evidence_node)
        builder.add_node("diagnose", self._diagnose_node)
        builder.add_node("verify", self._verify_node)
        builder.add_node("remediate", self._remediation_node)
        builder.add_node("abstain", self._abstain_node)
        builder.add_conditional_edges(START, self._entry_route)
        builder.add_edge("initialize", "collect_evidence")
        builder.add_edge("collect_evidence", "diagnose")
        builder.add_edge("diagnose", "verify")
        builder.add_conditional_edges(
            "verify",
            self._verification_route,
            {"remediate": "remediate", "abstain": "abstain"},
        )
        builder.add_edge("remediate", END)
        builder.add_edge("abstain", END)
        return builder.compile(name="sentinel-investigation")

    def _entry_route(self, state: InvestigationGraphState) -> GraphNode:
        runtime = state["runtime"]
        stage = str(runtime.metadata.get("graph_stage", ""))
        if stage == "initialized":
            return "collect_evidence"
        if stage == "evidence_collected":
            return "diagnose"
        if stage == "diagnosed":
            return "verify"
        if stage == "verified":
            supported = runtime.diagnosis is not None and runtime.diagnosis.status == "supported"
            return "remediate" if supported else "abstain"
        if stage == "remediation_proposed":
            return "remediate"
        if stage == "abstained":
            return "abstain"
        return "initialize"

    @staticmethod
    def _verification_route(state: InvestigationGraphState) -> Literal["remediate", "abstain"]:
        diagnosis = state["runtime"].diagnosis
        return "remediate" if diagnosis and diagnosis.status == "supported" else "abstain"

    async def _initialize_node(self, state: InvestigationGraphState) -> InvestigationGraphState:
        runtime = state["runtime"]
        if not any(task.agent == self.name for task in runtime.tasks):
            supervisor_task = AgentTask(
                id=state["supervisor_id"],
                agent=self.name,
                title="Investigate alert and coordinate evidence",
                status=TaskStatus.RUNNING,
            )
            self.repository.add_task(
                id=supervisor_task.id,
                incident_id=runtime.incident_id,
                execution_id=runtime.execution_id,
                parent_id=None,
                agent=self.name,
                title=supervisor_task.title,
                status=TaskStatus.RUNNING.value,
                inputs={"alert": self.repository.get_incident(runtime.incident_id).alert},
                outputs={},
                evidence_ids=[],
            )
            runtime = runtime.model_copy(update={"tasks": [*runtime.tasks, supervisor_task]})
        return self._advance(state, runtime, "initialized")

    async def _collect_evidence_node(
        self, state: InvestigationGraphState
    ) -> InvestigationGraphState:
        branches: list[tuple[str, str, EvidenceRunner]] = [
            ("infrastructure", "Inspect Kubernetes and runtime state", InfrastructureAgent().run),
            (
                "telemetry",
                "Analyze telemetry and logs",
                TelemetryAgent(use_snapshot_models=self.use_snapshot_models).run,
            ),
        ]
        scenario = self.snapshot.scenario
        if scenario.category in {"deployment", "kubernetes", "resources"}:
            branches.append(
                (
                    "change_analysis",
                    "Correlate recent deployment changes",
                    ChangeAnalysisAgent().run,
                )
            )
        if scenario.difficulty != "easy":
            branches.append(
                ("retrieval", "Retrieve similar incidents and runbooks", RetrievalAgent().run)
            )
        results = await asyncio.gather(
            *(
                self._run_evidence_task(
                    state["scheduler"],
                    state["context"],
                    state["supervisor_id"],
                    agent,
                    title,
                    runner,
                )
                for agent, title, runner in branches
            )
        )
        tasks = [task for task, _ in results]
        evidence = [item for _, branch_evidence in results for item in branch_evidence]
        runtime = state["runtime"].model_copy(
            update={"tasks": [*state["runtime"].tasks, *tasks], "evidence": evidence}
        )
        return self._advance(state, runtime, "evidence_collected")

    async def _diagnose_node(self, state: InvestigationGraphState) -> InvestigationGraphState:
        runtime = state["runtime"]
        task = self._start_task(
            state["scheduler"],
            runtime,
            state["supervisor_id"],
            "diagnosis",
            "Rank evidence-backed hypotheses",
        )
        diagnosis, hypotheses, invocation = await DiagnosisAgent().run_with_model(
            runtime.evidence,
            self.reasoner,
            self._model_context(runtime, task.id),
            state["ledger"],
        )
        task = self._finish_task(
            state["scheduler"],
            task,
            {
                "hypotheses": hypotheses,
                "diagnosis": diagnosis.model_dump(mode="json"),
                "model": f"{invocation.provider}/{invocation.model}",
            },
            diagnosis.evidence_ids,
        )
        step = self._model_step(task, invocation.provider, invocation.model, diagnosis.evidence_ids)
        runtime = runtime.model_copy(
            update={
                "tasks": [*runtime.tasks, task],
                "steps": [*runtime.steps, step],
                "diagnosis": diagnosis,
            }
        )
        advanced = self._advance(state, runtime, "diagnosed")
        advanced["hypotheses"] = hypotheses
        return advanced

    async def _verify_node(self, state: InvestigationGraphState) -> InvestigationGraphState:
        runtime = state["runtime"]
        if runtime.diagnosis is None:
            raise RuntimeError("diagnosis must exist before verification")
        task = self._start_task(
            state["scheduler"],
            runtime,
            state["supervisor_id"],
            "verifier",
            "Falsify the leading hypothesis",
        )
        verified, verification, invocation = await VerifierAgent().run_with_model(
            runtime.diagnosis,
            runtime.evidence,
            self.reasoner,
            self._model_context(runtime, task.id),
            state["ledger"],
        )
        task = self._finish_task(
            state["scheduler"],
            task,
            {**verification, "model": f"{invocation.provider}/{invocation.model}"},
            list(verified.contradictory_evidence_ids),
        )
        step = self._model_step(
            task,
            invocation.provider,
            invocation.model,
            list(verified.contradictory_evidence_ids),
        )
        runtime = runtime.model_copy(
            update={
                "tasks": [*runtime.tasks, task],
                "steps": [*runtime.steps, step],
                "diagnosis": verified,
            }
        )
        advanced = self._advance(state, runtime, "verified")
        advanced["verification"] = verification
        return advanced

    async def _remediation_node(self, state: InvestigationGraphState) -> InvestigationGraphState:
        runtime = state["runtime"]
        if runtime.diagnosis is None or runtime.diagnosis.status != "supported":
            raise RuntimeError("supported diagnosis is required before remediation")
        if runtime.remediation is None:
            task = self._start_task(
                state["scheduler"],
                runtime,
                state["supervisor_id"],
                "remediation",
                "Generate a policy-safe proposal",
            )
            remediation = RemediationAgent().run(
                runtime.incident_id, runtime.diagnosis, self.repository
            )
            task = self._finish_task(
                state["scheduler"],
                task,
                {"remediation_id": remediation.id, "plan": remediation.plan},
                runtime.diagnosis.evidence_ids,
            )
            runtime = runtime.model_copy(
                update={
                    "tasks": [*runtime.tasks, task],
                    "remediation": {
                        "id": remediation.id,
                        "action": remediation.action,
                        "risk_class": remediation.risk_class,
                        "plan": remediation.plan,
                        "status": remediation.status,
                    },
                }
            )
        self._finish_supervisor(runtime, "await_human_approval")
        runtime = runtime.model_copy(update={"status": ExecutionStatus.WAITING_APPROVAL})
        return self._advance(state, runtime, "remediation_proposed")

    async def _abstain_node(self, state: InvestigationGraphState) -> InvestigationGraphState:
        runtime = state["runtime"]
        self._finish_supervisor(runtime, "abstain")
        runtime = runtime.model_copy(update={"status": ExecutionStatus.INSUFFICIENT_EVIDENCE})
        return self._advance(state, runtime, "abstained")

    async def _run_evidence_task(
        self,
        scheduler: TaskScheduler,
        context: InvestigationContext,
        parent_id: str,
        agent: str,
        title: str,
        runner: EvidenceRunner,
    ) -> tuple[AgentTask, list[Evidence]]:
        task = self._start_task(scheduler, context.state, parent_id, agent, title)
        evidence = await runner(context, task.id)
        completed = self._finish_task(
            scheduler,
            task,
            {"evidence_count": len(evidence)},
            [item.id for item in evidence],
        )
        return completed, evidence

    def _advance(
        self, graph_state: InvestigationGraphState, runtime: RuntimeState, stage: str
    ) -> InvestigationGraphState:
        path = [str(item) for item in runtime.metadata.get("graph_path", [])]
        if not path or path[-1] != stage:
            path.append(stage)
        updated = runtime.model_copy(
            update={
                "metadata": {
                    **runtime.metadata,
                    "orchestrator": "langgraph",
                    "graph_name": "sentinel-investigation",
                    "graph_stage": stage,
                    "graph_path": path,
                }
            }
        )
        updated = self.checkpoints.save(updated)
        context = graph_state["context"]
        context.state = updated
        return InvestigationGraphState(
            runtime=updated,
            ledger=graph_state["ledger"],
            scheduler=graph_state["scheduler"],
            context=context,
            supervisor_id=graph_state["supervisor_id"],
            hypotheses=graph_state["hypotheses"],
            verification=graph_state["verification"],
        )

    def _start_task(
        self,
        scheduler: TaskScheduler,
        state: RuntimeState,
        parent_id: str,
        agent: str,
        title: str,
    ) -> AgentTask:
        task = AgentTask(id=self._new_task_id(), parent_id=parent_id, agent=agent, title=title)
        scheduler.spawn(task)
        running = scheduler.next()
        assert running is not None
        self.repository.add_task(
            id=running.id,
            incident_id=state.incident_id,
            execution_id=state.execution_id,
            parent_id=parent_id,
            agent=agent,
            title=title,
            status=TaskStatus.RUNNING.value,
            inputs={},
            outputs={},
            evidence_ids=[],
        )
        return running

    def _finish_task(
        self,
        scheduler: TaskScheduler,
        task: AgentTask,
        outputs: dict[str, object],
        evidence_ids: list[str],
    ) -> AgentTask:
        scheduler.complete(task.id, outputs, evidence_ids)
        self.repository.update_task(
            task.id,
            status=TaskStatus.COMPLETED.value,
            outputs=outputs,
            evidence_ids=evidence_ids,
        )
        return next(item for item in scheduler.snapshot() if item.id == task.id)

    def _finish_supervisor(self, runtime: RuntimeState, decision: str) -> None:
        supervisor = next(task for task in runtime.tasks if task.agent == self.name)
        self.repository.update_task(
            supervisor.id,
            status=TaskStatus.COMPLETED.value,
            outputs={"decision": decision},
            evidence_ids=runtime.diagnosis.evidence_ids if runtime.diagnosis else [],
        )

    @staticmethod
    def _model_context(runtime: RuntimeState, task_id: str) -> ModelCallContext:
        return ModelCallContext(
            incident_id=runtime.incident_id,
            execution_id=runtime.execution_id,
            task_id=task_id,
            trace_id=runtime.trace_id,
        )

    @staticmethod
    def _model_step(
        task: AgentTask, provider: str, model: str, evidence_ids: list[str]
    ) -> StepRecord:
        return StepRecord(
            id=f"step_{secrets.token_hex(8)}",
            task_id=task.id,
            agent=task.agent,
            status=TaskStatus.COMPLETED,
            outputs=task.outputs,
            model=f"{provider}/{model}",
            evidence_ids=evidence_ids,
            completed_at=datetime.now(UTC),
        )

    @classmethod
    def _supervisor_id(cls, state: RuntimeState) -> str:
        existing = next((task.id for task in state.tasks if task.agent == cls.name), None)
        return existing or cls._new_task_id()

    @staticmethod
    def _new_task_id() -> str:
        return f"task_{secrets.token_hex(8)}"
