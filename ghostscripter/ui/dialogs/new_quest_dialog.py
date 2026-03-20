"""
GhostScripter-K1-K2 — New Quest Dialog

Loads from ui_files/new_quest_dialog.ui when available (Qt Designer),
falls back to hand-built layout so the dialog always works without designer.
"""
from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QFrame,
    QListWidget, QListWidgetItem,
)
from ghostscripter.core.models.quest import QUEST_TEMPLATES
from ghostscripter.core.constants import GAME_CHOICES

_UI_FILE = Path(__file__).parent.parent / "ui_files" / "new_quest_dialog.ui"


def _try_load_ui(dialog: QDialog) -> bool:
    """Attempt to load the .ui file; return True on success."""
    if not _UI_FILE.exists():
        return False
    try:
        from qtpy import uic  # type: ignore[attr-defined]
        uic.loadUi(str(_UI_FILE), dialog)
        return True
    except Exception:
        return False


class NewQuestDialog(QDialog):
    """Dialog for creating a new quest.

    Tries to load from ``ui_files/new_quest_dialog.ui``; if that fails
    it builds the layout in Python — identical widget names so callers
    can use the same attribute API.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Quest")
        self.setMinimumWidth(380)
        self.setModal(True)

        if _try_load_ui(self):
            self._populate_from_ui()
        else:
            self._setup_ui()

    # ------------------------------------------------------------------
    # .ui population
    # ------------------------------------------------------------------
    def _populate_from_ui(self):
        """Wire .ui widgets that need runtime population."""
        try:
            combo: QComboBox = self.game_combo  # type: ignore[attr-defined]
            combo.clear()
            combo.addItems(GAME_CHOICES)
        except AttributeError:
            pass
        try:
            lst: QListWidget = self.template_list  # type: ignore[attr-defined]
            lst.clear()
            for key, info in QUEST_TEMPLATES.items():
                item = QListWidgetItem(info["display"])
                item.setData(Qt.UserRole, key)
                lst.addItem(item)
            lst.setCurrentRow(0)
            lst.currentItemChanged.connect(self._update_preview)
            self._update_preview()
        except AttributeError:
            pass
        try:
            self.buttonBox.accepted.connect(self._on_create)  # type: ignore[attr-defined]
            self.buttonBox.rejected.connect(self.reject)       # type: ignore[attr-defined]
        except AttributeError:
            pass

    # ------------------------------------------------------------------
    # Hand-built fallback layout
    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Create New Quest")
        title.setStyleSheet(
            "color:#9cdcfe; font-size:12pt; font-weight:bold;"
        )
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#3c3c3c;")
        layout.addWidget(sep)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        def lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color:#969696;")
            return l

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("MyQuest")
        form.addRow(lbl("Quest Name:*"), self.name_input)

        self.game_combo = QComboBox()
        self.game_combo.addItems(GAME_CHOICES)
        form.addRow(lbl("Target Game:"), self.game_combo)

        layout.addLayout(form)

        layout.addWidget(lbl("Select Template:"))
        self.template_list = QListWidget()
        self.template_list.setFixedHeight(100)
        self.template_list.setStyleSheet(
            "QListWidget { background:#1e1e1e; border:1px solid #3c3c3c; }"
            "QListWidget::item { color:#cccccc; padding:5px 8px; }"
            "QListWidget::item:hover { background:#2a2d2e; }"
            "QListWidget::item:selected { background:#094771; }"
        )
        for key, info in QUEST_TEMPLATES.items():
            item = QListWidgetItem(info["display"])
            item.setData(Qt.UserRole, key)
            self.template_list.addItem(item)
        self.template_list.setCurrentRow(0)
        layout.addWidget(self.template_list)

        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet(
            "color:#666666; font-size:8pt; padding:4px;"
        )
        layout.addWidget(self.preview_label)
        self.template_list.currentItemChanged.connect(self._update_preview)
        self._update_preview()

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(
            "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            " border-radius:3px; padding:5px 14px; }"
        )
        btn_row.addWidget(cancel_btn)

        create_btn = QPushButton("Create Quest →")
        create_btn.setDefault(True)
        create_btn.clicked.connect(self._on_create)
        create_btn.setStyleSheet(
            "QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;"
            " border-radius:3px; padding:5px 16px; font-weight:bold; }"
            "QPushButton:hover { background:#1a8fe0; }"
        )
        btn_row.addWidget(create_btn)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _update_preview(self, *args):
        lst = getattr(self, "template_list", None)
        lbl = getattr(self, "preview_label", None)
        if not lst or not lbl:
            return
        item = lst.currentItem()
        if not item:
            return
        key = item.data(Qt.UserRole)
        info = QUEST_TEMPLATES.get(key, {})
        states = info.get("states", [])
        vars_ = info.get("variables", [])
        lbl.setText(f"{len(states)} states • {len(vars_)} variables")

    def _on_create(self):
        name_w = getattr(self, "name_input", None) or getattr(self, "nameEdit", None)
        if name_w and not name_w.text().strip():
            name_w.setPlaceholderText("Name required!")
            return
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_data(self) -> dict:
        """Return the dialog values as a plain dict."""
        def _text(attr: str) -> str:
            w = getattr(self, attr, None)
            return w.text().strip() if w else ""

        def _combo(attr: str) -> str:
            w = getattr(self, attr, None)
            return w.currentText() if w else ""

        lst = getattr(self, "template_list", None)
        item = lst.currentItem() if lst else None
        return {
            "name":     _text("name_input") or _text("nameEdit"),
            "game":     _combo("game_combo") or _combo("gameCombo"),
            "template": item.data(Qt.UserRole) if item else "SIMPLE_QUEST",
        }
