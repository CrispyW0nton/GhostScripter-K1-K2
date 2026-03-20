"""Canonical IPC port registry for the Ghostworks Pipeline.

All three pipeline tools (GhostScripter, GModular, GhostRigger) read their
port numbers from this single source of truth.  Never hard-code port numbers
anywhere else in the codebase — always import from here.

Port allocation  (GhostWorks blueprint spec v1.0)
-------------------------------------------------
7001  GhostRigger-K1-K2  REST API  (model rigging / animation)
7002  GhostScripter-K1-K2 REST API  (script + dialogue IDE; stdio is default)
7003  GModular            REST API  (world editor / object placement)
7000  Ghostworks event bus  (pub/sub broadcast, future — not yet active)

Transport rules (SYSTEMS_DESIGN.md §Governance)
------------------------------------------------
* Default transport for MCP: **stdio** (no port needed).
* HTTP/SSE is allowed ONLY on localhost (127.0.0.1).
* No unmanaged MCP servers.
"""
from __future__ import annotations

# ── GhostRigger-K1-K2 (model rigging) ────────────────────────────────────────
GHOSTRIGGER_REST: int = 7001

# ── GhostScripter-K1-K2 ───────────────────────────────────────────────────────
GHOSTSCRIPTER_MCP_STDIO: int = 0          # 0 = stdio (default, no TCP port)
GHOSTSCRIPTER_REST: int = 7002            # HTTP REST (optional, localhost only)

# ── GModular (world editor) ───────────────────────────────────────────────────
GMODULAR_REST: int = 7003

# ── Ghostworks Pipeline internals ────────────────────────────────────────────
GHOSTWORKS_EVENT_BUS: int = 7000          # future pub/sub event bus

# ── Backward-compat alias (old constants.py used GHOSTRIGGER_REST_LEGACY) ────
GHOSTRIGGER_REST_LEGACY: int = GHOSTRIGGER_REST   # same value, alias only

# ── Convenience mapping (name → port) for logging / config screens ───────────
ALL_PORTS: dict[str, int] = {
    "GhostRigger REST": GHOSTRIGGER_REST,
    "GhostScripter REST": GHOSTSCRIPTER_REST,
    "GModular REST": GMODULAR_REST,
    "Ghostworks Event Bus": GHOSTWORKS_EVENT_BUS,
}

__all__ = [
    "GHOSTSCRIPTER_MCP_STDIO",
    "GHOSTSCRIPTER_REST",
    "GMODULAR_REST",
    "GHOSTRIGGER_REST",
    "GHOSTRIGGER_REST_LEGACY",
    "GHOSTWORKS_EVENT_BUS",
    "ALL_PORTS",
]
