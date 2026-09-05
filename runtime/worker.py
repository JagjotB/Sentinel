from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections.abc import Callable
from typing import Literal, Protocol, cast

from agents.service import InvestigationService
from api.settings import Settings, get_settings
from mcp.factory import ToolProviderConfig
from persistence.models import WorkItemRecord
from persistence.repository import SentinelRepository
from runtime.budgets import BudgetPolicy
from runtime.model_router import build_model_router
from runtime.state import RuntimeState
from runtime.tracing import (
    ERRORS,
    RETRIES,
    WORK_ITEMS,
    configure_telemetry,
    force_flush_telemetry,
    span,
)


class InvestigationRunner(Protocol):
    async def run_incident(self, incident_id: str) -> RuntimeState: ...


ServiceFactory = Callable[[Literal["simulator", "live"]], InvestigationRunner]


class InvestigationWorker:
    """Claims durable investigation jobs and renews their leases while they execute."""

    def __init__(
        self,
        repository: SentinelRepository,
        service_factory: ServiceFactory,
        *,
        worker_id: str | None = None,
        lease_seconds: float = 60.0,
        poll_seconds: float = 1.0,
    ) -> None:
        self.repository = repository
        self.service_factory = service_factory
        self.worker_id = worker_id or f"worker-{secrets.token_hex(6)}"
        self.lease_seconds = lease_seconds
        self.poll_seconds = poll_seconds

    async def run_once(self) -> WorkItemRecord | None:
        item = await asyncio.to_thread(
            self.repository.claim_work,
            self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if item is None:
            return None
        WORK_ITEMS.labels(event="claimed").inc()
        stop_heartbeat = asyncio.Event()
        heartbeat = asyncio.create_task(self._heartbeat(item.id, stop_heartbeat))
        try:
            mode = self._mode(item.provider_mode)
            with span(
                "worker.investigation",
                parent_trace_id=item.parent_trace_id,
                work_item_id=item.id,
                incident_id=item.incident_id,
                worker_id=self.worker_id,
                attempt=item.attempts,
            ):
                state = await self.service_factory(mode).run_incident(item.incident_id)
        except asyncio.CancelledError:
            await self._stop_heartbeat(stop_heartbeat, heartbeat)
            raise
        except Exception as exc:
            await self._stop_heartbeat(stop_heartbeat, heartbeat)
            delay = min(60.0, float(2 ** max(0, item.attempts - 1)))
            failed = await asyncio.to_thread(
                self.repository.fail_work,
                item.id,
                self.worker_id,
                str(exc),
                retry_delay_seconds=delay,
            )
            if failed.status == "failed":
                await asyncio.to_thread(
                    self.repository.update_incident,
                    item.incident_id,
                    status="failed_system",
                )
                WORK_ITEMS.labels(event="failed").inc()
            else:
                WORK_ITEMS.labels(event="retried").inc()
                RETRIES.labels(component="worker", name="investigation").inc()
            ERRORS.labels(component="worker", code="investigation_failed").inc()
            await asyncio.to_thread(
                self.repository.add_audit,
                incident_id=item.incident_id,
                event_type="investigation_work_failed",
                actor=self.worker_id,
                allowed=False,
                details={
                    "work_item_id": item.id,
                    "attempt": item.attempts,
                    "will_retry": failed.status == "queued",
                    "error": str(exc)[:1_000],
                },
            )
            return failed
        await self._stop_heartbeat(stop_heartbeat, heartbeat)
        completed = await asyncio.to_thread(
            self.repository.complete_work,
            item.id,
            self.worker_id,
            execution_id=state.execution_id,
        )
        await asyncio.to_thread(
            self.repository.add_audit,
            incident_id=item.incident_id,
            event_type="investigation_work_completed",
            actor=self.worker_id,
            allowed=True,
            details={"work_item_id": item.id, "execution_id": state.execution_id},
        )
        WORK_ITEMS.labels(event="completed").inc()
        return completed

    async def run_forever(self, stop: asyncio.Event | None = None) -> None:
        stop_event = stop or asyncio.Event()
        while not stop_event.is_set():
            item = await self.run_once()
            if item is None:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=self.poll_seconds)

    async def _heartbeat(self, work_item_id: str, stop: asyncio.Event) -> None:
        interval = max(0.1, self.lease_seconds / 3)
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                await asyncio.to_thread(
                    self.repository.heartbeat_work,
                    work_item_id,
                    self.worker_id,
                    lease_seconds=self.lease_seconds,
                )

    @staticmethod
    async def _stop_heartbeat(stop: asyncio.Event, heartbeat: asyncio.Task[None]) -> None:
        stop.set()
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat

    @staticmethod
    def _mode(value: str) -> Literal["simulator", "live"]:
        if value not in {"simulator", "live"}:
            raise ValueError(f"unsupported tool provider mode: {value}")
        return cast(Literal["simulator", "live"], value)


def service_factory(
    repository: SentinelRepository,
    settings: Settings,
) -> ServiceFactory:
    budget = BudgetPolicy(
        max_runtime_seconds=settings.max_runtime_seconds,
        max_model_tokens=settings.max_model_tokens,
        max_tool_calls=settings.max_tool_calls,
        max_subagents=settings.max_subagents,
        max_identical_tool_calls=settings.max_identical_tool_calls,
        max_cost_usd=settings.max_cost_usd,
    )

    def build(mode: Literal["simulator", "live"]) -> InvestigationService:
        tools = ToolProviderConfig(
            mode=mode,
            namespace=settings.kubernetes_namespace,
            kubectl_context=settings.kubectl_context,
            prometheus_url=settings.prometheus_url,
            tempo_url=settings.tempo_url,
            git_repository_path=settings.resolved_git_repository_path,
            github_repository=settings.github_repository,
            github_token=settings.github_token,
        )
        return InvestigationService(
            repository,
            budget,
            build_model_router(settings.model_provider, settings.model_name),
            tools,
        )

    return build


async def main() -> None:
    settings = get_settings()
    configure_telemetry("sentinel-worker", settings.otlp_endpoint)
    repository = SentinelRepository(settings.database_url)
    worker = InvestigationWorker(
        repository,
        service_factory(repository, settings),
        lease_seconds=settings.worker_lease_seconds,
        poll_seconds=settings.worker_poll_seconds,
    )
    try:
        await worker.run_forever()
    finally:
        force_flush_telemetry()


def run() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())


if __name__ == "__main__":
    run()
