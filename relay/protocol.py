"""JSON-safe input/output protocol for the two-queue evaluation contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    TRANSCRIPT_CHUNK = "transcript_chunk"
    INTERRUPTION = "interruption"
    TOOL_RESULT = "tool_result"
    AUDIO = "audio"
    VIDEO_FRAME = "video_frame"
    SHUTDOWN = "shutdown"


class ActionType(str, Enum):
    SPOKEN = "spoken"
    TOOL_CALL = "tool_call"
    CANCEL_CALL = "cancel_call"
    CLARIFICATION = "clarification"
    FINAL = "final"
    TRACE = "trace"


@dataclass(slots=True)
class InputEvent:
    event_id: str
    type: EventType
    timestamp_ms: int
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "InputEvent":
        return cls(
            event_id=str(value["event_id"]),
            type=EventType(value["type"]),
            timestamp_ms=int(value["timestamp_ms"]),
            payload=dict(value.get("payload", {})),
        )


@dataclass(slots=True)
class Action:
    action_id: str
    type: ActionType
    timestamp_ms: int
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["type"] = self.type.value
        return value


@dataclass(slots=True)
class StateSnapshot:
    version: int = 0
    intent: str = "unknown"
    slots: dict[str, Any] = field(default_factory=dict)
    active_call_ids: list[str] = field(default_factory=list)
    status: str = "idle"
    task_id: str | None = None
    paused_task_ids: list[str] = field(default_factory=list)
    branch_id: str | None = None
    branch_number: int = 0
    context_diff: dict[str, Any] = field(default_factory=dict)
    plan_steps: list[dict[str, Any]] = field(default_factory=list)
    plan_branches: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    memory_turn_count: int = 0
    memory_turn_limit: int = 40

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
