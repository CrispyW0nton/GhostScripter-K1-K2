"""
GhostScripter-K1-K2 — ERF / MOD / RIM Packer Widget

Builds KotOR archive files (ERF, MOD, SAV, RIM) from a file list.
Uses the ERFWriter from dlg_writer.py.

ERF binary format (from xoreos-tools + KotOR Scripting Tool):
  Header 160 bytes
  Key list  24 bytes × N
  Resource list 8 bytes × N
  Resource data (concatenated)

References:
  - xoreos-tools src/aurora/erfwriter.cpp
  - TSLPatcher lib/site/Bioware/ERF.pm
  - ghostscripter/core/export/dlg_writer.py (ERFWriter)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

from qtpy.QtCore import Qt, QMimeData, QUrl, Signal
from qtpy.QtGui import QFont, QColor, QDragEnterEvent, QDropEvent
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QFileDialog, QFrame,
    QComboBox, QLineEdit, QGroupBox, QFormLayout, QProgressBar,
    QAbstractItemView, QMenu, QPlainTextEdit, QDialog, QDialogButtonBox,
)

from ghostscripter.core.export.dlg_writer import ERFWriter


# ── Game Resource Picker Dialog ───────────────────────────────

class _GameResourcePickerDialog(QDialog):
    """Dialog to pick one or more resources from the game archives to extract."""

    def __init__(self, resource_manager, parent=None):
        super().__init__(parent)
        self._rm = resource_manager
        self._selected: List[str] = []
        self.setWindowTitle("Extract from Game Archives")
        self.setMinimumSize(560, 480)
        self.setStyleSheet("background:#252526; color:#cccccc;")
        self._setup_ui()
        self._populate()

    def _setup_ui(self):
        lay = QVBoxLayout(self)

        # Type filter
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("Resource type:"))
        self.type_combo = QComboBox()
        self.type_combo.setStyleSheet(
            "QComboBox { background:#3c3c3c; color:#cccccc; border:1px solid #555; padding:2px 6px; }"
            "QComboBox QAbstractItemView { background:#252526; color:#cccccc; selection-background-color:#094771; }"
        )
        for ext in [".ncs", ".nss", ".dlg", ".2da", ".utc", ".utp", ".uti",
                    ".utm", ".are", ".ifo", ".lyt", ".vis", ".mdl", ".tga", ".wav"]:
            self.type_combo.addItem(ext)
        self.type_combo.currentTextChanged.connect(self._populate)
        hdr.addWidget(self.type_combo)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by name…")
        self.filter_edit.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555; padding:2px 8px; }"
        )
        self.filter_edit.textChanged.connect(self._filter)
        hdr.addWidget(self.filter_edit)
        hdr.addStretch()

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color:#666; font-size:8pt;")
        hdr.addWidget(self.count_label)
        lay.addLayout(hdr)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setStyleSheet("""
            QListWidget { background:#1e1e1e; border:1px solid #3c3c3c; color:#cccccc; }
            QListWidget::item { padding:3px 8px; font-family:Consolas; font-size:9pt; }
            QListWidget::item:selected { background:#094771; }
        """)
        lay.addWidget(self.list_widget)

        info = QLabel("Select one or more resources to extract and add to the pack list.\n"
                      "Hold Ctrl/Shift for multi-select.")
        info.setStyleSheet("color:#666; font-size:8pt; padding:2px 0;")
        lay.addWidget(info)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Extract Selected")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _populate(self):
        self.list_widget.clear()
        ext = self.type_combo.currentText()
        ft = self.filter_edit.text().lower() if hasattr(self, 'filter_edit') else ""
        entries = self._rm.list_by_type(ext)
        count = 0
        for e in sorted(entries, key=lambda x: x.resref):
            if ft and ft not in e.resref.lower():
                continue
            item = QListWidgetItem(e.filename)
            item.setData(Qt.UserRole, e.filename)
            self.list_widget.addItem(item)
            count += 1
        if hasattr(self, 'count_label'):
            self.count_label.setText(f"{count} resources")

    def _filter(self, text: str):
        self._populate()

    def _on_accept(self):
        self._selected = [
            self.list_widget.item(i).data(Qt.UserRole)
            for i in range(self.list_widget.count())
            if self.list_widget.item(i).isSelected()
        ]
        self.accept()

    def get_selected(self) -> List[str]:
        return self._selected


# ── Known resource types ──────────────────────────────────────

RESTYPE_MAP = {
    ".ncs": (2010, "NCS - Compiled Script"),
    ".nss": (2009, "NSS - Script Source"),
    ".dlg": (2029, "DLG - Dialogue"),
    ".utc": (2023, "UTC - Creature Blueprint"),
    ".utp": (2025, "UTP - Placeable Blueprint"),
    ".uti": (2024, "UTI - Item Blueprint"),
    ".utm": (2026, "UTM - Merchant Blueprint"),
    ".uts": (2027, "UTS - Sound Blueprint"),
    ".utt": (2023, "UTT - Trigger Blueprint"),
    ".utw": (2034, "UTW - Waypoint Blueprint"),
    ".ute": (2022, "UTE - Encounter Blueprint"),
    ".2da": (2017, "2DA - Table"),
    ".mdl": (2002, "MDL - Model"),
    ".mdx": (3002, "MDX - Model Extension"),
    ".tpc": (3007, "TPC - Texture"),
    ".tga": (3001, "TGA - Texture"),
    ".wav": (3004, "WAV - Audio"),
    ".mp3": (3007, "MP3 - Audio"),
    ".are": (2012, "ARE - Area Template"),
    ".ifo": (2014, "IFO - Module Info"),
    ".git": (2023, "GIT - Dynamic Area Info"),
    ".lyt": (3005, "LYT - Layout"),
    ".vis": (3006, "VIS - Visibility"),
    ".pth": (2036, "PTH - Pathfinding"),
    ".lip": (4014, "LIP - Lipsync"),
    ".txi": (3002, "TXI - Texture Info"),
    ".tlk": (2018, "TLK - Talk Table"),
}


# ── Drag-and-drop list ────────────────────────────────────────

class DropFileList(QListWidget):
    """File list that accepts drag-and-drop from the OS."""

    files_dropped = Signal(list)   # list of Path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls()]
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


# ── ERF Packer Widget ─────────────────────────────────────────

class ERFPackerWidget(QWidget):
    """
    Visual ERF/MOD/RIM archive builder.
    Drag files into the list and click Pack.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: List[Path] = []
        self._game_dir: Path | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tb = self._build_toolbar()
        layout.addWidget(tb)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(2)
        split.addWidget(self._build_file_panel())
        split.addWidget(self._build_settings_panel())
        split.setSizes([700, 340])
        layout.addWidget(split)

    def _build_toolbar(self) -> QWidget:
        tb = QWidget()
        tb.setStyleSheet("background:#2d2d30; border-bottom:1px solid #3c3c3c;")
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(4)

        def btn(label, slot, tooltip="", primary=False):
            b = QPushButton(label)
            b.clicked.connect(slot)
            b.setToolTip(tooltip)
            b.setFixedHeight(24)
            b.setStyleSheet(
                "QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;"
                "  border-radius:3px; padding:2px 10px; font-weight:bold; }"
                "QPushButton:hover { background:#1a8fe0; }"
            ) if primary else b.setStyleSheet(
                "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
                "  border-radius:3px; padding:2px 8px; }"
                "QPushButton:hover { background:#4a4a4a; color:white; }"
            )
            return b

        lay.addWidget(btn("📂 Add Files",      self._add_files,     "Add files to pack"))
        lay.addWidget(btn("📁 Add Folder",     self._add_folder,    "Add all files from folder"))
        lay.addWidget(btn("🎮 From Game",      self._extract_from_game, "Extract resource(s) from game archives"))
        lay.addWidget(btn("✕ Remove Selected", self._remove_files,  "Remove selected files"))
        lay.addWidget(btn("🗑 Clear All",       self._clear_files,   "Clear file list"))

        sep = QFrame(); sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#3c3c3c;"); lay.addWidget(sep)

        lay.addWidget(btn("⚙ Pack Archive", self._pack, "Build the ERF/MOD/RIM archive", True))

        lay.addStretch()
        self.status_label = QLabel("No files added")
        self.status_label.setStyleSheet("color:#858585; font-size:9pt;")
        lay.addWidget(self.status_label)
        return tb

    def _build_file_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#1e1e1e;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Drop zone header
        hdr = QLabel("  Files to Pack  (drag & drop files here)")
        hdr.setStyleSheet(
            "background:#2d2d30; color:#cccccc; font-weight:bold;"
            " padding:5px 8px; border-bottom:1px solid #3c3c3c;"
        )
        lay.addWidget(hdr)

        # Column headers
        col_hdr = QWidget()
        col_hdr.setStyleSheet("background:#252526; border-bottom:1px solid #3c3c3c;")
        col_lay = QHBoxLayout(col_hdr)
        col_lay.setContentsMargins(8, 2, 8, 2)
        for label, stretch in [("ResRef", 1), ("Type", 0), ("Size", 0), ("Path", 2)]:
            lbl = QLabel(label)
            lbl.setStyleSheet("color:#858585; font-size:8pt;")
            if stretch:
                col_lay.addWidget(lbl, stretch)
            else:
                lbl.setFixedWidth(80)
                col_lay.addWidget(lbl)
        lay.addWidget(col_hdr)

        self.file_list = DropFileList()
        self.file_list.setFont(QFont("Consolas", 9))
        self.file_list.setStyleSheet("""
            QListWidget { background:#252526; border:none; color:#cccccc; }
            QListWidget::item { padding:3px 8px; }
            QListWidget::item:hover { background:#2a2d2e; }
            QListWidget::item:selected { background:#094771; }
        """)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._on_context_menu)
        self.file_list.files_dropped.connect(self._add_paths)
        lay.addWidget(self.file_list)

        # Log
        log_hdr = QLabel("  Build Log")
        log_hdr.setStyleSheet(
            "background:#2d2d30; color:#cccccc; font-weight:bold;"
            " padding:4px 8px; border-top:1px solid #3c3c3c;"
        )
        lay.addWidget(log_hdr)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(100)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setStyleSheet(
            "QPlainTextEdit { background:#1e1e1e; color:#969696; border:none; }"
        )
        lay.addWidget(self.log)
        return panel

    def _build_settings_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#252526;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        hdr = QLabel("Archive Settings")
        hdr.setStyleSheet(
            "color:#cccccc; font-weight:bold; font-size:10pt;"
            " border-bottom:1px solid #3c3c3c; padding-bottom:4px;"
        )
        lay.addWidget(hdr)

        # Archive type
        type_box = QGroupBox("Archive Type")
        type_box.setStyleSheet(
            "QGroupBox { color:#cccccc; border:1px solid #3c3c3c; margin-top:8px; padding:8px; }"
            "QGroupBox::title { subcontrol-position:top left; padding:0 4px; color:#569cd6; }"
        )
        type_lay = QFormLayout(type_box)
        type_lay.setSpacing(8)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["ERF  (Override-compatible)", "MOD  (Module)",
                                   "SAV  (Save file)", "RIM  (Rim archive)"])
        self.type_combo.setStyleSheet(
            "QComboBox { background:#3c3c3c; color:#cccccc; border:1px solid #555; padding:4px; }"
        )
        type_lay.addRow("Type:", self.type_combo)

        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("output.mod")
        self.output_edit.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555; padding:4px; }"
        )
        browse_btn = QPushButton("…")
        browse_btn.setFixedWidth(28)
        browse_btn.clicked.connect(self._browse_output)
        browse_btn.setStyleSheet(
            "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555; }"
        )

        out_lay = QHBoxLayout()
        out_lay.addWidget(self.output_edit)
        out_lay.addWidget(browse_btn)
        type_lay.addRow("Output:", out_lay)
        lay.addWidget(type_box)

        # Stats
        stats_box = QGroupBox("Statistics")
        stats_box.setStyleSheet(
            "QGroupBox { color:#cccccc; border:1px solid #3c3c3c; margin-top:8px; padding:8px; }"
            "QGroupBox::title { subcontrol-position:top left; padding:0 4px; color:#569cd6; }"
        )
        stats_lay = QFormLayout(stats_box)
        stats_lay.setSpacing(4)

        self.stat_files = QLabel("0")
        self.stat_size  = QLabel("0 KB")
        self.stat_types = QLabel("—")
        for label_text, widget in [
            ("Files:", self.stat_files),
            ("Total size:", self.stat_size),
            ("Resource types:", self.stat_types),
        ]:
            widget.setStyleSheet("color:#9cdcfe;")
            stats_lay.addRow(label_text, widget)
        lay.addWidget(stats_box)

        # Resource type reference
        ref_box = QGroupBox("Resource Type Reference")
        ref_box.setStyleSheet(
            "QGroupBox { color:#cccccc; border:1px solid #3c3c3c; margin-top:8px; padding:8px; }"
            "QGroupBox::title { subcontrol-position:top left; padding:0 4px; color:#569cd6; }"
        )
        ref_inner = QVBoxLayout(ref_box)
        ref_text = QPlainTextEdit()
        ref_text.setReadOnly(True)
        ref_text.setFont(QFont("Consolas", 8))
        ref_text.setMaximumHeight(200)
        ref_text.setStyleSheet(
            "QPlainTextEdit { background:#1e1e1e; color:#858585; border:none; }"
        )
        ref_text.setPlainText(
            "\n".join(f"  {ext:<6} {desc}" for ext, (_, desc) in sorted(RESTYPE_MAP.items()))
        )
        ref_inner.addWidget(ref_text)
        lay.addWidget(ref_box)

        lay.addStretch()
        return panel

    # ── File Management ───────────────────────────────────────

    def _add_files(self):
        exts = " ".join(f"*{ext}" for ext in RESTYPE_MAP)
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add Files to Archive", "",
            f"KotOR Resources ({exts});;All Files (*)"
        )
        if paths:
            self._add_paths([Path(p) for p in paths])

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Add Folder")
        if folder:
            paths = [p for p in Path(folder).iterdir() if p.is_file()]
            self._add_paths(paths)

    def _add_paths(self, paths: List[Path]):
        added = 0
        for path in paths:
            if path in self._files:
                continue
            if not path.is_file():
                continue
            self._files.append(path)
            ext = path.suffix.lower()
            rtype_id, rtype_desc = RESTYPE_MAP.get(ext, (0, "Unknown"))
            size_kb = path.stat().st_size / 1024
            item = QListWidgetItem(
                f"{path.stem:<20}  {ext:<6}  {size_kb:>6.1f} KB  {path}"
            )
            if rtype_id == 0:
                item.setForeground(QColor("#ff6b6b"))  # unknown = red
            elif ext in (".ncs", ".nss"):
                item.setForeground(QColor("#9cdcfe"))  # scripts = blue
            elif ext in (".dlg",):
                item.setForeground(QColor("#4ec9b0"))  # dialogue = teal
            elif ext in (".2da",):
                item.setForeground(QColor("#dcdcaa"))  # 2da = yellow
            else:
                item.setForeground(QColor("#cccccc"))
            item.setData(Qt.UserRole, path)
            self.file_list.addItem(item)
            added += 1
        self._update_stats()
        self._log(f"Added {added} file(s).")

    def _remove_files(self):
        for item in self.file_list.selectedItems():
            path = item.data(Qt.UserRole)
            if path in self._files:
                self._files.remove(path)
            self.file_list.takeItem(self.file_list.row(item))
        self._update_stats()

    def _clear_files(self):
        self._files.clear()
        self.file_list.clear()
        self._update_stats()

    def _update_stats(self):
        n = len(self._files)
        total_size = sum(p.stat().st_size for p in self._files if p.exists())
        exts = {p.suffix.lower() for p in self._files}
        self.stat_files.setText(str(n))
        self.stat_size.setText(f"{total_size / 1024:.1f} KB")
        self.stat_types.setText(", ".join(sorted(exts)) or "—")
        self.status_label.setText(
            f"{n} file(s)  —  {total_size / 1024:.1f} KB total"
        )

    def _on_context_menu(self, pos):
        item = self.file_list.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#252526; color:#cccccc; border:1px solid #3c3c3c; }"
            "QMenu::item:selected { background:#094771; }"
        )
        menu.addAction("✕ Remove",
                       lambda: self._remove_files())
        path = item.data(Qt.UserRole)
        if path:
            menu.addAction(f"📋 Copy path",
                           lambda p=str(path): __import__('PyQt5.QtWidgets',
                               fromlist=['QApplication']).QApplication.clipboard().setText(p))
        menu.exec_(self.file_list.viewport().mapToGlobal(pos))

    def _browse_output(self):
        type_name = self.type_combo.currentText().split()[0].lower()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Archive", f"mod_output.{type_name}",
            f"KotOR Archive (*.{type_name});;All Files (*)"
        )
        if path:
            self.output_edit.setText(path)

    # ── Pack ──────────────────────────────────────────────────

    def _pack(self):
        if not self._files:
            QMessageBox.warning(self, "No Files", "Add files before packing.")
            return

        output_path = self.output_edit.text().strip()
        if not output_path:
            self._browse_output()
            output_path = self.output_edit.text().strip()
        if not output_path:
            return

        # Determine archive type from combo
        type_str = self.type_combo.currentText().split()[0].upper()

        self._log(f"\n→ Building {type_str}: {output_path}")
        writer = ERFWriter(type_str + " ")

        errors = []
        for path in self._files:
            try:
                data = path.read_bytes()
                writer.add_resource(path.name, data)
                self._log(f"  + {path.name}  ({len(data)} bytes)")
            except OSError as e:
                errors.append(f"  ✗ {path.name}: {e}")

        if errors:
            for e in errors:
                self._log(e)

        try:
            archive_data = writer.build()
            Path(output_path).write_bytes(archive_data)
            self._log(
                f"\n✓ Archive built: {Path(output_path).name}"
                f"  ({len(archive_data) / 1024:.1f} KB, "
                f"{len(self._files)} resources)"
            )
        except Exception as e:
            self._log(f"\n✗ Pack failed: {e}")
            QMessageBox.critical(self, "Pack Failed", str(e))

    def _log(self, msg: str):
        self.log.appendPlainText(msg)

    # ── Game Integration ──────────────────────────────────────

    def set_game_dir(self, game_dir: "Path"):
        """Set game directory for 'Extract from Game' feature."""
        self._game_dir = game_dir
        self._log(f"Game directory set: {game_dir}")

    def _extract_from_game(self):
        """Browse game resources and extract one or more into the pack list."""
        if not self._game_dir or not (self._game_dir / "chitin.key").exists():
            # Ask user to point to game dir
            from qtpy.QtWidgets import QFileDialog
            game_dir = QFileDialog.getExistingDirectory(
                self, "Select KotOR Game Directory (contains chitin.key)",
                str(Path.home())
            )
            if not game_dir:
                return
            self._game_dir = Path(game_dir)

        try:
            from ghostscripter.core.resource_manager.resource_manager import ResourceManager
            rm = ResourceManager()
            if not rm.load_game(self._game_dir):
                QMessageBox.critical(self, "Error", "Failed to load game resources.")
                return
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Resource manager error:\n{e}")
            return

        # Show a picker dialog
        dlg = _GameResourcePickerDialog(rm, parent=self)
        if dlg.exec() != dlg.Accepted:
            return

        selected = dlg.get_selected()
        if not selected:
            return

        # Extract to a temp dir and add to file list
        import tempfile
        tmp_dir = Path(tempfile.mkdtemp(prefix="ghostscripter_extract_"))
        added = 0
        for resref_ext in selected:
            data = rm.read(resref_ext)
            if data is None:
                self._log(f"  ✗ Not found: {resref_ext}")
                continue
            dest = tmp_dir / resref_ext
            dest.write_bytes(data)
            self._add_paths([dest])
            self._log(f"  + Extracted: {resref_ext}  ({len(data)} bytes)")
            added += 1

        self._log(f"\\n→ Extracted {added} resource(s) from game archives")

    # ── External API ──────────────────────────────────────────

    def add_file(self, path: Path):
        """Programmatically add a single file."""
        self._add_paths([path])
