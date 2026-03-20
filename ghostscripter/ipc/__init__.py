"""
GhostScripter-K1-K2 — IPC Package

GhostWorks pipeline ports (blueprint spec v1.0)
  GhostRigger   → 7001
  GhostScripter → 7002  (this app — receives commands)
  GModular      → 7003
"""
from ghostscripter.ipc.ghostrigger_bridge import (
    GhostRiggerBridge,
    IPCCallbackServer,
    ModelPayload,
    GHOSTRIGGER_BASE,
    GHOSTRIGGER_PORT,
)
from ghostscripter.ipc.ipc_server import (
    IPCServer,
    GHOSTSCRIPTER_PORT,
    drain_event_queue,
)
from ghostscripter.ipc.gmodular_client import (
    notify_script_compiled,
    notify_gmodular_refresh,
    ping_gmodular,
    open_utc_in_rigger,
    ping_ghostrigger,
    GMODULAR_PORT,
    GHOSTRIGGER_PORT as GR_PORT,
    IPC_TIMEOUT,
)

# Backwards-compat alias (tests may import GhostScripterIPCServer)
GhostScripterIPCServer = IPCServer
GModularClient = notify_script_compiled  # legacy name — use module functions directly

__all__ = [
    # GhostRigger outgoing bridge
    "GhostRiggerBridge",
    "IPCCallbackServer",
    "ModelPayload",
    "GHOSTRIGGER_BASE",
    "GHOSTRIGGER_PORT",
    # Incoming IPC server
    "IPCServer",
    "GhostScripterIPCServer",   # backwards-compat
    "GHOSTSCRIPTER_PORT",
    "drain_event_queue",
    # GModular / GhostRigger outgoing client functions
    "notify_script_compiled",
    "notify_gmodular_refresh",
    "ping_gmodular",
    "open_utc_in_rigger",
    "ping_ghostrigger",
    "GMODULAR_PORT",
    "IPC_TIMEOUT",
]
