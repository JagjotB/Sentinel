from __future__ import annotations

import re
from pathlib import PurePosixPath


class SandboxViolation(ValueError):
    pass


SHELL_TOKENS = re.compile(
    r"(?i)(\brm\s+-rf\b|\bcurl\b|\bwget\b|powershell|cmd\.exe|`|\$\(|;|&&|\|\|)"
)


class ProposalSandbox:
    def __init__(
        self, allowed_roots: tuple[str, ...] = ("deploy", "config", "infrastructure")
    ) -> None:
        self.allowed_roots = allowed_roots

    def validate_path(self, path: str) -> str:
        normalized = PurePosixPath(path.replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts:
            raise SandboxViolation("path escapes the proposal workspace")
        if not normalized.parts or normalized.parts[0] not in self.allowed_roots:
            raise SandboxViolation("path is outside the proposal allowlist")
        return normalized.as_posix()

    def validate_patch(self, patch: str) -> None:
        if len(patch) > 50_000:
            raise SandboxViolation("patch exceeds size limit")
        if SHELL_TOKENS.search(patch):
            raise SandboxViolation("patch contains forbidden command syntax")
