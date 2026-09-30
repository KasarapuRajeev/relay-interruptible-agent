import unittest

from relay.harness import ScenarioHarness
from relay.protocol import ActionType, EventType


class HarnessTests(unittest.IsolatedAsyncioTestCase):
    async def test_trace_is_json_safe_and_timestamped(self):
        harness = ScenarioHarness()
        await harness.start()
        try:
            await harness.send(
                EventType.TRANSCRIPT_CHUNK,
                {"text": "Help with something", "end_of_turn": True},
                after_ms=25,
            )
            actions = await harness.collect(2)
            self.assertEqual(actions[0].type, ActionType.SPOKEN)
            self.assertEqual(actions[0].timestamp_ms, 25)
            self.assertEqual(harness.trace[0]["type"], "transcript_chunk")
        finally:
            await harness.agent.close()


if __name__ == "__main__":
    unittest.main()
