from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

from mcp.contracts import (
    ErrorCode,
    PermissionClass,
    ToolContext,
    ToolFailure,
    ToolResult,
    ToolServer,
    ToolSpec,
    artifact,
)
from mcp.git_server.server import EmptyRequest
from mcp.schemas import DiffRequest, FileAtRevisionRequest, PatchRequest, PullRequestRequest
from simulator.faults.kubernetes import CommandRunner, SubprocessCommandRunner


class LiveGitToolServer(ToolServer):
    """Audited local Git adapter with optional GitHub pull-request reads."""

    def __init__(
        self,
        repository_root: Path,
        *,
        github_repository: str = "",
        github_token: str = "",
        runner: CommandRunner | None = None,
        http_transport: httpx.BaseTransport | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.repository_root = repository_root.resolve()
        self.github_repository = github_repository
        self.github_token = github_token
        self.runner = runner or SubprocessCommandRunner()
        self.http_transport = http_transport
        self.register(
            ToolSpec("get_recent_commits", EmptyRequest, PermissionClass.READ, self._commits)
        )
        self.register(ToolSpec("get_diff", DiffRequest, PermissionClass.READ, self._diff))
        self.register(
            ToolSpec("get_pull_request", PullRequestRequest, PermissionClass.READ, self._pr)
        )
        self.register(
            ToolSpec(
                "get_file_at_revision",
                FileAtRevisionRequest,
                PermissionClass.READ,
                self._file,
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
            summary=f"Live source-control result for {name.replace('_', ' ')}",
            payload=result.data,
            raw=f"git://{self.repository_root.as_posix()}/{name}",
        )
        return result.model_copy(update={"evidence": [item]})

    def _commits(self, _: EmptyRequest, __: ToolContext) -> dict[str, Any]:
        output = self._git(
            "log",
            "-5",
            "--date=iso-strict",
            "--pretty=format:%H%x1f%cI%x1f%an%x1f%s",
        )
        commits = []
        for line in output.splitlines():
            fields = line.split("\x1f", maxsplit=3)
            if len(fields) == 4:
                commits.append(
                    {
                        "revision": fields[0],
                        "committed_at": fields[1],
                        "author": fields[2],
                        "subject": fields[3],
                    }
                )
        return {"commits": commits}

    def _diff(self, request: DiffRequest, _: ToolContext) -> dict[str, Any]:
        return {
            "base": request.base,
            "head": request.head,
            "diff": self._git("diff", "--no-ext-diff", request.base, request.head, "--"),
        }

    def _pr(self, request: PullRequestRequest, _: ToolContext) -> dict[str, Any]:
        if not self.github_repository:
            raise ToolFailure(
                ErrorCode.PROVIDER_UNAVAILABLE,
                "GitHub repository is not configured",
                retryable=False,
            )
        headers = {"Accept": "application/vnd.github+json"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        url = f"https://api.github.com/repos/{self.github_repository}/pulls/{request.number}"
        try:
            with httpx.Client(transport=self.http_transport, timeout=10) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolFailure(
                ErrorCode.PROVIDER_UNAVAILABLE,
                "GitHub pull-request lookup failed",
                retryable=True,
            ) from exc
        if not isinstance(payload, dict):
            raise ToolFailure(ErrorCode.INTERNAL, "GitHub response was not an object")
        return {
            "number": payload.get("number"),
            "title": payload.get("title"),
            "state": payload.get("state"),
            "merged": payload.get("merged"),
            "html_url": payload.get("html_url"),
            "base": payload.get("base"),
            "head": payload.get("head"),
        }

    def _file(self, request: FileAtRevisionRequest, _: ToolContext) -> dict[str, Any]:
        return {
            "path": request.path,
            "revision": request.revision,
            "content": self._git("show", f"{request.revision}:{request.path}"),
        }

    def _patch(self, request: PatchRequest, context: ToolContext) -> dict[str, Any]:
        proposal_dir = self.repository_root / ".sentinel" / "proposals"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(
            json.dumps(
                {
                    "incident": context.incident_id,
                    "title": request.title,
                    "path": request.path,
                    "patch": request.patch,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()[:16]
        destination = proposal_dir / f"{digest}.patch"
        destination.write_text(request.patch, encoding="utf-8")
        return {
            "artifact": str(destination.relative_to(self.repository_root).as_posix()),
            "sha256": hashlib.sha256(request.patch.encode()).hexdigest(),
            "title": request.title,
            "target_path": request.path,
            "created": True,
        }

    def _git(self, *arguments: str) -> str:
        args = ["git", "-C", str(self.repository_root), *arguments]
        result = self.runner.run(args, timeout_seconds=10)
        if result.returncode != 0:
            raise ToolFailure(
                ErrorCode.PROVIDER_UNAVAILABLE,
                result.stderr.strip() or "git command failed",
                retryable=False,
            )
        return result.stdout
