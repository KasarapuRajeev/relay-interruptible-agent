"""Fast/slow-path coordinator for interruptible agent execution."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from typing import Any

from .intent import IntentUpdate, understand
from .models import ModelAdapter, ModelContext
from .metrics import RuntimeMetrics
from .protocol import Action, ActionType, EventType, InputEvent, StateSnapshot
from .security import sanitize_error
from .tasks import TaskManager
from .tools import ToolCallRecord, ToolRegistry


Clock = Callable[[], int]


def system_clock_ms() -> int:
    return time.monotonic_ns() // 1_000_000


def grounded_fallback_text(results: list[dict[str, Any]]) -> str | None:
    """Render accepted tool evidence when provider-side synthesis is unavailable."""

    if not results:
        return None
    clean_results = [
        {key: value for key, value in result.items() if not key.startswith("_")}
        for result in results
        if isinstance(result, dict)
    ]
    if not clean_results:
        return None

    if len(clean_results) == 1:
        result = clean_results[0]
        summary = str(result.get("summary", "")).strip()
        sources = result.get("sources")
        if summary and not sources:
            return summary
        if summary and isinstance(sources, list) and not any(
            isinstance(source, dict) and source.get("extract") for source in sources
        ):
            links = [
                f"{source.get('title', 'Source')}: {source.get('url')}"
                for source in sources[:4]
                if isinstance(source, dict) and source.get("url")
            ]
            return "\n\n".join([summary, "Sources:\n" + "\n".join(links)]) if links else summary

    lines = [
        "Relay completed the live research and preserved the grounded evidence. "
        "The language provider was unavailable for the final synthesis, so here is "
        "the verified evidence directly:"
    ]
    source_count = 0
    for result in clean_results:
        aspect = str(result.get("aspect") or result.get("topic") or "Evidence").strip()
        summary = str(result.get("summary", "")).strip()
        lines.append(f"\n{aspect.title()}")
        if summary:
            lines.append(summary)
        sources = result.get("sources")
        if not isinstance(sources, list):
            continue
        for source in sources:
            if source_count >= 8 or not isinstance(source, dict):
                break
            title = str(source.get("title", "Source")).strip()
            url = str(source.get("url", "")).strip()
            extract = " ".join(str(source.get("extract", "")).split())
            if len(extract) > 420:
                extract = extract[:417].rstrip() + "..."
            detail = f"- {title}"
            if extract:
                detail += f": {extract}"
            if url:
                detail += f" ({url})"
            lines.append(detail)
            source_count += 1
    rendered = "\n".join(lines).strip()
    return rendered[:7000] if rendered else None


class RelayAgent:
    """Consumes timestamped events and emits structured actions on separate queues."""

    def __init__(
        self,
        *,
        clock: Clock = system_clock_ms,
        tool_timeout_seconds: float = 10.0,
        model: ModelAdapter | None = None,
        memory_turn_limit: int = 40,
    ) -> None:
        self.input_queue: asyncio.Queue[InputEvent] = asyncio.Queue()
        self.output_queue: asyncio.Queue[Action] = asyncio.Queue()
        self.clock = clock
        self.snapshot = StateSnapshot()
        self.tasks = TaskManager()
        self.tools = ToolRegistry()
        self.model = model
        self.tool_timeout_seconds = tool_timeout_seconds
        self._runner: asyncio.Task[None] | None = None
        self._slow_task: asyncio.Task[None] | None = None
        self._partial_transcript = ""
        self._active_calls: dict[str, ToolCallRecord] = {}
        self._timeout_tasks: dict[str, asyncio.Task[None]] = {}
        self._task_generation = 0
        self._latest_request_text = ""
        self.metrics = RuntimeMetrics()
        self.memory_turn_limit = max(4, memory_turn_limit)
        self._conversation_history: list[dict[str, Any]] = []
        self.snapshot.memory_turn_limit = self.memory_turn_limit

    async def start(self) -> None:
        if self._runner is None:
            self._runner = asyncio.create_task(self._event_loop())

    async def close(self) -> None:
        await self.submit(
            InputEvent(str(uuid.uuid4()), EventType.SHUTDOWN, self.clock(), {})
        )
        if self._runner:
            await self._runner

    async def submit(self, event: InputEvent | dict[str, Any]) -> None:
        if isinstance(event, dict):
            event = InputEvent.from_dict(event)
        await self.input_queue.put(event)

    async def next_action(self, timeout: float = 1.0) -> Action:
        return await asyncio.wait_for(self.output_queue.get(), timeout)

    async def _emit(self, kind: ActionType, **payload: Any) -> None:
        text = str(payload.get("text", "")).strip()
        should_remember = kind in {ActionType.FINAL, ActionType.CLARIFICATION} or (
            kind is ActionType.SPOKEN
            and not payload.get("acknowledgement")
            and bool(text)
        )
        if should_remember:
            self._remember_turn("assistant", text, kind.value)
        if isinstance(payload.get("state_snapshot"), dict):
            state_snapshot = dict(payload["state_snapshot"])
            state_snapshot["conversation_history"] = list(
                self.snapshot.conversation_history
            )
            state_snapshot["memory_turn_count"] = self.snapshot.memory_turn_count
            state_snapshot["memory_turn_limit"] = self.snapshot.memory_turn_limit
            payload["state_snapshot"] = state_snapshot
        await self.output_queue.put(
            Action(str(uuid.uuid4()), kind, self.clock(), payload)
        )

    def _remember_turn(self, role: str, text: str, kind: str) -> None:
        if not text:
            return
        self._conversation_history.append(
            {
                "turn_id": str(uuid.uuid4()),
                "role": role,
                "text": text,
                "kind": kind,
                "timestamp_ms": self.clock(),
            }
        )
        if len(self._conversation_history) > self.memory_turn_limit:
            del self._conversation_history[
                : len(self._conversation_history) - self.memory_turn_limit
            ]
        self.snapshot.conversation_history = [
            dict(turn) for turn in self._conversation_history
        ]
        self.snapshot.memory_turn_count = len(self._conversation_history)

    async def _event_loop(self) -> None:
        while True:
            event = await self.input_queue.get()
            if event.type is EventType.SHUTDOWN:
                await self._cancel_active("session_shutdown")
                return
            if event.type is EventType.TRANSCRIPT_CHUNK:
                await self._on_transcript(event)
            elif event.type is EventType.INTERRUPTION:
                await self._on_final_utterance(str(event.payload.get("text", "")), event)
            elif event.type is EventType.TOOL_RESULT:
                await self._on_tool_result(event)
            elif event.type in (EventType.AUDIO, EventType.VIDEO_FRAME):
                await self._emit(
                    ActionType.TRACE,
                    name="multimodal_input_buffered",
                    source_event_id=event.event_id,
                    modality=event.type.value,
                )

    async def _on_transcript(self, event: InputEvent) -> None:
        text = str(event.payload.get("text", ""))
        self._partial_transcript = text
        if not event.payload.get("end_of_turn", False):
            if len(text.split()) >= 3:
                await self._emit(
                    ActionType.TRACE,
                    name="speculative_intent_started",
                    source_event_id=event.event_id,
                    partial_text=text,
                )
            return
        self._partial_transcript = ""
        await self._on_final_utterance(text, event)

    async def _on_final_utterance(self, text: str, event: InputEvent) -> None:
        received_ms = event.timestamp_ms
        self._latest_request_text = text
        self._remember_turn("user", text.strip(), "message")
        update = understand(text, self.snapshot.intent, self.snapshot.slots)
        had_active_work = bool(self._active_calls) or (
            self._slow_task is not None and not self._slow_task.done()
        )

        if had_active_work:
            self.metrics.interruptions += 1
            await self._emit(
                ActionType.TRACE,
                name="interruption_detected",
                source_event_id=event.event_id,
                intent=update.intent,
                corrected_slots=update.corrected_slots,
            )
            await self._cancel_active("superseded_by_user")
            self.metrics.last_cancellation_latency_ms = max(0, self.clock() - received_ms)

        if update.is_cancel:
            cancelled = self.tasks.cancel_active()
            self._sync_snapshot()
            self.snapshot.status = "cancelled"
            self.snapshot.version += 1
            await self._emit(
                ActionType.SPOKEN,
                text="Stopped. The active work has been cancelled.",
                task_id=cancelled.task_id if cancelled else None,
                state_snapshot=self.snapshot.to_dict(),
            )
            return

        if update.is_pause:
            paused = self.tasks.pause_active()
            self._sync_snapshot()
            self.snapshot.status = "paused"
            self.snapshot.version += 1
            await self._emit(
                ActionType.SPOKEN,
                text="Paused. I preserved the current session state.",
                task_id=paused.task_id if paused else None,
                state_snapshot=self.snapshot.to_dict(),
            )
            return

        previous_intent = self.snapshot.intent
        task, resumed, invalidated_results = self._apply_update(update, text, had_active_work)
        if previous_intent not in {"unknown", update.intent}:
            self.metrics.task_switches += 1
        if resumed:
            self.metrics.tasks_resumed += 1
        if had_active_work or update.corrected_slots:
            self.metrics.replans += 1
        self.metrics.evidence_invalidated += invalidated_results
        self.metrics.evidence_preserved = sum(
            1 for record in task.evidence if record.status == "preserved"
        )
        if invalidated_results:
            await self._emit(
                ActionType.TRACE,
                name="grounded_results_invalidated",
                count=invalidated_results,
                corrected_slots=update.corrected_slots,
                task_id=task.task_id,
            )
        acknowledgement = (
            "Understood. I am applying that correction and replanning."
            if update.corrected_slots
            else "Resuming the saved task from its session checkpoint."
            if resumed
            else "Understood. I am working on that now; you can interrupt me at any time."
        )
        self.metrics.acknowledgement_latency_ms = max(0, self.clock() - received_ms)
        self._sync_snapshot()
        await self._emit(
            ActionType.SPOKEN,
            text=acknowledgement,
            acknowledgement=True,
            interruptible=True,
            source_event_id=event.event_id,
            task_id=task.task_id,
            state_snapshot=self.snapshot.to_dict(),
        )

        generation = self._task_generation = self._task_generation + 1
        self._slow_task = asyncio.create_task(self._run_slow_path(generation))

    def _apply_update(
        self, update: IntentUpdate, request_text: str, had_active_work: bool
    ):
        current = self.tasks.active()
        should_fork = bool(
            current
            and current.intent == update.intent
            and (
                had_active_work
                or update.corrected_slots
                or current.status == "complete"
            )
        )
        task, resumed = self.tasks.activate(
            update.intent,
            update.slots,
            request_text=request_text,
            fork_branch=should_fork,
        )
        invalidated_results = self.tasks.invalidate_results_for_corrections(
            task, update.corrected_slots
        )
        self._sync_snapshot()
        self.snapshot.version += 1
        self.snapshot.status = "working"
        return task, resumed, invalidated_results

    def _sync_snapshot(self) -> None:
        task = self.tasks.active()
        if task:
            self.snapshot.intent = task.intent
            self.snapshot.slots = dict(task.slots)
            self.snapshot.task_id = task.task_id
            self.snapshot.active_call_ids = list(task.active_call_ids)
            self.snapshot.status = task.status
            branch = task.active_branch()
            self.snapshot.branch_id = branch.branch_id if branch else None
            self.snapshot.branch_number = branch.number if branch else 0
            self.snapshot.context_diff = (
                branch.context_diff.to_dict() if branch else {}
            )
            self.snapshot.plan_steps = (
                [step.to_dict() for step in branch.steps] if branch else []
            )
            self.snapshot.plan_branches = [branch.to_dict() for branch in task.branches]
            self.snapshot.evidence = [record.to_dict() for record in task.evidence]
        else:
            self.snapshot.task_id = None
            self.snapshot.active_call_ids = []
            self.snapshot.branch_id = None
            self.snapshot.branch_number = 0
            self.snapshot.context_diff = {}
            self.snapshot.plan_steps = []
            self.snapshot.plan_branches = []
            self.snapshot.evidence = []
        self.snapshot.paused_task_ids = self.tasks.paused_task_ids()
        self.snapshot.metrics = self.metrics.to_dict()
        self.snapshot.tasks = self.tasks.summaries()

    async def _run_slow_path(
        self, generation: int, *, allow_grounded_fallback: bool = False
    ) -> None:
        try:
            missing = self._missing_required_slot()
            if missing:
                self.snapshot.status = "awaiting_clarification"
                await self._emit(
                    ActionType.CLARIFICATION,
                    text=f"What {missing.replace('_', ' ')} should I use?",
                    missing_slot=missing,
                    state_snapshot=self.snapshot.to_dict(),
                )
                return

            if self.model is not None:
                active_task = self.tasks.active()
                context = ModelContext(
                    task_id=self.snapshot.task_id or "unassigned",
                    intent=self.snapshot.intent,
                    slots=dict(self.snapshot.slots),
                    available_tools=[
                        {
                            "name": definition.name,
                            "description": definition.description,
                            "parameters": definition.parameters,
                            "state_modifying": definition.state_modifying,
                        }
                        for definition in self.tools.definitions.values()
                    ],
                    grounded_results=(
                        active_task.active_grounded_results() if active_task else []
                    ),
                    request_text=self._latest_request_text,
                    conversation_history=[
                        dict(turn) for turn in self._conversation_history
                    ],
                )
                decision = await self.model.decide(context)
                if generation != self._task_generation:
                    return
                if decision.kind == "clarification":
                    self.snapshot.status = "awaiting_clarification"
                    await self._emit(
                        ActionType.CLARIFICATION,
                        text=decision.text or "Could you clarify your request?",
                        state_snapshot=self.snapshot.to_dict(),
                    )
                    return
                if decision.kind == "final":
                    self.tasks.complete_active()
                    self._sync_snapshot()
                    self.snapshot.status = "complete"
                    await self._emit(
                        ActionType.FINAL,
                        text=decision.text,
                        state_snapshot=self.snapshot.to_dict(),
                    )
                    return
                tool_name = decision.tool_name or ""
                arguments = decision.arguments
            else:
                tool_name, arguments = self._select_tool()
            if tool_name not in self.tools.definitions:
                self.snapshot.status = "complete"
                await self._emit(
                    ActionType.FINAL,
                    text="The request is understood and the session state is ready for a domain tool.",
                    state_snapshot=self.snapshot.to_dict(),
                )
                return

            await self._start_tool_call(tool_name, arguments)
        except (KeyError, ValueError) as error:
            self.snapshot.status = "error"
            await self._emit(
                ActionType.CLARIFICATION,
                text="I cannot run that tool until its inputs are valid.",
                error=sanitize_error(error),
                state_snapshot=self.snapshot.to_dict(),
            )
        except Exception as error:
            active_task = self.tasks.active()
            fallback = (
                grounded_fallback_text(
                    active_task.active_grounded_results() if active_task else []
                )
                if allow_grounded_fallback
                else None
            )
            if fallback:
                completed = self.tasks.complete_active()
                self._sync_snapshot()
                self.snapshot.status = "complete"
                self.snapshot.version += 1
                await self._emit(
                    ActionType.FINAL,
                    text=fallback,
                    task_id=completed.task_id if completed else None,
                    provider_fallback=True,
                    error_type=type(error).__name__,
                    error_code=getattr(error, "error_code", None),
                    status_code=getattr(error, "status_code", None),
                    state_snapshot=self.snapshot.to_dict(),
                )
                return
            self.snapshot.status = "error"
            user_message = getattr(
                error,
                "user_message",
                "The reasoning provider is temporarily unavailable. Please try again.",
            )
            await self._emit(
                ActionType.CLARIFICATION,
                text=user_message,
                error_type=type(error).__name__,
                error_code=getattr(error, "error_code", None),
                status_code=getattr(error, "status_code", None),
                state_snapshot=self.snapshot.to_dict(),
            )
        except asyncio.CancelledError:
            raise
        finally:
            if generation != self._task_generation:
                return

    def _missing_required_slot(self) -> str | None:
        required = {
            "travel_planning": ("destination",),
            "study_planning": ("subject",),
        }.get(self.snapshot.intent, ())
        return next((slot for slot in required if slot not in self.snapshot.slots), None)

    def _select_tool(self) -> tuple[str, dict[str, Any]]:
        if self.snapshot.intent == "travel_planning":
            return "search_travel", dict(self.snapshot.slots)
        if self.snapshot.intent == "study_planning":
            return "build_study_plan", dict(self.snapshot.slots)
        return "general_assistant", dict(self.snapshot.slots)

    async def _start_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        attempt: int = 1,
        idempotency_key: str | None = None,
    ) -> ToolCallRecord:
        self.tools.validate_arguments(tool_name, arguments)
        if tool_name == "parallel_research" and not arguments.get("aspect"):
            calls = []
            for aspect in ("overview", "applications", "limitations and risks"):
                calls.append(
                    await self._start_tool_call(
                        tool_name,
                        {**arguments, "aspect": aspect},
                        attempt=attempt,
                        idempotency_key=idempotency_key,
                    )
                )
            return calls[-1]
        definition = self.tools.get(tool_name)
        task_id = self.snapshot.task_id or "unassigned"
        if definition.state_modifying:
            idempotency_key = idempotency_key or f"{task_id}:{tool_name}"
            if not self.tools.reserve_side_effect(tool_name, idempotency_key):
                raise ValueError("Duplicate state-changing tool call blocked")

        record = ToolCallRecord(
            call_id=str(uuid.uuid4()),
            task_id=task_id,
            tool_name=tool_name,
            arguments=dict(arguments),
            attempt=attempt,
            idempotency_key=idempotency_key,
            branch_id=self.snapshot.branch_id,
        )
        self._active_calls[record.call_id] = record
        active_task = self.tasks.active()
        if active_task:
            active_task.active_call_ids.append(record.call_id)
            branch = active_task.active_branch()
            if branch:
                branch.add_tool_step(record.tool_name, record.call_id, record.arguments)
        self._sync_snapshot()
        self.snapshot.active_call_ids = list(self._active_calls)
        await self._emit(
            ActionType.TOOL_CALL,
            call_id=record.call_id,
            tool_name=record.tool_name,
            arguments=record.arguments,
            attempt=record.attempt,
            idempotency_key=record.idempotency_key,
            task_id=record.task_id,
            branch_id=record.branch_id,
            state_snapshot=self.snapshot.to_dict(),
        )
        self._timeout_tasks[record.call_id] = asyncio.create_task(
            self._watch_tool_timeout(record.call_id)
        )
        return record

    async def _watch_tool_timeout(self, call_id: str) -> None:
        try:
            await asyncio.sleep(self.tool_timeout_seconds)
            active_task = self.tasks.active()
            branch = active_task.active_branch() if active_task else None
            if branch:
                branch.set_call_status(call_id, "failed")
            record = self._remove_active_call(call_id)
            if record is None:
                return
            await self._emit(
                ActionType.CANCEL_CALL,
                call_id=call_id,
                tool_name=record.tool_name,
                reason="timeout",
            )
            if self.tools.can_retry(record.tool_name, record.attempt):
                await self._emit(
                    ActionType.TRACE,
                    name="tool_retry_scheduled",
                    previous_call_id=call_id,
                    next_attempt=record.attempt + 1,
                )
                await self._start_tool_call(
                    record.tool_name,
                    record.arguments,
                    attempt=record.attempt + 1,
                    idempotency_key=record.idempotency_key,
                )
            else:
                self.snapshot.status = "error"
                await self._emit(
                    ActionType.CLARIFICATION,
                    text="The tool did not respond in time. Please try again.",
                    failed_call_id=call_id,
                    state_snapshot=self.snapshot.to_dict(),
                )
        except asyncio.CancelledError:
            return

    def _remove_active_call(self, call_id: str) -> ToolCallRecord | None:
        record = self._active_calls.pop(call_id, None)
        timeout_task = self._timeout_tasks.pop(call_id, None)
        current_task = asyncio.current_task()
        if timeout_task and timeout_task is not current_task:
            timeout_task.cancel()
        active_task = self.tasks.active()
        if active_task and call_id in active_task.active_call_ids:
            active_task.active_call_ids.remove(call_id)
        self.snapshot.active_call_ids = list(self._active_calls)
        return record

    async def _cancel_active(self, reason: str) -> None:
        self._task_generation += 1
        reasoning_was_active = bool(self._slow_task and not self._slow_task.done())
        if reasoning_was_active and self._slow_task:
            self._slow_task.cancel()
            await self._emit(
                ActionType.TRACE,
                name="reasoning_cancelled",
                reason=reason,
            )
        for call_id, record in list(self._active_calls.items()):
            active_task = self.tasks.active()
            branch = active_task.active_branch() if active_task else None
            if branch:
                branch.set_call_status(call_id, "cancelled")
            self.metrics.cancelled_calls += 1
            await self._emit(
                ActionType.CANCEL_CALL,
                call_id=call_id,
                tool_name=record.tool_name,
                reason=reason,
                branch_id=record.branch_id,
            )
            timeout_task = self._timeout_tasks.pop(call_id, None)
            if timeout_task:
                timeout_task.cancel()
        self._active_calls.clear()
        active_task = self.tasks.active()
        if active_task:
            active_task.active_call_ids = []
        self._sync_snapshot()

    async def _on_tool_result(self, event: InputEvent) -> None:
        call_id = str(event.payload.get("call_id", ""))
        if call_id not in self._active_calls:
            self.metrics.stale_results_rejected += 1
            self._sync_snapshot()
            await self._emit(
                ActionType.TRACE,
                name="stale_tool_result_dropped",
                call_id=call_id,
                state_snapshot=self.snapshot.to_dict(),
            )
            return
        record = self._remove_active_call(call_id)
        if record is None:
            return

        if event.payload.get("error"):
            active_task = self.tasks.active()
            branch = active_task.active_branch() if active_task else None
            if branch:
                branch.set_call_status(call_id, "failed")
            if self.tools.can_retry(record.tool_name, record.attempt):
                await self._emit(
                    ActionType.TRACE,
                    name="tool_retry_scheduled",
                    previous_call_id=call_id,
                    next_attempt=record.attempt + 1,
                    error=sanitize_error(event.payload["error"]),
                )
                await self._start_tool_call(
                    record.tool_name,
                    record.arguments,
                    attempt=record.attempt + 1,
                    idempotency_key=record.idempotency_key,
                )
            else:
                self.snapshot.status = "error"
                await self._emit(
                    ActionType.CLARIFICATION,
                    text="That tool failed and could not be safely retried.",
                    failed_call_id=call_id,
                    error=sanitize_error(event.payload["error"]),
                    state_snapshot=self.snapshot.to_dict(),
                )
            return

        result = event.payload.get("result")
        active_task = self.tasks.active()
        branch = active_task.active_branch() if active_task else None
        if branch:
            branch.set_call_status(call_id, "completed")
        if self.model is not None:
            if active_task:
                grounded = result if isinstance(result, dict) else {"value": result}
                if "summary" not in grounded and event.payload.get("summary"):
                    grounded["summary"] = str(event.payload["summary"])
                active_task.add_evidence(
                    call_id=record.call_id,
                    source=record.tool_name,
                    content=grounded,
                    depends_on=list(record.arguments),
                    branch_id=record.branch_id,
                )
            self._sync_snapshot()
            if self._active_calls:
                self.snapshot.status = "working"
                await self._emit(
                    ActionType.TRACE,
                    name="parallel_evidence_buffered",
                    completed_call_id=record.call_id,
                    remaining_calls=len(self._active_calls),
                    state_snapshot=self.snapshot.to_dict(),
                )
                return
            self.snapshot.status = "working"
            generation = self._task_generation = self._task_generation + 1
            self._slow_task = asyncio.create_task(
                self._run_slow_path(generation, allow_grounded_fallback=True)
            )
            return

        completed = self.tasks.complete_active(
            result if isinstance(result, dict) else None
        )
        self._sync_snapshot()
        self.snapshot.status = "complete"
        self.snapshot.version += 1
        await self._emit(
            ActionType.FINAL,
            text=str(event.payload.get("summary", "Task completed.")),
            call_id=call_id,
            task_id=completed.task_id if completed else None,
            grounded_result=result,
            state_snapshot=self.snapshot.to_dict(),
        )
