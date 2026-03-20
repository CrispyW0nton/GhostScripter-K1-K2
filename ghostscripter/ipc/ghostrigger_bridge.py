"""
GhostScripter-K1-K2 — GhostRigger IPC Bridge
Communicates with a running GhostRigger instance over localhost REST.

GhostRigger runs a small HTTP server on port 7001 (GhostWorks blueprint spec).
This bridge:
  • Polls connection status  (background daemon thread — never blocks Qt)
  • Pushes model import requests
  • Pulls rig-complete notifications (model name, appearance row)
  • Sends appearance.2da edit instructions

Performance notes
-----------------
  The HTTP poll runs entirely in a daemon thread so that connection
  timeouts NEVER stall the Qt main-event loop.  Results are forwarded
  back to the main thread via Qt signals (thread-safe).

Usage:
    bridge = GhostRiggerBridge()
    bridge.start()
    bridge.on_model_ready.connect(my_slot)
    bridge.request_rig("mymodel")
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

from qtpy.QtCore import QObject, Signal, QTimer

log = logging.getLogger(__name__)

GHOSTRIGGER_HOST = "http://localhost"
from ghostscripter.ipc.ports import (   # Blueprint spec
    GHOSTRIGGER_REST_LEGACY as GHOSTRIGGER_PORT,
    GHOSTSCRIPTER_REST as GHOSTSCRIPTER_PORT,
)
GHOSTRIGGER_BASE = f"{GHOSTRIGGER_HOST}:{GHOSTRIGGER_PORT}/api"

# How often the background thread checks for GhostRigger (seconds).
# Kept long so that a missing GhostRigger causes minimal overhead.
POLL_INTERVAL_S  = 8.0   # 8-second background poll
# Short connect-timeout so a refused connection returns fast in the thread.
CONNECT_TIMEOUT  = 0.5   # seconds


@dataclass
class ModelPayload:
    """Data returned by GhostRigger after a rig operation."""
    model_name: str
    mdl_path: str
    mdx_path: str = ""
    texture_paths: List[str] = field(default_factory=list)
    appearance_row: int = -1
    appearance_label: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


# ── Internal worker that runs all HTTP calls off the main thread ──────────────

class _PollWorker(threading.Thread):
    """
    Daemon thread that polls GhostRigger and puts result events onto a queue.
    The main thread drains that queue via a fast QTimer (no blocking I/O in Qt).
    """

    def __init__(self, result_queue: queue.Queue):
        super().__init__(daemon=True, name="ghostrigger-poll")
        self._q = result_queue
        self._stop_evt = threading.Event()
        self._session: "_requests.Session" | None = None

    def stop(self):
        self._stop_evt.set()

    def run(self):
        if not _HAS_REQUESTS:
            return
        self._session = _requests.Session()
        while not self._stop_evt.is_set():
            try:
                resp = self._session.get(
                    f"{GHOSTRIGGER_BASE}/status",
                    timeout=CONNECT_TIMEOUT,
                )
                ok = resp.status_code == 200
                version = resp.json().get("version", "?") if ok else ""
                self._q.put(("status", ok, version))

                if ok:
                    # Also fetch completed rig jobs while connected
                    try:
                        r2 = self._session.get(
                            f"{GHOSTRIGGER_BASE}/completed",
                            timeout=CONNECT_TIMEOUT,
                        )
                        if r2.status_code == 200:
                            for item in r2.json().get("models", []):
                                self._q.put(("model", item))
                    except Exception:
                        pass
            except Exception:
                self._q.put(("status", False, ""))

            # Sleep in small increments so stop() is responsive
            for _ in range(int(POLL_INTERVAL_S / 0.2)):
                if self._stop_evt.is_set():
                    break
                time.sleep(0.2)

        if self._session:
            self._session.close()


# ─────────────────────────────────────────────────────────────────────────────

class GhostRiggerBridge(QObject):
    """
    Qt-integrated IPC bridge to GhostRigger-K1-K2.

    All network I/O happens in a background daemon thread (_PollWorker).
    A lightweight QTimer (50 ms) drains the result queue and emits Qt
    signals — this means the main thread is NEVER blocked waiting for
    a network response.
    """

    # ── Signals ─────────────────────────────────────────────
    connected        = Signal(str)          # version string
    disconnected     = Signal()
    model_ready      = Signal(object)       # ModelPayload
    rig_error        = Signal(str)          # error message
    status_update    = Signal(str)          # general log

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._is_connected = False
        self._result_queue: queue.Queue = queue.Queue()
        self._worker: _PollWorker | None = None
        # Lightweight drain timer — just empties a Python queue, no I/O
        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(100)  # 100 ms drain — imperceptible
        self._drain_timer.timeout.connect(self._drain_queue)
        # Separate session for foreground API calls (request_rig, push_2da_edit)
        self._fg_session: "_requests.Session" | None = None

    # ── Lifecycle ────────────────────────────────────────────

    def start(self):
        """Begin background polling for GhostRigger connection."""
        if not _HAS_REQUESTS:
            log.warning("requests library not available — IPC bridge disabled")
            self.status_update.emit("⚠ requests not installed — IPC bridge disabled")
            return
        self._fg_session = _requests.Session()
        self._running = True
        self._worker = _PollWorker(self._result_queue)
        self._worker.start()
        self._drain_timer.start()
        log.info("GhostRigger IPC bridge started (background thread)")

    def stop(self):
        """Stop polling and clean up."""
        self._drain_timer.stop()
        self._running = False
        if self._worker:
            self._worker.stop()
            self._worker.join(timeout=1.0)
            self._worker = None
        if self._fg_session:
            self._fg_session.close()
            self._fg_session = None
        log.info("GhostRigger IPC bridge stopped")

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    # ── Queue drain (called by _drain_timer on the main thread) ──────────────

    def _drain_queue(self):
        """
        Drain results posted by the background worker.
        This method never does any I/O — it only reads a Python queue,
        which is always fast.
        """
        try:
            while True:
                event = self._result_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass

    def _handle_event(self, event):
        kind = event[0]
        if kind == "status":
            _, ok, version = event
            was = self._is_connected
            self._is_connected = ok
            if ok and not was:
                log.info(f"GhostRigger connected: {version}")
                self.connected.emit(version)
            elif not ok and was:
                log.info("GhostRigger disconnected")
                self.disconnected.emit()
        elif kind == "model":
            item = event[1]
            payload = ModelPayload(
                model_name=item.get("model_name", ""),
                mdl_path=item.get("mdl_path", ""),
                mdx_path=item.get("mdx_path", ""),
                texture_paths=item.get("texture_paths", []),
                appearance_row=item.get("appearance_row", -1),
                appearance_label=item.get("appearance_label", ""),
                extra=item,
            )
            log.info(f"Model ready from GhostRigger: {payload.model_name}")
            self.model_ready.emit(payload)

    # ── Foreground API Calls (user-initiated, brief) ──────────────────────────

    def request_rig(self, model_name: str, mdl_path: str = "") -> bool:
        """Ask GhostRigger to open a model for rigging."""
        if not self._is_connected or not self._fg_session:
            self.rig_error.emit("GhostRigger is not connected.")
            return False
        try:
            resp = self._fg_session.post(
                f"{GHOSTRIGGER_BASE}/rig",
                json={"model": model_name, "path": mdl_path},
                timeout=5,
            )
            if resp.status_code == 200:
                self.status_update.emit(f"GhostRigger: rigging {model_name}…")
                return True
            self.rig_error.emit(f"GhostRigger returned {resp.status_code}")
            return False
        except Exception as e:
            self.rig_error.emit(f"IPC error: {e}")
            return False

    def push_2da_edit(self, filename: str, row: int, col: str, value: str) -> bool:
        """Tell GhostRigger to apply a 2DA cell edit."""
        if not self._is_connected or not self._fg_session:
            return False
        try:
            resp = self._fg_session.post(
                f"{GHOSTRIGGER_BASE}/2da/edit",
                json={"file": filename, "row": row, "col": col, "value": value},
                timeout=3,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def get_rigger_version(self) -> str | None:
        """Query GhostRigger version string (foreground)."""
        if not self._fg_session:
            return None
        try:
            resp = self._fg_session.get(f"{GHOSTRIGGER_BASE}/version", timeout=2)
            if resp.status_code == 200:
                return resp.json().get("version", "unknown")
        except Exception:
            pass
        return None


# ── Standalone REST server (used by ghostscripter to receive callbacks) ──

def _make_callback_app(bridge: GhostRiggerBridge):
    """
    Create a minimal Flask app that GhostRigger can POST callbacks to.
    This allows push-style notification instead of polling.
    """
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        return None

    app = Flask("ghostscripter_ipc")
    app.config["DEBUG"] = False

    @app.route("/api/model_complete", methods=["POST"])
    def model_complete():
        data = request.json or {}
        payload = ModelPayload(
            model_name=data.get("model_name", ""),
            mdl_path=data.get("mdl_path", ""),
            mdx_path=data.get("mdx_path", ""),
            texture_paths=data.get("texture_paths", []),
            appearance_row=data.get("appearance_row", -1),
            appearance_label=data.get("appearance_label", ""),
        )
        bridge.model_ready.emit(payload)
        return jsonify({"status": "ok"})

    @app.route("/api/status", methods=["GET"])
    def status():
        return jsonify({"status": "running", "app": "GhostScripter-K1-K2"})

    return app


class IPCCallbackServer:
    """
    Optional Flask callback server running in a daemon thread.
    GhostRigger can POST to http://localhost:7002/api/model_complete
    (handled by GhostScripterIPCServer) or directly to this helper.

    .. deprecated::
        Prefer GhostScripterIPCServer (ipc_server.py / IPCServer) which also
        listens on port 7002 and handles the same /api/model_complete endpoint.
        Do NOT start both simultaneously — they will compete for the same port
        and the second one will fail with an ``OSError: [Errno 98] Address already
        in use`` error.  This class is kept only for backward-compatibility with
        code that does not yet use the newer IPCServer.
    """

    def __init__(self, bridge: GhostRiggerBridge, port: int = GHOSTSCRIPTER_PORT):
        self.port = port
        self._app = _make_callback_app(bridge)
        self._thread: threading.Thread | None = None

    def start(self):
        if not self._app:
            log.warning("Flask not available — callback server disabled")
            return
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="ipc-callback-server"
        )
        self._thread.start()
        log.info(f"IPC callback server listening on port {self.port}")

    def _run(self):
        try:
            import logging as _log
            _log.getLogger("werkzeug").setLevel(_log.ERROR)
            self._app.run(host="127.0.0.1", port=self.port, use_reloader=False)
        except Exception as e:
            log.error(f"IPC server error: {e}")
