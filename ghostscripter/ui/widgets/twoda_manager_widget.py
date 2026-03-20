"""
GhostScripter-K1-K2 — 2DA File Manager Widget
Full TSLPatcher-style editing + live game-library browser:
  - Load all 209 2DAs from the real KotOR BIF/KEY archives
  - Add Row / Copy Row / Modify Row
  - Add Column / Rename Column
  - Undo / Redo
  - Search & filter (both file list and table contents)
  - Export changes.ini (TSLPatcher format)
  - Right-click context menu on rows
"""
from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Dict, List

from qtpy.QtCore import Qt, Signal, QThread, Slot, QTimer
from qtpy.QtGui import QFont, QColor, QKeySequence
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QMessageBox, QFileDialog, QListWidget, QListWidgetItem,
    QComboBox, QFrame, QPlainTextEdit, QInputDialog, QShortcut,
    QMenu, QAction, QDialog, QFormLayout, QDialogButtonBox,
    QTextEdit, QAbstractItemView, QProgressBar, QApplication,
)

from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile, GlobalCatManager
from ghostscripter.core.resource_manager.resource_manager import ResourceManager

log = logging.getLogger(__name__)

# ── Sample data (shown when no game loaded) ───────────────────

SAMPLE_GLOBALCAT_TEXT = """2DA V2.0

      Name             Type
0     K_SWG_DEMO       Boolean
1     K_GLOBAL_ALIGN   Number
2     K_PARTY_SIZE     Number
"""

SAMPLE_APPEARANCE_TEXT = """2DA V2.0

     label                  modela  modelb  tex1
0    Revan_PC                p_mal01 ****    PMHC01
1    C_Bastila               p_bast  ****    PFHC03
2    C_HK47                  c_hk47  ****    C_HK47
"""

SAMPLE_SPELLS_TEXT = """2DA V2.0

     label           name    spelllevel  forcepriority
0    force_push      24157   1           1
1    force_choke     24162   2           2
2    force_lightning 24168   3           3
"""


# ── Dialogs ───────────────────────────────────────────────────

class CopyRowDialog(QDialog):
    """Dialog to copy a row with optional cell overrides."""

    def __init__(self, source_row, columns, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Copy Row")
        self.setMinimumWidth(480)
        self.setStyleSheet("background:#252526; color:#cccccc;")

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Copy row '{source_row.label}' to new row:"))

        form = QFormLayout()
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Auto-numbered if blank")
        self.label_edit.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555; padding:4px; }"
        )
        form.addRow("New row label:", self.label_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel("Override cells (leave blank to copy source value):"))

        self.cell_table = QTableWidget(len(columns), 2)
        self.cell_table.setHorizontalHeaderLabels(["Column", "Override Value"])
        self.cell_table.horizontalHeader().setStretchLastSection(True)
        self.cell_table.setStyleSheet("""
            QTableWidget { background:#1e1e1e; color:#cccccc; }
            QHeaderView::section { background:#2d2d30; color:#cccccc; }
        """)
        self.cell_table.setFont(QFont("Consolas", 9))

        for i, col in enumerate(columns):
            col_item = QTableWidgetItem(col)
            col_item.setFlags(col_item.flags() & ~Qt.ItemIsEditable)
            col_item.setForeground(QColor("#858585"))
            self.cell_table.setItem(i, 0, col_item)
            val_item = QTableWidgetItem("")
            val_item.setToolTip(f"Source: {source_row.get(col)}")
            self.cell_table.setItem(i, 1, val_item)

        self.cell_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        layout.addWidget(self.cell_table)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_result(self):
        label = self.label_edit.text().strip() or None
        overrides = {}
        for row in range(self.cell_table.rowCount()):
            col = self.cell_table.item(row, 0).text()
            val = self.cell_table.item(row, 1).text().strip()
            if val:
                overrides[col] = val
        return label, overrides


