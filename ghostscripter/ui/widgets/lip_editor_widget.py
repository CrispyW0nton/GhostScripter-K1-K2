"""
GhostScripter-K1-K2 — LIP (Lip-Sync) Editor Widget

Provides a visual editor for KotOR .lip files: a keyframe table with
shape names derived from the PyKotor LIPShape enum, a read-only timeline
bar, and import/export via the MCP readLIP / writeLIP tools.

LIP Binary Format (V1.0, from PyKotor lip_data.py + KotOR.js reference):
  Header (16 bytes):
    FileType    4 chars   "LIP "
    FileVersion 4 chars   "V1.0"
    Duration    float32   total sound length in seconds
    EntryCount  uint32    number of keyframe entries

  Keyframe Entry (5 bytes each):
    Time        float32   seconds from start of audio
    Shape       uint8     mouth-shape index 0-15 (LIPShape enum)

The numeric shape values are authoritative.  Semantic labels use the
retail-validated Reone mapping (0 = NEUTRAL/rest).

Usage:
    widget = LIPEditorWidget(parent)
    widget.load_from_bytes(raw_lip_bytes)   # or load_from_file(path)
    raw = widget.to_bytes()                 # encode back
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import List, NamedTuple

from qtpy.QtCore import Qt, QTimer, Signal
from qtpy.QtGui import QColor, QFont, QPainter, QPen, QBrush
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QDoubleSpinBox,
    QComboBox, QFileDialog, QMessageBox, QSizePolicy, QFrame,
    QSpinBox, QScrollArea,
)

from ghostscripter.core.lip import LIP_SHAPES, PHONEME_MAP


# Colour for each shape on the timeline (HSV-based palette)
_SHAPE_COLORS: list[str] = [
    "#555555", "#4ec9b0", "#9cdcfe", "#dcdcaa",
    "#ce9178", "#c586c0", "#6a9955", "#d7ba7d",
    "#f48771", "#569cd6", "#4fc1ff", "#b5cea8",
    "#e6db74", "#ae81ff", "#a6e22e", "#fd971f",
]

LIP_HEADER = b"LIP V1.0"
LIP_MAGIC = b"LIP "
LIP_VERSION = b"V1.0"


# ---------------------------------------------------------------------------
# LIP Timeline Widget (read-only mini canvas)
# ---------------------------------------------------------------------------
class _LIPTimeline(QWidget):
    """Paints a colour-coded bar showing all keyframe shapes over time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(36)
        self.setMaximumHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._frames: list[tuple[float, int]] = []
        self._duration: float = 1.0

    def set_data(self, frames: list[tuple[float, int]], duration: float) -> None:
        self._frames = frames
        self._duration = max(duration, 0.001)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        w, h = self.width(), self.height()
        p = QPainter(self)
        p.fillRect(0, 0, w, h, QColor("#1e1e1e"))

        if not self._frames:
            p.setPen(QColor("#555"))
            p.drawText(0, 0, w, h, Qt.AlignCenter, "No keyframes")
            return

        frames = sorted(self._frames, key=lambda kf: kf[0])
        for i, (t, shape) in enumerate(frames):
            x0 = int(t / self._duration * w)
            if i + 1 < len(frames):
                x1 = int(frames[i + 1][0] / self._duration * w)
            else:
                x1 = w
            color = QColor(_SHAPE_COLORS[min(shape, 15)])
            p.fillRect(x0, 2, max(x1 - x0, 2), h - 4, color)

        # Tick marks every 0.5 s
        p.setPen(QPen(QColor("#888"), 1))
        t = 0.5
        while t < self._duration:
            x = int(t / self._duration * w)
            p.drawLine(x, 0, x, 6)
            p.drawText(x + 2, 0, 40, h, Qt.AlignVCenter, f"{t:.1f}s")
            t += 0.5

        p.end()


