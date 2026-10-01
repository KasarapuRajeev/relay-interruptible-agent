"""Dependency-free local dashboard for demonstrating the Relay action stream."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import threading
import uuid
from collections import OrderedDict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .demo import MANIFEST
from .gemini_adapter import GeminiGenerateContentAdapter
from .integrations import calculate_expression, get_current_weather
from .models import DeterministicModelAdapter
from .openai_adapter import OpenAIResponsesAdapter
from .orchestrator import RelayAgent
from .protocol import Action, ActionType, EventType, InputEvent
from .research import search_wikipedia


WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
BUILD_VERSION = "2026.10.01.1"
MAX_ACTION_HISTORY = 2_000


class RelayHTTPServer(ThreadingHTTPServer):
    """Refuse duplicate listeners so a stale build cannot share Relay's port."""

    allow_reuse_address = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_EXCLUSIVEADDRUSE,
                1,
            )
        super().server_bind()


class RelayWebRuntime:
    def __init__(self) -> None:
        if os.environ.get("GEMINI_API_KEY"):
            self.provider = "Gemini"
            model = GeminiGenerateContentAdapter()
        elif os.environ.get("OPENAI_API_KEY"):
            self.provider = "OpenAI"
            model = OpenAIResponsesAdapter()
        else:
            self.provider = "Offline demo"
            model = DeterministicModelAdapter()
        self.agent = RelayAgent(model=model)
        self.agent.tools.load_manifest(MANIFEST)
        self.actions: list[dict[str, Any]] = []
        self._action_offset = 0
        self.latest_snapshot: dict[str, Any] = self.agent.snapshot.to_dict()
        self._lock = threading.Lock()
        self._loop = asyncio.new_event_loop()
        self._collector_task: asyncio.Task[None] | None = None
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self._start(), self._loop).result(timeout=5)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _start(self) -> None:
        await self.agent.start()
        self._collector_task = asyncio.create_task(self._collect_actions())

    def close(self) -> None:
        """Stop this session's agent and event loop when the session is evicted."""

        async def shutdown() -> None:
            await self.agent.close()
            if self._collector_task:
                self._collector_task.cancel()
                await asyncio.gather(self._collector_task, return_exceptions=True)

        try:
            asyncio.run_coroutine_threadsafe(shutdown(), self._loop).result(timeout=5)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=2)

    def submit_text(self, text: str) -> None:
        event = InputEvent(
            str(uuid.uuid4()),
            EventType.TRANSCRIPT_CHUNK,
            self.agent.clock(),
            {"text": text, "end_of_turn": True},
        )
        asyncio.run_coroutine_threadsafe(self.agent.submit(event), self._loop)

    def read_actions(self, after: int) -> tuple[list[dict[str, Any]], int]:
        with self._lock:
            start = max(0, after - self._action_offset)
            return (
                list(self.actions[start:]),
                self._action_offset + len(self.actions),
            )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "provider": self.provider,
                "build_version": BUILD_VERSION,
                "snapshot": dict(self.latest_snapshot),
                "action_count": self._action_offset + len(self.actions),
                "capabilities": [
                    {
                        "name": definition.name,
                        "description": definition.description,
                        "state_modifying": definition.state_modifying,
                    }
                    for definition in self.agent.tools.definitions.values()
                ],
            }

    def _record_action(
        self, action_data: dict[str, Any], snapshot: dict[str, Any] | None
    ) -> None:
        with self._lock:
            self.actions.append(action_data)
            excess = len(self.actions) - MAX_ACTION_HISTORY
            if excess > 0:
                del self.actions[:excess]
                self._action_offset += excess
            if snapshot is not None:
                self.latest_snapshot = snapshot

    async def _collect_actions(self) -> None:
        while True:
            action = await self.agent.next_action(timeout=3600)
            action_data = action.to_dict()
            snapshot = action.payload.get("state_snapshot")
            self._record_action(
                action_data,
                snapshot if isinstance(snapshot, dict) else None,
            )
            if action.type is ActionType.TOOL_CALL:
                asyncio.create_task(self._complete_demo_tool(action))

    async def _complete_demo_tool(self, action: Action) -> None:
        arguments = action.payload["arguments"]
        tool_name = action.payload["tool_name"]
        if tool_name == "search_travel":
            # Deterministic demo tools deliberately expose an interruption window.
            await asyncio.sleep(float(os.environ.get("RELAY_DEMO_TOOL_DELAY_SECONDS", "6")))
            destination = arguments.get("destination", "the destination")
            duration = arguments.get("duration_days") or 3
            budget = arguments.get("budget_inr")
            budget_text = f" within ₹{budget:,}" if isinstance(budget, int) else ""
            summary = (
                f"{destination} travel plan ({duration} days{budget_text})\n"
                f"Day 1: Arrival, old-city walk, and local dinner.\n"
                f"Day 2: Major landmarks, local transport, and cultural activity.\n"
                f"Day 3: Flexible morning, shopping or museum visit, then departure.\n"
                "Budget guardrail: compare transport and stays before booking; "
                "no reservation has been made in this demo."
            )
            result = {
                "summary": summary,
                "destination": destination,
                "budget_inr": budget,
                "duration_days": duration,
                "highlights": ["old-city walk", "major landmarks", "cultural activity"],
                "source": "deterministic_demo_tool",
            }
        elif tool_name == "build_study_plan":
            await asyncio.sleep(float(os.environ.get("RELAY_DEMO_TOOL_DELAY_SECONDS", "6")))
            subject = arguments.get("subject", "the requested subject")
            summary = (
                f"Study plan for {subject}\n"
                "Block 1 (45 min): Review concepts and create a one-page summary.\n"
                "Block 2 (60 min): Solve practice questions without notes.\n"
                "Block 3 (30 min): Check errors and revise weak areas.\n"
                "Final 15 min: Complete a timed self-test."
            )
            result = {
                "summary": summary,
                "subject": subject,
                "blocks": ["concept review", "practice", "self-test"],
                "source": "deterministic_demo_tool",
            }
        elif tool_name == "parallel_research":
            try:
                result = await asyncio.to_thread(
                    search_wikipedia,
                    str(arguments.get("topic", "")),
                    str(arguments.get("aspect", "overview")),
                )
            except Exception as error:
                await self.agent.submit(
                    InputEvent(
                        str(uuid.uuid4()),
                        EventType.TOOL_RESULT,
                        self.agent.clock(),
                        {"call_id": action.payload["call_id"], "error": str(error)},
                    )
                )
                return
        elif tool_name == "get_current_weather":
            try:
                result = await asyncio.to_thread(
                    get_current_weather,
                    str(arguments.get("location", "")),
                )
            except Exception as error:
                await self.agent.submit(
                    InputEvent(
                        str(uuid.uuid4()),
                        EventType.TOOL_RESULT,
                        self.agent.clock(),
                        {"call_id": action.payload["call_id"], "error": str(error)},
                    )
                )
                return
        elif tool_name == "calculate":
            try:
                result = calculate_expression(str(arguments.get("expression", "")))
            except Exception as error:
                await self.agent.submit(
                    InputEvent(
                        str(uuid.uuid4()),
                        EventType.TOOL_RESULT,
                        self.agent.clock(),
                        {"call_id": action.payload["call_id"], "error": str(error)},
                    )
                )
                return
        else:
            result = {
                "summary": "Completed the requested demo operation.",
                "source": "deterministic_demo_tool",
            }
        await self.agent.submit(
            InputEvent(
                str(uuid.uuid4()),
                EventType.TOOL_RESULT,
                self.agent.clock(),
                {
                    "call_id": action.payload["call_id"],
                    "summary": result["summary"],
                    "result": result,
                },
            )
        )


class RelaySessionRegistry:
    """Isolate browser sessions while keeping the dependency-free HTTP server."""

    def __init__(self, factory=RelayWebRuntime, max_sessions: int = 24) -> None:
        self.factory = factory
        self.max_sessions = max(1, max_sessions)
        self._sessions: OrderedDict[str, RelayWebRuntime] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, session_id: str) -> RelayWebRuntime:
        try:
            key = str(uuid.UUID(session_id))
        except (ValueError, AttributeError, TypeError):
            key = "default"
        evicted: RelayWebRuntime | None = None
        with self._lock:
            runtime = self._sessions.pop(key, None)
            if runtime is None:
                runtime = self.factory()
                if len(self._sessions) >= self.max_sessions:
                    _, evicted = self._sessions.popitem(last=False)
            self._sessions[key] = runtime
        if evicted is not None:
            evicted.close()
        return runtime


class RelayRequestHandler(BaseHTTPRequestHandler):
    runtime: RelayWebRuntime
    runtime_registry: RelaySessionRegistry | None = None

    def _runtime(self) -> RelayWebRuntime:
        if self.runtime_registry is None:
            return self.runtime
        return self.runtime_registry.get(self.headers.get("X-Relay-Session", ""))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            self._json(HTTPStatus.OK, self._runtime().status())
            return
        if parsed.path == "/api/actions":
            try:
                after = max(0, int(parse_qs(parsed.query).get("after", ["0"])[0]))
            except ValueError:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "after must be an integer"})
                return
            actions, cursor = self._runtime().read_actions(after)
            self._json(HTTPStatus.OK, {"actions": actions, "cursor": cursor})
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/messages":
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 50_000:
                raise ValueError("Request is too large")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            text = str(body.get("text", "")).strip()
            if not text:
                raise ValueError("Message text is required")
        except (ValueError, json.JSONDecodeError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._runtime().submit_text(text)
        self._json(HTTPStatus.ACCEPTED, {"accepted": True})

    def _serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path == "/" else request_path.lstrip("/")
        candidate = (WEB_ROOT / relative).resolve()
        try:
            candidate.relative_to(WEB_ROOT.resolve())
        except ValueError:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        if not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_types.get(candidate.suffix, "application/octet-stream"))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    RelayRequestHandler.runtime_registry = RelaySessionRegistry()
    host = os.environ.get("RELAY_HOST", "127.0.0.1")
    port = int(os.environ.get("RELAY_PORT") or os.environ.get("PORT", "8000"))
    try:
        server = RelayHTTPServer((host, port), RelayRequestHandler)
    except OSError as error:
        raise SystemExit(
            f"Relay could not start because port {port} is already in use. "
            "Stop the older Relay server or set RELAY_PORT to a free port."
        ) from error
    display_host = "127.0.0.1" if host == "0.0.0.0" else host
    print(f"Relay dashboard running at http://{display_host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
