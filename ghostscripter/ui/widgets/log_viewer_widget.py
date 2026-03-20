"""
ghostscripter/ui/widgets/log_viewer_widget.py
=============================================
In-app log viewer panel for GhostScripter.

Displays live log records from the logging subsystem in a
colour-coded, filterable, searchable table.  Wires itself into
the log_setup ring-buffer via add_ui_sink / remove_ui_sink so it
receives every log record produced anywhere in the application.

Layout
------
  ┌──────────────────────────────────────────────────────────┐
  │  [DEBUG][INFO][WARN][ERROR][CRIT]  Filter: [___________] │
  │  [Copy] [Save Log…] [Clear]                  Log path ▶ │
  ├──────────────────────────────────────────────────────────┤
  │  Time     Level    Logger               Message           │
  │  …                                                        │
  └──────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import List

from qtpy.QtCore import Qt, QTimer, Signal, QObject, QMutex, QMutexLocker
from qtpy.QtGui import QColor, QFont, QTextCharFormat, QBrush
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QCheckBox, QFileDialog,
    QApplication, QSizePolicy, QSplitter, QToolButton,
    QFrame,
)


# ── Colour palette (matches dark.qss theme) ───────────────────────────────────

_LEVEL_COLOURS = {
    logging.DEBUG:    QColor("#808080"),   # grey
    logging.INFO:     QColor("#9cdcfe"),   # light blue
    logging.WARNING:  QColor("#dcdcaa"),   # yellow
    logging.ERROR:    QColor("#f48771"),   # orange-red
    logging.CRITICAL: QColor("#ff0000"),   # bright red
}

_LEVEL_NAMES = {
    logging.DEBUG:    "DEBUG",
    logging.INFO:     "INFO",
    logging.WARNING:  "WARN",
    logging.ERROR:    "ERROR",
    logging.CRITICAL: "CRIT",
}

_BG_COLOURS = {
    logging.DEBUG:    QColor("#1e1e1e"),
    logging.INFO:     QColor("#1e1e1e"),
    logging.WARNING:  QColor("#2a2700"),
    logging.ERROR:    QColor("#2d1010"),
    logging.CRITICAL: QColor("#3d0000"),
}


# ── Thread-safe signal bridge ──────────────────────────────────────────────────

class _LogSignalBridge(QObject):
    """
    Receives log records from the logging thread and emits a Qt signal
    so the UI update always happens on the Qt main thread.
    """
    new_record = Signal(object)   # object = logging.LogRecord

    def __init__(self):
        super().__init__()
        self._mutex = QMutex()
        self._pending: List[logging.LogRecord] = []

    def push(self, record: logging.LogRecord) -> None:
        """Called from the logging thread — enqueue and schedule delivery."""
        with QMutexLocker(self._mutex):
            self._pending.append(record)
        # emit must happen on the main thread; we use QTimer.singleShot(0)
        # which is cross-thread-safe in Qt5
        QTimer.singleShot(0, self._deliver)

    def _deliver(self) -> None:
        with QMutexLocker(self._mutex):
            pending, self._pending = self._pending, []
        for r in pending:
            self.new_record.emit(r)


# ── Main widget ───────────────────────────────────────────────────────────────

class LogViewerWidget(QWidget):
    """
    Full-featured log panel.

    Call `attach()` to start receiving live records, `detach()` to stop.
    Both are idempotent.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bridge = _LogSignalBridge()
        self._bridge.new_record.connect(self._on_record)
        self._min_level = logging.DEBUG
        self._filter_text = ""
        self._attached = False
        self._record_count = 0

        self._build_ui()
        self._load_existing_records()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet(
            "background:#2d2d30; border-bottom:1px solid #3c3c3c;"
        )
        tbar_layout = QHBoxLayout(toolbar)
        tbar_layout.setContentsMargins(6, 3, 6, 3)
        tbar_layout.setSpacing(4)

        # Level filter buttons
        self._level_btns: dict = {}
        for lvl, name in [
            (logging.DEBUG,    "DEBUG"),
            (logging.INFO,     "INFO"),
            (logging.WARNING,  "WARN"),
            (logging.ERROR,    "ERROR"),
            (logging.CRITICAL, "CRIT"),
        ]:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedHeight(20)
            btn.setFixedWidth(46)
            colour = _LEVEL_COLOURS[lvl].name()
            btn.setStyleSheet(f"""
                QPushButton {{
                    background:#3c3c3c; color:{colour};
                    border:1px solid {colour}; border-radius:2px;
                    font-size:8pt; font-weight:bold; padding:0;
                }}
                QPushButton:checked {{
                    background:{colour}22; border:1px solid {colour};
                }}
                QPushButton:!checked {{
                    background:#2a2a2a; color:#555; border:1px solid #444;
                }}
                QPushButton:hover {{ background:{colour}33; }}
            """)
            btn.toggled.connect(self._on_level_toggled)
            tbar_layout.addWidget(btn)
            self._level_btns[lvl] = btn

        tbar_layout.addSpacing(8)

        # Text filter
        flt_lbl = QLabel("Filter:")
        flt_lbl.setStyleSheet("color:#aaa; font-size:8pt;")
        tbar_layout.addWidget(flt_lbl)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("logger name or message text…")
        self._filter_edit.setFixedHeight(20)
        self._filter_edit.setStyleSheet("""
            QLineEdit {
                background:#1e1e1e; color:#ccc; border:1px solid #555;
                border-radius:2px; font-size:8pt; padding:0 4px;
            }
        """)
        self._filter_edit.textChanged.connect(self._on_filter_changed)
        tbar_layout.addWidget(self._filter_edit, 1)

        tbar_layout.addSpacing(8)

        # Action buttons
        for label, slot in [
            ("Copy",     self._copy_selection),
            ("Save…",    self._save_log),
            ("Clear",    self._clear),
        ]:
            b = QPushButton(label)
            b.setFixedHeight(20)
            b.setFixedWidth(46)
            b.setStyleSheet("""
                QPushButton {
                    background:#3c3c3c; color:#969696;
                    border:1px solid #555; border-radius:2px;
                    font-size:8pt; padding:0;
                }
                QPushButton:hover { background:#4a4a4a; color:#ccc; }
            """)
            b.clicked.connect(slot)
            tbar_layout.addWidget(b)

        # Record counter label
        self._count_lbl = QLabel("0 records")
        self._count_lbl.setStyleSheet("color:#666; font-size:8pt;")
        tbar_layout.addSpacing(8)
        tbar_layout.addWidget(self._count_lbl)

        layout.addWidget(toolbar)

        # ── Log text area ───────────────────────────────────────
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(4000)
        self._text.setObjectName("logViewerText")
        self._text.setStyleSheet("""
            QPlainTextEdit#logViewerText {
                background: #1a1a1a;
                color: #cccccc;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 8pt;
                border: none;
            }
        """)
        layout.addWidget(self._text, 1)

        # ── Status bar ──────────────────────────────────────────
        self._status_bar = QLabel()
        self._status_bar.setStyleSheet(
            "background:#2d2d30; color:#666; font-size:7pt; padding:1px 6px;"
        )
        self._update_status_bar()
        layout.addWidget(self._status_bar)

    # ── Attach / Detach ────────────────────────────────────────────────────────

    def attach(self) -> None:
        """Start receiving live log records."""
        if not self._attached:
            from ghostscripter.utils.log_setup import add_ui_sink
            add_ui_sink(self._bridge.push)
            self._attached = True

    def detach(self) -> None:
        """Stop receiving live log records."""
        if self._attached:
            from ghostscripter.utils.log_setup import remove_ui_sink
            remove_ui_sink(self._bridge.push)
            self._attached = False

    def closeEvent(self, event):
        self.detach()
        super().closeEvent(event)

    # ── Load existing records ──────────────────────────────────────────────────

    def _load_existing_records(self) -> None:
        """Populate the viewer with records already in the ring buffer."""
        try:
            from ghostscripter.utils.log_setup import get_recent_records
            for rec in get_recent_records():
                self._append_record(rec)
        except Exception:
            pass

    # ── Record rendering ───────────────────────────────────────────────────────

    def _on_record(self, record: logging.LogRecord) -> None:
        """Called on the Qt main thread for each new log record."""
        self._append_record(record)

    def _passes_filter(self, record: logging.LogRecord) -> bool:
        """Return True if record should be displayed given current filters.

        Uses exact per-level matching: each level button acts as an independent
        toggle.  A record is displayed only when its exact level is in the set
        of checked levels.
        """
        # Level filter: each button is an exact per-level toggle (DEBUG / INFO /
        # WARN / ERROR / CRIT).  A record is shown only when its exact level has
        # its corresponding button checked.  This mirrors the VS Code output panel
        # style where you can mix arbitrary level combinations.
        checked_levels = {
            lvl for lvl, btn in self._level_btns.items() if btn.isChecked()
        }
        if not checked_levels:
            return False
        if record.levelno not in checked_levels:
            return False

        # Text filter
        if self._filter_text:
            ft = self._filter_text.lower()
            if ft not in record.name.lower() and ft not in record.getMessage().lower():
                return False
        return True

    def _append_record(self, record: logging.LogRecord) -> None:
        """Format and append one record to the text area."""
        if not self._passes_filter(record):
            return

        # Format: HH:MM:SS.mmm  LEVEL  logger:line  message
        ts = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.") + \
             f"{int(record.msecs):03d}"
        level_str = _LEVEL_NAMES.get(record.levelno, f"L{record.levelno}")
        logger_short = record.name.replace("ghostscripter.", "gs.")
        location = f"{logger_short}:{record.lineno}"
        msg = record.getMessage()

        # Include exception info if present
        if record.exc_info:
            import traceback as _tb
            exc_text = "".join(_tb.format_exception(*record.exc_info))
            msg = msg + "\n" + exc_text.rstrip()

        line = f"{ts}  {level_str:<5}  {location:<40}  {msg}"

        colour = _LEVEL_COLOURS.get(record.levelno, QColor("#cccccc"))

        # Use HTML-like colour via QTextCharFormat
        cursor = self._text.textCursor()
        cursor.movePosition(cursor.End)

        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(colour))
        cursor.setCharFormat(fmt)
        cursor.insertText(line + "\n")

        self._text.setTextCursor(cursor)
        # Auto-scroll only if already at bottom
        sb = self._text.verticalScrollBar()
        if sb.value() >= sb.maximum() - 4:
            self._text.ensureCursorVisible()

        self._record_count += 1
        self._count_lbl.setText(f"{self._record_count} records")

    # ── Toolbar callbacks ──────────────────────────────────────────────────────

    def _on_level_toggled(self, _checked: bool) -> None:
        """Re-render all records when a level filter button changes."""
        self._rebuild()

    def _on_filter_changed(self, text: str) -> None:
        self._filter_text = text
        self._rebuild()

    def _rebuild(self) -> None:
        """Clear the text area and re-render all buffered records."""
        self._text.clear()
        self._record_count = 0
        self._count_lbl.setText("0 records")
        try:
            from ghostscripter.utils.log_setup import get_recent_records
            for rec in get_recent_records():
                self._append_record(rec)
        except Exception:
            pass

    def _copy_selection(self) -> None:
        sel = self._text.textCursor().selectedText()
        if sel:
            QApplication.clipboard().setText(sel)
        else:
            QApplication.clipboard().setText(self._text.toPlainText())

    def _save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Log File", "ghostscripter.log",
            "Log files (*.log);;Text files (*.txt);;All files (*)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._text.toPlainText())
            except Exception as e:
                from qtpy.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Save Failed", str(e))

    def _clear(self) -> None:
        self._text.clear()
        self._record_count = 0
        self._count_lbl.setText("0 records")

    # ── Status bar ─────────────────────────────────────────────────────────────

    def _update_status_bar(self) -> None:
        try:
            from ghostscripter.utils.log_setup import get_log_path
            p = get_log_path()
            self._status_bar.setText(f"Log file: {p}")
        except Exception:
            self._status_bar.setText("Log file: (unavailable)")

    # ── Public helpers ─────────────────────────────────────────────────────────

    def append_text(self, text: str, level: int = logging.INFO) -> None:
        """Programmatically inject a plain text message (non-logging path)."""
        record = logging.LogRecord(
            name="app", level=level, pathname="", lineno=0,
            msg=text, args=(), exc_info=None,
        )
        self._append_record(record)
