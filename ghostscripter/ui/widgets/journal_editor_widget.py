"""
GhostScripter-K1-K2 — Journal Editor Widget
============================================
Provides a full UI for editing KotOR .jrl (journal/quest) files.

Layout
------
Left panel  : Category list  (quest categories, e.g. "K_SWG_MYQUEST")
Right panels: Category form  (name, tag, priority, comment)
              Entry table    (ID | Text | End | QuestEntry | Comment)
              Entry form     (edit selected entry)

Features
--------
- Add / Remove categories
- Add / Remove / Edit journal entries per category
- "End" entry flag (marks quest complete)
- "QuestEntry" flag (triggers a journal pop-up in-game)
- Export to .jrl binary (GFF V3.2) via JRLExporter
- Import from .jrl binary via JRLImporter
- Dirty-flag tracking → tab title shows * on changes
"""
from __future__ import annotations

import logging
from pathlib import Path


log = logging.getLogger(__name__)

try:
    from qtpy.QtWidgets import (
        QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
        QListWidget, QListWidgetItem, QLabel, QPushButton,
        QLineEdit, QTextEdit, QSpinBox, QCheckBox, QTableWidget,
        QTableWidgetItem, QHeaderView, QAbstractItemView,
        QGroupBox, QFormLayout, QMessageBox, QFileDialog,
        QFrame, QSizePolicy,
    )
    from qtpy.QtCore import Qt, Signal, QTimer
    from qtpy.QtGui import QColor, QFont
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

from ghostscripter.core.models.journal import (
    JournalFile, JournalCategory, JournalEntry, create_quest_journal,
)
from ghostscripter.core.export.jrl_writer import JRLExporter, JRLImporter


# ── Helpers ───────────────────────────────────────────────────────────────────

_DARK_HEADER = (
    "QHeaderView::section {"
    "  background:#2d2d30; color:#d4d4d4; padding:3px;"
    "  border:1px solid #3f3f46;"
    "}"
)
_DARK_TABLE = (
    "QTableWidget { background:#1e1e1e; color:#d4d4d4; gridline-color:#3f3f46; }"
    "QTableWidget::item:selected { background:#264f78; }"
)
_DARK_INPUT = (
    "QLineEdit, QTextEdit, QSpinBox {"
    "  background:#252526; color:#d4d4d4; border:1px solid #3f3f46;"
    "  border-radius:2px; padding:2px;"
    "}"
)
_DARK_BTN = (
    "QPushButton {"
    "  background:#3c3c3c; color:#d4d4d4; border:1px solid #555;"
    "  border-radius:3px; padding:4px 10px;"
    "}"
    "QPushButton:hover { background:#505050; }"
    "QPushButton:pressed { background:#0e639c; }"
)


