#!/usr/bin/env python3
"""
test_integration_pipeline.py — Phase-2 integration tests for the
                                GhostWorks IPC pipeline.

Tests the full GhostRigger (7001) → GhostScripter (7002) → GModular (7003)
message flow using real Flask test clients and mock HTTP endpoints.

Architecture under test
-----------------------
  GhostScripter IPC server (port 7002) — receives requests from GR / GM
  GhostScripter IPC client (port 7001 / 7003) — fires requests to GR / GM

Key flows validated
-------------------
  1.  GR → GS: open_script, open_dlg, open_2da, open_tlk
  2.  GS → GM: notify_script_compiled, notify_gmodular_refresh, ping_gmodular
  3.  GS → GR: open_utc_in_rigger, open_utp_in_rigger, ping_ghostrigger
  4.  Event queue: push / drain cycle
  5.  Port constants satisfy the blueprint spec
  6.  Client timeout / connection-refused returns False gracefully
"""
from __future__ import annotations

import json
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Import the modules under test ─────────────────────────────────────────────

from ghostscripter.ipc.server import (
    GHOSTSCRIPTER_PORT, _push_event, drain_event_queue, _build_flask_app,
    _event_queue, IPCServer,
)
from ghostscripter.ipc.gmodular_client import (
    GHOSTRIGGER_PORT, GMODULAR_PORT,
    notify_script_compiled, notify_gmodular_refresh, ping_gmodular,
    open_utc_in_rigger, open_utp_in_rigger, open_utd_in_rigger,
    open_mdl_in_rigger, ping_ghostrigger,
)


# ── Shared Flask test client fixture ──────────────────────────────────────────

def _get_flask_client():
    """Return a Flask test client for the GhostScripter IPC server."""
    app = _build_flask_app()
    if app is None:
        return None
    app.config["TESTING"] = True
    return app.test_client()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Port constants
# ═══════════════════════════════════════════════════════════════════════════════

