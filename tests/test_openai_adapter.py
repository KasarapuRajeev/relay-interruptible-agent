import json
import unittest

from relay.models import ModelContext
from relay.openai_adapter import OpenAIAdapterError, OpenAIResponsesAdapter


class OpenAIAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_structured_responses_request_and_parses_decision(self):
        captured = {}

        def transport(url, headers, payload, timeout):
            captured.update(
                {"url": url, "headers": headers, "payload": payload, "timeout": timeout}
            )
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "kind": "tool_call",
                                        "text": "",
                                        "tool_name": "search_travel",
                                        "arguments_json": '{"destination":"Jaipur"}',
                                    }
                                ),
                            }
                        ],
                    }
                ]
            }

        adapter = OpenAIResponsesAdapter(
            api_key="test-key", model="test-model", transport=transport
        )
        decision = await adapter.decide(
            ModelContext(
                task_id="task-1",
                intent="travel_planning",
                slots={"destination": "Jaipur"},
                available_tools=[],
                conversation_history=[{"role": "user", "text": "Keep it affordable"}],
            )
        )
        self.assertEqual(decision.tool_name, "search_travel")
        self.assertEqual(decision.arguments["destination"], "Jaipur")
        self.assertEqual(captured["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(captured["payload"]["text"]["format"]["type"], "json_schema")
        self.assertFalse(captured["payload"]["store"])
        input_data = json.loads(captured["payload"]["input"])
        self.assertEqual(
            input_data["conversation_history"][0]["text"],
            "Keep it affordable",
        )

    async def test_rejects_unstructured_provider_output(self):
        adapter = OpenAIResponsesAdapter(
            api_key="test-key",
            transport=lambda *_: {"output_text": "not-json"},
        )
        with self.assertRaises(OpenAIAdapterError):
            await adapter.decide(
                ModelContext("task-1", "general_assistance", {}, [])
            )

    def test_requires_api_key(self):
        with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
            OpenAIResponsesAdapter(api_key="")

    def test_translates_insufficient_quota_into_safe_user_guidance(self):
        error = OpenAIAdapterError.from_http(
            429,
            json.dumps(
                {
                    "error": {
                        "message": "You exceeded your current quota",
                        "type": "insufficient_quota",
                        "code": "insufficient_quota",
                    }
                }
            ),
        )
        self.assertEqual(error.status_code, 429)
        self.assertEqual(error.error_code, "insufficient_quota")
        self.assertIn("billing or credits", error.user_message)

    def test_translates_authentication_error_without_exposing_secret(self):
        error = OpenAIAdapterError.from_http(
            401,
            json.dumps({"error": {"message": "Incorrect API key provided"}}),
        )
        self.assertIn("authentication failed", error.user_message)
        self.assertNotIn("Incorrect API key provided", error.user_message)


if __name__ == "__main__":
    unittest.main()
