import asyncio
import http.client
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from relay.web import (
    MAX_ACTION_HISTORY,
    RelayHTTPServer,
    RelayRequestHandler,
    RelaySessionRegistry,
    RelayWebRuntime,
)
import relay.web


class _FakeRuntime:
    def __init__(self):
        self.provider = "test"
        self.messages = []

    def status(self):
        return {
            "provider": "test",
            "build_version": "test",
            "snapshot": {},
            "action_count": 0,
        }

    def read_actions(self, after):
        return [], after

    def submit_text(self, text):
        self.messages.append(text)


class WebBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = _FakeRuntime()
        RelayRequestHandler.runtime = cls.runtime
        RelayRequestHandler.runtime_registry = None
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RelayRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=1)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        return response.status, payload

    def test_status_and_static_dashboard_are_served(self):
        status, payload = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["provider"], "test")

        status, payload = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Interruption impact engine", payload)
        self.assertIn(b"Ask anything. Interrupt at any time.", payload)
        self.assertIn(b"Live backend", payload)
        self.assertNotIn(b"Start Delhi plan", payload)
        self.assertNotIn(b"Run interruption demo", payload)

    def test_valid_message_is_accepted(self):
        body = json.dumps({"text": "Plan a trip"}).encode()
        status, _ = self.request(
            "POST",
            "/api/messages",
            body,
            {"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        self.assertEqual(status, 202)
        self.assertEqual(self.runtime.messages[-1], "Plan a trip")

    def test_empty_and_oversized_messages_are_rejected(self):
        body = b'{"text":""}'
        status, _ = self.request(
            "POST",
            "/api/messages",
            body,
            {"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        self.assertEqual(status, 400)

        body = b"x" * 50_001
        status, _ = self.request(
            "POST",
            "/api/messages",
            body,
            {"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        self.assertEqual(status, 400)

    def test_static_path_traversal_is_rejected(self):
        status, _ = self.request("GET", "/../pyproject.toml")
        self.assertEqual(status, 404)


class ActionRetentionTests(unittest.TestCase):
    def test_action_history_is_bounded_without_breaking_cursor(self):
        runtime = RelayWebRuntime.__new__(RelayWebRuntime)
        runtime.actions = []
        runtime._action_offset = 0
        runtime.latest_snapshot = {}
        runtime._lock = threading.Lock()

        total = MAX_ACTION_HISTORY + 7
        for index in range(total):
            runtime._record_action({"sequence": index}, None)

        actions, cursor = runtime.read_actions(0)
        self.assertEqual(len(actions), MAX_ACTION_HISTORY)
        self.assertEqual(actions[0]["sequence"], 7)
        self.assertEqual(cursor, total)


class RuntimeLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_action_collector_is_strongly_owned(self):
        class BlockingAgent:
            async def start(self):
                return None

            async def next_action(self, timeout):
                await asyncio.Future()

        runtime = RelayWebRuntime.__new__(RelayWebRuntime)
        runtime.agent = BlockingAgent()
        runtime._collector_task = None

        await runtime._start()
        try:
            self.assertIsNotNone(runtime._collector_task)
            self.assertFalse(runtime._collector_task.done())
        finally:
            runtime._collector_task.cancel()
            await asyncio.gather(runtime._collector_task, return_exceptions=True)


class SessionIsolationTests(unittest.TestCase):
    def test_browser_sessions_receive_independent_runtimes(self):
        created = []

        class FakeSession:
            def __init__(self):
                self.number = len(created)
                self.closed = False
                created.append(self)

            def close(self):
                self.closed = True

        registry = RelaySessionRegistry(factory=FakeSession, max_sessions=2)
        first = registry.get("11111111-1111-1111-1111-111111111111")
        same = registry.get("11111111-1111-1111-1111-111111111111")
        second = registry.get("22222222-2222-2222-2222-222222222222")

        self.assertIs(first, same)
        self.assertIsNot(first, second)

    def test_oldest_session_is_closed_when_registry_is_full(self):
        class FakeSession:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        registry = RelaySessionRegistry(factory=FakeSession, max_sessions=1)
        first = registry.get("11111111-1111-1111-1111-111111111111")
        registry.get("22222222-2222-2222-2222-222222222222")

        self.assertTrue(first.closed)


class ServerStartupSafetyTests(unittest.TestCase):
    def test_relay_server_disables_address_reuse(self):
        self.assertFalse(RelayHTTPServer.allow_reuse_address)

    def test_render_host_and_port_environment_are_supported(self):
        captured = {}

        class FakeServer:
            def __init__(self, address, handler):
                captured["address"] = address

            def serve_forever(self):
                raise KeyboardInterrupt

            def server_close(self):
                pass

        fake_runtime = _FakeRuntime()
        with (
            patch.dict(
                os.environ,
                {"RELAY_HOST": "0.0.0.0", "PORT": "10000"},
                clear=True,
            ),
            patch.object(relay.web, "RelayWebRuntime", return_value=fake_runtime),
            patch.object(relay.web, "RelayHTTPServer", FakeServer),
        ):
            relay.web.main()

        self.assertEqual(captured["address"], ("0.0.0.0", 10000))


if __name__ == "__main__":
    unittest.main()
