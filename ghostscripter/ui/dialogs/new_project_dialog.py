"""
GhostScripter-K1-K2 — New Project Dialog
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QComboBox,
    QPushButton, QDialogButtonBox, QFrame,
)
from ghostscripter.core.constants import GAME_CHOICES


class NewProjectDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Mod Project")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel("Create New Mod Project")
        title.setStyleSheet("color:#9cdcfe; font-size:13pt; font-weight:bold; "
                             "padding-bottom:4px;")
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

        # Help note
        note = QLabel("* A project folder will be created in the directory you choose next.")
        note.setStyleSheet("color:#666666; font-size:8pt;")
        note.setWordWrap(True)
        layout.addWidget(note)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                          border-radius:3px; padding:5px 14px; }
            QPushButton:hover { background:#4a4a4a; }
        """)
        btn_row.addWidget(cancel_btn)

        create_btn = QPushButton("Create Project →")
        create_btn.clicked.connect(self._on_create)
        create_btn.setDefault(True)
        create_btn.setStyleSheet("""
            QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;
                          border-radius:3px; padding:5px 16px; font-weight:bold; }
            QPushButton:hover { background:#1a8fe0; }
        """)
        btn_row.addWidget(create_btn)
        layout.addLayout(btn_row)

    def _on_create(self):
        if not self.name_input.text().strip():
            self.name_input.setStyleSheet("""
                QLineEdit { border:1px solid #f48771; background:#3c3c3c; color:#cccccc;
                            border-radius:3px; padding:4px 8px; }
            """)
            self.name_input.setPlaceholderText("Name is required!")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "author": self.author_input.text().strip(),
            "game": self.game_combo.currentText(),
            "description": self.desc_input.toPlainText().strip(),
        }
