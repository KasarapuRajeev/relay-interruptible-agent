import asyncio
import json
import unittest

from relay.gemini_adapter import GeminiAdapterError, GeminiGenerateContentAdapter
from relay.models import ModelContext


class GeminiAdapterTests(unittest.TestCase):
    def test_strips_whitespace_from_api_key(self):
        adapter = GeminiGenerateContentAdapter(api_key="  test-key\r\n")
        self.assertEqual(adapter.api_key, "test-key")

    def test_builds_structured_request_and_parses_decision(self):
        captured = {}

        def transport(url, headers, payload, timeout):
            captured.update(url=url, headers=headers, payload=payload, timeout=timeout)
            decision = {
                "kind": "tool_call",
                "text": "",
                "tool_name": "search_travel",
                "arguments_json": '{"destination":"Jaipur"}',
            }
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(decision)}]}}]}

        adapter = GeminiGenerateContentAdapter(api_key="test-key", transport=transport)
        context = ModelContext(
            task_id="task-1",
            intent="travel_planning",
            slots={"destination": "Jaipur"},
            available_tools=[{"name": "search_travel"}],
            conversation_history=[{"role": "user", "text": "Use my earlier budget"}],
        )
        decision = asyncio.run(adapter.decide(context))

        self.assertEqual(decision.tool_name, "search_travel")
        self.assertEqual(decision.arguments, {"destination": "Jaipur"})
        self.assertIn("gemini-3.1-flash-lite", captured["url"])
        self.assertEqual(captured["headers"]["x-goog-api-key"], "test-key")
        self.assertEqual(
            captured["payload"]["generationConfig"]["responseMimeType"],
            "application/json",
        )
        input_data = json.loads(
            captured["payload"]["contents"][0]["parts"][0]["text"]
        )
        self.assertEqual(
            input_data["conversation_history"][0]["text"],
            "Use my earlier budget",
        )

    def test_requires_api_key(self):
        with self.assertRaises(ValueError):
            GeminiGenerateContentAdapter(api_key="")

    def test_translates_free_tier_rate_limit(self):
        error = GeminiAdapterError.from_http(
            429, '{"error":{"status":"RESOURCE_EXHAUSTED","message":"Quota exceeded"}}'
        )
        self.assertIn("free-tier rate limit", error.user_message)
        self.assertNotIn("Quota exceeded", error.user_message)

    def test_retries_http_503_then_succeeds(self):
        attempts = 0

        def transport(url, headers, payload, timeout):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise GeminiAdapterError.from_http(503, '{"error":{"status":"UNAVAILABLE"}}')
            decision = {
                "kind": "final",
                "text": "Recovered",
                "tool_name": "",
                "arguments_json": "{}",
            }
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(decision)}]}}]}

        adapter = GeminiGenerateContentAdapter(
            api_key="test-key", transport=transport, retry_delays=(0, 0)
        )
        context = ModelContext("task-1", "general_assistance", {}, [])
        decision = asyncio.run(adapter.decide(context))
        self.assertEqual(decision.text, "Recovered")
        self.assertEqual(attempts, 3)


if __name__ == "__main__":
    unittest.main()
