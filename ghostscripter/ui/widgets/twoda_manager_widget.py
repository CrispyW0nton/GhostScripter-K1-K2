"""
GhostScripter-K1-K2 — 2DA File Manager Widget
"""
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QMessageBox, QFileDialog, QListWidget, QListWidgetItem,
    QComboBox, QFrame, QPlainTextEdit, QInputDialog,
)

import importlib
_twoda = importlib.import_module("ghostscripter.core.2da_manager.twoda_manager")
TwoDAFile = _twoda.TwoDAFile
GlobalCatManager = _twoda.GlobalCatManager

# Sample built-in 2DA for demo
SAMPLE_GLOBALCAT_TEXT = """2DA V2.0

          Name             Type
0         K_SWG_DEMO       Boolean
1         K_GLOBAL_ALIGN   Number
2         K_PARTY_SIZE     Number
"""

SAMPLE_APPEARANCE_TEXT = """2DA V2.0

     label                  modela  modelb  tex1
0    Revan_PC                p_mal01 ****    PMHC01
1    C_Bastila               p_bast  ****    PFHC03
2    C_HK47                  c_hk47  ****    C_HK47
"""


class TwoDAManagerWidget(QWidget):

    def __init__(self, project=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.current_file: Optional[TwoDAFile] = None
        self._setup_ui()
        self._load_demo_files()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        tb = self._build_toolbar()
        layout.addWidget(tb)

        # Main splitter: file list | table editor
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(2)

        left = self._build_file_list()
        split.addWidget(left)

        right = self._build_editor()
        split.addWidget(right)

        split.setSizes([200, 900])
        layout.addWidget(split)

    def _build_toolbar(self) -> QWidget:
        tb = QWidget()
        tb.setStyleSheet("background:#2d2d30; border-bottom:1px solid #3c3c3c;")
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(4)

        def btn(label, slot, primary=False):
            b = QPushButton(label)
            b.clicked.connect(slot)
            b.setFixedHeight(24)
            if primary:
                b.setStyleSheet("QPushButton { background:#0078d4; color:white; "
                                 "border:1px solid #1a8fe0; border-radius:3px; "
                                 "padding:2px 10px; font-weight:bold; } "
                                 "QPushButton:hover { background:#1a8fe0; }")
            else:
                b.setStyleSheet("QPushButton { background:#3c3c3c; color:#cccccc; "
                                 "border:1px solid #555; border-radius:3px; "
                                 "padding:2px 8px; } "
                                 "QPushButton:hover { background:#4a4a4a; color:white; }")
            return b

        lay.addWidget(btn("Open 2DA", self._open_file, True))
        lay.addWidget(btn("Save", self._save_file))
        lay.addWidget(btn("+ Add Row", self._add_row))
        lay.addWidget(btn("Delete Row", self._delete_row))
        lay.addWidget(btn("+ Add Column", self._add_column))

        lay.addWidget(QFrame())  # spacer

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search rows…")
        self.search_input.setFixedWidth(180)
        self.search_input.setStyleSheet("""
            QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                        border-radius:3px; padding:3px 8px; }
        """)
        self.search_input.textChanged.connect(self._filter_rows)
        lay.addWidget(self.search_input)
        lay.addStretch()

        self.file_label = QLabel("No file")
        self.file_label.setStyleSheet("color:#569cd6; font-family:Consolas;")
        lay.addWidget(self.file_label)

        return tb

    def _build_file_list(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#252526;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QLabel("2DA Files")
        header.setStyleSheet("background:#2d2d30; color:#cccccc; font-weight:bold; "
                              "padding:5px 8px; border-bottom:1px solid #3c3c3c;")
        lay.addWidget(header)

        self.file_list = QListWidget()
        self.file_list.setStyleSheet("""
            QListWidget { background:#252526; border:none; }
            QListWidget::item { color:#cccccc; padding:4px 8px; font-family:Consolas; }
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

        # Header
        hdr = QWidget()
        hdr.setStyleSheet("background:#2d2d30; border-bottom:1px solid #3c3c3c;")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(8, 4, 8, 4)
        self.editor_title = QLabel("Select a 2DA file to edit")
        self.editor_title.setStyleSheet("color:#9cdcfe; font-weight:bold;")
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
            QTableWidget::item { padding:4px 6px; }
            QTableWidget::item:selected { background:#094771; color:white; }
            QTableWidget::item:hover { background:#2a2d2e; }
            QHeaderView::section { background:#2d2d30; color:#cccccc; border:none;
                                    border-right:1px solid #3c3c3c;
                                    border-bottom:1px solid #3c3c3c; padding:4px 8px; }
        """)
        self.table.setAlternatingRowColors(True)
        self.table.setFont(QFont("Consolas", 9))
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.cellChanged.connect(self._on_cell_changed)
        lay.addWidget(self.table)

        return panel

    # ── File Operations ───────────────────────────────────────

    def _load_demo_files(self):
        """Load demo 2DA files for display."""
        demo_files = {
            "globalcat.2da": SAMPLE_GLOBALCAT_TEXT,
            "appearance.2da": SAMPLE_APPEARANCE_TEXT,
        }
        self._demo_cache = {}
        for name, text in demo_files.items():
            f = TwoDAFile.from_text(text, name)
            self._demo_cache[name] = f
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            self.file_list.addItem(item)

        # Try loading from project
        if self.project and self.project.twoda_dir:
            for path in Path(self.project.twoda_dir).glob("*.2da"):
                if path.name not in self._demo_cache:
                    item = QListWidgetItem(path.name)
                    item.setData(Qt.UserRole, str(path))
                    item.setForeground(QColor("#4ec9b0"))
                    self.file_list.addItem(item)

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open 2DA File", "", "2DA Files (*.2da);;All Files (*)"
        )
        if not path:
            return
        try:
            f = TwoDAFile.from_file(Path(path))
            self.current_file = f
            self._display_file(f)
            # Add to list if not present
            name = Path(path).name
            existing = [self.file_list.item(i).text()
                        for i in range(self.file_list.count())]
            if name not in existing:
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, path)
                self.file_list.addItem(item)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open 2DA:\n{e}")

    def _save_file(self):
        if not self.current_file:
            return
        if self.current_file.file_path:
            try:
                self.current_file.save()
                QMessageBox.information(self, "Saved",
                    f"Saved: {self.current_file.filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save 2DA", self.current_file.filename, "2DA Files (*.2da)"
            )
            if path:
                self.current_file.save(Path(path))

    def _on_file_selected(self, item: QListWidgetItem):
        key = item.data(Qt.UserRole)
        if key in self._demo_cache:
            self.current_file = self._demo_cache[key]
            self._display_file(self.current_file)
        elif Path(key).exists():
            try:
                f = TwoDAFile.from_file(Path(key))
                self.current_file = f
                self._display_file(f)
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _display_file(self, f: TwoDAFile):
        self.table.cellChanged.disconnect(self._on_cell_changed)
        self.table.clear()
        self.editor_title.setText(f.filename)
        self.file_label.setText(f.filename)
        self.row_count_label.setText(f"{len(f.rows)} rows × {len(f.columns)} cols")

        # Set up columns: "Row" + data columns
        all_cols = ["Row"] + f.columns
        self.table.setColumnCount(len(all_cols))
        self.table.setHorizontalHeaderLabels(all_cols)
        self.table.setRowCount(len(f.rows))

        for row_idx, row in enumerate(f.rows):
            lbl_item = QTableWidgetItem(row.label)
            lbl_item.setForeground(QColor("#858585"))
            lbl_item.setFlags(lbl_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 0, lbl_item)
            for col_idx, col in enumerate(f.columns, start=1):
                val = row.data.get(col, "****")
                cell = QTableWidgetItem(val)
                if val == "****":
                    cell.setForeground(QColor("#444444"))
                self.table.setItem(row_idx, col_idx, cell)

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        for i in range(1, len(all_cols)):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.table.cellChanged.connect(self._on_cell_changed)

    def _on_cell_changed(self, row: int, col: int):
        if not self.current_file or col == 0:
            return
        item = self.table.item(row, col)
        if item and 0 <= row < len(self.current_file.rows):
            col_name = self.current_file.columns[col - 1]
            self.current_file.rows[row].data[col_name] = item.text()

    def _add_row(self):
        if not self.current_file:
            QMessageBox.warning(self, "No File", "Open a 2DA file first.")
            return
        label, ok = QInputDialog.getText(self, "Add Row", "Row label:")
        if ok and label:
            data = {col: "****" for col in self.current_file.columns}
            self.current_file.add_row(label, data)
            self._display_file(self.current_file)

    def _delete_row(self):
        row = self.table.currentRow()
        if row >= 0 and self.current_file and row < len(self.current_file.rows):
            reply = QMessageBox.question(
                self, "Delete Row",
                f"Delete row '{self.current_file.rows[row].label}'?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                del self.current_file.rows[row]
                self._display_file(self.current_file)

    def _add_column(self):
        if not self.current_file:
            return
        name, ok = QInputDialog.getText(self, "Add Column", "Column name:")
        if ok and name:
            self.current_file.add_column(name)
            self._display_file(self.current_file)

    def _filter_rows(self, text: str):
        if not self.current_file:
            return
        for row in range(self.table.rowCount()):
            match = False
            if not text:
                match = True
            else:
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if item and text.lower() in item.text().lower():
                        match = True
                        break
            self.table.setRowHidden(row, not match)
