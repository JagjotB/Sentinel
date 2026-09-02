from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from mcp.contracts import PermissionClass, ToolContext, ToolResult, ToolServer, ToolSpec, artifact
from mcp.schemas import DiffRequest, FileAtRevisionRequest, PatchRequest, PullRequestRequest
from simulator.engine import SimulationSnapshot


class EmptyRequest(BaseModel):
    pass


class GitToolServer(ToolServer):
    def __init__(self, snapshot: SimulationSnapshot, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.snapshot = snapshot
        self.register(
            ToolSpec("get_recent_commits", EmptyRequest, PermissionClass.READ, self._commits)
        )
        self.register(ToolSpec("get_diff", DiffRequest, PermissionClass.READ, self._diff))
        self.register(
            ToolSpec("get_pull_request", PullRequestRequest, PermissionClass.READ, self._pr)
        )
        self.register(
            ToolSpec(
                "get_file_at_revision", FileAtRevisionRequest, PermissionClass.READ, self._file
            )
        )
        self.register(
            ToolSpec(
                "create_proposed_patch_or_pr",
                PatchRequest,
                PermissionClass.LOW_RISK_WRITE,
                self._patch,
            )
        )

    async def call(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        result = await super().call(name, arguments, context)
        item = artifact(
            tool=name,
            source="git",
            kind="change",
            summary=f"Source-control result for {name.replace('_', ' ')}",
            payload=result.data,
            raw=f"simulator://{self.snapshot.scenario.id}/git/{name}",
        )
        return result.model_copy(update={"evidence": [item]})

    def _commits(self, _: EmptyRequest, __: ToolContext) -> dict[str, Any]:
        return {"commits": [self.snapshot.deployment]}

    def _diff(self, _: DiffRequest, __: ToolContext) -> dict[str, Any]:
        return {
            "diff": self.snapshot.deployment["diff"],
            "revision": self.snapshot.deployment["revision"],
        }

    def _pr(self, request: PullRequestRequest, _: ToolContext) -> dict[str, Any]:
        return {"number": request.number, "title": self.snapshot.scenario.title, "merged": True}

    def _file(self, request: FileAtRevisionRequest, _: ToolContext) -> dict[str, Any]:
        return {
            "path": request.path,
            "revision": request.revision,
            "content": self.snapshot.deployment["diff"],
        }

    def _patch(self, request: PatchRequest, _: ToolContext) -> dict[str, Any]:
        return {
            "artifact": f"proposals/{request.path}.patch",
            "title": request.title,
            "patch": request.patch,
        }