# ---------------------------------------------------------------------------
# Main LIP Editor Widget
# ---------------------------------------------------------------------------
class LIPEditorWidget(QWidget):
    """Visual editor for KotOR .lip files.

    Attributes:
        changed: Signal emitted whenever the keyframe table is modified.
    """

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames: list[list] = []    # [[time, shape], ...]
        self._duration: float = 1.0
        self._dirty: bool = False
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(8, 8, 8, 8)

        # ── Header ────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        lbl = QLabel("LIP Lip-Sync Editor")
        lbl.setStyleSheet(
            "color:#9cdcfe; font-size:11pt; font-weight:bold;"
        )
        hdr.addWidget(lbl)
        hdr.addStretch()

        self._btn_open = QPushButton("Open…")
        self._btn_open.setFixedWidth(70)
        self._btn_open.clicked.connect(self._open_file)
        hdr.addWidget(self._btn_open)

        self._btn_save = QPushButton("Save…")
        self._btn_save.setFixedWidth(70)
        self._btn_save.clicked.connect(self._save_file)
        hdr.addWidget(self._btn_save)

        root.addLayout(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#3c3c3c;")
        root.addWidget(sep)

        # ── Duration + summary ────────────────────────────────────────
        meta = QHBoxLayout()
        meta.addWidget(QLabel("Duration (s):"))
        self._dur_spin = QDoubleSpinBox()
        self._dur_spin.setRange(0.01, 600.0)
        self._dur_spin.setSingleStep(0.1)
        self._dur_spin.setDecimals(3)
        self._dur_spin.setValue(1.0)
        self._dur_spin.setFixedWidth(90)
        self._dur_spin.valueChanged.connect(self._on_duration_changed)
        meta.addWidget(self._dur_spin)
        meta.addSpacing(16)
        self._summary_lbl = QLabel("0 keyframes")
        self._summary_lbl.setStyleSheet("color:#969696;")
        meta.addWidget(self._summary_lbl)
        meta.addStretch()
        root.addLayout(meta)

        # ── Timeline canvas ───────────────────────────────────────────
        self._timeline = _LIPTimeline(self)
        root.addWidget(self._timeline)

        # ── Keyframe table ────────────────────────────────────────────
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Time (s)", "Shape #", "Shape Name"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.setStyleSheet(
            "QTableWidget { background:#1e1e1e; color:#cccccc; border:1px solid #3c3c3c;"
            " gridline-color:#2d2d2d; }"
            "QHeaderView::section { background:#252526; color:#cccccc;"
            " border:none; padding:4px; }"
            "QTableWidget::item:selected { background:#094771; }"
        )
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.cellChanged.connect(self._on_cell_changed)
        root.addWidget(self._table, 1)

        # ── Row edit bar ───────────────────────────────────────────────
        edit_bar = QHBoxLayout()

        add_btn = QPushButton("+ Add Frame")
        add_btn.clicked.connect(self._add_row)
        add_btn.setStyleSheet(
            "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            " border-radius:3px; padding:4px 10px; }"
            "QPushButton:hover { background:#4a4a4a; }"
        )
        edit_bar.addWidget(add_btn)

        del_btn = QPushButton("✕ Delete")
        del_btn.clicked.connect(self._delete_row)
        del_btn.setStyleSheet(
            "QPushButton { background:#3c3c3c; color:#f48771; border:1px solid #555;"
            " border-radius:3px; padding:4px 10px; }"
            "QPushButton:hover { background:#4a4a4a; }"
        )
        edit_bar.addWidget(del_btn)

        edit_bar.addStretch()

        sort_btn = QPushButton("⟳ Sort by Time")
        sort_btn.clicked.connect(self._sort_frames)
        sort_btn.setStyleSheet(
            "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            " border-radius:3px; padding:4px 10px; }"
        )
        edit_bar.addWidget(sort_btn)

        root.addLayout(edit_bar)

        # ── Shape legend ───────────────────────────────────────────────
        root.addWidget(self._build_legend())

    def _build_legend(self) -> QWidget:
        """Return a compact colour legend for all 16 shapes."""
        scroll = QScrollArea()
        scroll.setFixedHeight(52)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(4)

        for idx, name in enumerate(LIP_SHAPES):
            color = _SHAPE_COLORS[idx]
            swatch = QLabel(f"<b>{idx}</b> {name}")
            swatch.setFixedHeight(20)
            swatch.setStyleSheet(
                f"background:{color}; color:#111; border-radius:3px;"
                f" padding:1px 5px; font-size:8pt;"
            )
            row.addWidget(swatch)

        row.addStretch()
        scroll.setWidget(container)
        return scroll

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------
    def _refresh_table(self) -> None:
        """Repopulate the table from self._frames (no signal noise)."""
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for time_val, shape_idx in self._frames:
            row = self._table.rowCount()
            self._table.insertRow(row)
            t_item = QTableWidgetItem(f"{time_val:.4f}")
            t_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            s_item = QTableWidgetItem(str(shape_idx))
            s_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            name = LIP_SHAPES[shape_idx] if 0 <= shape_idx < 16 else "?"
            n_item = QTableWidgetItem(name)
            n_item.setFlags(n_item.flags() & ~Qt.ItemIsEditable)
            color = QColor(_SHAPE_COLORS[shape_idx] if 0 <= shape_idx < 16 else "#555")
            n_item.setBackground(QBrush(color))
            n_item.setForeground(QBrush(QColor("#111")))
            self._table.setItem(row, 0, t_item)
            self._table.setItem(row, 1, s_item)
            self._table.setItem(row, 2, n_item)
        self._table.blockSignals(False)
        self._update_summary()
        self._refresh_timeline()

    def _refresh_timeline(self) -> None:
        self._timeline.set_data(
            [(f[0], f[1]) for f in self._frames],
            self._duration,
        )

    def _update_summary(self) -> None:
        n = len(self._frames)
        self._summary_lbl.setText(
            f"{n} keyframe{'s' if n != 1 else ''}  •  duration {self._duration:.3f}s"
        )

    def _collect_frames_from_table(self) -> None:
        """Read back time/shape values from the editable table cells."""
        frames = []
        for row in range(self._table.rowCount()):
            try:
                t = float(self._table.item(row, 0).text())
                s = int(self._table.item(row, 1).text())
                s = max(0, min(15, s))
                frames.append([t, s])
            except (ValueError, AttributeError):
                pass
        self._frames = frames

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_duration_changed(self, value: float) -> None:
        self._duration = value
        self._refresh_timeline()
        self._update_summary()
        self._dirty = True
        self.changed.emit()

    def _on_cell_changed(self, row: int, col: int) -> None:
        if col in (0, 1):
            self._collect_frames_from_table()
            self._refresh_table()
            self._dirty = True
            self.changed.emit()

    def _add_row(self) -> None:
        # Add a NEUTRAL keyframe at the current last time + 0.1 s
        last_t = max((f[0] for f in self._frames), default=-0.1)
        self._frames.append([round(last_t + 0.1, 4), 0])
        self._refresh_table()
        self._table.scrollToBottom()
        self._dirty = True
        self.changed.emit()

    def _delete_row(self) -> None:
        rows = sorted({idx.row() for idx in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self._frames):
                del self._frames[r]
        self._refresh_table()
        self._dirty = True
        self.changed.emit()

    def _sort_frames(self) -> None:
        self._collect_frames_from_table()
        self._frames.sort(key=lambda kf: kf[0])
        self._refresh_table()
        self._dirty = True
        self.changed.emit()

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------
    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open LIP File", "", "LIP Files (*.lip);;All Files (*)"
        )
        if path:
            try:
                self.load_from_file(Path(path))
            except Exception as exc:
                QMessageBox.critical(self, "Open Error", str(exc))

    def _save_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save LIP File", "", "LIP Files (*.lip);;All Files (*)"
        )
        if path:
            try:
                data = self.to_bytes()
                Path(path).write_bytes(data)
                self._dirty = False
            except Exception as exc:
                QMessageBox.critical(self, "Save Error", str(exc))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def load_from_bytes(self, data: bytes) -> None:
        """Parse raw .lip binary data and populate the editor.

        Raises:
            ValueError: if the header magic or version is invalid.
        """
        if len(data) < 16:
            raise ValueError("LIP data too short (< 16 bytes)")
        magic = data[0:4]
        version = data[4:8]
        if magic != LIP_MAGIC:
            raise ValueError(f"Not a LIP file (magic={magic!r})")
        if version != LIP_VERSION:
            raise ValueError(f"Unsupported LIP version {version!r} (expected V1.0)")

        self._duration = struct.unpack_from("<f", data, 8)[0]
        count = struct.unpack_from("<I", data, 12)[0]

        self._frames = []
        offset = 16
        for _ in range(count):
            if offset + 5 > len(data):
                break
            t = struct.unpack_from("<f", data, offset)[0]
            s = data[offset + 4]
            self._frames.append([round(t, 5), s])
            offset += 5

        self._dur_spin.blockSignals(True)
        self._dur_spin.setValue(self._duration)
        self._dur_spin.blockSignals(False)
        self._refresh_table()
        self._dirty = False

    def load_from_file(self, path: Path) -> None:
        """Load a .lip file from disk."""
        self.load_from_bytes(path.read_bytes())

    def to_bytes(self) -> bytes:
        """Encode the current editor state as a valid LIP V1.0 binary.

        Raises:
            ValueError: if any shape index is out of range 0-15.
        """
        self._collect_frames_from_table()
        frames = sorted(self._frames, key=lambda kf: kf[0])

        for t, s in frames:
            if not (0 <= s <= 15):
                raise ValueError(
                    f"Shape index {s} at t={t:.4f}s is out of range 0-15."
                )

        buf = bytearray()
        buf += LIP_MAGIC
        buf += LIP_VERSION
        buf += struct.pack("<f", self._duration)
        buf += struct.pack("<I", len(frames))
        for t, s in frames:
            buf += struct.pack("<f", t)
            buf += struct.pack("<B", s)
        return bytes(buf)

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def is_dirty(self) -> bool:
        return self._dirty
