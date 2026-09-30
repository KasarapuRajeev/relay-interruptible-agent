import unittest

from relay.models import DeterministicModelAdapter, ModelContext, ModelDecision


class ModelContractTests(unittest.IsolatedAsyncioTestCase):
    def test_rejects_malformed_structured_decision(self):
        with self.assertRaisesRegex(ValueError, "decision kind"):
            ModelDecision.from_dict({"kind": "invented_action"})

    def test_tool_decision_requires_name(self):
        with self.assertRaisesRegex(ValueError, "requires tool_name"):
            ModelDecision.from_dict({"kind": "tool_call", "arguments": {}})

    async def test_offline_adapter_selects_declared_tool(self):
        adapter = DeterministicModelAdapter()
        decision = await adapter.decide(
            ModelContext(
                task_id="task-1",
                intent="travel_planning",
                slots={"destination": "Jaipur"},
                available_tools=[
                    {
                        "name": "search_travel",
                        "description": "Search travel",
                        "parameters": {},
                        "state_modifying": False,
                    }
                ],
            )
        )
        self.assertEqual(decision.kind, "tool_call")
        self.assertEqual(decision.tool_name, "search_travel")
        self.assertEqual(decision.arguments["destination"], "Jaipur")

    async def test_general_context_can_include_session_conversation(self):
        adapter = DeterministicModelAdapter()
        context = ModelContext(
            task_id="task-1",
            intent="general_assistance",
            slots={},
            available_tools=[],
            request_text="What fruit do I prefer?",
            conversation_history=[
                {"role": "user", "text": "I prefer mango", "kind": "message"}
            ],
        )
        decision = await adapter.decide(context)
        self.assertEqual(decision.kind, "final")

    async def test_offline_adapter_selects_provider_independent_integrations(self):
        adapter = DeterministicModelAdapter()
        for intent, name, slots in (
            ("weather_information", "get_current_weather", {"location": "Bengaluru"}),
            ("calculation", "calculate", {"expression": "2 + 2"}),
        ):
            decision = await adapter.decide(
                ModelContext(
                    task_id="task-1",
                    intent=intent,
                    slots=slots,
                    available_tools=[
                        {
                            "name": name,
                            "description": "Integration",
                            "parameters": {},
                            "state_modifying": False,
                        }
                    ],
                )
            )
            self.assertEqual(decision.tool_name, name)
            self.assertEqual(decision.arguments, slots)


if __name__ == "__main__":
    unittest.main()
