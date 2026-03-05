"""
GhostScripter-K1-K2 — Asset Library Widget
"""
from pathlib import Path
from typing import Optional, List

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QLineEdit, QTabWidget, QComboBox, QGroupBox, QFormLayout,
    QTextEdit, QFrame, QMessageBox, QFileDialog, QInputDialog,
    QPlainTextEdit,
)

from ghostscripter.core.models.script import ScriptFile
from ghostscripter.core.models.quest import QuestDefinition
from ghostscripter.core.models.dialogue import DialogueFile


class AssetLibraryWidget(QWidget):

    def __init__(self, project=None, parent=None):
        super().__init__(parent)
        self.project = project
        self._setup_ui()
        if project:
            self._populate(project)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar / search bar
        tb = self._build_toolbar()
        layout.addWidget(tb)

        # Splitter: tabs | detail panel
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(2)

        # Left: tabbed asset categories
        self.asset_tabs = QTabWidget()
        self.asset_tabs.setStyleSheet("""
            QTabWidget::pane { background:#1e1e1e; border:1px solid #3c3c3c; }
            QTabBar::tab { background:#2d2d30; color:#969696; padding:5px 14px;
                            border:1px solid #3c3c3c; border-bottom:none; }
            QTabBar::tab:selected { background:#1e1e1e; color:#ffffff;
                                     border-top:2px solid #0078d4; }
            QTabBar::tab:hover:!selected { background:#3c3c3c; }
        """)
        self.asset_tabs.addTab(self._build_scripts_tab(), "Scripts")
        self.asset_tabs.addTab(self._build_quests_tab(), "Quests")
        self.asset_tabs.addTab(self._build_dialogues_tab(), "Dialogues")
        self.asset_tabs.addTab(self._build_models_tab(), "Models")
        self.asset_tabs.addTab(self._build_templates_tab(), "Templates")
        split.addWidget(self.asset_tabs)

        # Right: detail / preview panel
        detail = self._build_detail_panel()
        split.addWidget(detail)

        split.setSizes([700, 300])
        layout.addWidget(split)

    def _build_toolbar(self) -> QWidget:
        tb = QWidget()
        tb.setStyleSheet("background:#2d2d30; border-bottom:1px solid #3c3c3c;")
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)

        lay.addWidget(QLabel("Asset Library"))

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#3c3c3c;")
        lay.addWidget(sep)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search all assets…")
        self.search.setFixedWidth(240)
        self.search.setStyleSheet("""
            QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                        border-radius:3px; padding:3px 8px; }
        """)
        self.search.textChanged.connect(self._filter_all)
        lay.addWidget(self.search)

        self.type_filter = QComboBox()
        self.type_filter.addItems(["All Types", "Scripts", "Quests", "Dialogues", "Models"])
        self.type_filter.setFixedWidth(120)
        self.type_filter.setStyleSheet("""
            QComboBox { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                        border-radius:3px; padding:3px 8px; }
        """)
        self.type_filter.currentTextChanged.connect(self._on_type_filter)
        lay.addWidget(self.type_filter)

        lay.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(24)
        refresh_btn.setStyleSheet("""
            QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                          border-radius:3px; padding:2px 8px; }
            QPushButton:hover { background:#4a4a4a; }
        """)
        refresh_btn.clicked.connect(self._refresh)
        lay.addWidget(refresh_btn)

        return tb

    def _list_style(self) -> str:
        return """
            QListWidget { background:#252526; border:none; }
            QListWidget::item { color:#cccccc; padding:4px 8px; }
            QListWidget::item:hover { background:#2a2d2e; }
            QListWidget::item:selected { background:#094771; color:white; }
        """

    def _tree_style(self) -> str:
        return """
            QTreeWidget { background:#252526; border:none; }
            QTreeWidget::item { color:#cccccc; padding:3px 4px; }
            QTreeWidget::item:hover { background:#2a2d2e; }
            QTreeWidget::item:selected { background:#094771; color:white; }
        """

    def _build_scripts_tab(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Action bar
        action = self._mini_action_bar([
            ("+ New Script", self._new_script),
            ("Open File", self._open_script_file),
            ("Delete", self._delete_selected),
        ])
        lay.addWidget(action)

        self.scripts_tree = QTreeWidget()
        self.scripts_tree.setHeaderHidden(True)
        self.scripts_tree.setStyleSheet(self._tree_style())
        self.scripts_tree.itemDoubleClicked.connect(self._on_script_double_click)
        lay.addWidget(self.scripts_tree)
        return widget

    def _build_quests_tab(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)

        action = self._mini_action_bar([
            ("+ New Quest", self._new_quest),
            ("Delete", self._delete_selected),
        ])
        lay.addWidget(action)

        self.quests_list = QListWidget()
        self.quests_list.setStyleSheet(self._list_style())
        self.quests_list.itemClicked.connect(self._on_quest_clicked)
        lay.addWidget(self.quests_list)
        return widget

    def _build_dialogues_tab(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)

        action = self._mini_action_bar([
            ("+ New Dialogue", self._new_dialogue),
            ("Open .dlg", self._open_dlg_file),
        ])
        lay.addWidget(action)

        self.dialogues_list = QListWidget()
        self.dialogues_list.setStyleSheet(self._list_style())
        lay.addWidget(self.dialogues_list)
        return widget

    def _build_models_tab(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)

        action = self._mini_action_bar([
            ("Import Model", self._import_model),
            ("Edit in GhostRigger", self._launch_ghostrigger),
            ("Browse Game Models", self._browse_game_models),
        ])
        lay.addWidget(action)

        self.models_list = QListWidget()
        self.models_list.setStyleSheet(self._list_style())
        lay.addWidget(self.models_list)

        # Info banner
        info = QLabel("MDL/MDX/TPC files — Import from GhostRigger or file system.")
        info.setStyleSheet("color:#666666; font-size:8pt; padding:6px 8px; "
                           "background:#1e1e1e; border-top:1px solid #3c3c3c;")
        info.setWordWrap(True)
        lay.addWidget(info)
        return widget

    def _build_templates_tab(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        templates = [
            ("Companion Recruitment Quest", "NPC_COMPANION_QUEST"),
            ("Simple Side Quest", "SIMPLE_QUEST"),
            ("Branching Light/Dark Quest", "BRANCHING_QUEST"),
            ("Greeting Dialogue (3 nodes)", "dialogue_greeting"),
            ("void main() Script", "script_void_main"),
            ("StartingConditional() Script", "script_conditional"),
        ]
        self.template_list = QListWidget()
        self.template_list.setStyleSheet(self._list_style())
        for name, key in templates:
            item = QListWidgetItem(f"▶  {name}")
            item.setData(Qt.UserRole, key)
            self.template_list.addItem(item)
        self.template_list.itemDoubleClicked.connect(self._use_template)
        lay.addWidget(self.template_list)

        use_btn = QPushButton("Use Template")
        use_btn.setStyleSheet("""
            QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;
                          border-radius:3px; padding:5px 14px; font-weight:bold; }
            QPushButton:hover { background:#1a8fe0; }
        """)
        use_btn.clicked.connect(lambda: self._use_template(self.template_list.currentItem()))
        lay.addWidget(use_btn)
        return widget

    def _build_detail_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#252526;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QLabel("Details")
        header.setStyleSheet("background:#2d2d30; color:#cccccc; font-weight:bold; "
                              "padding:5px 8px; border-bottom:1px solid #3c3c3c;")
        lay.addWidget(header)

        self.detail_text = QPlainTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setObjectName("outputConsole")
        self.detail_text.setPlaceholderText("Select an asset to view details…")
        lay.addWidget(self.detail_text)
        return panel

    def _mini_action_bar(self, buttons: list) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background:#2d2d30; border-bottom:1px solid #3c3c3c;")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(4)
        for label, slot in buttons:
            b = QPushButton(label)
            b.clicked.connect(slot)
            b.setFixedHeight(22)
            b.setStyleSheet("""
                QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                              border-radius:3px; padding:2px 6px; font-size:8pt; }
                QPushButton:hover { background:#4a4a4a; color:white; }
            """)
            lay.addWidget(b)
        lay.addStretch()
        return bar

    # ── Population ────────────────────────────────────────────

    def _populate(self, project):
        # Scripts tree
        self.scripts_tree.clear()
        for stype in ["quest", "dialogue", "event", "npc"]:
            scripts = [s for s in project.scripts if s.script_type == stype]
            if not scripts:
                continue
            cat = QTreeWidgetItem([f"{stype.capitalize()} Scripts ({len(scripts)})"])
            cat.setForeground(0, QColor("#dcdcaa"))
            cat.setExpanded(True)
            for s in scripts:
                item = QTreeWidgetItem([s.name + ".nss"])
                item.setForeground(0, QColor("#cccccc"))
                item.setData(0, Qt.UserRole, s)
                cat.addChild(item)
            self.scripts_tree.addTopLevelItem(cat)

        # Quests
        self.quests_list.clear()
        for q in project.quests:
            item = QListWidgetItem(f"⚔  {q.quest_name}  [{q.target_game}]")
            item.setData(Qt.UserRole, q)
            item.setForeground(QColor("#569cd6"))
            self.quests_list.addItem(item)

        # Dialogues
        self.dialogues_list.clear()
        for d in project.dialogues:
            item = QListWidgetItem(f"🗨  {d.name}.dlg")
            item.setData(Qt.UserRole, d)
            item.setForeground(QColor("#4ec9b0"))
            self.dialogues_list.addItem(item)

        # Models
        self.models_list.clear()
        for m in project.models:
            item = QListWidgetItem(f"◉  {m.name}.mdl")
            item.setData(Qt.UserRole, m)
            item.setForeground(QColor("#ce9178"))
            self.models_list.addItem(item)

    # ── Actions ───────────────────────────────────────────────

    def _new_script(self):
        name, ok = QInputDialog.getText(self, "New Script", "Script name (without .nss):")
        if ok and name:
            script = ScriptFile(name=name, script_type="quest")
            if self.project:
                self.project.scripts.append(script)
                self._populate(self.project)
            self.detail_text.setPlainText(f"Created script: {name}.nss")

    def _open_script_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Script", "", "NWScript (*.nss)"
        )
        if path:
            self.detail_text.setPlainText(f"Opened: {path}")

    def _new_quest(self):
        name, ok = QInputDialog.getText(self, "New Quest", "Quest name:")
        if ok and name:
            from ghostscripter.core.models.quest import create_quest_from_template
            quest = create_quest_from_template("SIMPLE_QUEST", name, "K1")
            if self.project:
                self.project.quests.append(quest)
                self._populate(self.project)

    def _new_dialogue(self):
        name, ok = QInputDialog.getText(self, "New Dialogue", "Dialogue name:")
        if ok and name:
            from ghostscripter.core.models.dialogue import create_simple_dialogue
            dlg = create_simple_dialogue(name, "npc_001")
            if self.project:
                self.project.dialogues.append(dlg)
                self._populate(self.project)

    def _open_dlg_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Dialogue", "", "Dialogue Files (*.dlg)"
        )
        if path:
            self.detail_text.setPlainText(f"Opened: {path}\n(DLG parser not yet connected)")

    def _import_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Model", "", "MDL Files (*.mdl)"
        )
        if path:
            from ghostscripter.core.models.project import ModelReference
            model = ModelReference(name=Path(path).stem, file_path=Path(path))
            if self.project:
                self.project.models.append(model)
                self._populate(self.project)
            self.detail_text.setPlainText(f"Imported model: {Path(path).name}")

    def _launch_ghostrigger(self):
        QMessageBox.information(self, "GhostRigger",
            "Launch GhostRigger-K1-K2 to edit the selected model.\n\n"
            "IPC bridge will connect when GhostRigger is installed.\n"
            "See ghostscripter/ipc/ghostrigger_bridge.py for config.")

    def _browse_game_models(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select KotOR Game Folder"
        )
        if folder:
            self.detail_text.setPlainText(
                f"Game folder: {folder}\n\n"
                "BIF extraction requires xoreos-tools.\n"
                "See ghostscripter/core/resource_manager/bif_extractor.py"
            )

    def _delete_selected(self):
        tab = self.asset_tabs.currentIndex()
        lists = [self.scripts_tree, self.quests_list,
                 self.dialogues_list, self.models_list, self.template_list]
        # Simple deletion - just confirm
        QMessageBox.information(self, "Delete", "Select item and confirm deletion.")

    def _on_script_double_click(self, item, col):
        data = item.data(0, Qt.UserRole)
        if data and hasattr(data, "to_dict"):
            import json
            self.detail_text.setPlainText(json.dumps(data.to_dict(), indent=2, default=str))

    def _on_quest_clicked(self, item):
        q = item.data(Qt.UserRole)
        if q and hasattr(q, "to_dict"):
            import json
            self.detail_text.setPlainText(json.dumps(q.to_dict(), indent=2, default=str))

    def _use_template(self, item):
        if not item:
            return
        key = item.data(Qt.UserRole)
        QMessageBox.information(self, "Template",
            f"Template '{key}' selected.\n"
            "Open the appropriate editor to use it.")

    def _filter_all(self, text: str):
        t = text.lower()
        for i in range(self.quests_list.count()):
            item = self.quests_list.item(i)
            item.setHidden(bool(t and t not in item.text().lower()))
        for i in range(self.dialogues_list.count()):
            item = self.dialogues_list.item(i)
            item.setHidden(bool(t and t not in item.text().lower()))

    def _on_type_filter(self, text: str):
        tab_map = {
            "Scripts": 0, "Quests": 1, "Dialogues": 2,
            "Models": 3,
        }
        if text in tab_map:
            self.asset_tabs.setCurrentIndex(tab_map[text])

    def _refresh(self):
        if self.project:
            self._populate(self.project)
