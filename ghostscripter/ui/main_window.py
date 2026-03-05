"""
GhostScripter-K1-K2 — Main Window
Dark IDE layout matching KotorModTools / GhostRigger aesthetic.
"""
import os
import sys
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QSize, QTimer
from PyQt5.QtGui import QIcon, QFont, QColor, QPalette, QKeySequence
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTabWidget, QLabel, QPushButton, QStatusBar, QMenuBar, QMenu,
    QAction, QFileDialog, QMessageBox, QToolBar, QDockWidget,
    QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QPlainTextEdit, QFrame, QSizePolicy, QApplication, QInputDialog,
    QComboBox, QLineEdit, QGroupBox, QFormLayout, QTextEdit, QProgressBar,
)

from ghostscripter.core.models.project import ModProject
from ghostscripter.core.models.script import (
    ScriptFile, make_void_main_template, make_quest_start_template
)
from ghostscripter.core.models.quest import QuestDefinition, create_quest_from_template, QUEST_TEMPLATES
from ghostscripter.core.models.dialogue import DialogueFile, create_simple_dialogue
from ghostscripter.core.constants import APP_NAME, APP_VERSION, GAME_CHOICES

from ghostscripter.ui.widgets.script_editor_widget import ScriptEditorWidget
from ghostscripter.ui.widgets.dialogue_editor_widget import DialogueEditorWidget
from ghostscripter.ui.widgets.quest_builder_widget import QuestBuilderWidget
from ghostscripter.ui.widgets.twoda_manager_widget import TwoDAManagerWidget
from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
from ghostscripter.ui.dialogs.new_project_dialog import NewProjectDialog
from ghostscripter.ui.dialogs.new_quest_dialog import NewQuestDialog


