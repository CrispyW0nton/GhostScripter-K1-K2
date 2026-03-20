"""
ghostscripter/utils/log_setup.py
================================
Centralised logging configuration for GhostScripter.

Features
--------
* Rotating file log  → <exe_dir>/ghostscripter.log  (5 × 1 MB)
* Stderr handler     → colour-coded in terminal
* Qt signal handler  → feeds the in-app log viewer in real-time
* Uncaught-exception hook → logs full tracebacks before crash
* Per-subsystem log levels settable at runtime

Usage
-----
    # In main.py, before any other imports that log:
    from ghostscripter.utils.log_setup import setup_logging, get_log_path
    setup_logging()

    # In any module:
    import logging
    log = logging.getLogger(__name__)
    log.info("...")
    log.warning("...")
    log.error("...", exc_info=True)   # includes traceback
"""

from __future__ import annotations

import collections
import logging
import logging.handlers
import sys
import traceback
from pathlib import Path
from typing import Callable, List


# ── Public names ──────────────────────────────────────────────────────────────

__all__ = [
    "setup_logging",
    "get_log_path",
    "get_recent_records",
    "add_ui_sink",
    "remove_ui_sink",
    "GS_LOG_NAME",
]

GS_LOG_NAME = "ghostscripter"

# ── Module-level state ────────────────────────────────────────────────────────

_LOG_PATH: Path | None = None
_MAX_RECENT = 2000
_RECENT: collections.deque = collections.deque(maxlen=_MAX_RECENT)  # O(1) append+trim
_UI_SINKS: List[Callable[[logging.LogRecord], None]] = []  # UI callbacks


# ── Log path helper ───────────────────────────────────────────────────────────

def get_log_path() -> Path:
    """Return the path of the active log file."""
    global _LOG_PATH
    if _LOG_PATH is None:
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).resolve().parent.parent.parent
        _LOG_PATH = base / "ghostscripter.log"
    return _LOG_PATH


# ── Recent-record ring buffer ─────────────────────────────────────────────────

def get_recent_records(
    level: int = logging.DEBUG,
    logger_prefix: str = "",
) -> List[logging.LogRecord]:
    """Return buffered records filtered by minimum level / logger prefix.

    Note: iteration over the deque is thread-safe in CPython (GIL), but
    callers that need a consistent snapshot should hold their own lock.
    """
    return [
        r for r in _RECENT
        if r.levelno >= level
        and (not logger_prefix or r.name.startswith(logger_prefix))
    ]


# ── UI sink registration ──────────────────────────────────────────────────────

def add_ui_sink(fn: Callable[[logging.LogRecord], None]) -> None:
    """Register a callback that is called for every new log record.

    The callback runs on the logging thread (usually the main Qt thread),
    so it is safe to update Qt widgets directly.
    """
    if fn not in _UI_SINKS:
        _UI_SINKS.append(fn)


def remove_ui_sink(fn: Callable[[logging.LogRecord], None]) -> None:
    """Unregister a previously added UI sink."""
    try:
        _UI_SINKS.remove(fn)
    except ValueError:
        pass


# ── Internal handlers ─────────────────────────────────────────────────────────

class _RingBufferHandler(logging.Handler):
    """Keeps the last _MAX_RECENT records in memory for the log viewer."""

    def emit(self, record: logging.LogRecord) -> None:
        # deque(maxlen=_MAX_RECENT) automatically discards the oldest record
        # when full — O(1) vs the previous O(n) del _RECENT[0].
        _RECENT.append(record)
        # Notify UI sinks (copy list to avoid mutation during iteration)
        for fn in list(_UI_SINKS):
            try:
                fn(record)
            except Exception:
                pass


class _ColourStderrHandler(logging.StreamHandler):
    """StreamHandler that adds ANSI colour codes on ttys."""

    _COLOURS = {
        logging.DEBUG:    "\033[36m",     # cyan
        logging.INFO:     "\033[32m",     # green
        logging.WARNING:  "\033[33m",     # yellow
        logging.ERROR:    "\033[31m",     # red
        logging.CRITICAL: "\033[1;31m",   # bold red
    }
    _RESET = "\033[0m"

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            stream = self.stream
            if stream.isatty():
                colour = self._COLOURS.get(record.levelno, "")
                stream.write(f"{colour}{msg}{self._RESET}\n")
            else:
                stream.write(msg + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)


# ── Detailed formatter ────────────────────────────────────────────────────────

_FILE_FMT = logging.Formatter(
    fmt="%(asctime)s  %(levelname)-8s  %(name)s:%(lineno)d  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_CONSOLE_FMT = logging.Formatter(
    fmt="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)


# ── Public setup function ─────────────────────────────────────────────────────

def setup_logging(
    level: int = logging.DEBUG,
    file_level: int = logging.DEBUG,
    console_level: int = logging.INFO,
    max_bytes: int = 1_048_576,   # 1 MB per file
    backup_count: int = 5,
) -> logging.Logger:
    """
    Configure the root 'ghostscripter' logger.

    Handlers attached
    -----------------
    1. RotatingFileHandler  → ghostscripter.log  (DEBUG and above)
    2. _ColourStderrHandler → stderr             (INFO and above by default)
    3. _RingBufferHandler   → in-memory buffer   (DEBUG and above)

    Returns the root GS logger.
    """
    root = logging.getLogger(GS_LOG_NAME)
    if root.handlers:
        # Already configured — don't add duplicate handlers
        return root

    root.setLevel(level)

    # 1. Rotating file
    try:
        log_path = get_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        fh.setLevel(file_level)
        fh.setFormatter(_FILE_FMT)
        root.addHandler(fh)
    except Exception as e:
        # Non-fatal — continue without file handler
        print(f"[GhostScripter] WARNING: could not open log file: {e}", file=sys.stderr)

    # 2. Colour stderr
    sh = _ColourStderrHandler(sys.stderr)
    sh.setLevel(console_level)
    sh.setFormatter(_CONSOLE_FMT)
    root.addHandler(sh)

    # 3. Ring buffer (feeds UI viewer)
    rb = _RingBufferHandler()
    rb.setLevel(logging.DEBUG)
    root.addHandler(rb)

    root.info("=" * 60)
    root.info("GhostScripter logging started  →  %s", get_log_path())
    root.info("=" * 60)

    # Install uncaught-exception hook
    _install_excepthook(root)

    return root


# ── Uncaught-exception hook ───────────────────────────────────────────────────

def _install_excepthook(logger: logging.Logger) -> None:
    """Replace sys.excepthook so unhandled exceptions are logged."""
    _orig = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            _orig(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "UNHANDLED EXCEPTION — %s: %s\n%s",
            exc_type.__name__,
            exc_value,
            "".join(traceback.format_tb(exc_tb)),
        )
        # Also write to crash log file
        try:
            crash_path = get_log_path().parent / "ghostscripter_crash.log"
            with open(crash_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=f)
        except Exception:
            pass
        _orig(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook
