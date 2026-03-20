"""
GhostScripter-K1-K2 — TLK (Talk Table) Editor Widget

The TLK file format stores all in-game text strings, referenced by integer
StrRef values. This editor allows reading, editing, and saving TLK files.

TLK Binary Format (from TK102 DLGEditor + TSLPatcher TLK.pm):
  Header (20 bytes):
    FileType    4 chars  "TLK "
    Version     4 chars  "V3.0"
    LanguageID  DWORD
    StringCount DWORD
    StringEntriesOffset DWORD   ← absolute byte offset to string data block

  StringData entries (40 bytes each):
    Flags         DWORD   (bit 0 = has text, bit 1 = has sound, bit 2 = has sound length)
    SoundResRef   16 chars  (null-padded ASCII, ignore non-ASCII bytes)
    VolumeVariance DWORD
    PitchVariance  DWORD
    OffsetToString DWORD  ← relative offset INTO string data block
    StringSize     DWORD
    SoundLength    FLOAT

  String data: raw bytes, no null terminator.
  Encoding: cp1252 for Western languages (English/French/German/Italian/Spanish/Polish);
            cp949 for Korean; cp950 for Chinese (Trad.); cp936 for Chinese (Simp.);
            cp932 for Japanese.  NOT latin-1 — the 0x80-0x9F range maps to real
            characters in cp1252 (curly quotes, em-dashes, etc.) that latin-1 decodes
            as C1 control characters, producing phantom entries in other tools.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from qtpy.QtCore import Qt, QTimer, Signal
from qtpy.QtGui import QFont, QColor
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit, QMessageBox,
    QFileDialog, QFrame, QTextEdit, QFormLayout, QGroupBox, QCheckBox,
    QAbstractItemView, QShortcut,
)
from qtpy.QtGui import QKeySequence

# ── TLK Domain Model — imported from core (not redefined here) ────────────────
# Coupling fix (Khononov): TLKEntry / TLKFile are domain objects that belong
# in ghostscripter.core.models.tlk, not in the UI layer.  Re-export them here
# for backward-compatibility with any widget code that used the old location.
from ghostscripter.core.models.tlk import (
    TLKEntry,
    TLKFile,
    TLK_FLAG_HAS_TEXT,
    TLK_FLAG_HAS_SOUND,
    TLK_FLAG_HAS_LENGTH,
    LANGUAGE_IDS,
    _LANGUAGE_ENCODING,
    _DEFAULT_ENCODING,
)


# ── TLK Editor Widget ─────────────────────────────────────────

class TLKEditorWidget(QWidget):
    """
    TLK file editor.
    - Open dialog.tlk / dialogF.tlk
    - Load game dialog.tlk automatically from game directory
    - Browse and search strings by StrRef
    - Edit text and sound ResRef
    - Save modified TLK
    Based on TK102 DLGEditor v2.3.4 VO_ResRef / TLK handling
    """

    strref_selected = Signal(int, str)  # strref, text

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tlk: TLKFile | None = None
        self._game_dir: Path | None = None
        self._loaded_tlk_path: Path | None = None

        # Debounce search so we don't re-populate the table on every keystroke
        self._tlk_filter_timer = QTimer(self)
        self._tlk_filter_timer.setSingleShot(True)
        self._tlk_filter_timer.setInterval(200)  # ms
        self._tlk_filter_timer.timeout.connect(self._apply_filter_strings)
        self._pending_tlk_filter = ""

        self._setup_ui()
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save_tlk)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tb = self._build_toolbar()
        layout.addWidget(tb)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(2)

        split.addWidget(self._build_string_list())
        split.addWidget(self._build_editor_panel())
        split.setSizes([650, 400])
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
            style = (
                "QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;"
                "  border-radius:3px; padding:2px 10px; font-weight:bold; }"
                "QPushButton:hover { background:#1a8fe0; }"
            ) if primary else (
                "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
                "  border-radius:3px; padding:2px 8px; }"
                "QPushButton:hover { background:#4a4a4a; color:white; }"
            )
            b.setStyleSheet(style)
            return b

        lay.addWidget(btn("🎮 Game TLK", self._load_game_tlk,
                           "Auto-load dialog.tlk from game directory (or browse)", True))
        lay.addWidget(btn("🔄 Reload", self._reload_tlk, "Reload the same TLK file from disk"))
        lay.addWidget(btn("📂 Open TLK", self._open_tlk, "Open any .tlk file"))
        lay.addWidget(btn("💾 Save TLK", self._save_tlk, "Save (Ctrl+S)"))
        lay.addWidget(btn("💾 Save As…", self._save_as_tlk, "Save to new path"))
        lay.addWidget(btn("+ Add Entry", self._add_entry, "Append new TLK entry"))

        sep = QFrame(); sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#3c3c3c;"); lay.addWidget(sep)

        # Jump to StrRef
        lay.addWidget(QLabel("StrRef:"))
        self.strref_jump = QLineEdit()
        self.strref_jump.setPlaceholderText("Go to…")
        self.strref_jump.setFixedWidth(80)
        self.strref_jump.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            "  border-radius:3px; padding:2px 6px; }"
        )
        self.strref_jump.returnPressed.connect(self._jump_to_strref)
        lay.addWidget(self.strref_jump)

        sep2 = QFrame(); sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color:#3c3c3c;"); lay.addWidget(sep2)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search text…")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            "  border-radius:3px; padding:2px 8px; }"
        )
        self.search_input.textChanged.connect(self._schedule_filter_strings)
        lay.addWidget(self.search_input)
        lay.addStretch()

        self.info_label = QLabel("No TLK loaded")
        self.info_label.setStyleSheet("color:#569cd6; font-size:9pt;")
        lay.addWidget(self.info_label)
        return tb

    def _build_string_list(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#1e1e1e;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Table: StrRef | Sound | Text preview
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["StrRef", "Sound", "Text Preview"])
        self.table.setStyleSheet("""
            QTableWidget { background:#252526; border:none; gridline-color:#3c3c3c;
                            color:#cccccc; }
            QTableWidget::item { padding:3px 6px; }
            QTableWidget::item:selected { background:#094771; color:white; }
            QHeaderView::section { background:#2d2d30; color:#cccccc; border:none;
                                    border-right:1px solid #3c3c3c;
                                    border-bottom:1px solid #3c3c3c; padding:4px 8px; }
        """)
        self.table.setFont(QFont("Consolas", 9))
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        lay.addWidget(self.table)
        return panel

    def _build_editor_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#252526;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        hdr = QLabel("String Editor")
        hdr.setStyleSheet(
            "color:#cccccc; font-weight:bold; font-size:10pt;"
            " border-bottom:1px solid #3c3c3c; padding-bottom:4px;"
        )
        lay.addWidget(hdr)

        # StrRef info
        info_box = QGroupBox("Entry Info")
        info_box.setStyleSheet(
            "QGroupBox { color:#cccccc; border:1px solid #3c3c3c; margin-top:8px; padding:8px; }"
            "QGroupBox::title { subcontrol-position:top left; padding:0 4px; color:#569cd6; }"
        )
        form = QFormLayout(info_box)
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(6)

        self.strref_label = QLabel("—")
        self.strref_label.setStyleSheet("color:#9cdcfe; font-family:Consolas;")
        form.addRow("StrRef:", self.strref_label)

        self.flags_label = QLabel("—")
        self.flags_label.setStyleSheet("color:#858585;")
        form.addRow("Flags:", self.flags_label)

        self.sound_edit = QLineEdit()
        self.sound_edit.setPlaceholderText("Sound ResRef (16 chars max)")
        self.sound_edit.setMaxLength(16)
        self.sound_edit.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555; padding:4px; }"
        )
        form.addRow("Sound ResRef:", self.sound_edit)
        lay.addWidget(info_box)

        # Text editor
        text_lbl = QLabel("Text:")
        text_lbl.setStyleSheet("color:#cccccc; font-weight:bold;")
        lay.addWidget(text_lbl)

        self.text_edit = QTextEdit()
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.setStyleSheet(
            "QTextEdit { background:#1e1e1e; color:#cccccc; border:1px solid #3c3c3c; padding:4px; }"
        )
        lay.addWidget(self.text_edit)

        # Apply button
        apply_btn = QPushButton("✓ Apply Changes")
        apply_btn.setStyleSheet(
            "QPushButton { background:#0078d4; color:white; border:none;"
            "  border-radius:3px; padding:6px 16px; font-weight:bold; }"
            "QPushButton:hover { background:#1a8fe0; }"
        )
        apply_btn.clicked.connect(self._apply_edit)
        lay.addWidget(apply_btn)
        lay.addStretch()
        return panel

    # ── File I/O ──────────────────────────────────────────────

    def load_tlk_from_path(self, tlk_path: Path):
        """Programmatically load a TLK file (called from MainWindow or game loader)."""
        try:
            self.tlk = TLKFile.from_file(tlk_path)
            lang = LANGUAGE_IDS.get(self.tlk.language_id, str(self.tlk.language_id))
            enc  = _LANGUAGE_ENCODING.get(self.tlk.language_id, _DEFAULT_ENCODING)
            self.info_label.setText(
                f"\U0001f3ae {tlk_path}  [{lang} / {enc}]  {len(self.tlk):,} entries"
            )
            # Show full path as tooltip so users can verify the correct file was loaded
            self.info_label.setToolTip(f"Loaded from: {tlk_path}")
            self._game_dir = tlk_path.parent
            self._loaded_tlk_path = tlk_path  # remember the exact path
            self._populate_table()
        except Exception as e:
            self.info_label.setText(f"\u26a0 Failed: {e}")
            self.info_label.setToolTip("")

    def set_game_dir(self, game_dir: Path):
        """Set game directory so auto-load can find dialog.tlk."""
        self._game_dir = game_dir
        # Auto-load dialog.tlk immediately if it hasn't been loaded yet,
        # OR if a different game directory is being set (re-load from new dir).
        prev_parent = self._loaded_tlk_path.parent if self._loaded_tlk_path else None
        needs_load = (not self.tlk) or (prev_parent and prev_parent != game_dir)
        if needs_load and game_dir and game_dir.exists():
            self._try_auto_load_game_tlk(game_dir)

    def _try_auto_load_game_tlk(self, game_dir: Path) -> bool:
        """Search standard KotOR locations for dialog.tlk and auto-load."""
        # KotOR stores dialog.tlk at the game root — try both spellings / cases
        candidates = [
            game_dir / "dialog.tlk",
            game_dir / "Dialog.tlk",
            game_dir / "DIALOG.TLK",
            game_dir / "dialogF.tlk",  # female voiceover variant (K2 / TSL)
        ]
        for candidate in candidates:
            if candidate.exists():
                try:
                    self.load_tlk_from_path(candidate)
                    return True
                except Exception:
                    continue
        return False

    def _load_game_tlk(self):
        """Load dialog.tlk — try auto-detect first, browse if game dir not set."""
        # If we have a game dir, try auto-detecting first before asking user to browse
        if self._game_dir and self._game_dir.exists():
            if self._try_auto_load_game_tlk(self._game_dir):
                # Show the path that was loaded so user can verify it's correct
                loaded_path = getattr(self, "_loaded_tlk_path", None)
                if loaded_path:
                    from qtpy.QtWidgets import QToolTip
                    self.info_label.setToolTip(f"Loaded from: {loaded_path}")
                return

        # Fallback: let user browse — start in game dir if known
        start = str(self._game_dir) if self._game_dir else str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Game dialog.tlk", start,
            "Talk Table Files (*.tlk);;All Files (*)"
        )
        if path:
            self.load_tlk_from_path(Path(path))

    def _open_tlk(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open TLK File", "",
            "Talk Table (*.tlk);;All Files (*)"
        )
        if path:
            self.load_tlk_from_path(Path(path))

    def _reload_tlk(self):
        """Reload the TLK from the same path it was loaded from (picks up external changes)."""
        reload_path = getattr(self, "_loaded_tlk_path", None) or (
            self.tlk.file_path if self.tlk else None
        )
        if not reload_path or not Path(reload_path).exists():
            self.info_label.setText("⚠ No file path to reload from — use 🎮 Game TLK or 📂 Open TLK first.")
            return
        self.load_tlk_from_path(Path(reload_path))

    def _save_tlk(self):
        if not self.tlk:
            return
        self._apply_edit()
        if self.tlk.file_path:
            try:
                self.tlk.save()
                self.info_label.setText(f"\u2713 Saved: {self.tlk.filename}")
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))
        else:
            self._save_as_tlk()

    def _save_as_tlk(self):
        if not self.tlk:
            return
        self._apply_edit()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save TLK As", self.tlk.filename or "dialog.tlk",
            "Talk Table (*.tlk)"
        )
        if path:
            try:
                self.tlk.save(Path(path))
                self.tlk.file_path = Path(path)
                self.tlk.filename = Path(path).name
                self.info_label.setText(f"\u2713 Saved: {Path(path).name}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", str(e))

    
    def _add_entry(self):
        if not self.tlk:
            QMessageBox.warning(self, "No TLK", "Open a TLK file first.")
            return
        new_strref = len(self.tlk.entries)
        e = TLKEntry(new_strref)
        e.text = ""
        self.tlk.entries.append(e)
        self._populate_table()
        # Select new row
        self.table.selectRow(self.table.rowCount() - 1)

    # ── Table ─────────────────────────────────────────────────

    def _populate_table(self, filter_text: str = ""):
        if not self.tlk:
            return
        ft = filter_text.lower()

        entries = self.tlk.entries
        if ft:
            entries = [e for e in entries if ft in e.text.lower()
                       or ft in str(e.strref)]

        # Freeze repaints for the entire population pass
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(entries))

        grey  = QColor("#858585")
        teal  = QColor("#4ec9b0")
        dim   = QColor("#444444")

        for row_idx, e in enumerate(entries):
            strref_item = QTableWidgetItem(str(e.strref))
            strref_item.setForeground(grey)
            strref_item.setData(Qt.UserRole, e.strref)
            self.table.setItem(row_idx, 0, strref_item)

            sound_item = QTableWidgetItem(e.sound_resref or "")
            sound_item.setForeground(teal if e.sound_resref else dim)
            self.table.setItem(row_idx, 1, sound_item)

            text_item = QTableWidgetItem(e.short_text())
            self.table.setItem(row_idx, 2, text_item)

        self.table.setUpdatesEnabled(True)

    def _schedule_filter_strings(self, text: str):
        """Debounce filter so the table is not rebuilt on every keystroke."""
        self._pending_tlk_filter = text
        self._tlk_filter_timer.start()

    def _apply_filter_strings(self):
        self._populate_table(self._pending_tlk_filter)

    def _filter_strings(self, text: str):
        """Direct filter — delegates to debounced version."""
        self._schedule_filter_strings(text)

    def _on_selection_changed(self):
        rows = self.table.selectedItems()
        if not rows or not self.tlk:
            return
        row = self.table.currentRow()
        strref_item = self.table.item(row, 0)
        if not strref_item:
            return
        strref = strref_item.data(Qt.UserRole)
        if strref is None:
            return
        strref = int(strref)
        if 0 <= strref < len(self.tlk.entries):
            e = self.tlk.entries[strref]
            self.strref_label.setText(str(e.strref))
            flags_desc = []
            if e.has_text:   flags_desc.append("TEXT")
            if e.has_sound:  flags_desc.append("SOUND")
            if e.flags & TLK_FLAG_HAS_LENGTH: flags_desc.append("SND_LEN")
            # Show any unknown/reserved bits so they're not silently lost
            unknown = e.flags & ~(TLK_FLAG_HAS_TEXT | TLK_FLAG_HAS_SOUND | TLK_FLAG_HAS_LENGTH)
            if unknown:
                flags_desc.append(f"0x{unknown:02X}")
            self.flags_label.setText(f"0x{e.flags:02X}  ({', '.join(flags_desc) or 'none'})")
            self.sound_edit.setText(e.sound_resref or "")
            self.text_edit.setPlainText(e.text or "")
            self.strref_selected.emit(strref, e.text)

    def _apply_edit(self):
        if not self.tlk:
            return
        strref_text = self.strref_label.text().strip()
        if not strref_text or strref_text == "—":
            return
        try:
            strref = int(strref_text)
        except ValueError:
            return
        if not (0 <= strref < len(self.tlk.entries)):
            return
        e = self.tlk.entries[strref]
        e.text = self.text_edit.toPlainText()
        e.sound_resref = self.sound_edit.text().strip()[:16]
        # Preserve every flag bit that isn't TEXT or SOUND — in particular
        # TLK_FLAG_HAS_LENGTH (0x04) must survive the edit or GRigger will
        # consider the entry malformed and may skip it on re-open.
        preserved = e.flags & ~(TLK_FLAG_HAS_TEXT | TLK_FLAG_HAS_SOUND)
        e.flags = preserved | TLK_FLAG_HAS_TEXT
        if e.sound_resref:
            e.flags |= TLK_FLAG_HAS_SOUND
        # Refresh table row
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == strref:
                self.table.item(row, 1).setText(e.sound_resref)
                self.table.item(row, 2).setText(e.short_text())
                break

    def _jump_to_strref(self):
        text = self.strref_jump.text().strip()
        if not text:
            return
        try:
            strref = int(text)
        except ValueError:
            return
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == strref:
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                return
        QMessageBox.information(self, "Not Found",
                                f"StrRef {strref} not found in current view.")

    # ── External access ───────────────────────────────────────

    def jump_to_strref(self, strref: int) -> bool:
        """
        Scroll to and select the row matching strref.
        Called by MainWindow.ipc_open_tlk().
        Returns True if found.
        """
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.UserRole) == strref:
                self.table.selectRow(row)
                self.table.scrollToItem(item)
                return True
        return False

    def get_string(self, strref: int) -> str:
        if self.tlk:
            return self.tlk.get_string(strref, "")
        return ""
