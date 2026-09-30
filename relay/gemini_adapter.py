"""Gemini GenerateContent adapter for Relay's provider-neutral model contract."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .models import ModelAdapter, ModelContext, ModelDecision
from .openai_adapter import DECISION_SCHEMA, SYSTEM_INSTRUCTIONS


Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


class GeminiAdapterError(RuntimeError):
    """Raised when Gemini cannot return a valid Relay decision."""

    def __init__(
        self,
        message: str,
        *,
        user_message: str | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.user_message = user_message or "The Gemini request failed. Please try again."
        self.status_code = status_code
        self.error_code = error_code

    @classmethod
    def from_http(cls, status_code: int, detail: str) -> "GeminiAdapterError":
        error_code = None
        provider_message = ""
        try:
            error_data = json.loads(detail).get("error", {})
            error_code = str(error_data.get("status") or error_data.get("code") or "")
            provider_message = str(error_data.get("message", ""))
        except (json.JSONDecodeError, AttributeError):
            provider_message = detail[:300]

        if status_code in (401, 403):
            user_message = (
                "Gemini authentication failed. Create a Gemini API key in Google AI Studio "
                "and make sure it is enabled for the Gemini API."
            )
        elif status_code == 429:
            user_message = "Gemini free-tier rate limit reached. Wait for the quota window and retry."
        elif status_code == 404:
            user_message = "The configured Gemini model is unavailable. Check GEMINI_MODEL."
        elif status_code == 400:
            user_message = "Gemini rejected the request or model configuration."
        else:
            user_message = f"Gemini returned HTTP {status_code}. Please try again."
        diagnostic = provider_message or error_code or "No provider detail"
        return cls(
            f"Gemini API returned HTTP {status_code}: {diagnostic}",
            user_message=user_message,
            status_code=status_code,
            error_code=error_code or None,
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
        raise GeminiAdapterError.from_http(error.code, detail) from error
    except urllib.error.URLError as error:
        raise GeminiAdapterError(
            f"Gemini API connection failed: {error.reason}",
            user_message="Relay could not reach the Gemini API. Check the internet connection.",
        ) from error


class GeminiGenerateContentAdapter(ModelAdapter):
    """Produces validated Relay decisions through Gemini structured output."""

    endpoint_template = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 30.0,
        retry_delays: tuple[float, ...] = (0.5, 1.0),
        transport: Transport = _default_transport,
    ) -> None:
        self.api_key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is required for the Gemini adapter")
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
        self.timeout_seconds = timeout_seconds
        self.retry_delays = retry_delays
        self.transport = transport

    async def decide(self, context: ModelContext) -> ModelDecision:
        input_data = {
            "task_id": context.task_id,
            "intent": context.intent,
            "slots": context.slots,
            "available_tools": context.available_tools,
            "grounded_results": context.grounded_results,
            "request_text": context.request_text,
            "conversation_history": context.conversation_history,
        }
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTIONS}]},
            "contents": [
                {"role": "user", "parts": [{"text": json.dumps(input_data, ensure_ascii=False)}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": DECISION_SCHEMA,
            },
        }
        response = await self._request_with_retry(payload)
        text = self._extract_text(response)
        try:
            raw_decision = json.loads(text)
            arguments = json.loads(raw_decision.get("arguments_json", "{}"))
        except (json.JSONDecodeError, TypeError) as error:
            raise GeminiAdapterError("Gemini returned invalid structured decision JSON") from error
        if not isinstance(arguments, dict):
            raise GeminiAdapterError("Gemini tool arguments must decode to an object")
        return ModelDecision.from_dict(
            {
                "kind": raw_decision.get("kind"),
                "text": raw_decision.get("text", ""),
                "tool_name": raw_decision.get("tool_name") or None,
                "arguments": arguments,
            }
        )

    async def _request_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        models = list(dict.fromkeys((self.model, "gemini-3.1-flash-lite")))
        last_error: GeminiAdapterError | None = None
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        for model_index, model in enumerate(models):
            delays = self.retry_delays if model_index == 0 else ()
            for attempt in range(len(delays) + 1):
                try:
                    return await asyncio.to_thread(
                        self.transport,
                        self.endpoint_template.format(model=model),
                        headers,
                        payload,
                        self.timeout_seconds,
                    )
                except GeminiAdapterError as error:
                    last_error = error
                    if error.status_code != 503:
                        raise
                    if attempt < len(delays):
                        await asyncio.sleep(delays[attempt])
            # A configured non-Lite model gets one final attempt on Flash-Lite.
        if last_error is not None:
            raise GeminiAdapterError(
                str(last_error),
                user_message=(
                    "Gemini is temporarily overloaded. Relay retried automatically; "
                    "please wait briefly and submit the request again."
                ),
                status_code=last_error.status_code,
                error_code=last_error.error_code,
            ) from last_error
        raise GeminiAdapterError("Gemini request failed before reaching the provider")

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        try:
            parts = response["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as error:
            raise GeminiAdapterError("Gemini response did not contain output text") from error
        if not text:
            raise GeminiAdapterError("Gemini response did not contain output text")
        return text
