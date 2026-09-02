from __future__ import annotations

from collections import deque

from runtime.budgets import BudgetLedger
from runtime.state import AgentTask, TaskStatus


class TaskScheduler:
    def __init__(self, ledger: BudgetLedger) -> None:
        self.ledger = ledger
        self._pending: deque[AgentTask] = deque()
        self._tasks: dict[str, AgentTask] = {}

    def spawn(self, task: AgentTask) -> AgentTask:
        if task.id in self._tasks:
            raise ValueError(f"duplicate task: {task.id}")
        self.ledger.consume_subagent()
        self._tasks[task.id] = task
        self._pending.append(task)
        return task

    def next(self) -> AgentTask | None:
        while self._pending:
            task = self._pending.popleft()
            current = self._tasks[task.id]
            if current.status is TaskStatus.PENDING:
                running = current.model_copy(update={"status": TaskStatus.RUNNING})
                self._tasks[task.id] = running
                return running
        return None

    def complete(self, task_id: str, outputs: dict[str, object], evidence_ids: list[str]) -> None:
        task = self._tasks[task_id]
        self._tasks[task_id] = task.model_copy(
            update={
                "status": TaskStatus.COMPLETED,
                "outputs": outputs,
                "evidence_ids": evidence_ids,
            }
        )

    def cancel(self, task_id: str) -> None:
        task = self._tasks[task_id]
        self._tasks[task_id] = task.model_copy(update={"status": TaskStatus.CANCELLED})

    def snapshot(self) -> list[AgentTask]:
        return list(self._tasks.values())
