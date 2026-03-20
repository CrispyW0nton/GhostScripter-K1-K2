#!/usr/bin/env python3
"""
test_ipc_server.py — Tests for the GhostScripter IPC server (port 7002)
                     and GModular / GhostRigger client functions.

Updated for v2.4.0 API:
  - IPCServer class (was GhostScripterIPCServer) in ipc_server.py
  - GHOSTSCRIPTER_PORT constant (was GHOSTSCRIPTER_IPC_PORT)
  - drain_event_queue() module-level function
  - Module-level client functions in gmodular_client.py
"""
import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ghostscripter.ipc.ipc_server import (
    IPCServer,
    GHOSTSCRIPTER_PORT,
    drain_event_queue,
    _push_event,
    _event_queue,
)
import ghostscripter.ipc.gmodular_client as gm
from ghostscripter.ipc.ghostrigger_bridge import GHOSTRIGGER_PORT
from ghostscripter.ipc.gmodular_client import GMODULAR_PORT


# ── Backwards-compat alias used in a few places ───────────────────────────────
GhostScripterIPCServer = IPCServer
GHOSTSCRIPTER_IPC_PORT = GHOSTSCRIPTER_PORT


class TestIPCPorts(unittest.TestCase):
    """Verify blueprint port constants match specification."""

    def test_ghostrigger_port(self):
        self.assertEqual(GHOSTRIGGER_PORT, 7001)

    def test_ghostscripter_port(self):
        self.assertEqual(GHOSTSCRIPTER_PORT, 7002)

    def test_gmodular_port(self):
        self.assertEqual(GMODULAR_PORT, 7003)


class TestIPCEventQueue(unittest.TestCase):
    """Test the module-level event queue used by the Flask routes."""

    def setUp(self):
        # Drain any leftover events from previous tests
        drain_event_queue()

    def test_push_and_drain(self):
        _push_event("open_script", {"resref": "k_test"})
        events = drain_event_queue()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "open_script")
        self.assertEqual(events[0][1]["resref"], "k_test")

    def test_drain_empty_queue(self):
        events = drain_event_queue()
        self.assertEqual(events, [])

    def test_drain_multiple_events(self):
        _push_event("open_script", {"resref": "a"})
        _push_event("open_dlg",    {"resref": "b"})
        _push_event("open_tlk",    {"strref": 42})
        events = drain_event_queue()
        self.assertEqual(len(events), 3)
        kinds = [e[0] for e in events]
        self.assertIn("open_script", kinds)
        self.assertIn("open_dlg", kinds)
        self.assertIn("open_tlk", kinds)

    def test_drain_clears_queue(self):
        _push_event("open_2da", {"table": "appearance", "row": 10})
        drain_event_queue()
        events = drain_event_queue()
        self.assertEqual(events, [])


class TestIPCServer(unittest.TestCase):
    """Test the IPCServer wrapper class."""

    def setUp(self):
        drain_event_queue()

    def test_instantiation(self):
        srv = IPCServer(port=GHOSTSCRIPTER_PORT)
        self.assertEqual(srv.port, GHOSTSCRIPTER_PORT)

    def test_available_when_flask_installed(self):
        srv = IPCServer()
        try:
            import flask  # noqa
            self.assertTrue(srv.available)
        except ImportError:
            self.assertFalse(srv.available)

    def test_stop_before_start_no_error(self):
        srv = IPCServer()
        srv.stop()  # should not raise