if _QT_AVAILABLE:

    class JournalEditorWidget(QWidget):
        """
        Full-featured editor for KotOR .jrl journal files.
        """

        # Emitted when the content changes (dirty flag set)
        journal_modified = Signal()

        def __init__(self, journal: JournalFile | None = None,
                     parent: QWidget | None = None):
            super().__init__(parent)
            self.journal: JournalFile = journal or JournalFile("new_journal")
            self._dirty = False
            self._updating = False   # guard against recursive _on_* calls
            self._game_dir: Path | None = None

            self._setup_ui()
            self._populate_category_list()
            self.setStyleSheet(_DARK_INPUT + _DARK_BTN)
            # Ensure the widget is large enough to show the table on first open
            self.setMinimumSize(900, 600)

        # ── Public API ────────────────────────────────────────────────────────

        @property
        def is_dirty(self) -> bool:
            return self._dirty

        def set_journal(self, journal: JournalFile) -> None:
            self.journal = journal
            self._dirty = False
            self._populate_category_list()

        def set_game_dir(self, path: Path) -> None:
            self._game_dir = path

        # ── UI Construction ───────────────────────────────────────────────────

        def _setup_ui(self) -> None:
            root = QHBoxLayout(self)
            root.setContentsMargins(4, 4, 4, 4)
            root.setSpacing(4)

            # Outer horizontal splitter: left (category panel) | right (entry panel)
            h_splitter = QSplitter(Qt.Horizontal)
            h_splitter.setHandleWidth(4)
            root.addWidget(h_splitter)

            # ── Left: category list + buttons ─────────────────────────────────
            left = QWidget()
            left.setMinimumWidth(160)
            lv = QVBoxLayout(left)
            lv.setContentsMargins(0, 0, 0, 0)
            lv.setSpacing(4)

            lbl = QLabel("📖 Categories")
            lbl.setStyleSheet("color:#9cdcfe; font-weight:bold; padding:3px 4px;")
            lv.addWidget(lbl)

            self.cat_list = QListWidget()
            self.cat_list.setStyleSheet(
                "QListWidget { background:#252526; color:#d4d4d4; "
                "border:1px solid #3f3f46; }"
                "QListWidget::item:selected { background:#264f78; }"
            )
            self.cat_list.currentRowChanged.connect(self._on_category_selected)
            lv.addWidget(self.cat_list, 1)  # stretch=1 so list fills available space

            btn_row = QHBoxLayout()
            btn_add_cat = QPushButton("+ Category")
            btn_add_cat.clicked.connect(self._add_category)
            btn_del_cat = QPushButton("✕ Remove")
            btn_del_cat.clicked.connect(self._remove_category)
            btn_row.addWidget(btn_add_cat)
            btn_row.addWidget(btn_del_cat)
            lv.addLayout(btn_row)

            # File ops
            btn_row2 = QHBoxLayout()
            btn_import = QPushButton("📂 Import .jrl")
            btn_import.clicked.connect(self._import_jrl)
            btn_export = QPushButton("💾 Export .jrl")
            btn_export.clicked.connect(self._export_jrl)
            btn_row2.addWidget(btn_import)
            btn_row2.addWidget(btn_export)
            lv.addLayout(btn_row2)

            h_splitter.addWidget(left)
            h_splitter.setStretchFactor(0, 0)

            # ── Right: vertical splitter (top = cat props + table) | (bottom = edit form)
            right_v_splitter = QSplitter(Qt.Vertical)
            right_v_splitter.setHandleWidth(4)

            # ── Top pane: category properties + entry table ───────────────────
            top_pane = QWidget()
            tp = QVBoxLayout(top_pane)
            tp.setContentsMargins(0, 0, 0, 0)
            tp.setSpacing(4)

            # Category properties group (compact, collapsible-feel via fixed max height)
            cat_group = QGroupBox("Category Properties")
            cat_group.setStyleSheet(
                "QGroupBox { color:#9cdcfe; border:1px solid #3f3f46; "
                "margin-top:6px; padding-bottom:4px; } "
                "QGroupBox::title { subcontrol-origin:margin; padding:0 4px; }"
            )
            cat_group.setMaximumHeight(140)  # keep it compact so table has space
            cg_form = QFormLayout(cat_group)
            cg_form.setLabelAlignment(Qt.AlignRight)
            cg_form.setSpacing(4)
            cg_form.setContentsMargins(6, 4, 6, 4)

            self.cat_tag = QLineEdit()
            self.cat_tag.setPlaceholderText("K_SWG_MYQUEST")
            self.cat_tag.textChanged.connect(self._on_cat_tag_changed)

            self.cat_name = QLineEdit()
            self.cat_name.setPlaceholderText("Quest display name")
            self.cat_name.textChanged.connect(self._on_cat_name_changed)

            self.cat_priority = QSpinBox()
            self.cat_priority.setRange(0, 99)
            self.cat_priority.valueChanged.connect(self._on_cat_priority_changed)

            self.cat_comment = QLineEdit()
            self.cat_comment.setPlaceholderText("(optional comment)")
            self.cat_comment.textChanged.connect(self._on_cat_comment_changed)

            cg_form.addRow("Tag:",      self.cat_tag)
            cg_form.addRow("Name:",     self.cat_name)
            cg_form.addRow("Priority:", self.cat_priority)
            cg_form.addRow("Comment:",  self.cat_comment)
            tp.addWidget(cat_group)

            # Entry table header + action bar
            entry_header = QWidget()
            eh_lay = QHBoxLayout(entry_header)
            eh_lay.setContentsMargins(2, 0, 2, 0)
            eh_lay.setSpacing(6)
            entry_lbl = QLabel("📝 Journal Entries")
            entry_lbl.setStyleSheet("color:#9cdcfe; font-weight:bold;")
            eh_lay.addWidget(entry_lbl)
            eh_lay.addStretch()
            btn_add_ent = QPushButton("+ Entry")
            btn_add_ent.setFixedHeight(22)
            btn_add_ent.clicked.connect(self._add_entry)
            btn_del_ent = QPushButton("✕ Remove")
            btn_del_ent.setFixedHeight(22)
            btn_del_ent.clicked.connect(self._remove_entry)
            btn_move_up = QPushButton("▲")
            btn_move_up.setFixedSize(28, 22)
            btn_move_up.clicked.connect(self._move_entry_up)
            btn_move_dn = QPushButton("▼")
            btn_move_dn.setFixedSize(28, 22)
            btn_move_dn.clicked.connect(self._move_entry_down)
            for b in (btn_add_ent, btn_del_ent, btn_move_up, btn_move_dn):
                b.setStyleSheet(
                    "QPushButton { background:#3c3c3c; color:#d4d4d4; border:1px solid #555;"
                    " border-radius:3px; padding:1px 6px; font-size:8pt; }"
                    "QPushButton:hover { background:#505050; }"
                )
                eh_lay.addWidget(b)
            tp.addWidget(entry_header)

            self.entry_table = QTableWidget(0, 5)
            self.entry_table.setHorizontalHeaderLabels(
                ["ID", "Text", "End", "Quest", "Comment"]
            )
            self.entry_table.horizontalHeader().setSectionResizeMode(
                1, QHeaderView.Stretch
            )
            self.entry_table.horizontalHeader().setSectionResizeMode(
                4, QHeaderView.ResizeToContents
            )
            self.entry_table.setColumnWidth(0, 55)   # ID column
            self.entry_table.setColumnWidth(2, 50)   # End column
            self.entry_table.setColumnWidth(3, 60)   # Quest column
            self.entry_table.setMinimumHeight(180)
            self.entry_table.setStyleSheet(_DARK_TABLE)
            self.entry_table.horizontalHeader().setStyleSheet(_DARK_HEADER)
            self.entry_table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self.entry_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.entry_table.setAlternatingRowColors(True)
            self.entry_table.setFont(QFont("Consolas", 9))
            self.entry_table.itemSelectionChanged.connect(self._on_entry_selection_changed)
            tp.addWidget(self.entry_table, 1)  # stretch=1: table grows to fill top pane

            right_v_splitter.addWidget(top_pane)

            # ── Bottom pane: entry edit form ──────────────────────────────────
            ent_group = QGroupBox("Edit Entry")
            ent_group.setStyleSheet(
                "QGroupBox { color:#9cdcfe; border:1px solid #3f3f46; "
                "margin-top:6px; } "
                "QGroupBox::title { subcontrol-origin:margin; padding:0 4px; }"
            )
            eg_form = QFormLayout(ent_group)
            eg_form.setLabelAlignment(Qt.AlignRight)
            eg_form.setSpacing(5)
            eg_form.setContentsMargins(6, 6, 6, 6)

            self.ent_id = QSpinBox()
            self.ent_id.setRange(0, 999)
            self.ent_id.valueChanged.connect(self._on_ent_id_changed)

            self.ent_text = QTextEdit()
            self.ent_text.setMinimumHeight(80)
            self.ent_text.setPlaceholderText("Journal entry text (shown in-game)")
            self.ent_text.textChanged.connect(self._on_ent_text_changed)

            self.ent_end = QCheckBox("End (quest complete)")
            self.ent_end.toggled.connect(self._on_ent_end_changed)

            self.ent_quest = QCheckBox("Quest Entry (show in journal)")
            self.ent_quest.toggled.connect(self._on_ent_quest_changed)

            self.ent_comment = QLineEdit()
            self.ent_comment.setPlaceholderText("(optional comment)")
            self.ent_comment.textChanged.connect(self._on_ent_comment_changed)

            eg_form.addRow("ID:",      self.ent_id)
            eg_form.addRow("Text:",    self.ent_text)
            eg_form.addRow("",         self.ent_end)
            eg_form.addRow("",         self.ent_quest)
            eg_form.addRow("Comment:", self.ent_comment)

            right_v_splitter.addWidget(ent_group)

            # Give top pane (table) ~65% of vertical space, edit form ~35%
            right_v_splitter.setSizes([520, 260])
            right_v_splitter.setStretchFactor(0, 1)
            right_v_splitter.setStretchFactor(1, 0)

            h_splitter.addWidget(right_v_splitter)
            h_splitter.setStretchFactor(1, 1)
            h_splitter.setSizes([220, 800])

            self._clear_category_form()
            self._clear_entry_form()

        # ── Category list population ──────────────────────────────────────────

        def _populate_category_list(self) -> None:
            self.cat_list.blockSignals(True)
            self.cat_list.clear()
            for cat in self.journal.categories:
                display = cat.tag or cat.name or "(unnamed)"
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, cat)
                self.cat_list.addItem(item)
            self.cat_list.blockSignals(False)
            if self.cat_list.count() > 0:
                self.cat_list.setCurrentRow(0)
            else:
                self._clear_category_form()
                self._clear_entry_form()

        def _current_category(self) -> JournalCategory | None:
            item = self.cat_list.currentItem()
            if item:
                return item.data(Qt.UserRole)
            return None

        # ── Category form ─────────────────────────────────────────────────────

        def _clear_category_form(self) -> None:
            self._updating = True
            self.cat_tag.clear()
            self.cat_name.clear()
            self.cat_priority.setValue(0)
            self.cat_comment.clear()
            self._updating = False

        def _load_category_form(self, cat: JournalCategory) -> None:
            self._updating = True
            self.cat_tag.setText(cat.tag)
            self.cat_name.setText(cat.name)
            self.cat_priority.setValue(cat.priority)
            self.cat_comment.setText(cat.comment)
            self._updating = False

        def _on_category_selected(self, row: int) -> None:
            if row < 0:
                self._clear_category_form()
                self._populate_entry_table(None)
                return
            item = self.cat_list.item(row)
            if item is None:
                return
            cat = item.data(Qt.UserRole)
            self._load_category_form(cat)
            self._populate_entry_table(cat)

        def _on_cat_tag_changed(self, text: str) -> None:
            if self._updating:
                return
            cat = self._current_category()
            if cat:
                cat.tag = text
                row = self.cat_list.currentRow()
                item = self.cat_list.item(row)
                if item:
                    item.setText(text or "(unnamed)")
            self._mark_dirty()

        def _on_cat_name_changed(self, text: str) -> None:
            if self._updating:
                return
            cat = self._current_category()
            if cat:
                cat.name = text
            self._mark_dirty()

        def _on_cat_priority_changed(self, val: int) -> None:
            if self._updating:
                return
            cat = self._current_category()
            if cat:
                cat.priority = val
            self._mark_dirty()

        def _on_cat_comment_changed(self, text: str) -> None:
            if self._updating:
                return
            cat = self._current_category()
            if cat:
                cat.comment = text
            self._mark_dirty()

        # ── Category add/remove ───────────────────────────────────────────────

        def _add_category(self) -> None:
            n = len(self.journal.categories) + 1
            cat = JournalCategory(
                tag=f"K_NEW_QUEST_{n}",
                name=f"New Quest {n}",
            )
            self.journal.categories.append(cat)
            item = QListWidgetItem(cat.tag)
            item.setData(Qt.UserRole, cat)
            self.cat_list.addItem(item)
            self.cat_list.setCurrentRow(self.cat_list.count() - 1)
            self._mark_dirty()

        def _remove_category(self) -> None:
            row = self.cat_list.currentRow()
            if row < 0:
                return
            item = self.cat_list.item(row)
            if item is None:
                return
            cat = item.data(Qt.UserRole)
            reply = QMessageBox.question(
                self, "Remove Category",
                f"Remove category '{cat.tag}'?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self.journal.categories.remove(cat)
            self.cat_list.takeItem(row)
            self._mark_dirty()

        # ── Entry table ────────────────────────────────────────────────────────

        def _populate_entry_table(self, cat: JournalCategory | None) -> None:
            self.entry_table.setUpdatesEnabled(False)
            self.entry_table.setRowCount(0)
            if cat is None:
                self.entry_table.setUpdatesEnabled(True)
                self._clear_entry_form()
                return

            self.entry_table.setRowCount(len(cat.entries))
            for row_idx, entry in enumerate(cat.entries):
                def _item(text, align=Qt.AlignCenter):
                    it = QTableWidgetItem(str(text))
                    it.setTextAlignment(align)
                    it.setData(Qt.UserRole, entry)
                    return it

                self.entry_table.setItem(row_idx, 0, _item(entry.state_id))
                self.entry_table.setItem(
                    row_idx, 1,
                    _item(entry.text[:60] + ("…" if len(entry.text) > 60 else ""),
                          Qt.AlignLeft | Qt.AlignVCenter)
                )
                end_item = _item("✓" if entry.is_end else "")
                if entry.is_end:
                    end_item.setForeground(QColor("#4ec9b0"))
                self.entry_table.setItem(row_idx, 2, end_item)
                quest_item = _item("✓" if entry.is_quest_entry else "")
                if entry.is_quest_entry:
                    quest_item.setForeground(QColor("#dcdcaa"))
                self.entry_table.setItem(row_idx, 3, quest_item)
                self.entry_table.setItem(
                    row_idx, 4,
                    _item(entry.comment[:30], Qt.AlignLeft | Qt.AlignVCenter)
                )

            self.entry_table.setUpdatesEnabled(True)
            if self.entry_table.rowCount() > 0:
                self.entry_table.selectRow(0)
            else:
                self._clear_entry_form()

        def _current_entry(self) -> JournalEntry | None:
            row = self.entry_table.currentRow()
            if row < 0:
                return None
            item = self.entry_table.item(row, 0)
            if item is None:
                return None
            return item.data(Qt.UserRole)

        # ── Entry form ────────────────────────────────────────────────────────

        def _clear_entry_form(self) -> None:
            self._updating = True
            self.ent_id.setValue(0)
            self.ent_text.setPlainText("")
            self.ent_end.setChecked(False)
            self.ent_quest.setChecked(False)
            self.ent_comment.clear()
            self._updating = False

        def _load_entry_form(self, entry: JournalEntry) -> None:
            self._updating = True
            self.ent_id.setValue(entry.state_id)
            self.ent_text.setPlainText(entry.text)
            self.ent_end.setChecked(entry.is_end)
            self.ent_quest.setChecked(entry.is_quest_entry)
            self.ent_comment.setText(entry.comment)
            self._updating = False

        def _on_entry_selected(self, row: int) -> None:
            if row < 0:
                self._clear_entry_form()
                return
            item = self.entry_table.item(row, 0)
            if item is None:
                return
            entry = item.data(Qt.UserRole)
            if entry:
                self._load_entry_form(entry)

        def _on_entry_selection_changed(self) -> None:
            row = self.entry_table.currentRow()
            self._on_entry_selected(row)

        def _on_ent_id_changed(self, val: int) -> None:
            if self._updating:
                return
            entry = self._current_entry()
            if entry:
                entry.state_id = val
                row = self.entry_table.currentRow()
                it = self.entry_table.item(row, 0)
                if it:
                    it.setText(str(val))
            self._mark_dirty()

        def _on_ent_text_changed(self) -> None:
            if self._updating:
                return
            entry = self._current_entry()
            if entry:
                entry.text = self.ent_text.toPlainText()
                row = self.entry_table.currentRow()
                it = self.entry_table.item(row, 1)
                if it:
                    t = entry.text
                    it.setText(t[:60] + ("…" if len(t) > 60 else ""))
            self._mark_dirty()

        def _on_ent_end_changed(self, checked: bool) -> None:
            if self._updating:
                return
            entry = self._current_entry()
            if entry:
                entry.is_end = checked
                row = self.entry_table.currentRow()
                it = self.entry_table.item(row, 2)
                if it:
                    it.setText("✓" if checked else "")
                    it.setForeground(
                        QColor("#4ec9b0") if checked else QColor("#d4d4d4")
                    )
            self._mark_dirty()

        def _on_ent_quest_changed(self, checked: bool) -> None:
            if self._updating:
                return
            entry = self._current_entry()
            if entry:
                entry.is_quest_entry = checked
                row = self.entry_table.currentRow()
                it = self.entry_table.item(row, 3)
                if it:
                    it.setText("✓" if checked else "")
                    it.setForeground(
                        QColor("#dcdcaa") if checked else QColor("#d4d4d4")
                    )
            self._mark_dirty()

        def _on_ent_comment_changed(self, text: str) -> None:
            if self._updating:
                return
            entry = self._current_entry()
            if entry:
                entry.comment = text
                row = self.entry_table.currentRow()
                it = self.entry_table.item(row, 4)
                if it:
                    it.setText(text[:30])
            self._mark_dirty()

        # ── Entry add / remove / reorder ──────────────────────────────────────

        def _add_entry(self) -> None:
            cat = self._current_category()
            if cat is None:
                QMessageBox.warning(self, "No Category",
                                    "Select a category first.")
                return
            next_id = max((e.state_id for e in cat.entries), default=-1) + 1
            entry = JournalEntry(state_id=next_id, text="", is_end=False, is_quest_entry=True)
            cat.entries.append(entry)
            self._populate_entry_table(cat)
            self.entry_table.selectRow(self.entry_table.rowCount() - 1)
            self._mark_dirty()

        def _remove_entry(self) -> None:
            cat = self._current_category()
            if cat is None:
                return
            entry = self._current_entry()
            if entry is None:
                return
            cat.entries.remove(entry)
            self._populate_entry_table(cat)
            self._mark_dirty()

        def _move_entry_up(self) -> None:
            cat = self._current_category()
            if cat is None:
                return
            row = self.entry_table.currentRow()
            if row <= 0:
                return
            cat.entries[row - 1], cat.entries[row] = (
                cat.entries[row], cat.entries[row - 1]
            )
            self._populate_entry_table(cat)
            self.entry_table.selectRow(row - 1)
            self._mark_dirty()

        def _move_entry_down(self) -> None:
            cat = self._current_category()
            if cat is None:
                return
            row = self.entry_table.currentRow()
            if row < 0 or row >= len(cat.entries) - 1:
                return
            cat.entries[row], cat.entries[row + 1] = (
                cat.entries[row + 1], cat.entries[row]
            )
            self._populate_entry_table(cat)
            self.entry_table.selectRow(row + 1)
            self._mark_dirty()

        # ── Import / Export ───────────────────────────────────────────────────

        def _import_jrl(self) -> None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Import .jrl File", "",
                "Journal Files (*.jrl);;All Files (*)"
            )
            if not path:
                return
            try:
                raw = Path(path).read_bytes()
                importer = JRLImporter()
                jrl = importer.import_from_bytes(raw)
                jrl.file_path = Path(path)
                self.set_journal(jrl)
                log.info(f"JRL imported: {path}")
            except Exception as exc:
                QMessageBox.critical(self, "Import Error",
                                     f"Failed to import .jrl:\n{exc}")

        def _export_jrl(self) -> None:
            default_name = getattr(self.journal, "name", "journal") or "journal"
            path, _ = QFileDialog.getSaveFileName(
                self, "Export .jrl File",
                f"{default_name}.jrl",
                "Journal Files (*.jrl);;All Files (*)"
            )
            if not path:
                return
            try:
                exporter = JRLExporter()
                data = exporter.export(self.journal)
                Path(path).write_bytes(data)
                self.journal.file_path = Path(path)
                self._dirty = False
                log.info(f"JRL exported: {path} ({len(data)} bytes)")
                QMessageBox.information(self, "Export Complete",
                                        f"Saved {len(data):,} bytes to:\n{path}")
            except Exception as exc:
                QMessageBox.critical(self, "Export Error",
                                     f"Failed to export .jrl:\n{exc}")

        # ── Dirty flag ────────────────────────────────────────────────────────

        def _mark_dirty(self) -> None:
            if not self._dirty:
                self._dirty = True
                self.journal_modified.emit()

else:
    # Headless stub — allows importing in test environments without PyQt5
    class JournalEditorWidget:  # type: ignore[no-redef]
        """Headless stub when PyQt5 is unavailable."""

        def __init__(self, journal=None, parent=None):
            from ghostscripter.core.models.journal import JournalFile
            self.journal = journal or JournalFile("stub")
            self._dirty = False

        @property
        def is_dirty(self) -> bool:
            return self._dirty

        def set_journal(self, journal) -> None:
            self.journal = journal
