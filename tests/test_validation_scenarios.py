import asyncio
import json
import unittest
import uuid

from relay.demo import MANIFEST
from relay.models import DeterministicModelAdapter, ModelDecision
from relay.orchestrator import RelayAgent
from relay.protocol import ActionType, EventType, InputEvent


def event(text: str, timestamp_ms: int = 0) -> InputEvent:
    return InputEvent(
        str(uuid.uuid4()),
        EventType.TRANSCRIPT_CHUNK,
        timestamp_ms,
        {"text": text, "end_of_turn": True},
    )


def result_event(call_id: str, result: dict) -> InputEvent:
    return InputEvent(
        str(uuid.uuid4()),
        EventType.TOOL_RESULT,
        10,
        {"call_id": call_id, "result": result},
    )


class FullSystemValidationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = RelayAgent(model=DeterministicModelAdapter())
        self.agent.tools.load_manifest(MANIFEST)
        await self.agent.start()

    async def asyncTearDown(self):
        await self.agent.close()

    async def test_three_parallel_calls_are_cancelled_once_and_late_results_are_rejected(self):
        await self.agent.submit(event("Research quantum computing"))
        await self.agent.next_action()  # acknowledgement
        calls = [await self.agent.next_action() for _ in range(3)]

        await self.agent.submit(event("Actually prioritize battery safety"))
        interruption = await self.agent.next_action()
        cancellations = [await self.agent.next_action() for _ in range(3)]
        acknowledgement = await self.agent.next_action()
        replacement_calls = [await self.agent.next_action() for _ in range(3)]

        self.assertEqual(interruption.payload["name"], "interruption_detected")
        self.assertEqual(
            {item.payload["call_id"] for item in cancellations},
            {item.payload["call_id"] for item in calls},
        )
        self.assertTrue(all(item.type is ActionType.CANCEL_CALL for item in cancellations))
        self.assertEqual(acknowledgement.type, ActionType.SPOKEN)
        self.assertTrue(all(item.type is ActionType.TOOL_CALL for item in replacement_calls))

        for call in calls:
            await self.agent.submit(
                result_event(call.payload["call_id"], {"summary": "obsolete evidence"})
            )
            rejected = await self.agent.next_action()
            self.assertEqual(rejected.payload["name"], "stale_tool_result_dropped")

        self.assertEqual(self.agent.metrics.cancelled_calls, 3)
        self.assertEqual(self.agent.metrics.stale_results_rejected, 3)

    async def test_parallel_results_may_arrive_in_reverse_order_without_duplicate_final(self):
        await self.agent.submit(event("Research quantum computing"))
        await self.agent.next_action()
        calls = [await self.agent.next_action() for _ in range(3)]

        for index, call in enumerate(reversed(calls)):
            aspect = call.payload["arguments"]["aspect"]
            await self.agent.submit(
                result_event(
                    call.payload["call_id"],
                    {
                        "summary": f"{aspect} evidence",
                        "topic": "quantum computing",
                        "aspect": aspect,
                        "sources": [{"url": f"https://example.test/{index}"}],
                    },
                )
            )
            action = await self.agent.next_action()
            if index < 2:
                self.assertEqual(action.payload["name"], "parallel_evidence_buffered")
            else:
                self.assertEqual(action.type, ActionType.FINAL)

        task = self.agent.tasks.active()
        self.assertIsNotNone(task)
        self.assertEqual(len(task.evidence), 3)
        self.assertEqual(len({record.call_id for record in task.evidence}), 3)

        duplicate = calls[0]
        await self.agent.submit(
            result_event(duplicate.payload["call_id"], {"summary": "duplicate"})
        )
        rejected = await self.agent.next_action()
        self.assertEqual(rejected.payload["name"], "stale_tool_result_dropped")
        self.assertEqual(len(task.evidence), 3)

    async def test_unknown_call_id_is_rejected_without_changing_evidence(self):
        await self.agent.submit(event("Research quantum computing"))
        await self.agent.next_action()
        await self.agent.next_action()
        await self.agent.next_action()
        await self.agent.next_action()

        await self.agent.submit(result_event("unknown-call", {"summary": "invented"}))
        rejected = await self.agent.next_action()

        self.assertEqual(rejected.payload["name"], "stale_tool_result_dropped")
        self.assertEqual(self.agent.tasks.active().evidence, [])

    async def test_rapid_corrections_leave_only_latest_branch_active(self):
        await self.agent.submit(event("Plan a 3-day trip to Delhi under ₹30,000"))
        await self.agent.next_action()
        delhi_call = await self.agent.next_action()

        await self.agent.submit(event("Actually change it to Jaipur under ₹20,000"))
        await self.agent.next_action()  # interruption
        await self.agent.next_action()  # cancellation
        await self.agent.next_action()  # acknowledgement
        jaipur_call = await self.agent.next_action()

        await self.agent.submit(event("Actually change it to Mumbai under ₹15,000"))
        await self.agent.next_action()  # interruption
        await self.agent.next_action()  # cancellation
        await self.agent.next_action()  # acknowledgement
        mumbai_call = await self.agent.next_action()

        self.assertNotEqual(delhi_call.payload["call_id"], jaipur_call.payload["call_id"])
        self.assertEqual(mumbai_call.payload["arguments"]["destination"], "Mumbai")
        self.assertEqual(mumbai_call.payload["arguments"]["budget_inr"], 15000)
        self.assertEqual(self.agent.snapshot.active_call_ids, [mumbai_call.payload["call_id"]])
        self.assertEqual(self.agent.snapshot.branch_number, 3)
        self.assertEqual(self.agent.snapshot.slots["duration_days"], 3)
        self.assertEqual(
            [branch.status for branch in self.agent.tasks.active().branches],
            ["superseded", "superseded", "active"],
        )

    async def test_protocol_actions_and_snapshot_remain_json_serializable(self):
        await self.agent.submit(event("Plan a trip to Delhi"))
        acknowledgement = await self.agent.next_action()
        tool_call = await self.agent.next_action()

        json.dumps(acknowledgement.to_dict())
        json.dumps(tool_call.to_dict())
        json.dumps(self.agent.snapshot.to_dict())

    async def test_tool_failure_does_not_expose_a_secret_in_actions(self):
        await self.agent.submit(event("Plan a trip to Delhi"))
        await self.agent.next_action()
        first_call = await self.agent.next_action()
        secret = "sk-" + "project-supersecret123456789"
        await self.agent.submit(
            InputEvent(
                str(uuid.uuid4()),
                EventType.TOOL_RESULT,
                10,
                {"call_id": first_call.payload["call_id"], "error": secret},
            )
        )
        retry_trace = await self.agent.next_action()

        self.assertNotIn(secret, json.dumps(retry_trace.to_dict()))
        self.assertIn("[REDACTED]", retry_trace.payload["error"])


class _BlockingModel:
    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def decide(self, context):
        self.started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return ModelDecision(kind="final", text="obsolete model answer")


class SlowReasoningCancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_interruption_cancels_in_flight_model_reasoning(self):
        model = _BlockingModel()
        agent = RelayAgent(model=model)
        agent.tools.load_manifest(MANIFEST)
        await agent.start()
        try:
            await agent.submit(event("Explain quantum computing"))
            acknowledgement = await agent.next_action()
            self.assertEqual(acknowledgement.type, ActionType.SPOKEN)
            await asyncio.wait_for(model.started.wait(), 0.2)

            await agent.submit(event("Actually plan a trip to Delhi"))
            interruption = await agent.next_action()
            reasoning_cancelled = await agent.next_action()
            acknowledgement = await agent.next_action()

            self.assertEqual(interruption.payload["name"], "interruption_detected")
            self.assertEqual(reasoning_cancelled.payload["name"], "reasoning_cancelled")
            self.assertEqual(acknowledgement.type, ActionType.SPOKEN)
            await asyncio.wait_for(model.cancelled.wait(), 0.2)
        finally:
            await agent.close()


if __name__ == "__main__":
    unittest.main()
