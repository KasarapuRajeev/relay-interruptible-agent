import asyncio
import unittest
import uuid

from relay.orchestrator import RelayAgent
from relay.models import DeterministicModelAdapter, ModelDecision
from relay.protocol import ActionType, EventType, InputEvent


TOOLS = [
    {
        "name": "search_travel",
        "description": "Search",
        "parameters": {
            "type": "object",
            "required": ["destination"],
            "properties": {"destination": {"type": "string"}},
        },
        "state_modifying": False,
        "max_retries": 1,
    }
]


def event(text):
    return InputEvent(
        str(uuid.uuid4()),
        EventType.TRANSCRIPT_CHUNK,
        0,
        {"text": text, "end_of_turn": True},
    )


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = RelayAgent(clock=lambda: 10)
        self.agent.tools.load_manifest(TOOLS)
        await self.agent.start()

    async def asyncTearDown(self):
        await self.agent.close()

    async def test_fast_path_precedes_tool_call(self):
        await self.agent.submit(event("Plan a trip to Delhi"))
        first = await self.agent.next_action()
        second = await self.agent.next_action()
        self.assertEqual(first.type, ActionType.SPOKEN)
        self.assertTrue(first.payload["acknowledgement"])
        self.assertTrue(first.payload["interruptible"])
        self.assertEqual(second.type, ActionType.TOOL_CALL)

    async def test_greeting_uses_local_fast_path_without_provider(self):
        class FailingModel:
            async def decide(self, context):
                raise AssertionError("The provider must not be called for a greeting")

        agent = RelayAgent(clock=lambda: 10, model=FailingModel())
        await agent.start()
        try:
            await agent.submit(event("hii"))
            acknowledgement = await agent.next_action()
            final = await agent.next_action()

            self.assertEqual(acknowledgement.type, ActionType.SPOKEN)
            self.assertEqual(final.type, ActionType.FINAL)
            self.assertTrue(final.payload["local_fast_path"])
            self.assertIn("I’m Relay", final.payload["text"])
            self.assertEqual(final.payload["state_snapshot"]["status"], "complete")
        finally:
            await agent.close()

    async def test_correction_cancels_old_call_and_updates_only_changed_slot(self):
        await self.agent.submit(event("Plan a 3-day trip to Delhi under ₹30,000"))
        await self.agent.next_action()
        old_call = await self.agent.next_action()

        await self.agent.submit(event("Actually change it to Jaipur under ₹20,000"))
        trace = await self.agent.next_action()
        cancellation = await self.agent.next_action()
        acknowledgement = await self.agent.next_action()
        new_call = await self.agent.next_action()

        self.assertEqual(trace.type, ActionType.TRACE)
        self.assertEqual(cancellation.type, ActionType.CANCEL_CALL)
        self.assertEqual(cancellation.payload["call_id"], old_call.payload["call_id"])
        self.assertEqual(acknowledgement.type, ActionType.SPOKEN)
        self.assertEqual(new_call.payload["arguments"]["destination"], "Jaipur")
        self.assertEqual(new_call.payload["arguments"]["duration_days"], 3)
        snapshot = new_call.payload["state_snapshot"]
        self.assertEqual(snapshot["branch_number"], 2)
        active_task = next(task for task in snapshot["tasks"] if task["active"])
        self.assertIn("Jaipur", active_task["request_text"])
        self.assertEqual(active_task["active_step"], "search travel")
        self.assertEqual(
            snapshot["context_diff"]["changed"]["destination"],
            {"old": "Delhi", "new": "Jaipur"},
        )
        self.assertEqual(snapshot["context_diff"]["preserved"]["duration_days"], 3)
        self.assertEqual(snapshot["plan_steps"][0]["status"], "running")
        self.assertEqual(snapshot["metrics"]["interruptions"], 1)
        self.assertEqual(snapshot["metrics"]["cancelled_calls"], 1)
        self.assertEqual(snapshot["metrics"]["replans"], 1)
        decisions = snapshot["plan_branches"][-1]["impact_decisions"]
        self.assertEqual(decisions[0]["action"], "cancel")
        self.assertEqual(decisions[0]["score"], 1)

    async def test_stale_tool_result_is_dropped(self):
        await self.agent.submit(event("Plan a trip to Delhi"))
        await self.agent.next_action()
        old_call = await self.agent.next_action()
        await self.agent.submit(event("Actually change it to Jaipur"))
        for _ in range(4):
            await self.agent.next_action()

        await self.agent.submit(
            InputEvent(
                str(uuid.uuid4()),
                EventType.TOOL_RESULT,
                20,
                {"call_id": old_call.payload["call_id"], "summary": "Old Delhi result"},
            )
        )
        action = await self.agent.next_action()
        self.assertEqual(action.type, ActionType.TRACE)
        self.assertEqual(action.payload["name"], "stale_tool_result_dropped")
        self.assertEqual(
            action.payload["state_snapshot"]["metrics"]["stale_results_rejected"],
            1,
        )

    async def test_partial_transcript_starts_speculation(self):
        partial = InputEvent(
            str(uuid.uuid4()),
            EventType.TRANSCRIPT_CHUNK,
            0,
            {"text": "Plan a trip", "end_of_turn": False},
        )
        await self.agent.submit(partial)
        action = await self.agent.next_action()
        self.assertEqual(action.payload["name"], "speculative_intent_started")

    async def test_pause_then_resume_restores_the_travel_checkpoint(self):
        await self.agent.submit(event("Plan a 3-day trip to Delhi under ₹30,000"))
        await self.agent.next_action()
        await self.agent.next_action()
        original_task_id = self.agent.snapshot.task_id

        await self.agent.submit(event("Pause this"))
        await self.agent.next_action()  # interruption trace
        await self.agent.next_action()  # cancellation
        paused = await self.agent.next_action()
        self.assertEqual(paused.type, ActionType.SPOKEN)
        self.assertEqual(paused.payload["state_snapshot"]["paused_task_ids"], [original_task_id])

        await self.agent.submit(event("Make a study plan for mathematics exam"))
        await self.agent.next_action()
        await self.agent.next_action()  # domain tool is absent in this test manifest

        await self.agent.submit(event("Continue my trip"))
        acknowledgement = await self.agent.next_action()
        self.assertEqual(acknowledgement.type, ActionType.SPOKEN)
        self.assertEqual(acknowledgement.payload["task_id"], original_task_id)
        self.assertEqual(acknowledgement.payload["state_snapshot"]["slots"]["destination"], "Delhi")
        snapshot = acknowledgement.payload["state_snapshot"]
        self.assertEqual(len(snapshot["tasks"]), 2)
        active = next(task for task in snapshot["tasks"] if task["active"])
        self.assertEqual(active["task_id"], original_task_id)
        self.assertEqual(snapshot["metrics"]["tasks_resumed"], 1)

    async def test_travel_correction_after_greeting_selects_travel_tool(self):
        agent = RelayAgent(model=DeterministicModelAdapter())
        agent.tools.load_manifest(TOOLS)
        await agent.start()
        try:
            await agent.submit(event("hii"))
            await agent.next_action()
            await agent.next_action()

            await agent.submit(event("Actually change it to Jaipur under ₹20,000"))
            acknowledgement = await agent.next_action()
            tool_call = await agent.next_action()
            self.assertEqual(
                acknowledgement.payload["state_snapshot"]["intent"],
                "travel_planning",
            )
            self.assertEqual(tool_call.type, ActionType.TOOL_CALL)
            self.assertEqual(tool_call.payload["tool_name"], "search_travel")
            self.assertEqual(tool_call.payload["arguments"]["destination"], "Jaipur")
        finally:
            await agent.close()

    async def test_cancel_subject_then_compare_replans_instead_of_stopping(self):
        research_tool = {
            "name": "parallel_research",
            "description": "Research in parallel",
            "parameters": {
                "type": "object",
                "required": ["topic"],
                "properties": {
                    "topic": {"type": "string"},
                    "aspect": {"type": "string"},
                    "budget_inr": {"type": "integer"},
                },
            },
            "state_modifying": False,
        }
        agent = RelayAgent(model=DeterministicModelAdapter())
        agent.tools.load_manifest([research_tool])
        await agent.start()
        try:
            await agent.submit(event("Research electric cars for college students"))
            await agent.next_action()
            for _ in range(3):
                await agent.next_action()

            await agent.submit(
                event("Actually cancel cars. Compare electric scooters under ₹80,000.")
            )
            interruption = await agent.next_action()
            cancellations = [await agent.next_action() for _ in range(3)]
            acknowledgement = await agent.next_action()
            replacement_calls = [await agent.next_action() for _ in range(3)]

            self.assertEqual(interruption.payload["name"], "interruption_detected")
            self.assertTrue(all(action.type is ActionType.CANCEL_CALL for action in cancellations))
            self.assertEqual(acknowledgement.type, ActionType.SPOKEN)
            snapshot = replacement_calls[-1].payload["state_snapshot"]
            self.assertEqual(snapshot["status"], "working")
            self.assertEqual(snapshot["intent"], "research")
            self.assertEqual(snapshot["slots"]["topic"], "electric scooters under ₹80,000")
            self.assertEqual(snapshot["slots"]["budget_inr"], 80000)
            self.assertEqual(snapshot["branch_number"], 2)
        finally:
            await agent.close()

    async def test_completed_delhi_result_is_invalidated_before_jaipur_research(self):
        agent = RelayAgent(model=DeterministicModelAdapter())
        agent.tools.load_manifest(TOOLS)
        await agent.start()
        try:
            await agent.submit(event("Plan a 3-day trip to Delhi under ₹30,000"))
            await agent.next_action()
            delhi_call = await agent.next_action()
            await agent.submit(
                InputEvent(
                    str(uuid.uuid4()),
                    EventType.TOOL_RESULT,
                    10,
                    {
                        "call_id": delhi_call.payload["call_id"],
                        "result": {
                            "summary": "Delhi plan",
                            "destination": "Delhi",
                            "budget_inr": 30000,
                            "duration_days": 3,
                        },
                    },
                )
            )
            delhi_final = await agent.next_action()
            self.assertEqual(delhi_final.type, ActionType.FINAL)

            await agent.submit(event("Actually change it to Jaipur under ₹20,000"))
            invalidation = await agent.next_action()
            acknowledgement = await agent.next_action()
            jaipur_call = await agent.next_action()
            self.assertEqual(invalidation.payload["name"], "grounded_results_invalidated")
            self.assertEqual(acknowledgement.type, ActionType.SPOKEN)
            self.assertEqual(jaipur_call.type, ActionType.TOOL_CALL)
            self.assertEqual(jaipur_call.payload["arguments"]["destination"], "Jaipur")
            self.assertEqual(jaipur_call.payload["arguments"]["duration_days"], 3)
        finally:
            await agent.close()


