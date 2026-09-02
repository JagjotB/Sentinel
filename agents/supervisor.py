from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from agents.base import InvestigationContext
from agents.change_analysis import ChangeAnalysisAgent
from agents.diagnosis import DiagnosisAgent
from agents.infrastructure import InfrastructureAgent
from agents.remediation import RemediationAgent
from agents.retrieval import RetrievalAgent
from agents.telemetry import TelemetryAgent
from agents.verifier import VerifierAgent
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetLedger
from runtime.checkpoints import CheckpointStore
from runtime.scheduler import TaskScheduler
from runtime.state import AgentTask, Evidence, ExecutionStatus, RuntimeState, TaskStatus
from runtime.tool_registry import ToolRegistry
from simulator.engine import SimulationSnapshot

EvidenceRunner = Callable[[InvestigationContext, str], Awaitable[list[Evidence]]]


class SupervisorAgent:
    name = "supervisor"

    def __init__(
        self,
        repository: SentinelRepository,
        tools: ToolRegistry,
        snapshot: SimulationSnapshot,
        checkpoints: CheckpointStore,
    ) -> None:
        self.repository = repository
        self.tools = tools
        self.snapshot = snapshot
        self.checkpoints = checkpoints

    async def run(self, state: RuntimeState, ledger: BudgetLedger) -> RuntimeState:
        scheduler = TaskScheduler(ledger)
        supervisor_id = self._new_task_id()
        supervisor_task = AgentTask(
            id=supervisor_id,
            agent=self.name,
            title="Investigate alert and coordinate evidence",
            status=TaskStatus.RUNNING,
        )
        self.repository.add_task(
            id=supervisor_id,
            incident_id=state.incident_id,
            execution_id=state.execution_id,
            parent_id=None,
            agent=self.name,
            title=supervisor_task.title,
            status=TaskStatus.RUNNING.value,
            inputs={"alert": self.repository.get_incident(state.incident_id).alert},
            outputs={},
            evidence_ids=[],
        )
        context = InvestigationContext(state, self.snapshot, self.repository, self.tools, ledger)
        collected: list[Evidence] = []
        task_results: list[AgentTask] = []

        branches: list[tuple[str, str, EvidenceRunner]] = [
            ("infrastructure", "Inspect Kubernetes and runtime state", InfrastructureAgent().run),
            ("telemetry", "Analyze telemetry and logs", TelemetryAgent().run),
        ]
        if self.snapshot.scenario.category in {"deployment", "kubernetes", "resources"}:
            branches.append(
                (
                    "change_analysis",
                    "Correlate recent deployment changes",
                    ChangeAnalysisAgent().run,
                )
            )
        if self.snapshot.scenario.difficulty != "easy":
            branches.append(
                ("retrieval", "Retrieve similar incidents and runbooks", RetrievalAgent().run)
            )
        for agent, title, runner in branches:
            task, evidence = await self._run_evidence_task(
                scheduler, context, supervisor_id, agent, title, runner
            )
            task_results.append(task)
            collected.extend(evidence)
        state = state.model_copy(
            update={"tasks": [supervisor_task, *task_results], "evidence": collected}
        )
        state = self.checkpoints.save(state)
        context.state = state

        diagnosis_task = self._start_task(
            scheduler, state, supervisor_id, "diagnosis", "Rank evidence-backed hypotheses"
        )
        diagnosis, hypotheses = DiagnosisAgent().run(collected)
        diagnosis_task = self._finish_task(
            scheduler,
            diagnosis_task,
            {"hypotheses": hypotheses, "diagnosis": diagnosis.model_dump(mode="json")},
            diagnosis.evidence_ids,
        )
        state = state.model_copy(
            update={"tasks": [*state.tasks, diagnosis_task], "diagnosis": diagnosis}
        )
        state = self.checkpoints.save(state)

        verifier_task = self._start_task(
            scheduler, state, supervisor_id, "verifier", "Falsify the leading hypothesis"
        )
        verified, verification = VerifierAgent().run(diagnosis, collected)
        verifier_task = self._finish_task(
            scheduler,
            verifier_task,
            verification,
            list(verified.contradictory_evidence_ids),
        )
        tasks = [*state.tasks, verifier_task]
        if verified.status != "supported":
            self.repository.update_task(
                supervisor_id,
                status=TaskStatus.COMPLETED.value,
                outputs={"decision": "abstain"},
                evidence_ids=[],
            )
            return state.model_copy(
                update={
                    "tasks": tasks,
                    "diagnosis": verified,
                    "status": ExecutionStatus.INSUFFICIENT_EVIDENCE,
                }
            )

        remediation_task = self._start_task(
            scheduler, state, supervisor_id, "remediation", "Generate a policy-safe proposal"
        )
        remediation = RemediationAgent().run(state.incident_id, verified, self.repository)
        remediation_task = self._finish_task(
            scheduler,
            remediation_task,
            {"remediation_id": remediation.id, "plan": remediation.plan},
            verified.evidence_ids,
        )
        self.repository.update_task(
            supervisor_id,
            status=TaskStatus.COMPLETED.value,
            outputs={"decision": "await_human_approval"},
            evidence_ids=verified.evidence_ids,
        )
        return state.model_copy(
            update={
                "tasks": [*tasks, remediation_task],
                "diagnosis": verified,
                "remediation": {
                    "id": remediation.id,
                    "action": remediation.action,
                    "risk_class": remediation.risk_class,
                    "plan": remediation.plan,
                    "status": remediation.status,
                },
                "status": ExecutionStatus.WAITING_APPROVAL,
            }
        )

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
        return scheduler.snapshot()[-1]

    @staticmethod
    def _new_task_id() -> str:
        return f"task_{secrets.token_hex(8)}"
