from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


class WorkingMemory:
    def __init__(self, max_items_per_execution: int = 100) -> None:
        self._items: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=max_items_per_execution)
        )

    def append(self, execution_id: str, item: dict[str, Any]) -> None:
        self._items[execution_id].append(dict(item))

    def read(self, execution_id: str) -> list[dict[str, Any]]:
        return list(self._items[execution_id])

    def clear(self, execution_id: str) -> None:
        self._items.pop(execution_id, None)

    def restore(self, execution_id: str, items: list[dict[str, Any]]) -> None:
        self.clear(execution_id)
        for item in items:
            self.append(execution_id, item)