class ToolSafetyTests(unittest.TestCase):
    def test_state_change_idempotency(self):
        agent = RelayAgent()
        agent.tools.load_manifest(
            [{"name": "book", "parameters": {}, "state_modifying": True}]
        )
        self.assertTrue(agent.tools.reserve_side_effect("book", "same-request"))
        self.assertFalse(agent.tools.reserve_side_effect("book", "same-request"))

    def test_manifest_argument_validation(self):
        agent = RelayAgent()
        agent.tools.load_manifest(TOOLS)
        with self.assertRaisesRegex(ValueError, "Missing required arguments"):
            agent.tools.validate_arguments("search_travel", {})

    def test_manifest_rejects_wrong_argument_type(self):
        agent = RelayAgent()
        agent.tools.load_manifest(TOOLS)
        with self.assertRaisesRegex(ValueError, "must be string"):
            agent.tools.validate_arguments("search_travel", {"destination": 123})

    def test_boolean_is_not_accepted_as_an_integer(self):
        agent = RelayAgent()
        agent.tools.load_manifest(
            [{
                "name": "set_days",
                "parameters": {
                    "properties": {"days": {"type": "integer"}},
                },
            }]
        )
        with self.assertRaisesRegex(ValueError, "must be integer"):
            agent.tools.validate_arguments("set_days", {"days": True})


class ToolLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_slots_repair_provider_tool_arguments(self):
        class MissingArgumentsModel:
            async def decide(self, context):
                return ModelDecision(
                    kind="tool_call",
                    tool_name="calculate",
                    arguments={},
                )

        calculate_tool = {
            "name": "calculate",
            "description": "Calculate safely",
            "parameters": {
                "type": "object",
                "required": ["expression"],
                "properties": {"expression": {"type": "string"}},
            },
            "state_modifying": False,
        }
        agent = RelayAgent(model=MissingArgumentsModel())
        agent.tools.load_manifest([calculate_tool])
        await agent.start()
        try:
            await agent.submit(event("Calculate (1250 * 3) + 499"))
            await agent.next_action()
            tool_call = await agent.next_action()
            self.assertEqual(tool_call.type, ActionType.TOOL_CALL)
            self.assertEqual(tool_call.payload["tool_name"], "calculate")
            self.assertEqual(
                tool_call.payload["arguments"]["expression"],
                "(1250 * 3) + 499",
            )
        finally:
            await agent.close()

    async def test_grounded_result_survives_provider_synthesis_timeout(self):
        class ToolThenTimeoutModel:
            async def decide(self, context):
                if context.grounded_results:
                    raise TimeoutError("provider synthesis timed out")
                return ModelDecision(
                    kind="tool_call",
                    tool_name="search_travel",
                    arguments={"destination": "Delhi"},
                )

        agent = RelayAgent(model=ToolThenTimeoutModel())
        agent.tools.load_manifest(TOOLS)
        await agent.start()
        try:
            await agent.submit(event("Plan a trip to Delhi"))
            await agent.next_action()
            tool_call = await agent.next_action()
            await agent.submit(
                InputEvent(
                    str(uuid.uuid4()),
                    EventType.TOOL_RESULT,
                    10,
                    {
                        "call_id": tool_call.payload["call_id"],
                        "result": {
                            "summary": "Grounded Delhi result",
                            "destination": "Delhi",
                        },
                    },
                )
            )
            final = await agent.next_action()
            self.assertEqual(final.type, ActionType.FINAL)
            self.assertEqual(final.payload["text"], "Grounded Delhi result")
            self.assertTrue(final.payload["provider_fallback"])
            self.assertEqual(final.payload["error_type"], "TimeoutError")
            self.assertEqual(final.payload["state_snapshot"]["status"], "complete")
        finally:
            await agent.close()

    async def test_general_conversation_history_is_sent_to_the_model_and_visible(self):
        class CapturingModel:
            def __init__(self):
                self.contexts = []

            async def decide(self, context):
                self.contexts.append(context)
                return ModelDecision(kind="final", text="Remembered answer")

        model = CapturingModel()
        agent = RelayAgent(model=model)
        agent.tools.load_manifest(TOOLS)
        await agent.start()
        try:
            await agent.submit(event("My favorite fruit is mango"))
            await agent.next_action()
            await agent.next_action()

            await agent.submit(event("What fruit do I prefer?"))
            await agent.next_action()
            final = await agent.next_action()

            history = model.contexts[-1].conversation_history
            self.assertEqual(
                [(turn["role"], turn["text"]) for turn in history],
                [
                    ("user", "My favorite fruit is mango"),
                    ("assistant", "Remembered answer"),
                    ("user", "What fruit do I prefer?"),
                ],
            )
            self.assertEqual(final.payload["state_snapshot"]["memory_turn_count"], 4)
            self.assertEqual(
                final.payload["state_snapshot"]["conversation_history"][-1]["text"],
                "Remembered answer",
            )
        finally:
            await agent.close()

    async def test_session_memory_is_bounded(self):
        class ImmediateModel:
            async def decide(self, context):
                return ModelDecision(kind="final", text="ok")

        agent = RelayAgent(model=ImmediateModel(), memory_turn_limit=4)
        await agent.start()
        try:
            for request in ("one", "two", "three"):
                await agent.submit(event(request))
                await agent.next_action()
                await agent.next_action()
            self.assertEqual(agent.snapshot.memory_turn_count, 4)
            self.assertEqual(
                [turn["text"] for turn in agent.snapshot.conversation_history],
                ["two", "ok", "three", "ok"],
            )
        finally:
            await agent.close()

    async def test_research_fans_out_and_waits_for_all_parallel_evidence(self):
        research_tool = {
            "name": "parallel_research",
            "description": "Research in parallel",
            "parameters": {
                "type": "object",
                "required": ["topic"],
                "properties": {
                    "topic": {"type": "string"},
                    "aspect": {"type": "string"},
                },
            },
            "state_modifying": False,
        }
        agent = RelayAgent(model=DeterministicModelAdapter())
        agent.tools.load_manifest([research_tool])
        await agent.start()
        try:
            await agent.submit(event("Research quantum computing"))
            await agent.next_action()  # acknowledgement
            calls = [await agent.next_action() for _ in range(3)]
            self.assertTrue(all(action.type is ActionType.TOOL_CALL for action in calls))
            self.assertEqual(
                {action.payload["arguments"]["aspect"] for action in calls},
                {"overview", "applications", "limitations and risks"},
            )

            for index, call in enumerate(calls):
                await agent.submit(
                    InputEvent(
                        str(uuid.uuid4()),
                        EventType.TOOL_RESULT,
                        10,
                        {
                            "call_id": call.payload["call_id"],
                            "result": {
                                "summary": f"Evidence {index}",
                                "topic": "quantum computing",
                                "aspect": call.payload["arguments"]["aspect"],
                                "sources": [{"url": f"https://example.com/{index}"}],
                            },
                        },
                    )
                )
                action = await agent.next_action()
                if index < 2:
                    self.assertEqual(action.payload["name"], "parallel_evidence_buffered")
                else:
                    self.assertEqual(action.type, ActionType.FINAL)
            self.assertEqual(len(agent.tasks.active().evidence), 3)
        finally:
            await agent.close()

    async def test_full_general_request_is_forwarded_to_model(self):
        class CapturingModel:
            context = None

            async def decide(self, context):
                self.context = context
                return ModelDecision(kind="final", text="General answer")

        model = CapturingModel()
        agent = RelayAgent(model=model)
        agent.tools.load_manifest(TOOLS)
        await agent.start()
        try:
            request = "Explain how solar panels work"
            await agent.submit(event(request))
            await agent.next_action()
            final = await agent.next_action()
            self.assertEqual(final.type, ActionType.FINAL)
            self.assertEqual(model.context.request_text, request)
        finally:
            await agent.close()

    async def test_model_adapter_drives_the_tool_call(self):
        agent = RelayAgent(model=DeterministicModelAdapter())
        agent.tools.load_manifest(TOOLS)
        await agent.start()
        try:
            await agent.submit(event("Plan a trip to Delhi"))
            await agent.next_action()
            tool_call = await agent.next_action()
            self.assertEqual(tool_call.type, ActionType.TOOL_CALL)
            self.assertEqual(tool_call.payload["tool_name"], "search_travel")
        finally:
            await agent.close()

    async def test_model_synthesizes_final_after_grounded_tool_result(self):
        agent = RelayAgent(model=DeterministicModelAdapter())
        agent.tools.load_manifest(TOOLS)
        await agent.start()
        try:
            await agent.submit(event("Plan a trip to Delhi"))
            await agent.next_action()
            tool_call = await agent.next_action()
            await agent.submit(
                InputEvent(
                    str(uuid.uuid4()),
                    EventType.TOOL_RESULT,
                    10,
                    {
                        "call_id": tool_call.payload["call_id"],
                        "summary": "Delhi evidence ready",
                        "result": {"summary": "Grounded Delhi itinerary"},
                    },
                )
            )
            final = await agent.next_action()
            self.assertEqual(final.type, ActionType.FINAL)
            self.assertEqual(final.payload["text"], "Grounded Delhi itinerary")
        finally:
            await agent.close()

    async def test_read_only_failure_retries_once(self):
        agent = RelayAgent(clock=lambda: 10, tool_timeout_seconds=1)
        agent.tools.load_manifest(TOOLS)
        await agent.start()
        try:
            await agent.submit(event("Plan a trip to Delhi"))
            await agent.next_action()
            first_call = await agent.next_action()
            await agent.submit(
                InputEvent(
                    str(uuid.uuid4()),
                    EventType.TOOL_RESULT,
                    10,
                    {"call_id": first_call.payload["call_id"], "error": "temporary"},
                )
            )
            retry_trace = await agent.next_action()
            retry_call = await agent.next_action()
            self.assertEqual(retry_trace.payload["name"], "tool_retry_scheduled")
            self.assertEqual(retry_call.type, ActionType.TOOL_CALL)
            self.assertEqual(retry_call.payload["attempt"], 2)
        finally:
            await agent.close()

    async def test_read_only_timeout_cancels_and_retries(self):
        agent = RelayAgent(clock=lambda: 10, tool_timeout_seconds=0.01)
        agent.tools.load_manifest(TOOLS)
        await agent.start()
        try:
            await agent.submit(event("Plan a trip to Delhi"))
            await agent.next_action()
            first_call = await agent.next_action()
            cancellation = await agent.next_action(timeout=0.2)
            retry_trace = await agent.next_action()
            retry_call = await agent.next_action()
            self.assertEqual(cancellation.type, ActionType.CANCEL_CALL)
            self.assertEqual(cancellation.payload["call_id"], first_call.payload["call_id"])
            self.assertEqual(retry_trace.payload["name"], "tool_retry_scheduled")
            self.assertEqual(retry_call.payload["attempt"], 2)
        finally:
            await agent.close()

    async def test_state_modifying_tool_is_never_auto_retried(self):
        agent = RelayAgent(clock=lambda: 10, tool_timeout_seconds=1)
        agent.tools.load_manifest(
            [
                {
                    "name": "search_travel",
                    "parameters": {},
                    "state_modifying": True,
                    "max_retries": 3,
                }
            ]
        )
        await agent.start()
        try:
            await agent.submit(event("Plan a trip to Delhi"))
            await agent.next_action()
            call = await agent.next_action()
            self.assertIsNotNone(call.payload["idempotency_key"])
            await agent.submit(
                InputEvent(
                    str(uuid.uuid4()),
                    EventType.TOOL_RESULT,
                    10,
                    {"call_id": call.payload["call_id"], "error": "uncertain outcome"},
                )
            )
            failure = await agent.next_action()
            self.assertEqual(failure.type, ActionType.CLARIFICATION)
        finally:
            await agent.close()


if __name__ == "__main__":
    unittest.main()
