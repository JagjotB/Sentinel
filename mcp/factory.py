from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from mcp.contracts import ToolServer
from mcp.git_server import GitToolServer
from mcp.git_server.live import LiveGitToolServer
from mcp.incidents_server import IncidentKnowledgeToolServer
from mcp.incidents_server.live import LiveIncidentKnowledgeToolServer
from mcp.kubernetes_server import KubernetesToolServer
from mcp.kubernetes_server.live import LiveKubernetesToolServer
from mcp.observability_server import ObservabilityToolServer
from mcp.observability_server.live import LiveObservabilityToolServer
from persistence.repository import SentinelRepository
from runtime.tool_registry import ToolRegistry
from simulator.engine import SimulationSnapshot


@dataclass(frozen=True)
class ToolProviderConfig:
    mode: Literal["simulator", "live"] = "simulator"
    namespace: str = "sentinel-demo"
    kubectl_context: str = ""
    prometheus_url: str = "http://localhost:9090"
    tempo_url: str = ""
    git_repository_path: Path = Path(".")
    github_repository: str = ""
    github_token: str = ""


def mount_investigation_tools(
    registry: ToolRegistry,
    repository: SentinelRepository,
    snapshot: SimulationSnapshot,
    config: ToolProviderConfig,
) -> None:
    servers: tuple[ToolServer, ...]
    if config.mode == "live":
        servers = (
            LiveKubernetesToolServer(
                namespace=config.namespace,
                kubectl_context=config.kubectl_context,
            ),
            LiveObservabilityToolServer(
                prometheus_url=config.prometheus_url,
                tempo_url=config.tempo_url,
                namespace=config.namespace,
            ),
            LiveGitToolServer(
                config.git_repository_path,
                github_repository=config.github_repository,
                github_token=config.github_token,
            ),
            LiveIncidentKnowledgeToolServer(repository),
        )
    else:
        servers = (
            KubernetesToolServer(snapshot),
            ObservabilityToolServer(snapshot),
            GitToolServer(snapshot),
            IncidentKnowledgeToolServer(snapshot),
        )
    for server in servers:
        registry.mount(server)
