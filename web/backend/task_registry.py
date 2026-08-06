"""In-process verification task registry with TTL."""
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from src.config import Config


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class TaskState:
    message_id: str
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class TaskRegistry:
    def __init__(self, ttl_sec: int = None):
        self.ttl_sec = ttl_sec or Config.VERIFICATION_WS_TTL_SEC
        self._tasks: Dict[str, TaskState] = {}

    def _cleanup(self) -> None:
        now = time.time()
        expired = [
            mid
            for mid, t in self._tasks.items()
            if now - t.updated_at > self.ttl_sec
        ]
        for mid in expired:
            del self._tasks[mid]

    def create(self, message_id: str) -> TaskState:
        self._cleanup()
        state = TaskState(message_id=message_id)
        self._tasks[message_id] = state
        return state

    def get(self, message_id: str) -> Optional[TaskState]:
        self._cleanup()
        return self._tasks.get(message_id)

    def set_running(self, message_id: str) -> None:
        t = self._tasks.get(message_id)
        if t:
            t.status = TaskStatus.RUNNING
            t.updated_at = time.time()

    def set_done(self, message_id: str, result: Dict[str, Any]) -> None:
        t = self._tasks.get(message_id)
        if t:
            t.status = TaskStatus.DONE
            t.result = result
            t.updated_at = time.time()

    def set_error(self, message_id: str, error: str) -> None:
        t = self._tasks.get(message_id)
        if t:
            t.status = TaskStatus.ERROR
            t.error = error
            t.updated_at = time.time()


_registry = TaskRegistry()


def get_task_registry() -> TaskRegistry:
    return _registry
