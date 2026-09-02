from __future__ import annotations

import hashlib
import json

from persistence.repository import SentinelRepository
from runtime.state import RuntimeState


class CheckpointCorrupt(RuntimeError):
    pass


class CheckpointStore:
    def __init__(self, repository: SentinelRepository) -> None:
        self.repository = repository

    def save(self, state: RuntimeState) -> RuntimeState:
        latest = self.repository.latest_checkpoint(state.execution_id)
        sequence = 1 if latest is None else latest.sequence + 1
        updated = state.model_copy(update={"checkpoint_sequence": sequence})
        payload = updated.model_dump(mode="json")
        self.repository.add_checkpoint(
            execution_id=state.execution_id,
            sequence=sequence,
            state=payload,
            checksum=self._checksum(payload),
        )
        return updated

    def load(self, execution_id: str) -> RuntimeState | None:
        checkpoint = self.repository.latest_checkpoint(execution_id)
        if checkpoint is None:
            return None
        if checkpoint.checksum != self._checksum(checkpoint.state):
            raise CheckpointCorrupt(f"invalid checkpoint checksum: {checkpoint.id}")
        return RuntimeState.model_validate(checkpoint.state)

    @staticmethod
    def _checksum(payload: dict[str, object]) -> str:
        value = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(value.encode()).hexdigest()
