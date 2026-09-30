"""Deterministic virtual-clock helpers for replayable evaluation traces."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .orchestrator import RelayAgent
from .protocol import Action, EventType, InputEvent


@dataclass(slots=True)
class VirtualClock:
    now_ms: int = 0

    def __call__(self) -> int:
        return self.now_ms

    def advance(self, milliseconds: int) -> None:
        if milliseconds < 0:
            raise ValueError("Virtual time cannot move backwards")
        self.now_ms += milliseconds


@dataclass(slots=True)
class ScenarioHarness:
    clock: VirtualClock = field(default_factory=VirtualClock)
    agent: RelayAgent = field(init=False)
    trace: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.agent = RelayAgent(clock=self.clock)

    async def start(self, manifest: list[dict[str, Any]] | None = None) -> None:
        if manifest is not None:
            self.agent.tools.load_manifest(manifest)
        await self.agent.start()

    async def send(
        self, kind: EventType, payload: dict[str, Any], *, after_ms: int = 0
    ) -> None:
        self.clock.advance(after_ms)
        event = InputEvent(str(uuid.uuid4()), kind, self.clock(), payload)
        event_record = asdict(event)
        event_record["type"] = event.type.value
        self.trace.append({"direction": "input", **event_record})
        await self.agent.submit(event)
        await asyncio.sleep(0)

    async def collect(self, count: int, timeout: float = 0.2) -> list[Action]:
        actions: list[Action] = []
        for _ in range(count):
            action = await self.agent.next_action(timeout)
            actions.append(action)
            self.trace.append({"direction": "output", **action.to_dict()})
        return actions
