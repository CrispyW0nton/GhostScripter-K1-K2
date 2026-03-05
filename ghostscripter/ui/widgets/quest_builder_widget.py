"""
GhostScripter-K1-K2 — Quest Builder Widget
"""
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QTreeWidget, QTreeWidgetItem, QTextEdit,
    QListWidget, QListWidgetItem, QGroupBox, QFormLayout,
    QLineEdit, QComboBox, QFrame, QMessageBox, QInputDialog,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QScrollArea, QPlainTextEdit,
)

from ghostscripter.core.models.quest import (
    QuestDefinition, GlobalVariable, QuestState, QuestTrigger,
    QUEST_TEMPLATES, create_quest_from_template,
)
from ghostscripter.core.models.script import (
    ScriptFile, make_quest_start_template, make_quest_complete_template,
    make_quest_check_template,
)
from ghostscripter.core.constants import VAR_TYPES, QUEST_TYPES


class QuestBuilderWidget(QWidget):

    def __init__(self, quest: Optional[QuestDefinition] = None,
                 project=None, parent=None):
        super().__init__(parent)
        self.quest = quest
        self.project = project
        self._setup_ui()
        if self.quest:
            self._load_quest(self.quest)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        tb = self._build_toolbar()
        layout.addWidget(tb)

        # Main content: left panel + right tabs
        h_split = QSplitter(Qt.Horizontal)
        h_split.setHandleWidth(2)

        # Left: quest list / template picker
        left = self._build_quest_list_panel()
        h_split.addWidget(left)

        # Right: quest details tabs
        self.detail_tabs = QTabWidget()
        self.detail_tabs.setStyleSheet("""
            QTabWidget::pane { background:#1e1e1e; border:1px solid #3c3c3c; }
            QTabBar::tab { background:#2d2d30; color:#969696; padding:5px 14px;
                            border:1px solid #3c3c3c; border-bottom:none; }
            QTabBar::tab:selected { background:#1e1e1e; color:#ffffff;
                                     border-top:2px solid #0078d4; }
        """)
        self.detail_tabs.addTab(self._build_overview_tab(), "Overview")
        self.detail_tabs.addTab(self._build_variables_tab(), "Variables")
        self.detail_tabs.addTab(self._build_states_tab(), "States")
        self.detail_tabs.addTab(self._build_scripts_tab(), "Scripts")
        self.detail_tabs.addTab(self._build_globalcat_tab(), "globalcat.2da")

        h_split.addWidget(self.detail_tabs)
        h_split.setSizes([220, 800])
        layout.addWidget(h_split)

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
            style = ("background:#0078d4; color:white; border:1px solid #1a8fe0; "
                     "border-radius:3px; padding:2px 10px; font-weight:bold; "
                     if primary else
                     "background:#3c3c3c; color:#cccccc; border:1px solid #555; "
                     "border-radius:3px; padding:2px 8px; ")
            hover = "background:#1a8fe0;" if primary else "background:#4a4a4a; color:white;"
            b.setStyleSheet(f"QPushButton {{ {style} }} QPushButton:hover {{ {hover} }}")
            return b

        lay.addWidget(btn("+ New Quest", self._new_quest, True))
        lay.addWidget(btn("+ Add Variable", self._add_variable))
        lay.addWidget(btn("+ Add State", self._add_state))
        lay.addWidget(btn("Generate Scripts", self._generate_scripts))
        lay.addWidget(btn("Validate", self._validate))
        lay.addStretch()

        if self.quest:
            lbl = QLabel(self.quest.quest_id or "no quest")
            lbl.setStyleSheet("color:#569cd6; font-family:Consolas;")
            lay.addWidget(lbl)

        return tb

    def _build_quest_list_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#252526;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QLabel("Templates")
        header.setStyleSheet("background:#2d2d30; color:#cccccc; font-weight:bold; "
                              "padding:5px 8px; border-bottom:1px solid #3c3c3c;")
        lay.addWidget(header)

        self.template_list = QListWidget()
        self.template_list.setStyleSheet("""
            QListWidget { background:#252526; border:none; }
            QListWidget::item { color:#cccccc; padding:5px 8px; }
            QListWidget::item:hover { background:#2a2d2e; }
            QListWidget::item:selected { background:#094771; }
        """)
        for key, info in QUEST_TEMPLATES.items():
            item = QListWidgetItem(info["display"])
            item.setData(Qt.UserRole, key)
            self.template_list.addItem(item)
        self.template_list.itemDoubleClicked.connect(self._load_template)
        lay.addWidget(self.template_list)

        sep = QLabel("Current Quest")
        sep.setStyleSheet("background:#2d2d30; color:#4ec9b0; font-weight:bold; "
                          "padding:5px 8px; border-bottom:1px solid #3c3c3c; "
                          "border-top:1px solid #3c3c3c;")
        lay.addWidget(sep)

        self.quest_info_label = QLabel("No quest loaded")
        self.quest_info_label.setWordWrap(True)
        self.quest_info_label.setStyleSheet("color:#969696; font-size:8pt; padding:8px;")
        lay.addWidget(self.quest_info_label)
        lay.addStretch()
        return panel

    def _build_overview_tab(self) -> QWidget:
        widget = QWidget()
        lay = QFormLayout(widget)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        lay.setLabelAlignment(Qt.AlignRight)

        self.ov_name = QLineEdit()
        self.ov_name.setPlaceholderText("Quest display name")
        self.ov_id = QLineEdit()
        self.ov_id.setPlaceholderText("e.g. k_swg_myquest")
        self.ov_id.setStyleSheet("font-family:Consolas;")
        self.ov_game = QComboBox()
        self.ov_game.addItems(["K1", "K2"])
        self.ov_type = QComboBox()
        self.ov_type.addItems(QUEST_TYPES)
        self.ov_desc = QTextEdit()
        self.ov_desc.setFixedHeight(80)
        self.ov_desc.setPlaceholderText("Quest description…")

        def lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color:#969696;")
            return l

        lay.addRow(lbl("Name:"), self.ov_name)
        lay.addRow(lbl("Quest ID:"), self.ov_id)
        lay.addRow(lbl("Target Game:"), self.ov_game)
        lay.addRow(lbl("Quest Type:"), self.ov_type)
        lay.addRow(lbl("Description:"), self.ov_desc)

        save_btn = QPushButton("Apply Changes")
        save_btn.clicked.connect(self._apply_overview)
        save_btn.setStyleSheet("""
            QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;
                          border-radius:3px; padding:5px 14px; font-weight:bold; }
            QPushButton:hover { background:#1a8fe0; }
        """)
        lay.addRow("", save_btn)
        return widget

    def _build_variables_tab(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        lay.addWidget(QLabel("Global Variables (globalcat.2da entries)"))

        self.vars_table = QTableWidget(0, 4)
        self.vars_table.setHorizontalHeaderLabels(["Variable Name", "Type", "Default", "Description"])
        self.vars_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.vars_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.vars_table.setStyleSheet("""
            QTableWidget { background:#252526; border:1px solid #3c3c3c; gridline-color:#3c3c3c; }
            QTableWidget::item { color:#cccccc; padding:4px; }
            QTableWidget::item:selected { background:#094771; }
            QHeaderView::section { background:#2d2d30; color:#cccccc; border:none;
                                    border-right:1px solid #3c3c3c; padding:4px 8px; }
        """)
        lay.addWidget(self.vars_table)

        btn_row = QHBoxLayout()
        add_var_btn = QPushButton("+ Add Variable")
        add_var_btn.clicked.connect(self._add_variable)
        add_var_btn.setStyleSheet("QPushButton { background:#3c3c3c; color:#cccccc; "
                                   "border:1px solid #555; border-radius:3px; padding:4px 8px; }")
        del_var_btn = QPushButton("Delete Selected")
        del_var_btn.clicked.connect(self._delete_selected_variable)
        del_var_btn.setStyleSheet("QPushButton { background:#5a1a1a; color:#f48771; "
                                   "border:1px solid #7a2a2a; border-radius:3px; padding:4px 8px; }")
        btn_row.addWidget(add_var_btn)
        btn_row.addWidget(del_var_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        return widget

    def _build_states_tab(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(8, 8, 8, 8)

        self.states_table = QTableWidget(0, 3)
        self.states_table.setHorizontalHeaderLabels(["State ID", "Name", "Description"])
        self.states_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.states_table.setStyleSheet("""
            QTableWidget { background:#252526; border:1px solid #3c3c3c; gridline-color:#3c3c3c; }
            QTableWidget::item { color:#cccccc; padding:4px; }
            QTableWidget::item:selected { background:#094771; }
            QHeaderView::section { background:#2d2d30; color:#cccccc; border:none;
                                    border-right:1px solid #3c3c3c; padding:4px 8px; }
        """)
        lay.addWidget(self.states_table)

        add_state_btn = QPushButton("+ Add State")
        add_state_btn.clicked.connect(self._add_state)
        add_state_btn.setStyleSheet("QPushButton { background:#3c3c3c; color:#cccccc; "
                                     "border:1px solid #555; border-radius:3px; padding:4px 8px; }")
        lay.addWidget(add_state_btn)
        return widget

    def _build_scripts_tab(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        lay.addWidget(QLabel("Generated Script Stubs"))

        self.scripts_list = QListWidget()
        self.scripts_list.setStyleSheet("""
            QListWidget { background:#252526; border:1px solid #3c3c3c; }
            QListWidget::item { color:#dcdcaa; font-family:Consolas; padding:4px 8px; }
            QListWidget::item:selected { background:#094771; }
        """)
        lay.addWidget(self.scripts_list)

        gen_btn = QPushButton("Generate Script Stubs")
        gen_btn.setStyleSheet("""
            QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;
                          border-radius:3px; padding:5px 14px; font-weight:bold; }
            QPushButton:hover { background:#1a8fe0; }
        """)
        gen_btn.clicked.connect(self._generate_scripts)
        lay.addWidget(gen_btn)

        return widget

    def _build_globalcat_tab(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        lay.addWidget(QLabel("globalcat.2da Entries Preview"))
        self.globalcat_preview = QPlainTextEdit()
        self.globalcat_preview.setReadOnly(True)
        self.globalcat_preview.setObjectName("outputConsole")
        self.globalcat_preview.setFont(QFont("Consolas", 10))
        lay.addWidget(self.globalcat_preview)

        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy_globalcat)
        lay.addWidget(copy_btn)
        return widget

    # ── Data Loading ──────────────────────────────────────────

    def _load_quest(self, quest: QuestDefinition):
        self.quest = quest
        self.quest_info_label.setText(
            f"<b style='color:#9cdcfe'>{quest.quest_name}</b><br>"
            f"<span style='color:#569cd6; font-family:Consolas'>{quest.quest_id}</span><br>"
            f"<span style='color:#4ec9b0'>{quest.target_game}</span><br>"
            f"<span style='color:#666'>{len(quest.states)} states • "
            f"{len(quest.variables)} vars</span>"
        )

        # Overview
        self.ov_name.setText(quest.quest_name)
        self.ov_id.setText(quest.quest_id)
        self.ov_game.setCurrentText(quest.target_game)
        self.ov_type.setCurrentText(quest.quest_type)
        self.ov_desc.setPlainText(quest.description)

        # Variables
        self.vars_table.setRowCount(0)
        for var in quest.variables:
            row = self.vars_table.rowCount()
            self.vars_table.insertRow(row)
            self.vars_table.setItem(row, 0, QTableWidgetItem(var.variable_name))
            self.vars_table.setItem(row, 1, QTableWidgetItem(var.variable_type))
            self.vars_table.setItem(row, 2, QTableWidgetItem(str(var.default_value)))
            self.vars_table.setItem(row, 3, QTableWidgetItem(var.description))

        # States
        self.states_table.setRowCount(0)
        for state in quest.states:
            row = self.states_table.rowCount()
            self.states_table.insertRow(row)
            self.states_table.setItem(row, 0, QTableWidgetItem(str(state.state_id)))
            self.states_table.setItem(row, 1, QTableWidgetItem(state.state_name))
            self.states_table.setItem(row, 2, QTableWidgetItem(state.description))

        # Scripts
        self.scripts_list.clear()
        for s in quest.scripts:
            self.scripts_list.addItem(s + ".nss")

        # globalcat preview
        self._update_globalcat_preview()

    def _update_globalcat_preview(self):
        if not self.quest:
            return
        lines = ["# globalcat.2da entries for: " + (self.quest.quest_name or "quest"), ""]
        for var in self.quest.variables:
            lines.append(var.globalcat_entry)
        self.globalcat_preview.setPlainText("\n".join(lines))

    # ── Actions ───────────────────────────────────────────────

    def _new_quest(self):
        from ghostscripter.ui.dialogs.new_quest_dialog import NewQuestDialog
        dlg = NewQuestDialog(self)
        if dlg.exec_():
            data = dlg.get_data()
            quest = create_quest_from_template(
                data["template"], data["name"], data.get("game", "K1")
            )
            if self.project:
                self.project.quests.append(quest)
            self._load_quest(quest)

    def _load_template(self, item: QListWidgetItem):
        key = item.data(Qt.UserRole)
        name, ok = QInputDialog.getText(self, "Quest Name", "Enter quest name:")
        if ok and name:
            game = self.ov_game.currentText() if self.quest else "K1"
            quest = create_quest_from_template(key, name, game)
            self._load_quest(quest)

    def _apply_overview(self):
        if not self.quest:
            self.quest = QuestDefinition()
        self.quest.quest_name = self.ov_name.text()
        self.quest.quest_id = self.ov_id.text()
        self.quest.target_game = self.ov_game.currentText()
        self.quest.quest_type = self.ov_type.currentText()
        self.quest.description = self.ov_desc.toPlainText()
        self._load_quest(self.quest)
        QMessageBox.information(self, "Saved", "Quest overview updated.")

    def _add_variable(self):
        if not self.quest:
            self.quest = QuestDefinition(quest_name="New Quest")
        name, ok = QInputDialog.getText(self, "Add Variable", "Variable name (e.g. K_SWG_MYQUEST):")
        if not ok or not name:
            return
        var_type, ok2 = QInputDialog.getItem(self, "Variable Type", "Select type:", VAR_TYPES, 0)
        if not ok2:
            return
        var = GlobalVariable(variable_name=name, variable_type=var_type)
        self.quest.variables.append(var)
        self._load_quest(self.quest)

    def _delete_selected_variable(self):
        row = self.vars_table.currentRow()
        if row >= 0 and self.quest and row < len(self.quest.variables):
            del self.quest.variables[row]
            self.vars_table.removeRow(row)
            self._update_globalcat_preview()

    def _add_state(self):
        if not self.quest:
            return
        state_id = len(self.quest.states)
        name, ok = QInputDialog.getText(self, "Add State", f"State {state_id} name:")
        if ok and name:
            state = QuestState(state_id=state_id, state_name=name)
            self.quest.states.append(state)
            self._load_quest(self.quest)

    def _generate_scripts(self):
        if not self.quest:
            QMessageBox.warning(self, "No Quest", "No quest loaded.")
            return
        self.quest.scripts.clear()
        for state in self.quest.states:
            script_name = f"{self.quest.quest_id}_{state.state_id:02d}"
            self.quest.scripts.append(script_name)
        self._load_quest(self.quest)
        QMessageBox.information(self, "Scripts Generated",
            f"Generated {len(self.quest.scripts)} script stubs.\n"
            f"Open each in the Script Editor to add logic.")

    def _validate(self):
        if not self.quest:
            return
        issues = []
        if not self.quest.quest_id:
            issues.append("Quest ID is empty")
        if not self.quest.quest_name:
            issues.append("Quest name is empty")
        if not self.quest.variables:
            issues.append("No global variables defined")
        if not self.quest.states:
            issues.append("No quest states defined")
        for v in self.quest.variables:
            if not v.variable_name.startswith("K_SWG_"):
                issues.append(f"Variable '{v.variable_name}' does not follow K_SWG_ convention")
        if issues:
            QMessageBox.warning(self, "Validation Issues",
                                 "\n".join(f"• {i}" for i in issues))
        else:
            QMessageBox.information(self, "✓ Valid", "Quest structure is valid!")

    def _copy_globalcat(self):
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(self.globalcat_preview.toPlainText())
        QMessageBox.information(self, "Copied", "globalcat.2da entries copied to clipboard.")
