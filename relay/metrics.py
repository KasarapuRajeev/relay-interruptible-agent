"""Session-scoped measurements for judge-visible interruption reliability."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class RuntimeMetrics:
    acknowledgement_latency_ms: int = 0
    last_cancellation_latency_ms: int = 0
    interruptions: int = 0
    replans: int = 0
    cancelled_calls: int = 0
    stale_results_rejected: int = 0
    evidence_preserved: int = 0
    evidence_invalidated: int = 0
    task_switches: int = 0
    tasks_resumed: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)
