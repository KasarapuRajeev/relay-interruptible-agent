"""Provider-independent model contract with strict structured-output validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


DecisionKind = Literal["tool_call", "final", "clarification"]


@dataclass(frozen=True, slots=True)
class ModelContext:
    task_id: str
    intent: str
    slots: dict[str, Any]
    available_tools: list[dict[str, Any]]
    grounded_results: list[dict[str, Any]] = field(default_factory=list)
    request_text: str = ""
    conversation_history: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ModelDecision:
    kind: DecisionKind
    text: str = ""
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ModelDecision":
        kind = value.get("kind")
        if kind not in {"tool_call", "final", "clarification"}:
            raise ValueError("Model decision kind must be tool_call, final, or clarification")
        tool_name = value.get("tool_name")
        arguments = value.get("arguments", {})
        if kind == "tool_call" and not isinstance(tool_name, str):
            raise ValueError("A tool_call decision requires tool_name")
        if not isinstance(arguments, dict):
            raise ValueError("Model decision arguments must be an object")
        return cls(
            kind=kind,
            text=str(value.get("text", "")),
            tool_name=tool_name,
            arguments=arguments,
        )


class ModelAdapter(Protocol):
    """The only interface a ChatGPT, Claude, Gemini, or local adapter must satisfy."""

    async def decide(self, context: ModelContext) -> ModelDecision:
        """Return one validated next action without executing tools directly."""
        ...


class DeterministicModelAdapter:
    """Offline development adapter used until a provider API is configured."""

    async def decide(self, context: ModelContext) -> ModelDecision:
        if context.grounded_results:
            latest = context.grounded_results[-1]
            return ModelDecision(
                kind="final",
                text=str(latest.get("summary", "The tool completed successfully.")),
            )
        preferred_tool = {
            "travel_planning": "search_travel",
            "study_planning": "build_study_plan",
            "research": "parallel_research",
            "weather_information": "get_current_weather",
            "calculation": "calculate",
        }.get(context.intent, "general_assistant")
        available_names = {tool["name"] for tool in context.available_tools}
        if preferred_tool in available_names:
            return ModelDecision(
                kind="tool_call",
                tool_name=preferred_tool,
                arguments=dict(context.slots),
            )
        return ModelDecision(
            kind="final",
            text=(
                "Relay is ready in offline demo mode. Ask me to plan a trip or "
                "create a study plan, then interrupt me while I work."
            ),
        )
