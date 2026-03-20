"""
GhostScripter-K1-K2 — Main Window
Dark IDE layout matching KotorModTools / GhostRigger aesthetic.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


from qtpy.QtCore import Qt, QSize, QTimer
from qtpy.QtGui import QIcon, QFont, QColor, QPalette, QKeySequence
from qtpy.QtWidgets import (
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
from ghostscripter.core.export.erf_writer import OverrideExporter, ERFWriter
from ghostscripter.core.export.dlg_writer import GFF3Writer as GFFWriter, DLGExporter
from ghostscripter.core.export.dlg_reader import DLGImporter
from ghostscripter.core.database.manager import get_db
from ghostscripter.ipc.ghostrigger_bridge import GhostRiggerBridge
from ghostscripter.ipc.ipc_server import (
    IPCServer as GhostScripterIPCServer,
    GHOSTSCRIPTER_PORT as GHOSTSCRIPTER_IPC_PORT,
    drain_event_queue as _drain_event_queue,
)
import ghostscripter.ipc.gmodular_client as _gm_client

from ghostscripter.ui.widgets.script_editor_widget import ScriptEditorWidget
from ghostscripter.ui.widgets.dialogue_editor_widget import DialogueEditorWidget
from ghostscripter.ui.widgets.quest_builder_widget import QuestBuilderWidget
from ghostscripter.ui.widgets.twoda_manager_widget import TwoDAManagerWidget
from ghostscripter.ui.widgets.asset_library_widget import AssetLibraryWidget
from ghostscripter.ui.widgets.tlk_editor_widget import TLKEditorWidget
from ghostscripter.ui.widgets.erf_packer_widget import ERFPackerWidget
from ghostscripter.ui.widgets.journal_editor_widget import JournalEditorWidget
from ghostscripter.ui.dialogs.new_project_dialog import NewProjectDialog
from ghostscripter.ui.dialogs.new_quest_dialog import NewQuestDialog
from ghostscripter.ui.dialogs.tutorial_dialog import TutorialDialog
from ghostscripter.ui.widgets.log_viewer_widget import LogViewerWidget
from ghostscripter.ui.widgets.gff_template_viewer_widget import GFFTemplateViewerWidget


class MainWindow(QMainWindow):
    """
    Primary application window for GhostScripter-K1-K2.
    Layout: Project Tree (left) | Tabbed Editor (center) | Properties (right)
    Output console docked at bottom.
    """

    def __init__(self):
        super().__init__()
        self.current_project: ModProject | None = None
        self._game_dir: Path | None = None          # KotOR install path
        self._twoda_widget: object | None = None    # TwoDAManagerWidget ref
        self._tlk_widget: object | None = None      # TLKEditorWidget ref
        # Blueprint title format
        self.setWindowTitle(f"GhostScripter — KotOR Script + Logic IDE  v{APP_VERSION}")

        # Debounce project-tree rebuilds so rapid consecutive calls
        # (e.g. opening a file triggers save + refresh + propagate) only
        # result in ONE repaint.
        self._tree_refresh_timer = QTimer(self)
        self._tree_refresh_timer.setSingleShot(True)
        self._tree_refresh_timer.setInterval(120)   # ms
        self._tree_refresh_timer.timeout.connect(self._do_refresh_project_tree)
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        # Set application icon
        self._set_app_icon()

        # Load saved settings (game dir etc.)
        self._load_settings()

        # Backend services
        try:
            self._db = get_db()
        except Exception as e:
            self._db = None

        # IPC bridge — only wired up, NOT started yet (output_console not ready)
        self._ipc_bridge = GhostRiggerBridge(self)
        self._ipc_bridge.connected.connect(self._on_rigger_connected)
        self._ipc_bridge.disconnected.connect(self._on_rigger_disconnected)
        self._ipc_bridge.model_ready.connect(self._on_model_ready)
        self._ipc_bridge.status_update.connect(self.log)

        # GhostScripter IPC server — receives commands from GhostRigger/GModular
        self._ipc_server = GhostScripterIPCServer(port=GHOSTSCRIPTER_IPC_PORT)

        # Drain timer — drains module-level queue, dispatches events to UI
        self._ipc_drain_timer = QTimer(self)
        self._ipc_drain_timer.setInterval(100)  # 100 ms — imperceptible
        self._ipc_drain_timer.timeout.connect(self._drain_ipc_events)

        # NOTE: all IPC services are started after _setup_ui() so that
        # self.output_console already exists when any status_update fires.

        self._setup_ui()          # creates self.output_console
        self._setup_menus()
        self._setup_toolbar()
        self._setup_statusbar()
        self._apply_theme()

        # Now it is safe to start all IPC services
        self._ipc_bridge.start()
        self._ipc_server.start()
        self._ipc_drain_timer.start()

        self.log(f"GhostScripter v{APP_VERSION} — KotOR Script + Logic IDE")
        self.log(f"IPC server listening on port {GHOSTSCRIPTER_IPC_PORT}")
        if self._db:
            stats = self._db.get_stats()
            self.log(f"Database: {stats.get('recent_projects', 0)} recent projects")

        # Auto-open asset library on startup if a game directory was saved
        if self._game_dir and self._game_dir.exists():
            self.log(f"✓ Restored game directory: {self._game_dir}")
            self.update_status(f"Game: {self._game_dir.name}")
            self.open_asset_library()

    # ── App Icon ──────────────────────────────────────────────

    def _set_app_icon(self):
        """Load and set the application window icon."""
        if getattr(sys, "frozen", False):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).resolve().parent.parent.parent

        ico_path = base / "resources" / "icons" / "ghostscripter.ico"
        png_path = base / "resources" / "icons" / "ghostscripter.png"

        for p in [ico_path, png_path]:
            if p.exists():
                self.setWindowIcon(QIcon(str(p)))
                QApplication.setWindowIcon(QIcon(str(p)))
                break

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
        """Build the bottom log panel using the new LogViewerWidget."""
        panel = QWidget()
        panel.setObjectName("outputPanel")
        panel.setFixedHeight(170)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header_row = QWidget()
        header_row.setObjectName("outputPanelHeader")
        header_row.setStyleSheet(
            "background:#2d2d30; border-top:1px solid #3c3c3c;"
        )
        header_layout = QHBoxLayout(header_row)
        header_layout.setContentsMargins(8, 3, 8, 3)
        header_layout.setSpacing(8)

        header_label = QLabel("Output / Log")
        header_label.setStyleSheet(
            "color:#cccccc; font-weight:bold; font-size:9pt;"
        )
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        # "Open log file" button
        open_log_btn = QPushButton("📄 Open Log")
        open_log_btn.setFixedHeight(20)
        open_log_btn.setFixedWidth(76)
        open_log_btn.setStyleSheet("""
            QPushButton { background:#3c3c3c; color:#9cdcfe; border:1px solid #555;
                          border-radius:2px; font-size:8pt; padding:0; }
            QPushButton:hover { background:#4a4a4a; color:#cce8ff; }
        """)
        open_log_btn.clicked.connect(self._open_log_file)
        header_layout.addWidget(open_log_btn)

        # ── Toggle button: collapse / expand the log body ─────────────────────
        self._log_expanded = True          # track visible state
        self._log_toggle_btn = QPushButton("▼ Hide")
        self._log_toggle_btn.setFixedHeight(20)
        self._log_toggle_btn.setFixedWidth(54)
        self._log_toggle_btn.setToolTip("Hide / show the output log panel")
        self._log_toggle_btn.setStyleSheet("""
            QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                          border-radius:2px; font-size:8pt; padding:0; }
            QPushButton:hover { background:#4a4a4a; color:white; }
        """)
        self._log_toggle_btn.clicked.connect(self._toggle_output_log)
        header_layout.addWidget(self._log_toggle_btn)

        layout.addWidget(header_row)
        # Store header height so we can restore it
        self._output_panel_header_h = 28

        # Embedded LogViewerWidget
        self.log_viewer = LogViewerWidget(parent=panel)
        self.log_viewer.attach()   # start receiving live records
        layout.addWidget(self.log_viewer)

        # Legacy compat: keep output_console pointing to something writable
        # so existing self.log() calls keep working
        self.output_console = self.log_viewer._text

        return panel

    def _toggle_output_log(self):
        """Collapse / expand the output log body (keeps header visible)."""
        self._log_expanded = not self._log_expanded
        self.log_viewer.setVisible(self._log_expanded)
        if self._log_expanded:
            self.output_panel.setFixedHeight(170)
            self._log_toggle_btn.setText("▼ Hide")
            self._log_toggle_btn.setToolTip("Hide the output log panel")
        else:
            # Collapse to header-bar height only
            self.output_panel.setFixedHeight(self._output_panel_header_h)
            self._log_toggle_btn.setText("▲ Show")
            self._log_toggle_btn.setToolTip("Show the output log panel")

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
        layout.addWidget(make_btn("TLK Editor", self.open_tlk_editor))
        layout.addWidget(make_btn("ERF Packer", self.open_erf_packer))

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
            "• NSS Script Editor — real autocomplete from nwscript.nss (K1 & K2)",
            "• Visual Dialogue Tree Editor — full GFF field set (VO, scripts, camera)",
            "• Quest Builder with templates and globalcat.2da integration",
            "• 2DA Manager — TSLPatcher-style AddRow / CopyRow / ModifyRow / ColumnAdd",
            "• TLK Editor — read, edit, and save dialog.tlk talk tables",
            "• ERF / MOD / RIM Packer — drag-and-drop archive builder",
            "• Asset Library — browse mod project files",
            "• Export to Override / ERF / DLG (GFF3 binary)",
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

    # ── Menus (blueprint layout: File|Script|Dialog|Tables|Strings|IPC|Help) ─

    def _setup_menus(self):
        menubar = self.menuBar()

        # ── File ──────────────────────────────────────────────────────────────
        file_menu = menubar.addMenu("File")
        file_menu.addAction(self._action("New Project", self.new_project, "Ctrl+Shift+N"))
        file_menu.addAction(self._action("Open Project…", self.open_project, "Ctrl+O"))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Save Project", self.save_project, "Ctrl+S"))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Set KotOR Game Directory…", self._set_game_directory))
        file_menu.addAction(self._action("Clear Game Directory", self._clear_game_directory))
        file_menu.addSeparator()
        file_menu.addAction(self._action("Exit", self.close, "Alt+F4"))

        # ── Script ────────────────────────────────────────────────────────────
        script_menu = menubar.addMenu("Script")
        script_menu.addAction(self._action("New Script", self.new_script, "Ctrl+N"))
        script_menu.addAction(self._action("Open .NSS File…", self.open_nss_file, "Ctrl+Shift+S"))
        script_menu.addSeparator()
        script_menu.addAction(self._action("Script Editor", self.open_script_editor))
        script_menu.addAction(self._action("Quest Builder", self.open_quest_builder))

        # ── Dialog ────────────────────────────────────────────────────────────
        dialog_menu = menubar.addMenu("Dialog")
        dialog_menu.addAction(self._action("New Dialogue", self.new_dialogue))
        dialog_menu.addAction(self._action("Open .DLG File…", self.open_dlg_file, "Ctrl+Shift+D"))
        dialog_menu.addSeparator()
        dialog_menu.addAction(self._action("Dialogue Editor", self.open_dialogue_editor))
        dialog_menu.addSeparator()
        dialog_menu.addAction(self._action("Export DLG Files", self.export_dlg))

        # ── Tables ────────────────────────────────────────────────────────────
        tables_menu = menubar.addMenu("Tables")
        tables_menu.addAction(self._action("2DA Manager", self.open_2da_manager))
        tables_menu.addAction(self._action("Open 2DA Manager with Game Library", self._open_2da_with_game))
        tables_menu.addSeparator()
        tables_menu.addAction(self._action("Asset Library", self.open_asset_library))
        tables_menu.addSeparator()
        tables_menu.addAction(self._action("Export to Override", self.export_override))
        tables_menu.addAction(self._action("Export to ERF", self.export_erf))
        tables_menu.addSeparator()
        tables_menu.addAction(self._action("ERF Packer", self.open_erf_packer))

        # ── Strings ───────────────────────────────────────────────────────────
        strings_menu = menubar.addMenu("Strings")
        strings_menu.addAction(self._action("TLK Editor", self.open_tlk_editor))
        strings_menu.addAction(self._action("Journal Editor", self.open_journal_editor))

        # ── IPC ───────────────────────────────────────────────────────────────
        ipc_menu = menubar.addMenu("IPC")
        ipc_menu.addAction(self._action("IPC Status…", self._show_ipc_status))
        ipc_menu.addSeparator()
        ipc_menu.addAction(self._action("Ping GhostRigger", self._ping_ghostrigger))
        ipc_menu.addAction(self._action("Ping GModular", self._ping_gmodular))

        # ── Help ──────────────────────────────────────────────────────────────
        help_menu = menubar.addMenu("Help")
        self._tutorial_action = self._action(
            "📖 Quick-Start Guide / Tutorial",
            self._toggle_tutorial,
            shortcut="F1",
        )
        self._tutorial_action.setCheckable(True)
        help_menu.addAction(self._tutorial_action)
        help_menu.addSeparator()
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
        tb.addWidget(tb_btn("TLK Editor", self.open_tlk_editor, "Open TLK/talk-table editor"))
        tb.addWidget(tb_btn("Journal", self.open_journal_editor, "Open Journal (.jrl) editor"))
        tb.addWidget(tb_btn("ERF Packer", self.open_erf_packer, "Pack files into ERF/MOD archive"))
        tb.addSeparator()
        tb.addWidget(tb_btn("Export Override", self.export_override))
        tb.addWidget(tb_btn("Export ERF", self.export_erf))
        tb.addSeparator()
        help_btn = tb_btn("❓", self._toggle_tutorial, tooltip="Quick-Start Guide / Tutorial  (F1)")
        help_btn.setFixedWidth(30)
        help_btn.setStyleSheet("""
            QPushButton { background:#0f3460; color:#4ec9b0; border:1px solid #1a5a8a;
                          border-radius:3px; padding:2px 4px; font-weight:bold; font-size:11pt; }
            QPushButton:hover { background:#1a4a80; color:#5fd9c4; }
            QPushButton:pressed { background:#0a2a50; }
        """)
        tb.addWidget(help_btn)

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

        # GhostRigger IPC indicator
        self.rigger_status_label = QLabel("GR: —")
        self.rigger_status_label.setStyleSheet(
            "color:#858585; padding: 0 8px; font-size:8pt;"
            "border-left:1px solid rgba(255,255,255,0.2);"
        )
        self.rigger_status_label.setToolTip("GhostRigger connection status")
        sb.addPermanentWidget(self.rigger_status_label)

        # GModular IPC indicator
        self.gmodular_status_label = QLabel("GM: —")
        self.gmodular_status_label.setStyleSheet(
            "color:#858585; padding: 0 8px; font-size:8pt;"
            "border-left:1px solid rgba(255,255,255,0.2);"
        )
        self.gmodular_status_label.setToolTip("GModular connection status")
        sb.addPermanentWidget(self.gmodular_status_label)

        version_label = QLabel(f"GhostScripter {APP_VERSION}")
        version_label.setStyleSheet("color:#ffffff; padding: 0 10px; "
                                     "border-left:1px solid rgba(255,255,255,0.3);")
        sb.addPermanentWidget(version_label)

    # ── Theme ─────────────────────────────────────────────────

    def _apply_theme(self):
        """Load and apply the dark QSS theme."""
        import sys
        if getattr(sys, "frozen", False):
            # Running inside PyInstaller bundle
            base = Path(sys._MEIPASS)
            qss_path = base / "ghostscripter" / "ui" / "styles" / "dark.qss"
        else:
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

        # App icon
        from ghostscripter.core.constants import APP_VERSION
        icon_path = Path(__file__).parent.parent.parent / "resources" / "icons" / "ghostscripter.png"
        if not icon_path.exists() and getattr(sys, 'frozen', False):
            icon_path = Path(sys._MEIPASS) / "resources" / "icons" / "ghostscripter.png"
        if icon_path.exists():
            from qtpy.QtGui import QPixmap
            icon_lbl = QLabel()
            pix = QPixmap(str(icon_path)).scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_lbl.setPixmap(pix)
            icon_lbl.setAlignment(Qt.AlignCenter)
            lay.addWidget(icon_lbl)

        title = QLabel("GhostScripter")
        title.setStyleSheet("color:#9cdcfe; font-size:26pt; font-weight:bold; letter-spacing:2px;")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        sub = QLabel("All-in-one IDE for KotOR 1 &amp; 2 TSL Modding")
        sub.setTextFormat(Qt.RichText)
        sub.setStyleSheet("color:#569cd6; font-size:13pt;")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)

        ver_lbl = QLabel(f"v{APP_VERSION}  •  GPL-3.0  •  KotOR Community")
        ver_lbl.setStyleSheet("color:#555555; font-size:9pt;")
        ver_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(ver_lbl)

        lay.addSpacing(20)

        # Quick start buttons
        btn_row = QWidget()
        btn_row.setStyleSheet("background:transparent;")
        btn_lay = QHBoxLayout(btn_row)
        btn_lay.setSpacing(12)

        actions = [
            ("+ New Project", self.new_project, True),
            ("Open Project", self.open_project, False),
            ("Open .DLG File", self.open_dlg_file, False),
            ("Open .NSS Script", self.open_nss_file, False),
            ("Script Editor", self.open_script_editor, False),
            ("Dialogue Editor", self.open_dialogue_editor, False),
            ("Quest Builder", self.open_quest_builder, True),
            ("2DA Manager", self.open_2da_manager, False),
            ("TLK Editor", self.open_tlk_editor, False),
            ("Journal Editor", self.open_journal_editor, False),
            ("ERF Packer", self.open_erf_packer, False),
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

        lay.addSpacing(20)

        # Feature hint labels
        hints = [
            "NWScript Editor with real autocomplete  •  Visual Dialogue Tree Editor (full GFF fields)",
            "2DA Manager (TSLPatcher-style)  •  TLK Editor  •  ERF/MOD/RIM Packer",
            "DLG Import/Export (GFF3 binary)  •  Quest Builder  •  GhostRigger IPC Bridge",
        ]
        for h in hints:
            hl = QLabel(h)
            hl.setStyleSheet("color:#4a4a4a; font-size:8pt;")
            hl.setAlignment(Qt.AlignCenter)
            lay.addWidget(hl)

        # ── Recent Projects ──────────────────────────────────
        lay.addSpacing(16)
        recent_section = self._build_recent_projects_section()
        if recent_section:
            lay.addWidget(recent_section)

        idx = self.editor_tabs.addTab(welcome, "Welcome")
        self.editor_tabs.tabBar().setTabButton(idx, self.editor_tabs.tabBar().RightSide, None)

    def _build_recent_projects_section(self) -> QWidget | None:
        """Build a compact recent-projects list for the Welcome tab."""
        if not self._db:
            return None
        recents = self._db.get_recent_projects(limit=6)
        if not recents:
            return None

        container = QWidget()
        container.setStyleSheet("background:transparent;")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(4)

        hdr = QLabel("Recent Projects")
        hdr.setStyleSheet("color:#4ec9b0; font-weight:bold; font-size:9pt;")
        hdr.setAlignment(Qt.AlignCenter)
        vlay.addWidget(hdr)

        for proj in recents:
            name = proj.get("name", "Unknown")
            path = proj.get("path", "")
            game = proj.get("game", "")
            game_str = f"[{game}]  " if game else ""
            row = QPushButton(f"📁  {game_str}{name}   —   {path}")
            row.setToolTip(f"Open project: {path}")
            row.setStyleSheet("""
                QPushButton {
                    background:#252526; color:#cccccc;
                    border:1px solid #3c3c3c; border-radius:3px;
                    padding:4px 12px; text-align:left; font-size:8pt;
                }
                QPushButton:hover { background:#2d2d30; color:white;
                                    border-color:#0078d4; }
            """)
            # Capture path in closure
            proj_path = path
            row.clicked.connect(lambda checked, p=proj_path: self._open_recent_project(p))
            vlay.addWidget(row)

        return container

    def _open_recent_project(self, path: str):
        """Open a project by its stored path."""
        if not path or not Path(path).exists():
            QMessageBox.warning(
                self, "Project Not Found",
                f"The project folder no longer exists:\n{path}"
            )
            return
        try:
            from ghostscripter.core.models.project import ModProject
            self.current_project = ModProject.load(Path(path))
            self._refresh_project_tree()
            self._update_status(f"Loaded: {self.current_project.name}")
            self.game_selector.setCurrentText(self.current_project.target_game)
            self.log(f"✓ Opened recent project: {self.current_project.name}")
            if self._db:
                self._db.save_recent_project(self.current_project)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")

    # ── Project Operations ────────────────────────────────────

    def new_project(self):
        dlg = NewProjectDialog(self)
        if dlg.exec():
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
                if self._db:
                    self._db.save_recent_project(self.current_project)
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
            if self._db:
                self._db.save_recent_project(self.current_project)
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
            if self._db:
                self._db.save_recent_project(self.current_project)
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
        name = name.strip()
        script = ScriptFile(name=name, source_code=make_void_main_template())
        if self.current_project and self.current_project.script_dir:
            script.file_path = self.current_project.script_dir / f"{name}.nss"
            script.save_to_disk()
            self.current_project.scripts.append(script)
            self._refresh_project_tree()
        editor = ScriptEditorWidget(script=script, project=self.current_project)
        if self._game_dir:
            editor.set_game_dir(self._game_dir)
        idx = self.editor_tabs.addTab(editor, f"✎ {name}.nss")
        self.editor_tabs.setCurrentIndex(idx)
        self.log(f"✓ New script: {name}.nss")

    def open_script_editor(self):
        script = ScriptFile(name="untitled", source_code=make_void_main_template())
        editor = ScriptEditorWidget(script=script, project=self.current_project)
        if self._game_dir:
            editor.set_game_dir(self._game_dir)
        title = "Script Editor"
        idx = self.editor_tabs.addTab(editor, title)
        self.editor_tabs.setCurrentIndex(idx)

    def new_dialogue(self):
        name, ok = QInputDialog.getText(self, "New Dialogue", "Dialogue name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        dlg_file = create_simple_dialogue(name, "npc_001")
        if self.current_project and self.current_project.dialogue_dir:
            dlg_file.file_path = self.current_project.dialogue_dir / f"{name}.dlg"
            # Write GFF/DLG binary to disk
            try:
                exporter = DLGExporter()
                data = exporter.export(dlg_file)
                with open(dlg_file.file_path, "wb") as f:
                    f.write(data)
                self.log(f"  DLG written: {dlg_file.file_path}")
            except Exception as e:
                self.log(f"  ⚠ DLG write: {e}")
            self.current_project.dialogues.append(dlg_file)
            self._refresh_project_tree()
            if self._db:
                self._db.save_dialogue_snapshot(
                    self.current_project.project_id, dlg_file
                )
        editor = DialogueEditorWidget(dialogue=dlg_file)
        if self._game_dir:
            editor.set_game_dir(self._game_dir)
        idx = self.editor_tabs.addTab(editor, f"🗨 {name}.dlg")
        self.editor_tabs.setCurrentIndex(idx)
        self.log(f"✓ New dialogue: {name}.dlg")

    def open_dialogue_editor(self):
        dlg_file = create_simple_dialogue("new_dialogue", "npc_001")
        editor = DialogueEditorWidget(dialogue=dlg_file)
        if self._game_dir:
            editor.set_game_dir(self._game_dir)
        idx = self.editor_tabs.addTab(editor, "Dialogue Editor")
        self.editor_tabs.setCurrentIndex(idx)

    def open_dlg_file(self):
        """Open an existing .dlg (GFF binary) file for editing."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open DLG File", "",
            "KotOR Dialogue Files (*.dlg);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            importer = DLGImporter()
            dlg_file = importer.import_from_bytes(data)
            dlg_file.file_path = Path(path)
            dlg_file.name = Path(path).stem
            editor = DialogueEditorWidget(dialogue=dlg_file)
            if self._game_dir:
                editor.set_game_dir(self._game_dir)
            title = f"🗨 {Path(path).name}"
            idx = self.editor_tabs.addTab(editor, title)
            self.editor_tabs.setCurrentIndex(idx)
            self.log(f"✓ Opened DLG: {path}")
            self.log(f"  Entries: {len(dlg_file.entries)}, Replies: {len(dlg_file.replies)}")
            self._update_status(f"Dialogue: {Path(path).name}  ({len(dlg_file.entries)} entries)")
        except Exception as e:
            self.log(f"✗ Failed to open DLG: {e}")
            QMessageBox.critical(self, "Open DLG Error",
                f"Could not load dialogue file:\n{path}\n\n{e}")

    def open_nss_file(self):
        """Open an existing .nss NWScript file for editing."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open NWScript File", "",
            "NWScript Files (*.nss);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                source = f.read()
            script = ScriptFile(name=Path(path).stem, source_code=source)
            script.file_path = Path(path)
            editor = ScriptEditorWidget(script=script, project=self.current_project)
            if self._game_dir:
                editor.set_game_dir(self._game_dir)
            title = f"✎ {Path(path).name}"
            idx = self.editor_tabs.addTab(editor, title)
            self.editor_tabs.setCurrentIndex(idx)
            self.log(f"✓ Opened script: {path}")
            self._update_status(f"Script: {Path(path).name}")
        except Exception as e:
            self.log(f"✗ Failed to open NSS: {e}")
            QMessageBox.critical(self, "Open Script Error",
                f"Could not load script file:\n{path}\n\n{e}")

    def new_quest(self):
        dlg = NewQuestDialog(self)
        if dlg.exec():
            data = dlg.get_data()
            quest = create_quest_from_template(
                data["template"], data["name"], data.get("game", "K1")
            )
            if self.current_project:
                self.current_project.quests.append(quest)
                self._refresh_project_tree()
                if self._db:
                    self._db.save_quest_snapshot(
                        self.current_project.project_id, quest
                    )
            editor = QuestBuilderWidget(quest=quest, project=self.current_project)
            idx = self.editor_tabs.addTab(editor, f"⚔ {data['name']}")
            self.editor_tabs.setCurrentIndex(idx)
            self.log(f"✓ New quest: {data['name']} ({data['template']})")

    def open_quest_builder(self):
        editor = QuestBuilderWidget(project=self.current_project)
        self._find_or_open_tab("Quest Builder", lambda: editor)

    def open_2da_manager(self):
        def _make():
            w = TwoDAManagerWidget(project=self.current_project)
            self._twoda_widget = w
            # Auto-load game if we have a path
            if self._game_dir and self._game_dir.exists():
                w.load_game_from_path(self._game_dir)
            return w
        self._find_or_open_tab("2DA Manager", _make)
        # If already open, try to load game
        if self._twoda_widget and self._game_dir and self._game_dir.exists():
            pass  # already handled in _make

    def _open_2da_with_game(self):
        """Open 2DA manager and prompt for game directory if not set."""
        if not self._game_dir:
            self._set_game_directory()
        self.open_2da_manager()

    def _set_game_directory(self):
        """Prompt user to pick the KotOR installation directory."""
        start = str(self._game_dir) if self._game_dir else str(Path.home())
        game_dir = QFileDialog.getExistingDirectory(
            self, "Select KotOR Game Directory (must contain chitin.key)", start
        )
        if not game_dir:
            return
        path = Path(game_dir)
        if not (path / "chitin.key").exists():
            QMessageBox.warning(
                self, "Invalid Directory",
                f"chitin.key not found in:\n{game_dir}\n\n"
                "Please select the folder that contains chitin.key"
            )
            return
        self._game_dir = path
        self._save_settings()
        self.log(f"✓ Game directory set: {game_dir}")
        self.update_status(f"Game: {path.name}")
        # Propagate to all open game-aware widgets
        self._propagate_game_dir(path)
        QMessageBox.information(
            self, "Game Directory Set",
            f"KotOR directory configured:\n{game_dir}\n\n"
            "Open the 2DA Manager, TLK Editor, or ERF Packer to access game files."
        )

    def _propagate_game_dir(self, path):
        """Push the new game dir to every open game-aware widget."""
        if self._twoda_widget:
            self._twoda_widget.load_game_from_path(path)
        if hasattr(self, "editor_tabs"):
            for i in range(self.editor_tabs.count()):
                w = self.editor_tabs.widget(i)
                if hasattr(w, "set_game_dir"):
                    w.set_game_dir(path)
                # For TLK editor: always reload from the new game dir
                if hasattr(w, "load_tlk_from_path") and hasattr(w, "tlk"):
                    tlk_path = path / "dialog.tlk"
                    if tlk_path.exists():
                        w.load_tlk_from_path(tlk_path)

    def _clear_game_directory(self):
        self._game_dir = None
        self._save_settings()
        self.log("Game directory cleared.")
        self.update_status("No game loaded")

    def _load_settings(self):
        """Load persisted settings from JSON file."""
        settings_path = Path.home() / ".ghostscripter" / "settings.json"
        try:
            if settings_path.exists():
                data = json.loads(settings_path.read_text())
                gd = data.get("game_dir", "")
                if gd and Path(gd).exists():
                    self._game_dir = Path(gd)
        except Exception:
            pass

    def _save_settings(self):
        """Persist settings to JSON file."""
        settings_path = Path.home() / ".ghostscripter" / "settings.json"
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"game_dir": str(self._game_dir) if self._game_dir else ""}
            settings_path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def open_asset_library(self):
        def _make():
            w = AssetLibraryWidget(
                project=self.current_project,
                game_dir=self._game_dir,
            )
            w.open_asset_requested.connect(self.open_asset_from_library)
            return w
        self._find_or_open_tab("Asset Library", _make)

    def open_asset_from_library(self, resref: str, ext: str, raw_data) -> None:
        """
        Route an asset double-clicked in the Asset Library to the correct editor.

        Called by AssetLibraryWidget.open_asset_requested signal.
        raw_data is bytes (from ResourceManager.read) or None.
        """
        import base64
        ext = ext.lower()
        self.log(f"📂 Opening game asset: {resref}{ext}")

        # ── Dialogue files (.dlg) ─────────────────────────────────────────────
        if ext == ".dlg":
            b64 = base64.b64encode(raw_data).decode() if raw_data else ""
            self.ipc_open_dlg(resref, bytes_b64=b64)

        # ── NWScript source (.nss) ────────────────────────────────────────────
        elif ext == ".nss":
            src = ""
            if raw_data:
                try:
                    src = raw_data.decode("utf-8", errors="replace")
                except Exception:
                    pass
            if not src:
                # .nss files are NOT stored in game BIFs — only .ncs compiled
                # versions are. Try the Override folder / project dir via
                # _locate_script, then fall back to decompiling the .ncs twin.
                located = self._locate_script(resref)
                if located:
                    src = located.source_code
                else:
                    # Fetch the compiled .ncs from ResourceManager and decompile
                    ncs_data = self._read_asset_from_rm(resref, ".ncs")
                    if ncs_data:
                        src = self._decompile_ncs_bytes(ncs_data, resref)
            self.ipc_open_script(resref, source=src)

        # ── Compiled script (.ncs) — decompile and show NSS source ────────────
        elif ext == ".ncs":
            src = self._decompile_ncs_bytes(raw_data, resref) if raw_data else f"// {resref}.ncs — no data\n"
            self.ipc_open_script(resref, source=src)

        # ── 2DA tables ────────────────────────────────────────────────────────
        elif ext == ".2da":
            self.ipc_open_2da(resref)

        # ── GFF-based templates (.uti, .utc, .utp, .utt, .utm, .uts, .utw,
        #    .are, .git, .gic, .ifo, .bic, .gui, .fac, .jrl, .pth) ───────────
        elif ext in {".uti", ".utc", ".utp", ".utt", ".utm", ".uts", ".utw",
                     ".are", ".git", ".gic", ".ifo", ".bic", ".gui",
                     ".fac", ".jrl", ".pth"}:
            # raw_data may be None if the widget's RM read failed (e.g. BIF
            # access issue). Retry via the asset library's ResourceManager.
            if not raw_data:
                raw_data = self._read_asset_from_rm(resref, ext)
            self._open_gff_asset(resref, ext, raw_data)

        # ── TLK string table ──────────────────────────────────────────────────
        elif ext == ".tlk":
            self.ipc_open_tlk()

        # ── Model files — show info in detail panel (no 3-D viewer yet) ───────
        elif ext in {".mdl", ".mdx"}:
            self._open_model_info(resref, ext, raw_data)

        # ── Anything else — show hex/text dump in detail panel ────────────────
        else:
            self._open_generic_asset(resref, ext, raw_data)

    # ── GFF template types that get a full viewer tab ─────────────────────────
    _GFF_VIEWER_TYPES = frozenset({
        ".utc", ".uti", ".utp", ".utt", ".utm", ".uts", ".utw",
    })

    def _open_gff_asset(self, resref: str, ext: str, raw_data) -> None:
        """Open a GFF-based asset.

        - For the well-known template types (.utc, .uti, .utp, .utt, .utm,
          .uts, .utw) a full :class:`GFFTemplateViewerWidget` tab is opened
          (or focused if already open).
        - All other GFF types (.are, .git, .gic, .ifo, …) fall back to a
          summary in the asset-library detail panel.
        """
        if not raw_data:
            self.log(f"  ✗ No data for {resref}{ext}")
            return

        # ── Full viewer for supported template types ──────────────────────────
        if ext in self._GFF_VIEWER_TYPES:
            tab_title = f"{ext.lstrip('.')} {resref}"
            # Focus existing tab if already open
            for i in range(self.editor_tabs.count()):
                if self.editor_tabs.tabText(i) == tab_title:
                    self.editor_tabs.setCurrentIndex(i)
                    self.log(f"  ↩ Focused existing tab: {tab_title}")
                    return
            # Create new viewer tab
            try:
                viewer = GFFTemplateViewerWidget(resref, ext, raw_data)
                idx = self.editor_tabs.addTab(viewer, tab_title)
                self.editor_tabs.setCurrentIndex(idx)
                # Enable close button
                btn = self.editor_tabs.tabBar().tabButton(idx, self.editor_tabs.tabBar().RightSide)
                if btn:
                    btn.setVisible(True)
                self.log(f"  ✓ Opened {ext.lstrip('.').upper()} viewer: {resref}{ext}")
            except Exception as exc:
                self.log(f"  ✗ Could not open GFF viewer for {resref}{ext}: {exc}")
            return

        # ── Fallback: summary in detail panel ────────────────────────────────
        try:
            file_type = raw_data[:4].decode("ascii", errors="replace").strip()
            version   = raw_data[4:8].decode("ascii", errors="replace").strip()
            size_kb   = len(raw_data) / 1024
            summary = (
                f"File:     {resref}{ext}\n"
                f"Type:     {file_type}  ({version})\n"
                f"Size:     {size_kb:.1f} KB  ({len(raw_data):,} bytes)\n"
                f"\n(Detailed viewer not yet available for {ext} files.)"
            )
            for i in range(self.editor_tabs.count()):
                w = self.editor_tabs.widget(i)
                if hasattr(w, "_set_detail_text"):
                    w._set_detail_text(summary)
                    self.editor_tabs.setCurrentIndex(i)
                    return
            self.log(summary)
        except Exception as exc:
            self.log(f"  ✗ Could not parse {resref}{ext}: {exc}")

    def _open_model_info(self, resref: str, ext: str, raw_data) -> None:
        """Show model info in the asset library detail panel."""
        size_kb = len(raw_data) / 1024 if raw_data else 0
        summary = (
            f"Model:    {resref}{ext}\n"
            f"Size:     {size_kb:.1f} KB\n\n"
            "KotOR MDL/MDX models are binary format.\n"
            "To edit: use GhostRigger-K1-K2 (standalone).\n"
            "To convert: use KotOR Tool or mdlops."
        )
        for i in range(self.editor_tabs.count()):
            w = self.editor_tabs.widget(i)
            if hasattr(w, "_set_detail_text"):
                w._set_detail_text(summary)
                self.editor_tabs.setCurrentIndex(i)
                return
        self.log(summary)

    def _open_generic_asset(self, resref: str, ext: str, raw_data) -> None:
        """Dump raw bytes / text preview into the asset library detail panel."""
        if not raw_data:
            return
        try:
            preview = raw_data[:2000].decode("utf-8", errors="replace")
        except Exception:
            preview = repr(raw_data[:200])
        summary = f"Asset: {resref}{ext}  ({len(raw_data):,} bytes)\n\n{preview}"
        for i in range(self.editor_tabs.count()):
            w = self.editor_tabs.widget(i)
            if hasattr(w, "_set_detail_text"):
                w._set_detail_text(summary)
                self.editor_tabs.setCurrentIndex(i)
                return
        self.log(f"Asset {resref}{ext}: {len(raw_data):,} bytes")

    def _read_asset_from_rm(self, resref: str, ext: str) -> bytes | None:
        """Read raw bytes for resref+ext from the asset library's ResourceManager."""
        for i in range(self.editor_tabs.count()):
            w = self.editor_tabs.widget(i)
            rm = getattr(w, "_resource_manager", None)
            if rm is not None:
                try:
                    return rm.read(resref + ext)
                except Exception:
                    pass
        return None

    def _decompile_ncs_bytes(self, ncs_bytes: bytes, resref: str) -> str:
        """
        Decompile raw NCS bytes to NSS source using PyKotor.

        Tries three strategies in order:
          1. PyKotor NCSDecompiler (full NSS source)
          2. PyKotor NCSBinaryReader disassembly (low-level but readable)
          3. Plain hex-dump header + size stub
        Always returns a non-empty string.
        """
        if not ncs_bytes:
            return f"// {resref}.ncs — empty file\n"

        # ── Strategy 1 & 2: PyKotor ──────────────────────────────────────────
        try:
            from pykotor.resource.formats.ncs.ncs_auto import read_ncs      # type: ignore
            from pykotor.resource.formats.ncs.decompiler import NCSDecompiler  # type: ignore
            from pykotor.common.misc import Game as PyGame                  # type: ignore

            game_id = "K1"
            if self._game_dir:
                # Heuristic: K2 installs usually have "swkotor2" in the path
                if "swkotor2" in str(self._game_dir).lower() or "kotor2" in str(self._game_dir).lower():
                    game_id = "K2"
            game_enum = PyGame.K2 if game_id == "K2" else PyGame.K1

            ncs_obj = read_ncs(ncs_bytes)

            # Strategy 1 — full decompile
            try:
                src = NCSDecompiler(ncs_obj, game_enum).decompile()
                if src and src.strip():
                    self.log(f"  ✓ Decompiled {resref}.ncs ({len(ncs_bytes):,} bytes → {len(src):,} chars)")
                    return src
            except Exception as e:
                self.log(f"  ⚠ NCSDecompiler failed for {resref}: {e} — trying disassembly")

            # Strategy 2 — disassembly
            try:
                from pykotor.resource.formats.ncs.io_ncs import NCSBinaryReader  # type: ignore
                reader = NCSBinaryReader(ncs_bytes)
                ncs_data = reader.load()
                lines = [f"// {resref}.ncs — disassembly ({len(ncs_bytes):,} bytes)", ""]
                for i, instr in enumerate(ncs_data.instructions):
                    lines.append(f"{i:4d}  {instr.ins_type.name:<20} {' '.join(str(a) for a in instr.args)}")
                self.log(f"  ✓ Disassembled {resref}.ncs ({len(ncs_data.instructions)} instructions)")
                return "\n".join(lines)
            except Exception as e:
                self.log(f"  ⚠ NCS disassembly failed for {resref}: {e}")

        except ImportError:
            self.log(f"  ⚠ PyKotor not available — cannot decompile {resref}.ncs")
        except Exception as e:
            self.log(f"  ⚠ Decompile error for {resref}: {e}")

        # ── Strategy 3: stub ──────────────────────────────────────────────────
        header = ncs_bytes[:8].hex(" ") if len(ncs_bytes) >= 8 else ncs_bytes.hex(" ")
        return (
            f"// {resref}.ncs — could not decompile\n"
            f"// Size: {len(ncs_bytes):,} bytes\n"
            f"// Header: {header}\n"
            f"//\n"
            f"// To decompile manually, use the MCP tool:\n"
            f"//   decompileScript({{resref: \"{resref}\", game: \"K1\"}})\n"
        )

    def open_tlk_editor(self):
        def _make():
            w = TLKEditorWidget()
            # Auto-load game dialog.tlk if game dir is set
            if self._game_dir and self._game_dir.exists():
                w.set_game_dir(self._game_dir)
                tlk_path = self._game_dir / "dialog.tlk"
                if tlk_path.exists():
                    w.load_tlk_from_path(tlk_path)
            self._tlk_widget = w   # store ref for IPC jump_to_strref
            return w
        self._find_or_open_tab("📖 TLK Editor", _make)

    def open_journal_editor(self, journal=None):
        """Open (or focus) the Journal (.jrl) editor tab."""
        from ghostscripter.core.models.journal import JournalFile, create_quest_journal
        def _make():
            jrl = journal or create_quest_journal("K_JOURNAL", "Main Quest")
            w = JournalEditorWidget(journal=jrl)
            w.journal_modified.connect(
                lambda: self.log("📝 Journal modified (unsaved)")
            )
            if self._game_dir:
                w.set_game_dir(self._game_dir)
            return w
        self._find_or_open_tab("📖 Journal Editor", _make)

    def open_erf_packer(self):
        def _make():
            w = ERFPackerWidget()
            if self._game_dir and self._game_dir.exists():
                w.set_game_dir(self._game_dir)
            return w
        self._find_or_open_tab("📦 ERF Packer", _make)

    # ── Export ────────────────────────────────────────────────

    def export_override(self):
        if not self.current_project:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Select KotOR installation folder")
        if not folder:
            return
        self.log(f"→ Exporting to override: {folder}/override/…")
        try:
            exporter = OverrideExporter()
            result = exporter.export(
                self.current_project,
                Path(folder),
            )
            if result.success:
                self.log(f"✓ {result.message}")
                for f in result.files_exported:
                    self.log(f"  • {f}")
                if self._db:
                    self._db.log_export(
                        self.current_project.project_id,
                        "override",
                        str(result.output_path),
                        len(result.files_exported),
                        True,
                    )
                QMessageBox.information(self, "Export Complete", result.message)
            else:
                self.log(f"✗ Export failed: {result.message}")
                for err in result.errors:
                    self.log(f"  ✗ {err}")
                QMessageBox.warning(self, "Export Issues", result.message)
        except Exception as e:
            self.log(f"✗ Export error: {e}")
            QMessageBox.critical(self, "Export Error", str(e))

    def export_erf(self):
        if not self.current_project:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return
        default_name = self.current_project.name.replace(" ", "_") + ".erf"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export ERF", default_name, "ERF Files (*.erf);;MOD Files (*.mod)"
        )
        if not path:
            return
        file_type = "MOD " if path.endswith(".mod") else "ERF "
        self.log(f"→ Building ERF archive: {path}…")
        try:
            writer = ERFWriter(file_type=file_type)
            result = writer.build_from_project(self.current_project, Path(path))
            if result.success:
                self.log(f"✓ {result.message}")
                for f in result.files_exported:
                    self.log(f"  • {f}")
                if self._db:
                    self._db.log_export(
                        self.current_project.project_id,
                        "erf",
                        path,
                        len(result.files_exported),
                        True,
                    )
                QMessageBox.information(self, "ERF Export Complete", result.message)
            else:
                self.log(f"✗ ERF export failed: {result.message}")
                QMessageBox.warning(self, "ERF Export Failed", result.message)
        except Exception as e:
            self.log(f"✗ ERF error: {e}")
            QMessageBox.critical(self, "ERF Error", str(e))

    def export_dlg(self):
        """Export all open dialogue files as GFF/DLG binary."""
        if not self.current_project:
            QMessageBox.warning(self, "No Project", "Please open a project first.")
            return
        if not self.current_project.dialogues:
            QMessageBox.information(self, "No Dialogues",
                                     "No dialogues in this project.")
            return
        exporter = DLGExporter()
        game = getattr(self.current_project, "target_game", "K1")
        exported = 0
        for dlg in self.current_project.dialogues:
            if dlg.file_path:
                try:
                    data = exporter.export(dlg, target_game=game)
                    with open(dlg.file_path, "wb") as f:
                        f.write(data)
                    exported += 1
                    self.log(f"  ✓ DLG: {dlg.file_path.name}")
                except Exception as e:
                    self.log(f"  ✗ DLG {dlg.name}: {e}")
        self.log(f"✓ Exported {exported} DLG file(s).")

    # ── Project Tree ──────────────────────────────────────────

    def _refresh_project_tree(self):
        """Schedule a tree rebuild; coalesces rapid back-to-back calls."""
        self._tree_refresh_timer.start()   # restarts if already running

    def _do_refresh_project_tree(self):
        """Actual tree rebuild — called at most once per 120 ms."""
        self.project_tree.setUpdatesEnabled(False)
        self.project_tree.clear()
        if not self.current_project:
            root = QTreeWidgetItem(["No project loaded"])
            root.setForeground(0, QColor("#666666"))
            self.project_tree.addTopLevelItem(root)
            self.project_tree.setUpdatesEnabled(True)
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

        self.project_tree.setUpdatesEnabled(True)

    def _on_tree_item_double_clicked(self, item, col):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, obj = data
        if kind == "script":
            editor = ScriptEditorWidget(script=obj, project=self.current_project)
            if self._game_dir:
                editor.set_game_dir(self._game_dir)
            idx = self.editor_tabs.addTab(editor, f"✎ {obj.name}.nss")
            self.editor_tabs.setCurrentIndex(idx)
        elif kind == "quest":
            editor = QuestBuilderWidget(quest=obj, project=self.current_project)
            idx = self.editor_tabs.addTab(editor, f"⚔ {obj.quest_name}")
            self.editor_tabs.setCurrentIndex(idx)
        elif kind == "dialogue":
            editor = DialogueEditorWidget(dialogue=obj)
            if self._game_dir:
                editor.set_game_dir(self._game_dir)
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

    # ── IPC / GhostRigger ─────────────────────────────────────

    def _on_rigger_connected(self, version: str):
        self.log(f"🔗 GhostRigger connected (v{version})")
        self._update_status(f"GhostRigger v{version} connected")
        if hasattr(self, "rigger_status_label"):
            self.rigger_status_label.setText(f"GR: ✓ v{version}")
            self.rigger_status_label.setStyleSheet(
                "color:#4ec9b0; padding: 0 8px; font-size:8pt;"
                "border-left:1px solid rgba(255,255,255,0.2);"
            )

    def _on_rigger_disconnected(self):
        self.log("⚠ GhostRigger disconnected")
        if hasattr(self, "rigger_status_label"):
            self.rigger_status_label.setText("GR: ✗")
            self.rigger_status_label.setStyleSheet(
                "color:#f48771; padding: 0 8px; font-size:8pt;"
                "border-left:1px solid rgba(255,255,255,0.2);"
            )

    def _on_model_ready(self, payload):
        self.log(f"📦 Model ready from GhostRigger: {payload.model_name}")
        if payload.appearance_row >= 0:
            self.log(f"   Appearance row: {payload.appearance_row}")
        if self.current_project and payload.mdl_path:
            from ghostscripter.core.models.project import ModelReference
            model = ModelReference(
                name=payload.model_name,
                file_path=Path(payload.mdl_path),
            )
            self.current_project.models.append(model)
            self._refresh_project_tree()

    # ── Helpers ───────────────────────────────────────────────

    def log(self, message: str):
        """Append a message to the log panel (legacy / IPC bridge path)."""
        import logging as _log_mod
        _log = _log_mod.getLogger("ghostscripter.main_window")
        _log.info("%s", message)
        # Also keep the old direct-append path so it appears immediately
        if hasattr(self, "log_viewer"):
            self.log_viewer.append_text(message)

    def _clear_output(self):
        if hasattr(self, "log_viewer"):
            self.log_viewer._clear()

    def _open_log_file(self):
        """Open the active log file in the system default text viewer."""
        import subprocess, os
        try:
            from ghostscripter.utils.log_setup import get_log_path
            p = get_log_path()
            if p.exists():
                if sys.platform.startswith("win"):
                    os.startfile(str(p))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(p)])
                else:
                    subprocess.Popen(["xdg-open", str(p)])
            else:
                QMessageBox.information(self, "Log File",
                    f"Log file not found yet:\n{p}")
        except Exception as e:
            QMessageBox.warning(self, "Open Log", f"Could not open log file:\n{e}")

    def _update_status(self, message: str):
        self.status_label.setText(message)

    def update_status(self, message: str):
        """Public alias for _update_status."""
        self.status_label.setText(message)
        # If message contains game info, update game status
        if self._game_dir and hasattr(self, "game_status"):
            self.game_status.setText(f"🎮 {self._game_dir.name}")

    def _toggle_tutorial(self):
        """Show or hide the tutorial helper window (Help menu / F1 / ? button)."""
        instance = TutorialDialog._instance
        if instance is not None and instance.isVisible():
            instance.close()
            self._tutorial_action.setChecked(False)
        else:
            TutorialDialog.show_tutorial(self)
            self._tutorial_action.setChecked(True)
            # Keep the checkmark in sync when the user closes the window manually
            if TutorialDialog._instance is not None:
                try:
                    TutorialDialog._instance.destroyed.connect(
                        lambda: self._tutorial_action.setChecked(False)
                    )
                    TutorialDialog._instance.finished.connect(
                        lambda _: self._tutorial_action.setChecked(False)
                    )
                except Exception:
                    pass

    def show_tutorial_on_startup(self):
        """Called once after the main window is shown; opens tutorial if user opted in."""
        if TutorialDialog.should_show_on_startup():
            TutorialDialog.show_tutorial(self)
            self._tutorial_action.setChecked(True)
            if TutorialDialog._instance is not None:
                try:
                    TutorialDialog._instance.finished.connect(
                        lambda _: self._tutorial_action.setChecked(False)
                    )
                except Exception:
                    pass

    def closeEvent(self, event):
        """Clean up IPC services and DB on close."""
        self._ipc_drain_timer.stop()
        self._ipc_bridge.stop()
        self._ipc_server.stop()
        if self._db:
            self._db.close()
        super().closeEvent(event)

    # ── IPC event queue drain ────────────────────────────────────────────────

    def _drain_ipc_events(self) -> None:
        """Called every 100 ms — dispatch queued IPC events on the main thread."""
        from ghostscripter.ipc.ipc_server import drain_event_queue
        for kind, payload in drain_event_queue():
            try:
                if kind == "open_script":
                    self.ipc_open_script(
                        payload.get("resref", ""),
                        slot=payload.get("slot", ""),
                        object_tag=payload.get("object_tag", ""),
                        source=payload.get("source", ""),
                    )
                elif kind == "open_dlg":
                    self.ipc_open_dlg(
                        payload.get("resref", ""),
                        bytes_b64=payload.get("bytes_b64", ""),
                    )
                elif kind == "open_2da":
                    table = payload.get("table", "")
                    row   = payload.get("row", 0)
                    self.ipc_open_2da(table, row=row)
                elif kind == "open_tlk":
                    strref = payload.get("strref", 0)
                    self.ipc_open_tlk(strref=strref)
            except Exception as exc:
                self.log(f"⚠ IPC dispatch error ({kind}): {exc}")

    # ── IPC Handlers ─────────────────────────────────────────────────────────

    def ipc_open_script(self, resref: str, slot: str = "",
                         object_tag: str = "", source: str = "") -> None:
        """Open (or focus) a script editor tab for the given resref."""
        self.log(f"📨 IPC open_script: {resref} [slot={slot}, obj={object_tag}]")
        # Look for already-open tab
        for i in range(self.editor_tabs.count()):
            w = self.editor_tabs.widget(i)
            if isinstance(w, ScriptEditorWidget) and getattr(w, "_ipc_resref", "") == resref:
                self.editor_tabs.setCurrentIndex(i)
                self.activateWindow()
                self.raise_()
                return
        # Build or load script
        if source:
            script = ScriptFile(name=resref, source_code=source)
        else:
            # Try to find on disk in game Override or project scripts dir
            script = self._locate_script(resref) or ScriptFile(
                name=resref, source_code=make_void_main_template()
            )
        editor = ScriptEditorWidget(script=script, project=self.current_project)
        editor._ipc_resref = resref         # tag for later focus lookups
        editor._ipc_slot = slot
        editor._ipc_object_tag = object_tag
        if self._game_dir:
            editor.set_game_dir(self._game_dir)
        idx = self.editor_tabs.addTab(editor, f"✎ {resref}.nss")
        self.editor_tabs.setCurrentIndex(idx)
        self.activateWindow()
        self.raise_()

    def _locate_script(self, resref: str) -> "ScriptFile | None":
        """Try to find a .nss file by resref in the project or game dir."""
        candidates = []
        if self.current_project and self.current_project.script_dir:
            candidates.append(self.current_project.script_dir / f"{resref}.nss")
        if self._game_dir:
            candidates.append(self._game_dir / "Override" / f"{resref}.nss")
        for path in candidates:
            if path and path.exists():
                try:
                    src = path.read_text(encoding="utf-8", errors="replace")
                    sf = ScriptFile(name=resref, source_code=src)
                    sf.file_path = path
                    return sf
                except Exception:
                    pass
        return None

    def ipc_open_dlg(self, resref: str, bytes_b64: str = "") -> None:
        """Open a dialogue editor tab for the given resref."""
        self.log(f"📨 IPC open_dlg: {resref}")
        # Focus existing tab
        for i in range(self.editor_tabs.count()):
            w = self.editor_tabs.widget(i)
            if isinstance(w, DialogueEditorWidget) and getattr(w, "_ipc_resref", "") == resref:
                self.editor_tabs.setCurrentIndex(i)
                self.activateWindow()
                self.raise_()
                return
        # Load from bytes or disk
        from ghostscripter.core.models.dialogue import DialogueFile, create_simple_dialogue
        from ghostscripter.core.export.dlg_reader import DLGImporter
        dlg_file = None
        if bytes_b64:
            try:
                import base64
                raw = base64.b64decode(bytes_b64)
                importer = DLGImporter()
                dlg_file = importer.import_from_bytes(raw)
                dlg_file.name = resref
            except Exception as e:
                self.log(f"  ✗ IPC DLG decode: {e}")
        if not dlg_file:
            # Try disk
            candidates = []
            if self.current_project and self.current_project.dialogue_dir:
                candidates.append(self.current_project.dialogue_dir / f"{resref}.dlg")
            if self._game_dir:
                candidates.append(self._game_dir / "Override" / f"{resref}.dlg")
            for path in candidates:
                if path and path.exists():
                    try:
                        raw = path.read_bytes()
                        importer = DLGImporter()
                        dlg_file = importer.import_from_bytes(raw)
                        dlg_file.file_path = path
                        dlg_file.name = resref
                        break
                    except Exception:
                        pass
        if not dlg_file:
            dlg_file = create_simple_dialogue(resref, "npc_001")
        editor = DialogueEditorWidget(dialogue=dlg_file)
        editor._ipc_resref = resref
        if self._game_dir:
            editor.set_game_dir(self._game_dir)
        idx = self.editor_tabs.addTab(editor, f"🗨 {resref}.dlg")
        self.editor_tabs.setCurrentIndex(idx)
        self.activateWindow()
        self.raise_()

    def ipc_open_2da(self, table: str, row: int = 0) -> None:
        """Open/focus the 2DA manager and navigate to table[row]."""
        self.log(f"📨 IPC open_2da: {table}[{row}]")
        self.open_2da_manager()
        if self._twoda_widget and hasattr(self._twoda_widget, "select_file"):
            self._twoda_widget.select_file(table)
        if self._twoda_widget and hasattr(self._twoda_widget, "scroll_to_row"):
            self._twoda_widget.scroll_to_row(row)

    def ipc_open_tlk(self, strref: int = 0) -> None:
        """Open/focus the TLK editor and optionally jump to strref."""
        self.log(f"📨 IPC open_tlk: strref={strref}")
        self.open_tlk_editor()
        if hasattr(self, "_tlk_widget") and self._tlk_widget and strref:
            if hasattr(self._tlk_widget, "jump_to_strref"):
                self._tlk_widget.jump_to_strref(strref)

    def notify_script_compiled(self, resref: str, ncs_path: str = "",
                                slot: str = "", object_tag: str = "") -> None:
        """Called by ScriptEditorWidget after a successful compile."""
        self.log(f"→ Notifying GModular: {resref}.ncs compiled")
        ok, err = _gm_client.notify_script_compiled(resref, slot, object_tag)
        if ok:
            if hasattr(self, "gmodular_status_label"):
                self.gmodular_status_label.setText("GM: ✓")
                self.gmodular_status_label.setStyleSheet(
                    "color:#4ec9b0; padding: 0 8px; font-size:8pt;"
                    "border-left:1px solid rgba(255,255,255,0.2);"
                )
        else:
            self.log(f"  GModular not reachable: {err}")

    # ── IPC Menu helpers ─────────────────────────────────────────────────────

    def _show_ipc_status(self):
        rigger_status = "Connected" if self._ipc_bridge.is_connected else "Disconnected"
        from ghostscripter.ipc.ipc_server import GHOSTSCRIPTER_PORT as SP
        from ghostscripter.ipc.ghostrigger_bridge import GHOSTRIGGER_PORT as RP
        from ghostscripter.ipc.gmodular_client import GMODULAR_PORT as GP
        ok_gm, _ = _gm_client.ping_gmodular()
        gmod_status = "Connected" if ok_gm else "Disconnected"
        QMessageBox.information(self, "GhostWorks IPC Status",
            f"<b>GhostWorks Pipeline IPC (v1.0)</b><br><br>"
            f"GhostRigger  (port {RP}) : <b>{rigger_status}</b><br>"
            f"GhostScripter (port {SP}): <b>Listening</b><br>"
            f"GModular     (port {GP}) : <b>{gmod_status}</b><br><br>"
            "To enable: launch GhostRigger-K1-K2 and/or GModular."
        )

    def _ping_ghostrigger(self):
        ver = self._ipc_bridge.get_rigger_version()
        if ver:
            QMessageBox.information(self, "GhostRigger Ping",
                f"GhostRigger responded: v{ver}")
        else:
            QMessageBox.warning(self, "GhostRigger Ping",
                "No response from GhostRigger on port 7001.\n"
                "Make sure GhostRigger-K1-K2 is running.")

    def _ping_gmodular(self):
        ok, _ = _gm_client.ping_gmodular()
        if ok:
            QMessageBox.information(self, "GModular Ping", "GModular is running.")
        else:
            QMessageBox.warning(self, "GModular Ping",
                "No response from GModular on port 7003.\n"
                "Make sure GModular is running.")

    def _show_about(self):
        QMessageBox.about(self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b><br>Version {APP_VERSION}<br><br>"
            f"All-in-one IDE for KotOR 1 &amp; 2 TSL modding.<br><br>"
            f"GPL-3.0 License<br>"
            f"Credits: KotOR community, xoreos-tools, Fred Tetra, TK102, Cortisol")