class TestIPCFlaskApp(unittest.TestCase):
    """Test the Flask app routes if Flask is available."""

    @classmethod
    def setUpClass(cls):
        try:
            import flask  # noqa
            cls._has_flask = True
        except ImportError:
            cls._has_flask = False

    def setUp(self):
        if not self._has_flask:
            self.skipTest("Flask not installed")
        drain_event_queue()  # clear queue before each test

    def _make_client(self):
        """Build the Flask test client using the module-level app factory."""
        from ghostscripter.ipc.ipc_server import _build_flask_app
        app = _build_flask_app()
        app.config["TESTING"] = True
        return app.test_client()

    # ── ping ─────────────────────────────────────────────────────────────────

    def test_ping_get(self):
        client = self._make_client()
        resp = client.get("/api/ping")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "ok")

    def test_ping_contains_program(self):
        client = self._make_client()
        resp = client.get("/api/ping")
        data = resp.get_json()
        self.assertIn("program", data["payload"])
        self.assertEqual(data["payload"]["program"], "GhostScripter")

    def test_ping_post(self):
        client = self._make_client()
        resp = client.post("/api/ping", json={})
        self.assertEqual(resp.status_code, 200)

    # ── status ────────────────────────────────────────────────────────────────

    def test_status(self):
        client = self._make_client()
        resp = client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "running")

    def test_status_contains_port(self):
        client = self._make_client()
        resp = client.get("/api/status")
        data = resp.get_json()
        self.assertEqual(data["port"], GHOSTSCRIPTER_PORT)

    # ── open_script ──────────────────────────────────────────────────────────

    def test_open_script_queued(self):
        client = self._make_client()
        resp = client.post("/api/open_script", json={
            "resref": "k_npc_on_spawn",
            "slot": "OnSpawn",
            "object_tag": "k_npc_001",
        })
        self.assertEqual(resp.status_code, 200)
        events = drain_event_queue()
        self.assertEqual(len(events), 1)
        kind, payload = events[0]
        self.assertEqual(kind, "open_script")
        self.assertEqual(payload["resref"], "k_npc_on_spawn")
        self.assertEqual(payload["slot"], "OnSpawn")

    def test_open_script_missing_resref(self):
        client = self._make_client()
        resp = client.post("/api/open_script", json={})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["status"], "error")

    def test_open_script_accepts_envelope(self):
        """Standard blueprint envelope wrapper should be accepted."""
        client = self._make_client()
        resp = client.post("/api/open_script", json={
            "version": "1.0",
            "sender": "GModular",
            "action": "open_script",
            "payload": {"resref": "k_test_script"},
        })
        self.assertEqual(resp.status_code, 200)
        events = drain_event_queue()
        self.assertEqual(events[0][1]["resref"], "k_test_script")

    # ── open_dlg ──────────────────────────────────────────────────────────────

    def test_open_dlg_queued(self):
        client = self._make_client()
        resp = client.post("/api/open_dlg", json={"resref": "k_npc_dlg"})
        self.assertEqual(resp.status_code, 200)
        events = drain_event_queue()
        kind, payload = events[0]
        self.assertEqual(kind, "open_dlg")
        self.assertEqual(payload["resref"], "k_npc_dlg")

    def test_open_dlg_missing_resref(self):
        client = self._make_client()
        resp = client.post("/api/open_dlg", json={})
        self.assertEqual(resp.status_code, 400)

    # ── open_2da ──────────────────────────────────────────────────────────────

    def test_open_2da_queued(self):
        client = self._make_client()
        resp = client.post("/api/open_2da", json={
            "table": "appearance",
            "row": 147,
        })
        self.assertEqual(resp.status_code, 200)
        events = drain_event_queue()
        kind, payload = events[0]
        self.assertEqual(kind, "open_2da")
        self.assertEqual(payload["table"], "appearance")
        self.assertEqual(payload["row"], 147)

    def test_open_2da_missing_table(self):
        client = self._make_client()
        resp = client.post("/api/open_2da", json={})
        self.assertEqual(resp.status_code, 400)

    # ── open_tlk ──────────────────────────────────────────────────────────────

    def test_open_tlk_queued(self):
        client = self._make_client()
        resp = client.post("/api/open_tlk", json={"strref": 42001, "game": "k1"})
        self.assertEqual(resp.status_code, 200)
        events = drain_event_queue()
        kind, payload = events[0]
        self.assertEqual(kind, "open_tlk")
        self.assertEqual(payload["strref"], 42001)

    def test_open_tlk_defaults(self):
        client = self._make_client()
        resp = client.post("/api/open_tlk", json={})
        self.assertEqual(resp.status_code, 200)


class TestGModularClientFunctions(unittest.TestCase):
    """Test module-level GModular/GhostRigger client functions (no real HTTP)."""

    def test_notify_script_compiled_no_server(self):
        """notify_script_compiled should return (False, err) gracefully."""
        ok, err = gm.notify_script_compiled("k_test", "on_spawn", "K_NPC_001")
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(err, str)
        # No server running: should be False
        self.assertFalse(ok)

    def test_ping_gmodular_no_server(self):
        ok, err = gm.ping_gmodular()
        self.assertFalse(ok)
        self.assertIsInstance(err, str)

    def test_ping_ghostrigger_no_server(self):
        ok, err = gm.ping_ghostrigger()
        self.assertFalse(ok)
        self.assertIsInstance(err, str)

    def test_open_utc_no_server(self):
        ok, err = gm.open_utc_in_rigger("c_rodian")
        self.assertFalse(ok)

    def test_gmodular_port_constant(self):
        self.assertEqual(gm.GMODULAR_PORT, 7003)

    def test_ghostrigger_port_constant(self):
        self.assertEqual(gm.GHOSTRIGGER_PORT, 7001)

    def test_ipc_timeout_constant(self):
        self.assertIsInstance(gm.IPC_TIMEOUT, float)
        self.assertGreater(gm.IPC_TIMEOUT, 0)


if __name__ == "__main__":
    unittest.main()
