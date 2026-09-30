"""Branch-aware plan records for explainable interruption recovery."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .impact import classify_impact


StepStatus = Literal[
    "queued", "running", "preserved", "cancelled", "invalidated", "completed", "failed"
]
BranchStatus = Literal["active", "superseded", "paused", "cancelled", "completed"]
EvidenceStatus = Literal["valid", "preserved", "invalidated"]


@dataclass(slots=True)
class ContextDiff:
    """Machine-readable explanation of what changed between two branches."""

    changed: dict[str, dict[str, Any]] = field(default_factory=dict)
    added: dict[str, Any] = field(default_factory=dict)
    removed: dict[str, Any] = field(default_factory=dict)
    preserved: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def between(cls, previous: dict[str, Any], current: dict[str, Any]) -> "ContextDiff":
        changed: dict[str, dict[str, Any]] = {}
        added: dict[str, Any] = {}
        removed: dict[str, Any] = {}
        preserved: dict[str, Any] = {}
        for key in previous.keys() | current.keys():
            if key not in previous:
                added[key] = current[key]
            elif key not in current:
                removed[key] = previous[key]
            elif previous[key] != current[key]:
                changed[key] = {"old": previous[key], "new": current[key]}
            else:
                preserved[key] = current[key]
        return cls(changed=changed, added=added, removed=removed, preserved=preserved)

    @property
    def affected_keys(self) -> set[str]:
        return set(self.changed) | set(self.added) | set(self.removed)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PlanStep:
    step_id: str
    branch_id: str
    name: str
    status: StepStatus = "queued"
    depends_on: list[str] = field(default_factory=list)
    tool_name: str | None = None
    call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvidenceRecord:
    """A tool result with provenance and context dependencies."""

    evidence_id: str
    task_id: str
    origin_branch_id: str
    call_id: str
    source: str
    content: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)
    status: EvidenceStatus = "valid"
    valid_branch_ids: list[str] = field(default_factory=list)
    invalidated_in_branch_id: str | None = None

    def is_valid_for(self, branch_id: str | None) -> bool:
        return bool(
            branch_id
            and self.status != "invalidated"
            and branch_id in self.valid_branch_ids
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PlanBranch:
    branch_id: str
    number: int
    request_text: str
    slots: dict[str, Any]
    parent_branch_id: str | None = None
    status: BranchStatus = "active"
    context_diff: ContextDiff = field(default_factory=ContextDiff)
    steps: list[PlanStep] = field(default_factory=list)
    impact_decisions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def initial(cls, request_text: str, slots: dict[str, Any]) -> "PlanBranch":
        return cls(
            branch_id=str(uuid.uuid4()),
            number=1,
            request_text=request_text,
            slots=dict(slots),
            context_diff=ContextDiff(added=dict(slots)),
        )

    def fork(self, request_text: str, slots: dict[str, Any]) -> "PlanBranch":
        self.status = "superseded"
        diff = ContextDiff.between(self.slots, slots)
        if request_text.strip() != self.request_text.strip():
            diff.changed["goal"] = {
                "old": self.request_text,
                "new": request_text,
            }
        preserved_steps: list[PlanStep] = []
        decisions: list[dict[str, Any]] = []
        for step in self.steps:
            decision = classify_impact(
                target_id=step.step_id,
                target_type="plan_step",
                dependencies=step.depends_on,
                context_diff=diff,
                active=step.status in {"queued", "running", "cancelled"},
            )
            decisions.append(decision.to_dict())
            if decision.action != "preserve" or step.status != "completed":
                if step.status == "completed" and decision.action == "invalidate":
                    step.status = "invalidated"
                continue
            preserved_steps.append(
                PlanStep(
                    step_id=str(uuid.uuid4()),
                    branch_id="",  # assigned after the child branch is created
                    name=step.name,
                    status="preserved",
                    depends_on=list(step.depends_on),
                    tool_name=step.tool_name,
                )
            )
        child = PlanBranch(
            branch_id=str(uuid.uuid4()),
            number=self.number + 1,
            request_text=request_text,
            slots=dict(slots),
            parent_branch_id=self.branch_id,
            context_diff=diff,
            steps=preserved_steps,
            impact_decisions=decisions,
        )
        for step in child.steps:
            step.branch_id = child.branch_id
        return child

    def add_tool_step(
        self, tool_name: str, call_id: str, arguments: dict[str, Any]
    ) -> PlanStep:
        step = PlanStep(
            step_id=str(uuid.uuid4()),
            branch_id=self.branch_id,
            name=tool_name.replace("_", " "),
            status="running",
            depends_on=sorted(arguments),
            tool_name=tool_name,
            call_id=call_id,
        )
        self.steps.append(step)
        return step

    def set_call_status(self, call_id: str, status: StepStatus) -> PlanStep | None:
        for step in reversed(self.steps):
            if step.call_id == call_id:
                step.status = status
                return step
        return None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return value
