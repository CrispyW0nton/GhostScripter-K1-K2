"""
GhostScripter-K1-K2 — IPC Client
==================================
Blueprint: GHOSTWORKS_BLUEPRINT.md §3

Sends HTTP POST requests to other programs in the Ghostworks pipeline.

Targets
-------
  GhostRigger  — port 7001  (open_utc / open_utp / open_utd / open_mdl)
  GModular     — port 7003  (script_compiled, refresh_viewport)

All calls are fire-and-forget from the caller's perspective:
  - 2-second timeout per the blueprint spec
  - If connection refused or timeout → non-blocking status bar message
  - Never raises an exception; always returns (bool, str)
"""
from __future__ import annotations

import logging
from typing import Dict, Any

log = logging.getLogger(__name__)

# Module-level import so tests can patch 'ghostscripter.ipc.gmodular_client.requests'
try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore[assignment]

# ── Blueprint port assignments — imported from canonical ports registry ──────
from ghostscripter.ipc.ports import (    # noqa: E402
    GHOSTRIGGER_REST_LEGACY as GHOSTRIGGER_PORT,
    GMODULAR_REST as GMODULAR_PORT,
)
IPC_TIMEOUT      = 2.0   # seconds — per blueprint §3.4

GHOSTRIGGER_BASE = f"http://localhost:{GHOSTRIGGER_PORT}/api"
GMODULAR_BASE    = f"http://localhost:{GMODULAR_PORT}/api"

_APP_ID  = "GhostScripter"
_VERSION = "1.0"


def _post(base_url: str, action: str, payload: Dict[str, Any],
          timeout: float = IPC_TIMEOUT) -> tuple[bool, str]:
    """
    POST the standard blueprint envelope to base_url/action.
    Returns (success: bool, error_message: str).
    Never raises.
    """
    if requests is None:
        return False, "requests library not installed"

    url = f"{base_url}/{action}"
    envelope = {
        "version": _VERSION,
        "sender":  _APP_ID,
        "action":  action,
        "payload": payload,
    }
    try:
        resp = requests.post(url, json=envelope, timeout=timeout)
        if resp.status_code == 200:
            return True, ""
        data = resp.json() if resp.content else {}
        msg = data.get("message", f"HTTP {resp.status_code}")
        return False, msg
    except requests.exceptions.ConnectionError:
        return False, "connection refused"
    except requests.exceptions.Timeout:
        return False, "timeout"
    except Exception as e:
        return False, str(e)


# ── GModular calls ────────────────────────────────────────────────────────────

def notify_script_compiled(resref: str, slot: str = "",
                            object_tag: str = "") -> tuple[bool, str]:
    """
    POST script_compiled to GModular (port 7003).

    Blueprint §6.4 — On compile success:
        POST script_compiled to GModular port 7003:
        {"resref": "c_rodian_sp", "slot": "on_spawn", "object_tag": "RODIAN_01"}

    GModular fills the script field in the inspector for that object.
    """
    ok, err = _post(GMODULAR_BASE, "script_compiled", {
        "resref":     resref,
        "slot":       slot,
        "object_tag": object_tag,
    })
    if ok:
        log.info(f"→ GModular: script_compiled {resref} (slot={slot})")
    else:
        log.debug(f"GModular not reachable for script_compiled: {err}")
    return ok, err


def notify_gmodular_refresh() -> tuple[bool, str]:
    """POST refresh_viewport to GModular."""
    ok, err = _post(GMODULAR_BASE, "refresh_viewport", {})
    if ok:
        log.info("→ GModular: refresh_viewport")
    return ok, err


def ping_gmodular() -> tuple[bool, str]:
    """Ping GModular — returns (True, version) or (False, error)."""
    if requests is None:
        return False, "requests library not installed"
    try:
        resp = requests.get(f"{GMODULAR_BASE}/ping", timeout=IPC_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return True, data.get("program", "GModular")
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)


# ── GhostRigger calls ─────────────────────────────────────────────────────────

def open_utc_in_rigger(resref: str, module_dir: str = "") -> tuple[bool, str]:
    """Ask GhostRigger to open a creature blueprint (UTC)."""
    ok, err = _post(GHOSTRIGGER_BASE, "open_utc", {
        "resref": resref, "module_dir": module_dir,
    })
    if ok:
        log.info(f"→ GhostRigger: open_utc {resref}")
    else:
        log.debug(f"GhostRigger not reachable for open_utc: {err}")
    return ok, err


def open_utp_in_rigger(resref: str, module_dir: str = "") -> tuple[bool, str]:
    """Ask GhostRigger to open a placeable blueprint (UTP)."""
    return _post(GHOSTRIGGER_BASE, "open_utp", {
        "resref": resref, "module_dir": module_dir,
    })


def open_utd_in_rigger(resref: str, module_dir: str = "") -> tuple[bool, str]:
    """Ask GhostRigger to open a door blueprint (UTD)."""
    return _post(GHOSTRIGGER_BASE, "open_utd", {
        "resref": resref, "module_dir": module_dir,
    })


def open_mdl_in_rigger(resref: str, module_dir: str = "") -> tuple[bool, str]:
    """Ask GhostRigger to open a model (MDL) for viewing/editing."""
    return _post(GHOSTRIGGER_BASE, "open_mdl", {
        "resref": resref, "module_dir": module_dir,
    })


def ping_ghostrigger() -> tuple[bool, str]:
    """Ping GhostRigger — returns (True, program_name) or (False, error)."""
    if requests is None:
        return False, "requests library not installed"
    try:
        resp = requests.get(f"{GHOSTRIGGER_BASE}/ping", timeout=IPC_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return True, data.get("program", "GhostRigger")
        return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, str(e)
