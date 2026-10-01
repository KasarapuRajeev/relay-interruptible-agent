"""Session-scoped task checkpoints for pause, switch, and resume behavior."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .plans import EvidenceRecord, PlanBranch
from .impact import classify_impact


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    intent: str
    slots: dict[str, Any] = field(default_factory=dict)
    status: str = "working"
    active_call_ids: list[str] = field(default_factory=list)
    grounded_results: list[dict[str, Any]] = field(default_factory=list)
    branches: list[PlanBranch] = field(default_factory=list)
    active_branch_id: str | None = None
    evidence: list[EvidenceRecord] = field(default_factory=list)

    def active_branch(self) -> PlanBranch | None:
        return next(
            (branch for branch in self.branches if branch.branch_id == self.active_branch_id),
            None,
        )

    def summary(self, *, active: bool = False) -> dict[str, Any]:
        branch = self.active_branch()
        active_step = next(
            (step for step in reversed(branch.steps) if step.status == "running"),
            None,
        ) if branch else None
        return {
            "task_id": self.task_id,
            "intent": self.intent,
            "status": self.status,
            "active": active,
            "branch_id": branch.branch_id if branch else None,
            "branch_number": branch.number if branch else 0,
            "request_text": branch.request_text if branch else "",
            "active_step": active_step.name if active_step else None,
            "slot_count": len(self.slots),
            "evidence_count": len(self.active_grounded_results()),
        }

    def start_branch(self, request_text: str) -> PlanBranch:
        current = self.active_branch()
        branch = (
            current.fork(request_text, self.slots)
            if current
            else PlanBranch.initial(request_text, self.slots)
        )
        self.branches.append(branch)
        self.active_branch_id = branch.branch_id
        return branch

    def add_evidence(
        self,
        *,
        call_id: str,
        source: str,
        content: dict[str, Any],
        depends_on: list[str],
        branch_id: str | None = None,
    ) -> EvidenceRecord:
        origin_branch_id = branch_id or self.active_branch_id or "unassigned"
        record = EvidenceRecord(
            evidence_id=str(uuid.uuid4()),
            task_id=self.task_id,
            origin_branch_id=origin_branch_id,
            call_id=call_id,
            source=source,
            content=dict(content),
            depends_on=sorted(set(depends_on)),
            valid_branch_ids=[origin_branch_id],
        )
        self.evidence.append(record)
        self.grounded_results.append(dict(content))
        return record

    def active_grounded_results(self) -> list[dict[str, Any]]:
        values = [
            {
                **record.content,
                "_evidence_id": record.evidence_id,
                "_source": record.source,
                "_origin_branch_id": record.origin_branch_id,
            }
            for record in self.evidence
            if record.is_valid_for(self.active_branch_id)
        ]
        return values if self.evidence else list(self.grounded_results)

    def reconcile_evidence(self) -> int:
        branch = self.active_branch()
        if branch is None:
            return 0
        invalidated = 0
        retained_results: list[dict[str, Any]] = []
        for record in self.evidence:
            if record.status == "invalidated":
                continue
            decision = classify_impact(
                target_id=record.evidence_id,
                target_type="evidence",
                dependencies=record.depends_on,
                context_diff=branch.context_diff,
            )
            branch.impact_decisions.append(decision.to_dict())
            if decision.action == "invalidate":
                record.status = "invalidated"
                record.invalidated_in_branch_id = branch.branch_id
                invalidated += 1
                continue
            record.status = "preserved"
            if branch.branch_id not in record.valid_branch_ids:
                record.valid_branch_ids.append(branch.branch_id)
            retained_results.append(dict(record.content))
        if self.evidence:
            self.grounded_results = retained_results
        return invalidated


@dataclass(slots=True)
class TaskManager:
    """Owns task checkpoints for one session only; it never persists across sessions."""

    tasks: dict[str, TaskRecord] = field(default_factory=dict)
    active_task_id: str | None = None

    def active(self) -> TaskRecord | None:
        return self.tasks.get(self.active_task_id) if self.active_task_id else None

    def activate(
        self,
        intent: str,
        slots: dict[str, Any],
        *,
        request_text: str = "",
        fork_branch: bool = False,
    ) -> tuple[TaskRecord, bool]:
        """Activate a matching paused task or create a new one.

        Returns the task and whether it was resumed from a checkpoint.
        """
        current = self.active()
        if current and current.intent == intent:
            current.slots.update(slots)
            current.status = "working"
            if fork_branch or current.active_branch() is None:
                current.start_branch(request_text)
            return current, False

        if current:
            current.status = "superseded"

        for task in reversed(list(self.tasks.values())):
            if task.status == "paused" and task.intent == intent:
                task.slots.update(slots)
                task.status = "working"
                self.active_task_id = task.task_id
                branch = task.active_branch()
                if branch:
                    branch.status = "active"
                return task, True

        task = TaskRecord(task_id=str(uuid.uuid4()), intent=intent, slots=dict(slots))
        task.start_branch(request_text)
        self.tasks[task.task_id] = task
        self.active_task_id = task.task_id
        return task, False

    def pause_active(self) -> TaskRecord | None:
        task = self.active()
        if task:
            task.status = "paused"
            task.active_call_ids = []
            branch = task.active_branch()
            if branch:
                branch.status = "paused"
            self.active_task_id = None
        return task

    def cancel_active(self) -> TaskRecord | None:
        task = self.active()
        if task:
            task.status = "cancelled"
            task.active_call_ids = []
            branch = task.active_branch()
            if branch:
                branch.status = "cancelled"
            self.active_task_id = None
        return task

    def complete_active(self, result: dict[str, Any] | None = None) -> TaskRecord | None:
        task = self.active()
        if task:
            task.status = "complete"
            task.active_call_ids = []
            branch = task.active_branch()
            if branch:
                branch.status = "completed"
            if result is not None:
                task.grounded_results.append(result)
        return task

    def invalidate_results_for_corrections(
        self, task: TaskRecord, corrected_slots: list[str]
    ) -> int:
        """Drop cached results whose recorded inputs conflict with corrected slots."""
        evidence_invalidated = task.reconcile_evidence()
        if task.evidence:
            return evidence_invalidated
        if not corrected_slots or not task.grounded_results:
            return 0
        retained: list[dict[str, Any]] = []
        invalidated = 0
        for result in task.grounded_results:
            conflicts = any(
                slot in result
                and slot in task.slots
                and result[slot] != task.slots[slot]
                for slot in corrected_slots
            )
            if conflicts:
                invalidated += 1
            else:
                retained.append(result)
        task.grounded_results = retained
        return invalidated

    def paused_task_ids(self) -> list[str]:
        return [task.task_id for task in self.tasks.values() if task.status == "paused"]

    def summaries(self) -> list[dict[str, Any]]:
        return [
            task.summary(active=task.task_id == self.active_task_id)
            for task in reversed(list(self.tasks.values()))
        ]
