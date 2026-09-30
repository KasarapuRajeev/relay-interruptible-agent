"""Minimal CLI demonstration of correction, cancellation, and stale-result safety."""

from __future__ import annotations

import asyncio
import json
import os
import uuid

from .gemini_adapter import GeminiGenerateContentAdapter
from .models import DeterministicModelAdapter
from .openai_adapter import OpenAIResponsesAdapter
from .orchestrator import RelayAgent
from .protocol import ActionType, EventType, InputEvent


MANIFEST = [
    {
        "name": "search_travel",
        "description": "Search travel options",
        "parameters": {
            "type": "object",
            "required": ["destination"],
            "properties": {
                "destination": {"type": "string"},
                "budget_inr": {"type": "integer"},
                "duration_days": {"type": "integer"},
            },
        },
        "state_modifying": False,
    },
    {
        "name": "build_study_plan",
        "description": "Create a study plan",
        "parameters": {
            "type": "object",
            "required": ["subject"],
            "properties": {"subject": {"type": "string"}},
        },
        "state_modifying": False,
    },
    {
        "name": "parallel_research",
        "description": "Search multiple live cited sources in parallel by research aspect",
        "parameters": {
            "type": "object",
            "required": ["topic"],
            "properties": {
                "topic": {"type": "string"},
                "aspect": {"type": "string"},
                "budget_inr": {"type": "integer"},
                "priority": {"type": "string"},
            },
        },
        "state_modifying": False,
        "max_retries": 1,
    },
    {
        "name": "get_current_weather",
        "description": "Get live current weather for a named location using cited Open-Meteo data",
        "parameters": {
            "type": "object",
            "required": ["location"],
            "properties": {"location": {"type": "string"}},
        },
        "state_modifying": False,
        "max_retries": 1,
    },
    {
        "name": "calculate",
        "description": "Safely calculate an exact arithmetic expression",
        "parameters": {
            "type": "object",
            "required": ["expression"],
            "properties": {"expression": {"type": "string"}},
        },
        "state_modifying": False,
        "max_retries": 0,
    },
]


async def run_demo() -> None:
    if os.environ.get("GEMINI_API_KEY"):
        model = GeminiGenerateContentAdapter()
        provider = "Gemini"
    elif os.environ.get("OPENAI_API_KEY"):
        model = OpenAIResponsesAdapter()
        provider = "OpenAI"
    else:
        model = DeterministicModelAdapter()
        provider = "offline deterministic model"
    agent = RelayAgent(model=model)
    agent.tools.load_manifest(MANIFEST)
    await agent.start()
    print(f"Relay CLI ({provider}) - type a request, interrupt it, or type 'quit'.")

    async def complete_mock_tool(action) -> None:
        await asyncio.sleep(1.0)
        arguments = action.payload["arguments"]
        tool_name = action.payload["tool_name"]
        if tool_name == "search_travel":
            destination = arguments.get("destination", "the destination")
            summary = f"Prepared a grounded travel outline for {destination}."
            result = {
                "summary": summary,
                "destination": destination,
                "budget_inr": arguments.get("budget_inr"),
                "duration_days": arguments.get("duration_days"),
                "source": "deterministic_demo_tool",
            }
        else:
            subject = arguments.get("subject", "the requested subject")
            summary = f"Prepared a grounded study-plan outline for {subject}."
            result = {"summary": summary, "subject": subject, "source": "deterministic_demo_tool"}
        await agent.submit(
            InputEvent(
                str(uuid.uuid4()),
                EventType.TOOL_RESULT,
                agent.clock(),
                {
                    "call_id": action.payload["call_id"],
                    "summary": summary,
                    "result": result,
                },
            )
        )

    async def printer() -> None:
        while True:
            action = await agent.next_action(timeout=3600)
            print(json.dumps(action.to_dict(), indent=2))
            if action.type is ActionType.TOOL_CALL:
                asyncio.create_task(complete_mock_tool(action))

    printer_task = asyncio.create_task(printer())
    try:
        while True:
            text = await asyncio.to_thread(input, "you> ")
            if text.strip().lower() in {"quit", "exit"}:
                break
            await agent.submit(
                InputEvent(
                    str(uuid.uuid4()),
                    EventType.TRANSCRIPT_CHUNK,
                    agent.clock(),
                    {"text": text, "end_of_turn": True},
                )
            )
    finally:
        printer_task.cancel()
        await agent.close()


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