class AddRowDialog(QDialog):
    """Dialog to add a new row with cell values."""

    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Row")
        self.setMinimumWidth(400)
        self.setStyleSheet("background:#252526; color:#cccccc;")

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Auto-numbered if blank")
        self.label_edit.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555; padding:4px; }"
        )
        form.addRow("Row label:", self.label_edit)

        self.exclusive_edit = QLineEdit()
        self.exclusive_edit.setPlaceholderText("Column to check for uniqueness (optional)")
        self.exclusive_edit.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555; padding:4px; }"
        )
        form.addRow("Exclusive column:", self.exclusive_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel("Cell values (leave blank = '****'):"))

        self.cell_table = QTableWidget(len(columns), 2)
        self.cell_table.setHorizontalHeaderLabels(["Column", "Value"])
        self.cell_table.horizontalHeader().setStretchLastSection(True)
        self.cell_table.setStyleSheet("""
            QTableWidget { background:#1e1e1e; color:#cccccc; }
            QHeaderView::section { background:#2d2d30; color:#cccccc; }
        """)
        self.cell_table.setFont(QFont("Consolas", 9))

        for i, col in enumerate(columns):
            col_item = QTableWidgetItem(col)
            col_item.setFlags(col_item.flags() & ~Qt.ItemIsEditable)
            col_item.setForeground(QColor("#858585"))
            self.cell_table.setItem(i, 0, col_item)
            self.cell_table.setItem(i, 1, QTableWidgetItem(""))

        self.cell_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        layout.addWidget(self.cell_table)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_result(self):
        label = self.label_edit.text().strip() or None
        exclusive = self.exclusive_edit.text().strip() or None
        data = {}
        for row in range(self.cell_table.rowCount()):
            col = self.cell_table.item(row, 0).text()
            val = self.cell_table.item(row, 1).text().strip()
            data[col] = val if val else "****"
        return label, exclusive, data


# ── 2DA Manager Widget ────────────────────────────────────────

