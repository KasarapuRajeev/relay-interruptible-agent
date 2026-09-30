"""OpenAI Responses API adapter for Relay's provider-neutral model contract."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .models import ModelAdapter, ModelContext, ModelDecision


Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["tool_call", "final", "clarification"]},
        "text": {"type": "string"},
        "tool_name": {"type": "string"},
        "arguments_json": {"type": "string"},
    },
    "required": ["kind", "text", "tool_name", "arguments_json"],
    "additionalProperties": False,
}


SYSTEM_INSTRUCTIONS = """You are the general-purpose reasoning component inside Relay,
an interruptible conversational agent runtime. Help with ordinary conversation,
explanations, writing, brainstorming, coding guidance, planning, and any other safe
general topic, even when no tool matches. The available tool list limits external
actions, not what you may discuss from general knowledge.

Return exactly one structured decision. The newest request_text is authoritative. Use
conversation_history for follow-ups, pronouns, preferences, and information the user
already supplied, but never allow an older instruction to override a newer correction.
If a short request is genuinely ambiguous (for example, "I need fruits"), ask one useful
clarifying question instead of claiming Relay only supports travel, study, or research.

Use only tools listed in available_tools. Select tool_call only when external evidence
or an available action is genuinely required. Never claim that an external action,
purchase, booking, search, or tool completed unless its result appears in
grounded_results. Once grounded_results contains sufficient evidence, return a truthful
final response based only on that evidence. For normal questions that do not need an
external tool, answer directly with a final decision.

Use clarification when essential information is missing. Put an empty string in
tool_name when no tool is selected. Put tool arguments as a JSON object encoded in
arguments_json. When grounded evidence contains source URLs, cite only those URLs. Do
not invent citations or sources."""


class OpenAIAdapterError(RuntimeError):
    """Raised when the provider cannot return a valid Relay decision."""

    def __init__(
        self,
        message: str,
        *,
        user_message: str | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.user_message = user_message or "The OpenAI request failed. Please try again."
        self.status_code = status_code
        self.error_code = error_code

    @classmethod
    def from_http(cls, status_code: int, detail: str) -> "OpenAIAdapterError":
        error_code = None
        provider_message = ""
        try:
            parsed = json.loads(detail)
            error_data = parsed.get("error", {})
            error_code = error_data.get("code") or error_data.get("type")
            provider_message = str(error_data.get("message", ""))
        except (json.JSONDecodeError, AttributeError):
            provider_message = detail[:300]

        if status_code in (401, 403):
            user_message = (
                "OpenAI authentication failed. Verify that you entered a valid project API "
                "key and that the project permits API access."
            )
        elif status_code == 429 and error_code == "insufficient_quota":
            user_message = (
                "OpenAI API quota is unavailable. Add API billing or credits to the project, "
                "then restart Relay. A ChatGPT subscription does not supply API quota."
            )
        elif status_code == 429:
            user_message = "OpenAI rate limit reached. Wait briefly and try again."
        elif status_code == 404 or error_code == "model_not_found":
            user_message = (
                "The configured OpenAI model is not available to this project. "
                "Set OPENAI_MODEL to a model enabled for your API account."
            )
        elif status_code == 400:
            user_message = "OpenAI rejected the request format or model settings."
        else:
            user_message = f"OpenAI returned HTTP {status_code}. Please try again."

        diagnostic = provider_message or error_code or "No provider detail"
        return cls(
            f"OpenAI API returned HTTP {status_code}: {diagnostic}",
            user_message=user_message,
            status_code=status_code,
            error_code=error_code,
        )


def _default_transport(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise OpenAIAdapterError.from_http(error.code, detail) from error
    except urllib.error.URLError as error:
        raise OpenAIAdapterError(
            f"OpenAI API connection failed: {error.reason}",
            user_message="Relay could not reach the OpenAI API. Check the internet connection.",
        ) from error


class OpenAIResponsesAdapter(ModelAdapter):
    """Produces validated Relay decisions through the OpenAI Responses API."""

    endpoint = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 30.0,
        transport: Transport = _default_transport,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI adapter")
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def decide(self, context: ModelContext) -> ModelDecision:
        payload = {
            "model": self.model,
            "instructions": SYSTEM_INSTRUCTIONS,
            "input": json.dumps(
                {
                    "task_id": context.task_id,
                    "intent": context.intent,
                    "slots": context.slots,
                    "available_tools": context.available_tools,
                    "grounded_results": context.grounded_results,
                    "request_text": context.request_text,
                    "conversation_history": context.conversation_history,
                },
                ensure_ascii=False,
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "relay_decision",
                    "strict": True,
                    "schema": DECISION_SCHEMA,
                }
            },
            "store": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = await asyncio.to_thread(
            self.transport, self.endpoint, headers, payload, self.timeout_seconds
        )
        text = self._extract_output_text(response)
        try:
            raw_decision = json.loads(text)
            arguments = json.loads(raw_decision.get("arguments_json", "{}"))
        except (json.JSONDecodeError, TypeError) as error:
            raise OpenAIAdapterError("OpenAI returned invalid structured decision JSON") from error
        if not isinstance(arguments, dict):
            raise OpenAIAdapterError("OpenAI tool arguments must decode to an object")
        return ModelDecision.from_dict(
            {
                "kind": raw_decision.get("kind"),
                "text": raw_decision.get("text", ""),
                "tool_name": raw_decision.get("tool_name") or None,
                "arguments": arguments,
            }
        )

    @staticmethod
    def _extract_output_text(response: dict[str, Any]) -> str:
        if isinstance(response.get("output_text"), str):
            return response["output_text"]
        for item in response.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        raise OpenAIAdapterError("OpenAI response did not contain output text")