class TestPortConstants(unittest.TestCase):

    def test_ghostrigger_port(self):
        self.assertEqual(GHOSTRIGGER_PORT, 7001)

    def test_ghostscripter_port(self):
        self.assertEqual(GHOSTSCRIPTER_PORT, 7002)

    def test_gmodular_port(self):
        self.assertEqual(GMODULAR_PORT, 7003)

    def test_ports_distinct(self):
        ports = {GHOSTRIGGER_PORT, GHOSTSCRIPTER_PORT, GMODULAR_PORT}
        self.assertEqual(len(ports), 3)

    def test_ports_in_7000_range(self):
        for p in (GHOSTRIGGER_PORT, GHOSTSCRIPTER_PORT, GMODULAR_PORT):
            self.assertGreaterEqual(p, 7000)
            self.assertLess(p, 8000)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Event queue (server-side threading bridge)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventQueue(unittest.TestCase):

    def setUp(self):
        # Drain any leftover events from previous tests
        drain_event_queue()

    def test_push_and_drain_single_event(self):
        _push_event("open_script", {"resref": "my_script"})
        events = drain_event_queue()
        self.assertEqual(len(events), 1)
        kind, payload = events[0]
        self.assertEqual(kind, "open_script")
        self.assertEqual(payload["resref"], "my_script")

    def test_drain_empty_queue(self):
        events = drain_event_queue()
        self.assertEqual(events, [])

    def test_push_multiple_events(self):
        _push_event("open_script", {"resref": "a"})
        _push_event("open_dlg",    {"resref": "b"})
        _push_event("open_2da",    {"table": "appearance"})
        events = drain_event_queue()
        self.assertEqual(len(events), 3)
        kinds = [e[0] for e in events]
        self.assertEqual(kinds, ["open_script", "open_dlg", "open_2da"])

    def test_drain_clears_queue(self):
        _push_event("open_tlk", {"strref": 100})
        drain_event_queue()
        # Second drain must be empty
        self.assertEqual(drain_event_queue(), [])

    def test_queue_thread_safety(self):
        """Push from multiple threads; all events must be drained."""
        results = []
        def pusher(n):
            for i in range(10):
                _push_event("test", {"i": i, "n": n})

        threads = [threading.Thread(target=pusher, args=(n,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        events = drain_event_queue()
        self.assertEqual(len(events), 50)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. GS IPC server — Flask endpoints (GR→GS direction)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIPCServerFlask(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = _get_flask_client()

    def setUp(self):
        drain_event_queue()

    def _post(self, path: str, payload: dict) -> dict:
        resp = self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )
        return resp.get_json(), resp.status_code

    # ── /api/ping ──────────────────────────────────────────────────────────────

    def test_ping_get(self):
        if self.client is None:
            self.skipTest("Flask not installed")
        resp = self.client.get("/api/ping")
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["action"], "ping")

    def test_ping_post(self):
        if self.client is None:
            self.skipTest("Flask not installed")
        data, code = self._post("/api/ping", {})
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["payload"]["program"], "GhostScripter")
        self.assertEqual(data["payload"]["port"], GHOSTSCRIPTER_PORT)

    # ── /api/open_script ──────────────────────────────────────────────────────

    def test_open_script_valid(self):
        if self.client is None:
            self.skipTest("Flask not installed")
        payload = {
            "payload": {
                "resref":     "c_rodian_sp",
                "module_dir": "C:/KotOR/modules/dantooine",
                "slot":       "on_spawn",
                "object_tag": "RODIAN_01",
            }
        }
        data, code = self._post("/api/open_script", payload)
        self.assertEqual(code, 200)
        self.assertEqual(data["status"], "ok")
        events = drain_event_queue()
        self.assertEqual(len(events), 1)
        kind, ep = events[0]
        self.assertEqual(kind, "open_script")
        self.assertEqual(ep["resref"], "c_rodian_sp")
        self.assertEqual(ep["slot"], "on_spawn")

    def test_open_script_bare_payload(self):
        """Server must also accept bare (non-wrapped) payloads."""
        if self.client is None:
            self.skipTest("Flask not installed")
        data, code = self._post("/api/open_script",
                                 {"resref": "bare_script"})
        self.assertEqual(code, 200)
        events = drain_event_queue()
        self.assertEqual(events[0][1]["resref"], "bare_script")

    def test_open_script_missing_resref(self):
        if self.client is None:
            self.skipTest("Flask not installed")
        data, code = self._post("/api/open_script", {"payload": {}})
        self.assertEqual(code, 400)
        self.assertEqual(data["status"], "error")

    # ── /api/open_dlg ─────────────────────────────────────────────────────────

    def test_open_dlg_valid(self):
        if self.client is None:
            self.skipTest("Flask not installed")
        data, code = self._post("/api/open_dlg",
                                 {"payload": {"resref": "dan13_01"}})
        self.assertEqual(code, 200)
        events = drain_event_queue()
        self.assertEqual(events[0][1]["resref"], "dan13_01")

    def test_open_dlg_missing_resref(self):
        if self.client is None:
            self.skipTest("Flask not installed")
        data, code = self._post("/api/open_dlg", {"payload": {}})
        self.assertEqual(code, 400)

    # ── /api/open_2da ─────────────────────────────────────────────────────────

    def test_open_2da_valid(self):
        if self.client is None:
            self.skipTest("Flask not installed")
        data, code = self._post("/api/open_2da",
                                 {"payload": {"table": "appearance", "row": 42}})
        self.assertEqual(code, 200)
        events = drain_event_queue()
        kind, ep = events[0]
        self.assertEqual(kind, "open_2da")
        self.assertEqual(ep["table"], "appearance")
        self.assertEqual(ep["row"], 42)

    def test_open_2da_missing_table(self):
        if self.client is None:
            self.skipTest("Flask not installed")
        data, code = self._post("/api/open_2da", {"payload": {}})
        self.assertEqual(code, 400)

    # ── /api/open_tlk ─────────────────────────────────────────────────────────

    def test_open_tlk_valid(self):
        if self.client is None:
            self.skipTest("Flask not installed")
        data, code = self._post("/api/open_tlk",
                                 {"payload": {"strref": 1234, "game": "K1"}})
        self.assertEqual(code, 200)
        events = drain_event_queue()
        kind, ep = events[0]
        self.assertEqual(kind, "open_tlk")
        self.assertEqual(ep["strref"], 1234)
        self.assertEqual(ep["game"], "K1")

    def test_open_tlk_no_strref_defaults_zero(self):
        """open_tlk with no strref defaults to 0 -- server returns 200."""
        if self.client is None:
            self.skipTest("Flask not installed")
        data, code = self._post("/api/open_tlk", {"payload": {}})
        # Server defaults strref=0 and accepts it
        self.assertEqual(code, 200)
        events = drain_event_queue()
        self.assertEqual(events[0][1]["strref"], 0)

    # ── /api/status ───────────────────────────────────────────────────────────

    def test_status_endpoint(self):
        if self.client is None:
            self.skipTest("Flask not installed")
        resp = self.client.get("/api/status")
        data = resp.get_json()
        self.assertIn("program",  data)
        self.assertIn("port",     data)
        self.assertIn("version",  data)
        # status field carries the string "running" (not a nested bool key)
        self.assertEqual(data.get("status"), "running")
        self.assertEqual(data["port"], GHOSTSCRIPTER_PORT)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. IPCServer class
# ═══════════════════════════════════════════════════════════════════════════════

class TestIPCServerClass(unittest.TestCase):

    def test_default_port(self):
        srv = IPCServer()
        self.assertEqual(srv.port, GHOSTSCRIPTER_PORT)

    def test_custom_port(self):
        srv = IPCServer(port=9999)
        self.assertEqual(srv.port, 9999)

    def test_not_running_before_start(self):
        srv = IPCServer()
        self.assertFalse(srv._running)

    def test_drain_events_no_main_window(self):
        """Module-level drain_event_queue() must not crash."""
        drain_event_queue()  # clear queue
        _push_event("open_script", {"resref": "test"})
        try:
            events = drain_event_queue()  # must not raise
            self.assertEqual(len(events), 1)
        except Exception as exc:
            self.fail(f"drain_event_queue() raised {exc!r}")

    def test_start_creates_thread(self):
        srv = IPCServer()
        srv.start()
        time.sleep(0.15)
        self.assertTrue(srv._running)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GS IPC client — GS→GM direction (mocked HTTP)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIPCClientGModular(unittest.TestCase):
    """Test client functions that talk to GModular (port 7003)."""

    def _mock_ok_response(self):
        """A requests.Response-like mock that looks like HTTP 200."""
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {"status": "ok"}
        return mock

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_notify_script_compiled_success(self, mock_requests):
        mock_requests.post.return_value = self._mock_ok_response()
        mock_requests.exceptions.ConnectionError = ConnectionError
        ok, msg = notify_script_compiled("my_script", slot="on_spawn",
                                          object_tag="RODIAN_01")
        self.assertTrue(ok)
        called_url = mock_requests.post.call_args[0][0]
        self.assertIn(str(GMODULAR_PORT), called_url)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_notify_script_compiled_payload(self, mock_requests):
        mock_requests.post.return_value = self._mock_ok_response()
        mock_requests.exceptions.ConnectionError = ConnectionError
        notify_script_compiled("abc", slot="on_death", object_tag="NPC_01")
        body_str = str(mock_requests.post.call_args)
        self.assertIn("abc", body_str)
        self.assertIn("on_death", body_str)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_notify_script_compiled_connection_refused(self, mock_requests):
        mock_requests.post.side_effect = ConnectionRefusedError("refused")
        mock_requests.exceptions.ConnectionError = ConnectionError
        ok, msg = notify_script_compiled("xyz")
        self.assertFalse(ok)
        self.assertIsInstance(msg, str)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_ping_gmodular_success(self, mock_requests):
        mock_resp = self._mock_ok_response()
        mock_resp.json.return_value = {"status": "ok", "program": "GModular"}
        mock_requests.get.return_value = mock_resp
        mock_requests.exceptions.ConnectionError = ConnectionError
        ok, msg = ping_gmodular()
        self.assertTrue(ok)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_ping_gmodular_refused(self, mock_requests):
        mock_requests.get.side_effect = ConnectionRefusedError()
        ok, msg = ping_gmodular()
        self.assertFalse(ok)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_notify_gmodular_refresh(self, mock_requests):
        mock_requests.post.return_value = self._mock_ok_response()
        mock_requests.exceptions.ConnectionError = ConnectionError
        ok, msg = notify_gmodular_refresh()
        self.assertTrue(ok)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. GS IPC client — GS→GR direction (mocked HTTP)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIPCClientGhostRigger(unittest.TestCase):
    """Test client functions that talk to GhostRigger (port 7001)."""

    def _mock_ok(self):
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {"status": "ok", "version": "1.0.0"}
        return mock

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_open_utc_in_rigger_success(self, mock_requests):
        mock_requests.post.return_value = self._mock_ok()
        mock_requests.exceptions.ConnectionError = ConnectionError
        ok, msg = open_utc_in_rigger("c_rodian")
        self.assertTrue(ok)
        url = mock_requests.post.call_args[0][0]
        self.assertIn(str(GHOSTRIGGER_PORT), url)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_open_utc_in_rigger_refused(self, mock_requests):
        mock_requests.post.side_effect = ConnectionRefusedError()
        mock_requests.exceptions.ConnectionError = ConnectionError
        ok, msg = open_utc_in_rigger("c_rodian")
        self.assertFalse(ok)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_open_utp_in_rigger(self, mock_requests):
        mock_requests.post.return_value = self._mock_ok()
        mock_requests.exceptions.ConnectionError = ConnectionError
        ok, _ = open_utp_in_rigger("plc_footlocker")
        self.assertTrue(ok)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_open_utd_in_rigger(self, mock_requests):
        mock_requests.post.return_value = self._mock_ok()
        mock_requests.exceptions.ConnectionError = ConnectionError
        ok, _ = open_utd_in_rigger("door_airlock")
        self.assertTrue(ok)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_open_mdl_in_rigger(self, mock_requests):
        mock_requests.post.return_value = self._mock_ok()
        mock_requests.exceptions.ConnectionError = ConnectionError
        ok, _ = open_mdl_in_rigger("p_bastila")
        self.assertTrue(ok)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_ping_ghostrigger_success(self, mock_requests):
        mock_requests.get.return_value = self._mock_ok()
        ok, msg = ping_ghostrigger()
        self.assertTrue(ok)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_ping_ghostrigger_refused(self, mock_requests):
        mock_requests.get.side_effect = ConnectionRefusedError()
        ok, msg = ping_ghostrigger()
        self.assertFalse(ok)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Full GR→GS→GM round-trip (mock GModular; real Flask server test client)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullPipeline(unittest.TestCase):
    """
    Simulates the complete pipeline:
      GhostRigger sends open_script → GhostScripter IPC server queues event
      → drain_event_queue returns event
      → GhostScripter notifies GModular (mocked HTTP)
    """

    @classmethod
    def setUpClass(cls):
        cls.flask_client = _get_flask_client()

    def setUp(self):
        drain_event_queue()

    def _gs_receive(self, action: str, payload: dict) -> dict:
        resp = self.flask_client.post(
            f"/api/{action}",
            data=json.dumps({"payload": payload}),
            content_type="application/json",
        )
        return resp.get_json()

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_notify_script_compiled_success(self, mock_requests):
        if self.flask_client is None:
            self.skipTest("Flask not available")

        mock_requests.post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"status": "ok"})
        )
        mock_requests.exceptions.ConnectionError = ConnectionError

        # Step 1: GhostRigger sends open_script to GhostScripter
        resp = self._gs_receive("open_script", {
            "resref": "c_bastila_sp",
            "slot":   "on_spawn",
            "object_tag": "BASTILA",
        })
        self.assertEqual(resp["status"], "ok")

        # Step 2: GhostScripter drains the event
        events = drain_event_queue()
        self.assertEqual(len(events), 1)
        kind, ep = events[0]
        self.assertEqual(kind, "open_script")
        self.assertEqual(ep["resref"], "c_bastila_sp")

        # Step 3: After compiling, GhostScripter notifies GModular
        ok, _ = notify_script_compiled(
            ep["resref"], slot=ep["slot"], object_tag=ep["object_tag"]
        )
        self.assertTrue(ok)
        url = mock_requests.post.call_args[0][0]
        self.assertIn(str(GMODULAR_PORT), url)

    @patch("ghostscripter.ipc.gmodular_client.requests")
    def test_open_dlg_pipeline(self, mock_requests):
        if self.flask_client is None:
            self.skipTest("Flask not available")

        mock_requests.post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"status": "ok"})
        )
        mock_requests.exceptions.ConnectionError = ConnectionError

        resp = self._gs_receive("open_dlg", {
            "resref":     "dan13_carth",
            "module_dir": "C:/KotOR/modules",
        })
        self.assertEqual(resp["status"], "ok")

        events = drain_event_queue()
        self.assertEqual(events[0][0], "open_dlg")
        self.assertEqual(events[0][1]["resref"], "dan13_carth")

    def test_open_2da_pipeline(self):
        if self.flask_client is None:
            self.skipTest("Flask not available")

        resp = self._gs_receive("open_2da", {
            "table": "appearance",
            "row":   999,
        })
        self.assertEqual(resp["status"], "ok")

        events = drain_event_queue()
        kind, ep = events[0]
        self.assertEqual(kind, "open_2da")
        self.assertEqual(ep["table"], "appearance")
        self.assertEqual(ep["row"], 999)

    def test_open_tlk_pipeline(self):
        if self.flask_client is None:
            self.skipTest("Flask not available")

        resp = self._gs_receive("open_tlk", {
            "strref": 30000,
            "game":   "K2",
        })
        self.assertEqual(resp["status"], "ok")

        events = drain_event_queue()
        kind, ep = events[0]
        self.assertEqual(kind, "open_tlk")
        self.assertEqual(ep["strref"], 30000)


if __name__ == "__main__":
    unittest.main()