class TwoDAManagerWidget(QWidget):
    """
    Full-featured 2DA editor with live game library browser.
    Loads all 209 2DAs from the real KotOR BIF/KEY archives.
    """
    # Emitted when a game is loaded or changed
    game_loaded = Signal(str)

    def __init__(self, project=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.current_file: TwoDAFile | None = None
        self._original_file: TwoDAFile | None = None
        self._demo_cache: Dict[str, TwoDAFile] = {}
        self._resource_manager: ResourceManager | None = None
        self._game_2da_entries: List = []   # list of ResourceEntry for .2da
        self._game_cache: Dict[str, TwoDAFile] = {}  # resref -> TwoDAFile cache

        # Debounce timers – avoid re-rendering on every keystroke
        self._filter_rows_timer = QTimer(self)
        self._filter_rows_timer.setSingleShot(True)
        self._filter_rows_timer.setInterval(180)  # ms
        self._filter_rows_timer.timeout.connect(self._apply_filter_rows)
        self._pending_filter_text = ""

        self._filter_list_timer = QTimer(self)
        self._filter_list_timer.setSingleShot(True)
        self._filter_list_timer.setInterval(150)
        self._filter_list_timer.timeout.connect(self._apply_filter_file_list)
        self._pending_list_filter = ""

        self._setup_ui()
        self._load_demo_files()

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self._undo)
        QShortcut(QKeySequence("Ctrl+Y"), self).activated.connect(self._redo)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save_file)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            lambda: self.search_input.setFocus())

    # ── UI Construction ───────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_toolbar())

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(2)
        split.addWidget(self._build_file_panel())
        split.addWidget(self._build_editor())
        split.setSizes([220, 900])
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
            if primary:
                b.setStyleSheet(
                    "QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;"
                    "  border-radius:3px; padding:2px 10px; font-weight:bold; }"
                    "QPushButton:hover { background:#1a8fe0; }"
                )
            else:
                b.setStyleSheet(
                    "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
                    "  border-radius:3px; padding:2px 8px; }"
                    "QPushButton:hover { background:#4a4a4a; color:white; }"
                )
            return b

        lay.addWidget(btn("🎮 Load Game",   self._load_game_dir, "Load KotOR game directory", True))
        lay.addWidget(btn("📂 Open .2da",   self._open_file,     "Open a .2da file from disk"))
        lay.addWidget(btn("💾 Save",        self._save_file,     "Save current (Ctrl+S)"))
        lay.addWidget(btn("💾 Save As…",    self._save_as,       "Save to a new file"))

        sep = QFrame(); sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#3c3c3c;"); lay.addWidget(sep)

        lay.addWidget(btn("↩ Undo",        self._undo,          "Undo (Ctrl+Z)"))
        lay.addWidget(btn("↪ Redo",        self._redo,          "Redo (Ctrl+Y)"))

        sep2 = QFrame(); sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color:#3c3c3c;"); lay.addWidget(sep2)

        lay.addWidget(btn("+ Row",         self._add_row,       "Add a new row"))
        lay.addWidget(btn("⧉ Copy Row",    self._copy_row,      "Copy selected row"))
        lay.addWidget(btn("✏ Modify",      self._modify_row,    "Modify selected row cells"))
        lay.addWidget(btn("✕ Del Row",     self._delete_row,    "Delete selected row"))

        sep3 = QFrame(); sep3.setFrameShape(QFrame.VLine)
        sep3.setStyleSheet("color:#3c3c3c;"); lay.addWidget(sep3)

        lay.addWidget(btn("+ Column",      self._add_column,    "Add a new column"))
        lay.addWidget(btn("Export .ini",   self._export_ini,    "Export TSLPatcher changes.ini"))

        lay.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search rows…  (Ctrl+F)")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            "  border-radius:3px; padding:3px 8px; }"
        )
        self.search_input.textChanged.connect(self._schedule_filter_rows)
        lay.addWidget(self.search_input)

        self.file_label = QLabel("No file loaded")
        self.file_label.setStyleSheet("color:#569cd6; font-family:Consolas; margin-left:8px;")
        lay.addWidget(self.file_label)

        return tb

    def _build_file_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#252526;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Tab-like header with source selector
        hdr = QWidget()
        hdr.setStyleSheet("background:#2d2d30; border-bottom:1px solid #3c3c3c;")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(6, 3, 6, 3)
        hdr_lay.setSpacing(4)

        lbl = QLabel("2DA Files")
        lbl.setStyleSheet("color:#cccccc; font-weight:bold;")
        hdr_lay.addWidget(lbl)

        self.source_combo = QComboBox()
        self.source_combo.addItem("Demo", "demo")
        self.source_combo.setStyleSheet("""
            QComboBox { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                        border-radius:3px; padding:1px 6px; }
            QComboBox::drop-down { border:none; }
            QComboBox QAbstractItemView { background:#252526; color:#cccccc;
                                           selection-background-color:#094771; }
        """)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        hdr_lay.addWidget(self.source_combo)
        hdr_lay.addStretch()
        lay.addWidget(hdr)

        # Filter box for file list
        self.file_filter = QLineEdit()
        self.file_filter.setPlaceholderText("Filter files…")
        self.file_filter.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:none;"
            "  border-bottom:1px solid #3c3c3c; padding:4px 8px; }"
        )
        self.file_filter.textChanged.connect(self._schedule_filter_file_list)
        lay.addWidget(self.file_filter)

        # Info label
        self.file_count_label = QLabel("")
        self.file_count_label.setStyleSheet(
            "color:#666; font-size:8pt; padding:2px 8px;"
        )
        lay.addWidget(self.file_count_label)

        # File list
        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget { background:#252526; border:none; }
            QListWidget::item { color:#cccccc; padding:3px 8px; font-family:Consolas;
                                font-size:9pt; }
            QListWidget::item:hover { background:#2a2d2e; }
            QListWidget::item:selected { background:#094771; }
        """)
        self.file_list.itemClicked.connect(self._on_file_selected)
        lay.addWidget(self.file_list)

        return panel

    def _build_editor(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#1e1e1e;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header bar
        hdr = QWidget()
        hdr.setStyleSheet("background:#2d2d30; border-bottom:1px solid #3c3c3c;")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(8, 4, 8, 4)
        self.editor_title = QLabel("Select a 2DA file to edit")
        self.editor_title.setStyleSheet("color:#9cdcfe; font-weight:bold; font-size:10pt;")
        hdr_lay.addWidget(self.editor_title)
        hdr_lay.addStretch()
        self.row_count_label = QLabel("")
        self.row_count_label.setStyleSheet("color:#666666; font-size:8pt;")
        hdr_lay.addWidget(self.row_count_label)
        lay.addWidget(hdr)

        # Table
        self.table = QTableWidget(0, 0)
        self.table.setStyleSheet("""
            QTableWidget { background:#252526; border:none; gridline-color:#3c3c3c;
                            color:#cccccc; }
            QTableWidget::item { padding:2px 6px; }
            QTableWidget::item:selected { background:#094771; color:white; }
            QTableWidget::item:hover { background:#2a2d2e; }
            QHeaderView::section { background:#2d2d30; color:#9cdcfe;
                                    border:none;
                                    border-right:1px solid #3c3c3c;
                                    border-bottom:1px solid #3c3c3c;
                                    padding:3px 8px; font-family:Consolas; }
        """)
        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Consolas", 9))
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.cellChanged.connect(self._on_cell_changed)
        # Enable sorting
        self.table.setSortingEnabled(False)  # disable while filling; user can enable
        lay.addWidget(self.table)

        return panel

    # ── Game Loading ──────────────────────────────────────────

    def _load_game_dir(self):
        """Ask user for KotOR installation dir, then populate the file list."""
        game_dir = QFileDialog.getExistingDirectory(
            self, "Select KotOR Game Directory (contains chitin.key)",
            str(Path.home())
        )
        if not game_dir:
            return
        self._load_game(Path(game_dir))

    def load_game_from_path(self, game_path: Path):
        """Called programmatically (e.g. from MainWindow settings)."""
        self._load_game(game_path)

    def _load_game(self, game_dir: Path):
        """Load KotOR resource manager and populate 2DA file list."""
        rm = ResourceManager()
        if not rm.load_game(game_dir):
            QMessageBox.critical(
                self, "Load Failed",
                f"Could not load game from:\n{game_dir}\n\nMake sure chitin.key exists."
            )
            return

        self._resource_manager = rm
        self._game_cache.clear()
        self._game_2da_entries = rm.list_by_type(".2da")

        # Add "Game Library" entry to source combo if not already there
        for i in range(self.source_combo.count()):
            if self.source_combo.itemData(i) == "game":
                self.source_combo.removeItem(i)
                break
        self.source_combo.addItem(f"🎮 Game Library ({len(self._game_2da_entries)} files)", "game")
        self.source_combo.setCurrentIndex(self.source_combo.count() - 1)

        log.info(f"Game loaded: {game_dir}, {len(self._game_2da_entries)} 2DAs")
        self.game_loaded.emit(str(game_dir))

    def _on_source_changed(self, idx: int):
        source = self.source_combo.itemData(idx)
        self.file_filter.clear()
        self.file_list.clear()

        if source == "demo":
            for name in self._demo_cache:
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, ("demo", name))
                self.file_list.addItem(item)
            self.file_count_label.setText(f"{self.file_list.count()} demo files")
        elif source == "game":
            self._populate_game_list()

    def _populate_game_list(self, filter_text: str = ""):
        """Fill the file list with the game's 2DA entries."""
        self.file_list.clear()
        ft = filter_text.lower()
        count = 0
        for entry in self._game_2da_entries:
            if ft and ft not in entry.resref.lower():
                continue
            item = QListWidgetItem(entry.filename)
            item.setData(Qt.UserRole, ("game", entry.resref))
            item.setForeground(QColor("#4ec9b0"))
            self.file_list.addItem(item)
            count += 1
        self.file_count_label.setText(
            f"{count} / {len(self._game_2da_entries)} game 2DAs"
        )

    # ── File Operations ───────────────────────────────────────

    def _load_demo_files(self):
        demos = {
            "globalcat.2da": SAMPLE_GLOBALCAT_TEXT,
            "appearance.2da": SAMPLE_APPEARANCE_TEXT,
            "spells.2da": SAMPLE_SPELLS_TEXT,
        }
        for name, text in demos.items():
            f = TwoDAFile.from_text(text, name)
            self._demo_cache[name] = f
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, ("demo", name))
            self.file_list.addItem(item)
        self.file_count_label.setText(f"{len(demos)} demo files")

        # Also check project 2DA dir
        if self.project:
            twoda_dir = getattr(self.project, "twoda_dir", None)
            if twoda_dir and Path(twoda_dir).exists():
                for path in Path(twoda_dir).glob("*.2da"):
                    if path.name not in self._demo_cache:
                        item = QListWidgetItem(path.name)
                        item.setData(Qt.UserRole, ("disk", str(path)))
                        item.setForeground(QColor("#ce9178"))
                        self.file_list.addItem(item)

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open 2DA File", "", "2DA Files (*.2da);;All Files (*)"
        )
        if not path:
            return
        try:
            f = TwoDAFile.from_file(Path(path))
            self._original_file = copy.deepcopy(f)
            self.current_file = f
            self._display_file(f)
            # Add to list if not present
            name = Path(path).name
            existing = [self.file_list.item(i).text()
                        for i in range(self.file_list.count())]
            if name not in existing:
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, ("disk", path))
                item.setForeground(QColor("#ce9178"))
                self.file_list.addItem(item)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open 2DA:\n{e}")

    def _save_file(self):
        if not self.current_file:
            return
        if self.current_file.file_path:
            try:
                self.current_file.save()
                self.file_label.setText(f"✓ {self.current_file.filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
        else:
            self._save_as()

    def _save_as(self):
        if not self.current_file:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save 2DA", self.current_file.filename, "2DA Files (*.2da)"
        )
        if path:
            try:
                self.current_file.save(Path(path))
                self.current_file.file_path = Path(path)
                self.file_label.setText(f"✓ {Path(path).name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _on_file_selected(self, item: QListWidgetItem):
        source, key = item.data(Qt.UserRole)
        try:
            if source == "demo":
                self.current_file = self._demo_cache.get(key)
                self._original_file = None
                if self.current_file:
                    self._display_file(self.current_file)
            elif source == "game":
                self._load_game_2da(key)
            elif source == "disk":
                f = TwoDAFile.from_file(Path(key))
                self._original_file = copy.deepcopy(f)
                self.current_file = f
                self._display_file(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _load_game_2da(self, resref: str):
        """Load a 2DA from the game resource manager."""
        if not self._resource_manager:
            return

        # Check cache
        if resref in self._game_cache:
            self.current_file = self._game_cache[resref]
            self._display_file(self.current_file)
            return

        filename = f"{resref}.2da"
        data = self._resource_manager.read(filename)
        if data is None:
            QMessageBox.warning(self, "Not Found", f"Could not read: {filename}")
            return

        try:
            f = TwoDAFile.from_bytes(data, filename)
            self._game_cache[resref] = f
            # Keep original for change tracking
            self._original_file = TwoDAFile.from_bytes(data, filename)
            self.current_file = f
            self._display_file(f)
        except Exception as e:
            QMessageBox.critical(self, "Parse Error",
                                 f"Failed to parse {filename}:\n{e}")

    # ── Display ───────────────────────────────────────────────

    # Shared colours — created once, reused across renders
    _GREY    = QColor("#858585")
    _DIM     = QColor("#444444")
    _GREEN   = QColor("#b5cea8")
    _NO_EDIT = Qt.ItemIsSelectable | Qt.ItemIsEnabled

    def _display_file(self, f: TwoDAFile):
        """Full table render — used on initial load / undo / redo / column changes."""
        self.table.cellChanged.disconnect(self._on_cell_changed)
        self.table.setSortingEnabled(False)

        # Freeze all repaints until the table is fully populated
        self.table.setUpdatesEnabled(False)
        self.table.clearContents()

        self.editor_title.setText(f.filename)
        self.file_label.setText(f.filename)
        self.row_count_label.setText(
            f"{len(f.rows)} rows × {len(f.columns)} cols"
        )

        all_cols = ["Row"] + f.columns
        self.table.setColumnCount(len(all_cols))
        self.table.setHorizontalHeaderLabels(all_cols)
        self.table.setRowCount(len(f.rows))

        grey    = self._GREY
        dim     = self._DIM
        green   = self._GREEN
        no_edit = self._NO_EDIT

        for row_idx, row in enumerate(f.rows):
            lbl_item = QTableWidgetItem(row.label)
            lbl_item.setForeground(grey)
            lbl_item.setFlags(no_edit)
            self.table.setItem(row_idx, 0, lbl_item)
            for col_idx, col in enumerate(f.columns, start=1):
                val = row.data.get(col, "****")
                cell = QTableWidgetItem(val)
                if val == "****":
                    cell.setForeground(dim)
                elif val.isdigit():
                    cell.setForeground(green)
                self.table.setItem(row_idx, col_idx, cell)

        # Fixed column widths — avoid ResizeToContents which is O(rows×cols)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.setColumnWidth(0, 80)   # row-label column fixed
        for i in range(1, len(all_cols)):
            hdr.setSectionResizeMode(i, QHeaderView.Interactive)
            self.table.setColumnWidth(i, 90)

        self.table.setUpdatesEnabled(True)
        self.table.cellChanged.connect(self._on_cell_changed)

    def _append_row_to_table(self, row_idx: int):
        """Append a single already-added row to the table without a full re-render."""
        if not self.current_file:
            return
        f = self.current_file
        self.table.cellChanged.disconnect(self._on_cell_changed)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(row_idx + 1)
        row = f.rows[row_idx]
        grey    = self._GREY
        dim     = self._DIM
        green   = self._GREEN
        no_edit = self._NO_EDIT
        lbl_item = QTableWidgetItem(row.label)
        lbl_item.setForeground(grey)
        lbl_item.setFlags(no_edit)
        self.table.setItem(row_idx, 0, lbl_item)
        for col_idx, col in enumerate(f.columns, start=1):
            val = row.data.get(col, "****")
            cell = QTableWidgetItem(val)
            if val == "****":
                cell.setForeground(dim)
            elif val.isdigit():
                cell.setForeground(green)
            self.table.setItem(row_idx, col_idx, cell)
        self.row_count_label.setText(f"{len(f.rows)} rows × {len(f.columns)} cols")
        self.table.setUpdatesEnabled(True)
        self.table.cellChanged.connect(self._on_cell_changed)

    def _update_row_in_table(self, row_idx: int):
        """Update cells for a single existing row in-place (no full re-render)."""
        if not self.current_file or row_idx >= len(self.current_file.rows):
            return
        f = self.current_file
        row = f.rows[row_idx]
        self.table.cellChanged.disconnect(self._on_cell_changed)
        self.table.setUpdatesEnabled(False)
        dim   = self._DIM
        green = self._GREEN
        for col_idx, col in enumerate(f.columns, start=1):
            val = row.data.get(col, "****")
            item = self.table.item(row_idx, col_idx)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row_idx, col_idx, item)
            item.setText(val)
            if val == "****":
                item.setForeground(dim)
            elif val.isdigit():
                item.setForeground(green)
            else:
                item.setForeground(QColor("#cccccc"))
        self.table.setUpdatesEnabled(True)
        self.table.cellChanged.connect(self._on_cell_changed)

    def _refresh_display(self):
        """Full re-render — used for undo/redo and column structure changes."""
        if self.current_file:
            self._display_file(self.current_file)

    def _on_cell_changed(self, row: int, col: int):
        if not self.current_file or col == 0:
            return
        item = self.table.item(row, col)
        if item and 0 <= row < len(self.current_file.rows):
            col_name = self.current_file.columns[col - 1]
            self.current_file.rows[row].data[col_name] = item.text()

    # ── Row Operations ────────────────────────────────────────

    def _add_row(self):
        if not self.current_file:
            QMessageBox.warning(self, "No File", "Open a 2DA file first.")
            return
        dlg = AddRowDialog(self.current_file.columns, self)
        if dlg.exec() != QDialog.Accepted:
            return
        label, exclusive, data = dlg.get_result()
        idx = self.current_file.add_row(label or "", data, exclusive_column=exclusive)
        self._append_row_to_table(idx)
        self.table.scrollToItem(self.table.item(idx, 0))

    def _copy_row(self):
        row = self.table.currentRow()
        if row < 0 or not self.current_file:
            QMessageBox.warning(self, "No Selection", "Select a row to copy.")
            return
        source = self.current_file.rows[row]
        dlg = CopyRowDialog(source, self.current_file.columns, self)
        if dlg.exec() != QDialog.Accepted:
            return
        new_label, overrides = dlg.get_result()
        try:
            new_idx = self.current_file.copy_row(row, new_label, overrides)
            self._append_row_to_table(new_idx)
            self.table.scrollToItem(self.table.item(new_idx, 0))
        except Exception as e:
            QMessageBox.critical(self, "Copy Row Failed", str(e))

    def _modify_row(self):
        row = self.table.currentRow()
        if row < 0 or not self.current_file:
            QMessageBox.warning(self, "No Selection", "Select a row to modify.")
            return
        source = self.current_file.rows[row]
        dlg = CopyRowDialog(source, self.current_file.columns, self)
        dlg.setWindowTitle("Modify Row")
        dlg.label_edit.hide()
        if dlg.exec() != QDialog.Accepted:
            return
        _, overrides = dlg.get_result()
        if overrides:
            self.current_file.modify_row(row, overrides)
            self._update_row_in_table(row)

    def _delete_row(self):
        row = self.table.currentRow()
        if row < 0 or not self.current_file:
            return
        if row >= len(self.current_file.rows):
            return
        label = self.current_file.rows[row].label
        reply = QMessageBox.question(
            self, "Delete Row", f"Delete row '{label}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.current_file.remove_row_by_index(row)
            self._refresh_display()

    def _add_column(self):
        if not self.current_file:
            return
        name, ok = QInputDialog.getText(self, "Add Column", "Column name:")
        if ok and name:
            default, ok2 = QInputDialog.getText(
                self, "Default Value", f"Default value for '{name}':", text="****"
            )
            if ok2:
                self.current_file.add_column(name, default or "****")
                self._refresh_display()

    # ── Undo / Redo ───────────────────────────────────────────

    def _undo(self):
        if self.current_file and self.current_file.undo():
            self._refresh_display()

    def _redo(self):
        if self.current_file and self.current_file.redo():
            self._refresh_display()

    # ── Export ────────────────────────────────────────────────

    def _export_ini(self):
        if not self.current_file:
            QMessageBox.warning(self, "No File", "Open a 2DA file first.")
            return
        if self._original_file:
            ini_text = self.current_file.export_changes_ini(self._original_file)
        else:
            lines = [f"[{self.current_file.filename}]"]
            for row in self.current_file.rows:
                cells = ", ".join(f"{col}={val}" for col, val in row.data.items()
                                  if val != "****")
                lines.append(f"AddRow {row.label}={cells}")
            ini_text = "\n".join(lines)

        dlg = QDialog(self)
        dlg.setWindowTitle("TSLPatcher changes.ini Export")
        dlg.setMinimumSize(600, 440)
        dlg.setStyleSheet("background:#252526; color:#cccccc;")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Paste this into your TSLPatcher changes.ini:"))
        te = QTextEdit()
        te.setPlainText(ini_text)
        te.setFont(QFont("Consolas", 9))
        te.setStyleSheet("background:#1e1e1e; color:#cccccc; border:none;")
        lay.addWidget(te)

        btn_bar = QHBoxLayout()
        copy_btn = QPushButton("📋 Copy to Clipboard")
        copy_btn.clicked.connect(
            lambda: QApplication.clipboard().setText(ini_text))
        save_btn = QPushButton("💾 Save As…")

        def _save():
            path, _ = QFileDialog.getSaveFileName(
                dlg, "Save changes.ini", "changes.ini", "INI (*.ini)")
            if path:
                Path(path).write_text(ini_text, encoding="utf-8")

        save_btn.clicked.connect(_save)
        for b in (copy_btn, save_btn):
            b.setStyleSheet(
                "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
                "  border-radius:3px; padding:4px 12px; }"
            )
        btn_bar.addWidget(copy_btn)
        btn_bar.addWidget(save_btn)
        btn_bar.addStretch()
        lay.addLayout(btn_bar)
        dlg.exec()

    # ── Context Menu ──────────────────────────────────────────

    def _on_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if not self.current_file or row < 0:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#252526; color:#cccccc; border:1px solid #3c3c3c; }
            QMenu::item:selected { background:#094771; }
        """)

        menu.addAction("✕ Delete Row",    self._delete_row)
        menu.addAction("⧉ Copy Row",      self._copy_row)
        menu.addAction("✏ Modify Row",    self._modify_row)
        menu.addSeparator()

        col = self.table.columnAt(pos.x())
        item = self.table.item(row, col)
        if item:
            val = item.text()
            menu.addAction(
                f"📋 Copy: \"{val[:40]}{'…' if len(val) > 40 else ''}\"",
                lambda v=val: QApplication.clipboard().setText(v)
            )

        menu.addSeparator()
        menu.addAction("📤 Export row as TSLPatcher AddRow",
                       lambda r=row: self._export_single_row(r))

        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _export_single_row(self, row_idx: int):
        """Export just one row as a TSLPatcher AddRow snippet."""
        if not self.current_file or row_idx >= len(self.current_file.rows):
            return
        row = self.current_file.rows[row_idx]
        cells = ", ".join(f"{col}={val}" for col, val in row.data.items()
                          if val != "****")
        snippet = f"[{self.current_file.filename}]\nAddRow {row.label}={cells}"
        QApplication.clipboard().setText(snippet)
        QMessageBox.information(self, "Copied",
                                "Row exported as TSLPatcher snippet and copied to clipboard.")

    # ── Filter / Search ───────────────────────────────────────

    # ── Debounced filter helpers ─────────────────────────────────────

    def _schedule_filter_file_list(self, text: str):
        """Debounce file-list filtering (150 ms after last keystroke)."""
        self._pending_list_filter = text
        self._filter_list_timer.start()

    def _schedule_filter_rows(self, text: str):
        """Debounce row filtering (180 ms after last keystroke)."""
        self._pending_filter_text = text
        self._filter_rows_timer.start()

    def _apply_filter_file_list(self):
        text = self._pending_list_filter
        source = self.source_combo.currentData()
        if source == "game":
            # Rebuild list only when debounce fires, not on every keystroke
            self._populate_game_list(text)
        else:
            ft = text.lower()
            for i in range(self.file_list.count()):
                item = self.file_list.item(i)
                item.setHidden(ft not in item.text().lower())

    def _filter_file_list(self, text: str):
        """Direct filter — delegates to debounced version."""
        self._schedule_filter_file_list(text)

    def _apply_filter_rows(self):
        """Filter visible table rows (called after debounce timer fires)."""
        text = self._pending_filter_text
        ft = text.lower()
        self.table.setUpdatesEnabled(False)
        for row in range(self.table.rowCount()):
            if not ft:
                self.table.setRowHidden(row, False)
                continue
            match = False
            for col in range(self.table.columnCount()):
                it = self.table.item(row, col)
                if it and ft in it.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)
        self.table.setUpdatesEnabled(True)

    def _filter_rows(self, text: str):
        """Direct filter — delegates to debounced version."""
        self._schedule_filter_rows(text)

    # ── IPC integration ───────────────────────────────────────

    def select_file(self, filename: str) -> bool:
        """
        Select and load a named .2da file in the file list.
        Called by MainWindow.ipc_open_2da() when another GhostWorks
        app sends an open_2da IPC message.

        ``filename`` may be a bare name ("appearance"), a full name
        ("appearance.2da"), or any case variant.

        Returns True if the file was found and selected.
        """
        # Normalise: strip extension, lower-case for comparison
        stem = filename.lower().removesuffix(".2da")

        # First clear any active filter so the item is visible
        self.file_filter.clear()

        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item is None:
                continue
            item_text = item.text().lower().removesuffix(".2da")
            if item_text == stem:
                self.file_list.setCurrentItem(item)
                self.file_list.scrollToItem(item)
                self._on_file_selected(item)
                return True

        # Not visible in list — try to load directly from the resource manager
        if self._resource_manager:
            resref = stem  # resource manager keys are bare stems
            if resref in [n.lower() for n in (self._resource_manager.list_by_type(".2da") or [])]:
                # Synthesise a list item and select it
                item = QListWidgetItem(f"{stem}.2da")
                item.setData(Qt.UserRole, ("game", stem))
                self.file_list.addItem(item)
                self.file_list.setCurrentItem(item)
                self.file_list.scrollToItem(item)
                self._on_file_selected(item)
                return True

        log.warning(f"TwoDAManagerWidget.select_file: '{filename}' not found in list")
        return False

    def scroll_to_row(self, row_index: int) -> bool:
        """
        Scroll the 2DA table so that row_index is visible and select it.
        Called by MainWindow.ipc_open_2da() with the row hint from the
        open_2da IPC payload.

        Returns True if the row was visible in the current table.
        """
        if not hasattr(self, "table_widget") or self.table_widget is None:
            return False
        row_count = self.table_widget.rowCount()
        if row_count == 0 or row_index < 0:
            return False
        target = min(row_index, row_count - 1)
        self.table_widget.selectRow(target)
        item = self.table_widget.item(target, 0)
        if item:
            self.table_widget.scrollToItem(item)
        return True