class MainWindow(QMainWindow):
    """
    Primary application window for GhostScripter-K1-K2.
    Layout: Project Tree (left) | Tabbed Editor (center) | Properties (right)
    Output console docked at bottom.
    """

    def __init__(self):
        super().__init__()
        self.current_project: Optional[ModProject] = None
        self.setWindowTitle(f"{APP_NAME}  ·  v{APP_VERSION}")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._setup_statusbar()
        self._apply_theme()

        self.log("GhostScripter-K1-K2 initialized. Ready.")
        self.log(f"Version {APP_VERSION}")

    # ── Setup ─────────────────────────────────────────────────

    def _setup_ui(self):
        """Build the three-column IDE layout."""
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Main horizontal splitter ──────────────────────────
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setHandleWidth(2)

        # ── LEFT: Project Panel ───────────────────────────────
        self.project_panel = self._build_project_panel()
        self.main_splitter.addWidget(self.project_panel)

        # ── CENTER: Tab editor ────────────────────────────────
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.editor_tabs = QTabWidget()
        self.editor_tabs.setTabsClosable(True)
        self.editor_tabs.tabCloseRequested.connect(self._close_tab)
        self.editor_tabs.setObjectName("editorTabs")
        center_layout.addWidget(self.editor_tabs)

        # Add default tabs
        self._add_welcome_tab()

        # ── Output console ────────────────────────────────────
        self.output_panel = self._build_output_panel()
        center_layout.addWidget(self.output_panel)

        self.main_splitter.addWidget(center_widget)

        # ── RIGHT: Properties panel ───────────────────────────
        self.props_panel = self._build_properties_panel()
        self.main_splitter.addWidget(self.props_panel)

        # Sizes: 220 | flex | 260
        self.main_splitter.setSizes([220, 800, 260])
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)

        root_layout.addWidget(self.main_splitter)

    def _build_project_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("projectPanel")
        panel.setMinimumWidth(180)
        panel.setMaximumWidth(320)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QLabel("Project")
        header.setObjectName("projectPanelHeader")
        header.setFixedHeight(28)
        layout.addWidget(header)

        # Game selector row
        sel_row = QWidget()
        sel_row.setStyleSheet("background:#2d2d30; padding: 4px 6px;")
        sel_layout = QHBoxLayout(sel_row)
        sel_layout.setContentsMargins(6, 2, 6, 2)
        sel_layout.setSpacing(6)
        self.game_label = QLabel("Game:")
        self.game_label.setStyleSheet("color:#969696; font-size:8pt;")
        self.game_selector = QComboBox()
        self.game_selector.addItems(["K1", "K2"])
        self.game_selector.setFixedWidth(55)
        self.game_selector.currentTextChanged.connect(self._on_game_changed)
        sel_layout.addWidget(self.game_label)
        sel_layout.addWidget(self.game_selector)
        sel_layout.addStretch()
        layout.addWidget(sel_row)

        # Project tree
        self.project_tree = QTreeWidget()
        self.project_tree.setHeaderHidden(True)
        self.project_tree.setIndentation(14)
        self.project_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self.project_tree.itemSelectionChanged.connect(self._on_tree_item_selected)
        layout.addWidget(self.project_tree)

        # Bottom buttons
        btn_row = QWidget()
        btn_row.setStyleSheet("background:#252526; border-top:1px solid #3c3c3c;")
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(6, 4, 6, 4)
        btn_layout.setSpacing(4)

        new_project_btn = QPushButton("+ Project")
        new_project_btn.clicked.connect(self.new_project)
        new_project_btn.setToolTip("Create new mod project")
        btn_layout.addWidget(new_project_btn)

        open_btn = QPushButton("Open")
        open_btn.clicked.connect(self.open_project)
        open_btn.setToolTip("Open existing project")
        btn_layout.addWidget(open_btn)

        layout.addWidget(btn_row)
        return panel

    def _build_output_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("outputPanel")
        panel.setFixedHeight(150)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header_row = QWidget()
        header_row.setObjectName("outputPanelHeader")
        header_row.setStyleSheet("background:#2d2d30; border-top:1px solid #3c3c3c;")
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(8, 3, 8, 3)
        header_layout.setSpacing(8)

        header_label = QLabel("Output Log")
        header_label.setStyleSheet("color:#cccccc; font-weight:bold; font-size:9pt;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedSize(48, 20)
        clear_btn.setStyleSheet("""
            QPushButton { background:#3c3c3c; color:#969696; border:1px solid #555;
                          border-radius:2px; font-size:8pt; padding:0; }
            QPushButton:hover { background:#4a4a4a; color:#cccccc; }
        """)
        clear_btn.clicked.connect(self._clear_output)
        header_layout.addWidget(clear_btn)
        layout.addWidget(header_row)

        self.output_console = QPlainTextEdit()
        self.output_console.setObjectName("outputConsole")
        self.output_console.setReadOnly(True)
        self.output_console.setMaximumBlockCount(500)
        layout.addWidget(self.output_console)

        return panel

    def _build_properties_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("propertiesPanel")
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tabs: Props / Info / About
        self.props_tabs = QTabWidget()
        self.props_tabs.setObjectName("propsTabs")

        # Properties tab
        self.props_content = QWidget()
        props_layout = QVBoxLayout(self.props_content)
        props_layout.setContentsMargins(8, 8, 8, 8)

        self.props_text = QPlainTextEdit()
        self.props_text.setReadOnly(True)
        self.props_text.setObjectName("outputConsole")
        self.props_text.setPlaceholderText("Select an item to view properties...")
        props_layout.addWidget(self.props_text)
        self.props_tabs.addTab(self.props_content, "Properties")

        # Quick actions tab
        self.quick_content = self._build_quick_actions()
        self.props_tabs.addTab(self.quick_content, "Quick")

        # About tab
        self.about_content = self._build_about_tab()
        self.props_tabs.addTab(self.about_content, "About")

        layout.addWidget(self.props_tabs)
        return panel

    def _build_quick_actions(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addWidget(self._section_label("New Assets"))

        def make_btn(label, slot, tooltip="", is_primary=False):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            btn.setToolTip(tooltip)
            if is_primary:
                btn.setProperty("class", "primary")
            return btn

        layout.addWidget(make_btn("+ New Script", self.new_script, "Create new NSS script"))
        layout.addWidget(make_btn("+ New Quest", self.new_quest, "Create new quest", True))
        layout.addWidget(make_btn("+ New Dialogue", self.new_dialogue, "Create new dialogue file"))
        layout.addWidget(make_btn("+ New 2DA Edit", self.open_2da_manager, "Open 2DA editor"))

        layout.addSpacing(10)
        layout.addWidget(self._section_label("Export"))
        layout.addWidget(make_btn("Export to Override", self.export_override))
        layout.addWidget(make_btn("Export to ERF", self.export_erf))

        layout.addSpacing(10)
        layout.addWidget(self._section_label("Tools"))
        layout.addWidget(make_btn("Script Editor", self.open_script_editor))
        layout.addWidget(make_btn("Dialogue Editor", self.open_dialogue_editor))
        layout.addWidget(make_btn("Asset Library", self.open_asset_library))

        layout.addStretch()
        return widget

    def _build_about_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        def lbl(text, style=""):
            l = QLabel(text)
            l.setWordWrap(True)
            if style:
                l.setStyleSheet(style)
            return l

        layout.addWidget(lbl(APP_NAME,
            "color:#9cdcfe; font-weight:bold; font-size:12pt;"))
        layout.addWidget(lbl(f"Version {APP_VERSION}",
            "color:#569cd6; font-size:10pt;"))
        layout.addWidget(lbl("All-in-one IDE for KotOR 1 & 2 TSL modding.",
            "color:#969696;"))

        layout.addSpacing(10)
        layout.addWidget(lbl("Features:", "color:#dcdcaa; font-weight:bold;"))
        features = [
            "• NSS Script Editor with syntax highlighting",
            "• Visual Dialogue Tree Editor",
            "• Quest Builder with templates",
            "• 2DA File Manager",
            "• Asset Library",
            "• Export to Override / ERF",
            "• GhostRigger IPC Bridge",
        ]
        for f in features:
            layout.addWidget(lbl(f, "color:#cccccc; font-size:8pt;"))

        layout.addSpacing(10)
        layout.addWidget(lbl("GPL-3.0 License", "color:#666666; font-size:8pt;"))
        layout.addWidget(lbl("Credits: KotOR community, xoreos-tools,\nFred Tetra, TK102, Cortisol",
            "color:#666666; font-size:8pt;"))

        layout.addStretch()
        return widget

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#4ec9b0; font-weight:bold; font-size:8pt; "
                          "padding-bottom:2px; border-bottom:1px solid #3c3c3c;")
        return lbl

    # ── Menus ─────────────────────────────────────────────────

    def _setup_menus(self):
        menubar = self.menuBar()

        # File
        file_menu = menubar.addMenu("File")
        file_menu.addAction(self._action("New Project", self.new_project, "Ctrl+Shift+N"))
        file_menu.addAction(self._action("Open Project…", self.open_project, "Ctrl+O"))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Save Project", self.save_project, "Ctrl+S"))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Exit", self.close, "Alt+F4"))

        # Edit
        edit_menu = menubar.addMenu("Edit")
        edit_menu.addAction(self._action("New Script", self.new_script, "Ctrl+N"))
        edit_menu.addAction(self._action("New Quest", self.new_quest))
        edit_menu.addAction(self._action("New Dialogue", self.new_dialogue))

        # View
        view_menu = menubar.addMenu("View")
        view_menu.addAction(self._action("Script Editor", self.open_script_editor))
        view_menu.addAction(self._action("Dialogue Editor", self.open_dialogue_editor))
        view_menu.addAction(self._action("Quest Builder", self.open_quest_builder))
        view_menu.addAction(self._action("2DA Manager", self.open_2da_manager))
        view_menu.addAction(self._action("Asset Library", self.open_asset_library))

        # Tools
        tools_menu = menubar.addMenu("Tools")
        tools_menu.addAction(self._action("Export to Override", self.export_override))
        tools_menu.addAction(self._action("Export to ERF", self.export_erf))

        # Help
        help_menu = menubar.addMenu("Help")
        help_menu.addAction(self._action("About GhostScripter", self._show_about))

    def _action(self, text: str, slot, shortcut: str = "") -> QAction:
        act = QAction(text, self)
        act.triggered.connect(slot)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        return act

    # ── Toolbar ───────────────────────────────────────────────

    def _setup_toolbar(self):
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setObjectName("mainToolbar")
        self.addToolBar(tb)

        def tb_btn(label, slot, tooltip="", primary=False):
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            btn.setToolTip(tooltip)
            btn.setFixedHeight(26)
            if primary:
                btn.setStyleSheet("""
                    QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;
                                  border-radius:3px; padding:2px 10px; font-weight:bold; }
                    QPushButton:hover { background:#1a8fe0; }
                    QPushButton:pressed { background:#005a9e; }
                """)
            return btn

        tb.addWidget(tb_btn("+ Project", self.new_project, "New mod project"))
        tb.addWidget(tb_btn("Open", self.open_project, "Open project"))
        tb.addWidget(tb_btn("Save", self.save_project, "Save project"))
        tb.addSeparator()
        tb.addWidget(tb_btn("Script Editor", self.open_script_editor, "Open script editor"))
        tb.addWidget(tb_btn("Dialogue Editor", self.open_dialogue_editor, "Open dialogue editor"))
        tb.addWidget(tb_btn("Quest Builder", self.open_quest_builder, "Open quest builder", True))
        tb.addWidget(tb_btn("2DA Manager", self.open_2da_manager, "Open 2DA manager"))
        tb.addWidget(tb_btn("Asset Library", self.open_asset_library, "Open asset library"))
        tb.addSeparator()
        tb.addWidget(tb_btn("Export Override", self.export_override))
        tb.addWidget(tb_btn("Export ERF", self.export_erf))

    # ── Status Bar ────────────────────────────────────────────

    def _setup_statusbar(self):
        sb = self.statusBar()
        sb.setObjectName("mainStatusBar")
        self.status_label = QLabel("No project loaded")
        self.status_label.setStyleSheet("color:#ffffff; padding: 0 6px;")
        sb.addWidget(self.status_label)

        # Right side info
        self.game_status = QLabel("K1")
        self.game_status.setStyleSheet("color:#ffffff; padding: 0 10px; "
                                        "border-left:1px solid rgba(255,255,255,0.3);")
        sb.addPermanentWidget(self.game_status)

        version_label = QLabel(f"GhostScripter {APP_VERSION}")
        version_label.setStyleSheet("color:#ffffff; padding: 0 10px; "
                                     "border-left:1px solid rgba(255,255,255,0.3);")
        sb.addPermanentWidget(version_label)

    # ── Theme ─────────────────────────────────────────────────

    def _apply_theme(self):
        """Load and apply the dark QSS theme."""
        qss_path = Path(__file__).parent / "styles" / "dark.qss"
        if qss_path.exists():
            with open(qss_path, encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        else:
            # Minimal fallback
            self.setStyleSheet("""
                QWidget { background:#1e1e1e; color:#d4d4d4; }
                QMenuBar { background:#252526; }
                QToolBar { background:#252526; }
            """)

    # ── Welcome Tab ───────────────────────────────────────────

    def _add_welcome_tab(self):
        welcome = QWidget()
        welcome.setStyleSheet("background:#1e1e1e;")
        lay = QVBoxLayout(welcome)
        lay.setAlignment(Qt.AlignCenter)

        title = QLabel("GhostScripter-K1-K2")
        title.setStyleSheet("color:#9cdcfe; font-size:24pt; font-weight:bold;")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        sub = QLabel("All-in-one IDE for KotOR 1 & 2 TSL Modding")
        sub.setStyleSheet("color:#569cd6; font-size:13pt;")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)

        lay.addSpacing(20)

        # Quick start buttons
        btn_row = QWidget()
        btn_row.setStyleSheet("background:transparent;")
        btn_lay = QHBoxLayout(btn_row)
        btn_lay.setSpacing(12)

        actions = [
            ("+ New Project", self.new_project, True),
            ("Open Project", self.open_project, False),
            ("Script Editor", self.open_script_editor, False),
            ("Dialogue Editor", self.open_dialogue_editor, False),
            ("Quest Builder", self.open_quest_builder, True),
        ]
        for label, slot, primary in actions:
            btn = QPushButton(label)
            btn.setFixedSize(140, 36)
            btn.clicked.connect(slot)
            if primary:
                btn.setStyleSheet("""
                    QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;
                                  border-radius:4px; font-weight:bold; font-size:10pt; }
                    QPushButton:hover { background:#1a8fe0; }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                                  border-radius:4px; font-size:10pt; }
                    QPushButton:hover { background:#4a4a4a; color:white; }
                """)
            btn_lay.addWidget(btn)
        lay.addWidget(btn_row)

        lay.addSpacing(30)
        hint = QLabel("KotOR 1 & 2 modding made simple  •  GPL-3.0")
        hint.setStyleSheet("color:#555555; font-size:9pt;")
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)

        idx = self.editor_tabs.addTab(welcome, "Welcome")
        self.editor_tabs.tabBar().setTabButton(idx, self.editor_tabs.tabBar().RightSide, None)

    # ── Project Operations ────────────────────────────────────

    def new_project(self):
        dlg = NewProjectDialog(self)
        if dlg.exec_():
            data = dlg.get_data()
            folder = QFileDialog.getExistingDirectory(
                self, "Choose Project Folder", str(Path.home())
            )
            if not folder:
                return
            project_dir = Path(folder) / data["name"].replace(" ", "_")
            try:
                self.current_project = ModProject.create_new(
                    name=data["name"],
                    author=data["author"],
                    target_game=data["game"],
                    root_directory=project_dir,
                    description=data["description"],
                )
                self._refresh_project_tree()
                self._update_status(f"Project '{data['name']}' created at {project_dir}")
                self.game_selector.setCurrentText(data["game"])
                self.log(f"✓ Created project: {data['name']} ({data['game']})")
                self.log(f"  Location: {project_dir}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create project:\n{e}")
                self.log(f"✗ Error creating project: {e}")

    def open_project(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Project Folder")
        if not folder:
            return
        try:
            self.current_project = ModProject.load(Path(folder))
            self._refresh_project_tree()
            self._update_status(f"Loaded: {self.current_project.name}")
            self.game_selector.setCurrentText(self.current_project.target_game)
            self.log(f"✓ Opened project: {self.current_project.name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")

    def save_project(self):
        if not self.current_project:
            self.log("⚠ No project to save.")
            return
        try:
            self.current_project.save()
            self._update_status(f"Saved: {self.current_project.name}")
            self.log(f"✓ Project saved: {self.current_project.name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save:\n{e}")

    # ── Tab Management ────────────────────────────────────────

    def _find_or_open_tab(self, title: str, widget_factory) -> int:
        """Find existing tab by title or create new one."""
        for i in range(self.editor_tabs.count()):
            if self.editor_tabs.tabText(i) == title:
                self.editor_tabs.setCurrentIndex(i)
                return i
        widget = widget_factory()
        idx = self.editor_tabs.addTab(widget, title)
        self.editor_tabs.setCurrentIndex(idx)
        return idx

    def _close_tab(self, index: int):
        if self.editor_tabs.tabText(index) != "Welcome":
            self.editor_tabs.removeTab(index)

    # ── Editor Opens ──────────────────────────────────────────

    def new_script(self):
        name, ok = QInputDialog.getText(self, "New Script", "Script name (without .nss):")
        if not ok or not name.strip():
            return
        script = ScriptFile(name=name.strip(), source_code=make_void_main_template())
        if self.current_project and self.current_project.script_dir:
            script.file_path = self.current_project.script_dir / f"{name}.nss"
            self.current_project.scripts.append(script)
            self._refresh_project_tree()
        editor = ScriptEditorWidget(script=script, project=self.current_project)
        idx = self.editor_tabs.addTab(editor, f"✎ {name}.nss")
        self.editor_tabs.setCurrentIndex(idx)
        self.log(f"✓ New script: {name}.nss")

    def open_script_editor(self):
        script = ScriptFile(name="untitled", source_code=make_void_main_template())
        editor = ScriptEditorWidget(script=script, project=self.current_project)
        title = "Script Editor"
        idx = self.editor_tabs.addTab(editor, title)
        self.editor_tabs.setCurrentIndex(idx)

    def new_dialogue(self):
        name, ok = QInputDialog.getText(self, "New Dialogue", "Dialogue name:")
        if not ok or not name.strip():
            return
        dlg_file = create_simple_dialogue(name.strip(), "npc_001")
        if self.current_project and self.current_project.dialogue_dir:
            dlg_file.file_path = self.current_project.dialogue_dir / f"{name}.dlg"
            self.current_project.dialogues.append(dlg_file)
            self._refresh_project_tree()
        editor = DialogueEditorWidget(dialogue=dlg_file)
        idx = self.editor_tabs.addTab(editor, f"🗨 {name}.dlg")
        self.editor_tabs.setCurrentIndex(idx)
        self.log(f"✓ New dialogue: {name}.dlg")

    def open_dialogue_editor(self):
        dlg_file = create_simple_dialogue("new_dialogue", "npc_001")
        editor = DialogueEditorWidget(dialogue=dlg_file)
        idx = self.editor_tabs.addTab(editor, "Dialogue Editor")
        self.editor_tabs.setCurrentIndex(idx)

    def new_quest(self):
        dlg = NewQuestDialog(self)
        if dlg.exec_():
            data = dlg.get_data()
            quest = create_quest_from_template(
                data["template"], data["name"], data.get("game", "K1")
            )
            if self.current_project:
                self.current_project.quests.append(quest)
                self._refresh_project_tree()
            editor = QuestBuilderWidget(quest=quest, project=self.current_project)
            idx = self.editor_tabs.addTab(editor, f"⚔ {data['name']}")
            self.editor_tabs.setCurrentIndex(idx)
            self.log(f"✓ New quest: {data['name']} ({data['template']})")

    def open_quest_builder(self):
        editor = QuestBuilderWidget(project=self.current_project)
        self._find_or_open_tab("Quest Builder", lambda: editor)

    def open_2da_manager(self):
        editor = TwoDAManagerWidget(project=self.current_project)
        self._find_or_open_tab("2DA Manager", lambda: editor)

    def open_asset_library(self):
        editor = AssetLibraryWidget(project=self.current_project)
        self._find_or_open_tab("Asset Library", lambda: editor)

    # ── Export ────────────────────────────────────────────────

    def export_override(self):
        if not self.current_project:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Select KotOR installation folder")
        if folder:
            self.log(f"→ Export to override: {folder}/override/")
            QMessageBox.information(self, "Export",
                f"Files would be exported to:\n{folder}\\override\\\n\n"
                "(Export module not yet connected to file system)")

    def export_erf(self):
        if not self.current_project:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export ERF", "", "ERF Files (*.erf)")
        if path:
            self.log(f"→ Export ERF: {path}")
            QMessageBox.information(self, "Export ERF",
                f"ERF would be written to:\n{path}\n\n"
                "(ERF writer module not yet connected)")

    # ── Project Tree ──────────────────────────────────────────

    def _refresh_project_tree(self):
        self.project_tree.clear()
        if not self.current_project:
            root = QTreeWidgetItem(["No project loaded"])
            root.setForeground(0, QColor("#666666"))
            self.project_tree.addTopLevelItem(root)
            return

        p = self.current_project
        root = QTreeWidgetItem([p.name])
        root.setForeground(0, QColor("#9cdcfe"))
        root.setExpanded(True)
        self.project_tree.addTopLevelItem(root)

        def section(label, count, color="#cccccc"):
            item = QTreeWidgetItem([f"{label} ({count})"])
            item.setForeground(0, QColor(color))
            return item

        def child(parent, label, data=None):
            item = QTreeWidgetItem([label])
            item.setForeground(0, QColor("#cccccc"))
            if data:
                item.setData(0, Qt.UserRole, data)
            parent.addChild(item)
            return item

        # Scripts
        scripts_item = section("Scripts", len(p.scripts), "#dcdcaa")
        scripts_item.setExpanded(True)
        root.addChild(scripts_item)
        for s in p.scripts:
            child(scripts_item, s.name, ("script", s))

        # Quests
        quests_item = section("Quests", len(p.quests), "#569cd6")
        quests_item.setExpanded(True)
        root.addChild(quests_item)
        for q in p.quests:
            child(quests_item, q.quest_name, ("quest", q))

        # Dialogues
        dlg_item = section("Dialogues", len(p.dialogues), "#4ec9b0")
        dlg_item.setExpanded(True)
        root.addChild(dlg_item)
        for d in p.dialogues:
            child(dlg_item, d.name, ("dialogue", d))

        # Models
        models_item = section("Models", len(p.models), "#ce9178")
        root.addChild(models_item)

    def _on_tree_item_double_clicked(self, item, col):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, obj = data
        if kind == "script":
            editor = ScriptEditorWidget(script=obj, project=self.current_project)
            idx = self.editor_tabs.addTab(editor, f"✎ {obj.name}.nss")
            self.editor_tabs.setCurrentIndex(idx)
        elif kind == "quest":
            editor = QuestBuilderWidget(quest=obj, project=self.current_project)
            idx = self.editor_tabs.addTab(editor, f"⚔ {obj.quest_name}")
            self.editor_tabs.setCurrentIndex(idx)
        elif kind == "dialogue":
            editor = DialogueEditorWidget(dialogue=obj)
            idx = self.editor_tabs.addTab(editor, f"🗨 {obj.name}.dlg")
            self.editor_tabs.setCurrentIndex(idx)

    def _on_tree_item_selected(self):
        items = self.project_tree.selectedItems()
        if not items:
            return
        item = items[0]
        data = item.data(0, Qt.UserRole)
        if not data:
            self.props_text.setPlainText("")
            return
        kind, obj = data
        if hasattr(obj, "to_dict"):
            import json
            self.props_text.setPlainText(
                json.dumps(obj.to_dict(), indent=2, default=str)
            )

    # ── Game Selector ─────────────────────────────────────────

    def _on_game_changed(self, game: str):
        self.game_status.setText(game)
        if self.current_project:
            self.current_project.target_game = game

    # ── Helpers ───────────────────────────────────────────────

    def log(self, message: str):
        self.output_console.appendPlainText(message)

    def _clear_output(self):
        self.output_console.clear()

    def _update_status(self, message: str):
        self.status_label.setText(message)

    def _show_about(self):
        QMessageBox.about(self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br>Version {APP_VERSION}<br><br>"
            f"All-in-one IDE for KotOR 1 &amp; 2 TSL modding.<br><br>"
            f"GPL-3.0 License<br>"
            f"Credits: KotOR community, xoreos-tools, Fred Tetra, TK102, Cortisol")
