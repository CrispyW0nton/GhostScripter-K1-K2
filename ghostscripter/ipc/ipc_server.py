"""
GhostScripter-K1-K2 — IPC Server (port 7002)
=============================================
Blueprint: GHOSTWORKS_BLUEPRINT.md §3

Runs a Flask HTTP server in a background daemon thread.
Receives JSON POST requests from GhostRigger (7001) and GModular (7003).

Supported endpoints
-------------------
POST /api/open_script  — open a .nss file in the script editor
POST /api/open_dlg     — open a .dlg file in the dialogue editor
POST /api/open_2da     — jump to a specific 2DA table + row
POST /api/open_tlk     — jump to a specific TLK StrRef
POST /api/ping         — connectivity check

Request envelope (all actions):
    {
        "version": "1.0",
        "sender": "GModular",
        "action": "open_script",
        "payload": { ... action-specific fields ... }
    }

Response envelope:
    { "status": "ok",    "action": "open_script", "payload": {} }
    { "status": "error", "action": "open_script", "message": "..." }
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Dict, Any

log = logging.getLogger(__name__)

from ghostscripter.ipc.ports import GHOSTSCRIPTER_REST as GHOSTSCRIPTER_PORT  # noqa: E402


# ── Qt signal bridge ──────────────────────────────────────────────────────────
# Flask runs in a thread; Qt widgets must only be touched on the main thread.
# We bridge via a thread-safe queue + QTimer drain (same pattern as the
# GhostRigger client bridge).

import queue as _queue

_event_queue: _queue.Queue = _queue.Queue()


def _push_event(kind: str, payload: dict):
    """Called from Flask thread — put event onto the queue."""
    _event_queue.put((kind, payload))


def drain_event_queue() -> list[tuple[str, dict]]:
    """
    Called from the main thread (e.g. via QTimer).
    Returns all pending events and clears the queue.
    """
    events = []
    try:
        while True:
            events.append(_event_queue.get_nowait())
    except _queue.Empty:
        pass
    return events


# ── Flask application ─────────────────────────────────────────────────────────

def _build_flask_app() -> object | None:
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        log.warning("Flask not installed — IPC server disabled. Run: pip install flask")
        return None

    app = Flask("ghostscripter_ipc_server")
    app.config["DEBUG"] = False

    # Silence Flask/Werkzeug request logs — they'd spam the output console
    import logging as _log
    _log.getLogger("werkzeug").setLevel(_log.ERROR)

    def _ok(action: str, payload: dict = None) -> object:
        return jsonify({"status": "ok", "action": action,
                        "payload": payload or {}})

    def _err(action: str, message: str) -> object:
        return jsonify({"status": "error", "action": action,
                        "message": message}), 400

    def _envelope(action: str) -> dict | None:
        """Extract and validate the request envelope."""
        data = request.get_json(silent=True) or {}
        # Accept both bare payload and wrapped envelope
        if "payload" in data:
            return data.get("payload", {})
        return data  # bare payload (legacy / simple callers)

    # ── /api/ping ─────────────────────────────────────────────────────────────

    @app.route("/api/ping", methods=["GET", "POST"])
    def ping():
        return _ok("ping", {"program": "GhostScripter", "port": GHOSTSCRIPTER_PORT})

    # ── /api/open_script ─────────────────────────────────────────────────────

    @app.route("/api/open_script", methods=["POST"])
    def open_script():
        """
        Payload: {
            "resref":     "c_rodian_sp",          -- script filename (no ext)
            "module_dir": "C:/path/to/module",    -- where to find the .nss
            "template":   "walk_spawn",           -- optional template name
            "slot":       "on_spawn",             -- which script slot this is
            "object_tag": "RODIAN_01"             -- tag of the owning object
        }
        """
        p = _envelope("open_script")
        resref     = p.get("resref", "")
        module_dir = p.get("module_dir", "")
        template   = p.get("template", "")
        slot       = p.get("slot", "")
        object_tag = p.get("object_tag", "")

        if not resref:
            return _err("open_script", "resref is required")

        _push_event("open_script", {
            "resref":     resref,
            "module_dir": module_dir,
            "template":   template,
            "slot":       slot,
            "object_tag": object_tag,
        })
        log.info(f"IPC open_script: {resref} (slot={slot}, obj={object_tag})")
        return _ok("open_script")

    # ── /api/open_dlg ─────────────────────────────────────────────────────────

    @app.route("/api/open_dlg", methods=["POST"])
    def open_dlg():
        """
        Payload: {
            "resref":     "dan13_01",
            "module_dir": "C:/path/to/module"
        }
        """
        p = _envelope("open_dlg")
        resref     = p.get("resref", "")
        module_dir = p.get("module_dir", "")

        if not resref:
            return _err("open_dlg", "resref is required")

        _push_event("open_dlg", {
            "resref":     resref,
            "module_dir": module_dir,
        })
        log.info(f"IPC open_dlg: {resref}")
        return _ok("open_dlg")

    # ── /api/open_2da ─────────────────────────────────────────────────────────

    @app.route("/api/open_2da", methods=["POST"])
    def open_2da():
        """
        Payload: {
            "table": "appearance",
            "row":   147
        }
        """
        p = _envelope("open_2da")
        table = p.get("table", "")
        row   = p.get("row", 0)

        if not table:
            return _err("open_2da", "table name is required")

        _push_event("open_2da", {"table": table, "row": int(row)})
        log.info(f"IPC open_2da: {table}[{row}]")
        return _ok("open_2da")

    # ── /api/open_tlk ─────────────────────────────────────────────────────────

    @app.route("/api/open_tlk", methods=["POST"])
    def open_tlk():
        """
        Payload: {
            "strref": 42001,
            "game":   "k1"
        }
        """
        p = _envelope("open_tlk")
        strref = p.get("strref", 0)
        game   = p.get("game", "k1")

        _push_event("open_tlk", {"strref": int(strref), "game": game})
        log.info(f"IPC open_tlk: strref={strref} game={game}")
        return _ok("open_tlk")

    # ── /api/status ───────────────────────────────────────────────────────────

    @app.route("/api/status", methods=["GET"])
    def status():
        return jsonify({
            "status":  "running",
            "program": "GhostScripter",
            "port":    GHOSTSCRIPTER_PORT,
            "version": "2.4.0",
        })

    return app


# ── Server thread ─────────────────────────────────────────────────────────────

class IPCServer:
    """
    Wraps the Flask app in a daemon thread.
    Call start() once at application startup; stop() on close.
    """

    def __init__(self, port: int = GHOSTSCRIPTER_PORT):
        self.port = port
        self._app  = _build_flask_app()
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def available(self) -> bool:
        """True if Flask is installed and the server can run."""
        return self._app is not None

    def start(self):
        if not self._app:
            log.warning("IPC server not started (Flask not available)")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="gs-ipc-server"
        )
        self._thread.start()
        log.info(f"GhostScripter IPC server started on port {self.port}")

    def _run(self):
        try:
            self._app.run(
                host="127.0.0.1",
                port=self.port,
                use_reloader=False,
                threaded=True,
            )
        except OSError as e:
            log.error(f"IPC server failed to bind port {self.port}: {e}")
        except Exception as e:
            log.error(f"IPC server error: {e}")

    def stop(self):
        # Flask dev server has no clean shutdown; the daemon thread exits
        # when the process ends.
        self._running = False
        log.info("GhostScripter IPC server stopped")
