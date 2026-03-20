"""
GhostScripter-K1-K2 — New Project Dialog

Loads from ui_files/new_project_dialog.ui when available (Qt Designer),
falls back to hand-built layout so the dialog always works without designer.
"""
from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QComboBox,
    QPushButton, QFrame,
)
from ghostscripter.core.constants import GAME_CHOICES

_UI_FILE = Path(__file__).parent.parent / "ui_files" / "new_project_dialog.ui"


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


class NewProjectDialog(QDialog):
    """Dialog for creating a new mod project.

    Tries to load from ``ui_files/new_project_dialog.ui``; if that fails
    (no Qt Designer file, or uic not available) it builds the layout in
    Python — identical widget names so callers can use the same attribute API.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Mod Project")
        self.setMinimumWidth(420)
        self.setModal(True)

        if _try_load_ui(self):
            # .ui loaded — wire the combo box items and connect buttons
            self._populate_from_ui()
        else:
            self._setup_ui()

    # ------------------------------------------------------------------
    # .ui population (widget names match Designer names)
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
            self.buttonBox.accepted.connect(self._on_create)  # type: ignore[attr-defined]
            self.buttonBox.rejected.connect(self.reject)       # type: ignore[attr-defined]
        except AttributeError:
            pass

    # ------------------------------------------------------------------
    # Hand-built fallback layout
    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel("Create New Mod Project")
        title.setStyleSheet(
            "color:#9cdcfe; font-size:13pt; font-weight:bold; padding-bottom:4px;"
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
        self.name_input.setPlaceholderText("My Awesome Mod")
        form.addRow(lbl("Project Name:*"), self.name_input)

        self.author_input = QLineEdit()
        self.author_input.setPlaceholderText("Your name")
        form.addRow(lbl("Author:"), self.author_input)

        self.game_combo = QComboBox()
        self.game_combo.addItems(GAME_CHOICES)
        form.addRow(lbl("Target Game:*"), self.game_combo)

        self.desc_input = QTextEdit()
        self.desc_input.setFixedHeight(70)
        self.desc_input.setPlaceholderText("Brief description of your mod…")
        form.addRow(lbl("Description:"), self.desc_input)

        layout.addLayout(form)

        note = QLabel(
            "* A project folder will be created in the directory you choose next."
        )
        note.setStyleSheet("color:#666666; font-size:8pt;")
        note.setWordWrap(True)
        layout.addWidget(note)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(
            "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            " border-radius:3px; padding:5px 14px; }"
            "QPushButton:hover { background:#4a4a4a; }"
        )
        btn_row.addWidget(cancel_btn)

        create_btn = QPushButton("Create Project →")
        create_btn.clicked.connect(self._on_create)
        create_btn.setDefault(True)
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
    def _on_create(self):
        name_widget = getattr(self, "name_input", None) or getattr(self, "nameEdit", None)
        if name_widget and not name_widget.text().strip():
            name_widget.setStyleSheet(
                "QLineEdit { border:1px solid #f48771; background:#3c3c3c;"
                " color:#cccccc; border-radius:3px; padding:4px 8px; }"
            )
            name_widget.setPlaceholderText("Name is required!")
            return
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_data(self) -> dict:
        """Return the dialog values as a plain dict."""
        def _text(attr: str, fallback: str = "") -> str:
            w = getattr(self, attr, None)
            if w is None:
                return fallback
            if hasattr(w, "toPlainText"):
                return w.toPlainText().strip()
            return w.text().strip()

        def _combo(attr: str) -> str:
            w = getattr(self, attr, None)
            return w.currentText() if w else ""

        return {
            "name":        _text("name_input") or _text("nameEdit"),
            "author":      _text("author_input") or _text("authorEdit"),
            "game":        _combo("game_combo") or _combo("gameCombo"),
            "description": _text("desc_input") or _text("descEdit"),
        }
