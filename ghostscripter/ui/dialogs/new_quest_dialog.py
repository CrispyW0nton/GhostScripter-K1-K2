"""
GhostScripter-K1-K2 — New Quest Dialog
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QFrame,
    QListWidget, QListWidgetItem,
)
from ghostscripter.core.models.quest import QUEST_TEMPLATES
from ghostscripter.core.constants import GAME_CHOICES


class NewQuestDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Quest")
        self.setMinimumWidth(380)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Create New Quest")
        title.setStyleSheet("color:#9cdcfe; font-size:12pt; font-weight:bold;")
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

        # Template picker
        layout.addWidget(lbl("Select Template:"))
        self.template_list = QListWidget()
        self.template_list.setFixedHeight(100)
        self.template_list.setStyleSheet("""
            QListWidget { background:#1e1e1e; border:1px solid #3c3c3c; }
            QListWidget::item { color:#cccccc; padding:5px 8px; }
            QListWidget::item:hover { background:#2a2d2e; }
            QListWidget::item:selected { background:#094771; }
        """)
        for key, info in QUEST_TEMPLATES.items():
            item = QListWidgetItem(info["display"])
            item.setData(Qt.UserRole, key)
            self.template_list.addItem(item)
        self.template_list.setCurrentRow(0)
        layout.addWidget(self.template_list)

        # Preview label
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("color:#666666; font-size:8pt; padding:4px;")
        layout.addWidget(self.preview_label)
        self.template_list.currentItemChanged.connect(self._update_preview)
        self._update_preview()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet("""
            QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                          border-radius:3px; padding:5px 14px; }
        """)
        btn_row.addWidget(cancel_btn)

        create_btn = QPushButton("Create Quest →")
        create_btn.setDefault(True)
        create_btn.clicked.connect(self._on_create)
        create_btn.setStyleSheet("""
            QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;
                          border-radius:3px; padding:5px 16px; font-weight:bold; }
            QPushButton:hover { background:#1a8fe0; }
        """)
        btn_row.addWidget(create_btn)
        layout.addLayout(btn_row)

    def _update_preview(self, *args):
        item = self.template_list.currentItem()
        if not item:
            return
        key = item.data(Qt.UserRole)
        info = QUEST_TEMPLATES.get(key, {})
        states = info.get("states", [])
        vars_ = info.get("variables", [])
        self.preview_label.setText(
            f"{len(states)} states • {len(vars_)} variables"
        )

    def _on_create(self):
        if not self.name_input.text().strip():
            self.name_input.setPlaceholderText("Name required!")
            return
        self.accept()

    def get_data(self) -> dict:
        item = self.template_list.currentItem()
        return {
            "name": self.name_input.text().strip(),
            "game": self.game_combo.currentText(),
            "template": item.data(Qt.UserRole) if item else "SIMPLE_QUEST",
        }
