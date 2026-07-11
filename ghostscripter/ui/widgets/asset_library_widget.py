"""
GhostScripter-K1-K2 — Asset Library Widget
==========================================
Shows project assets AND (when game dir is set) game assets extracted
from the installed KotOR KEY/BIF/RIM archives via ResourceManager.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from qtpy.QtCore import Qt, QThread, Signal
from qtpy.QtGui import QColor, QFont
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QTreeWidget, QTreeWidgetItem, QListWidget, QListWidgetItem,
    QLineEdit, QTabWidget, QComboBox, QGroupBox, QFormLayout,
    QTextEdit, QFrame, QMessageBox, QFileDialog, QInputDialog,
    QPlainTextEdit, QProgressBar, QSizePolicy,
)

from ghostscripter.core.models.script import (
    ScriptFile,
    make_starting_conditional_template,
    make_void_main_template,
)
from ghostscripter.core.models.quest import QuestDefinition
from ghostscripter.core.models.dialogue import DialogueFile


# ── Background worker for ResourceManager loading ────────────────────────────

class _GameAssetLoader(QThread):
    """Loads game assets in the background so the UI stays responsive."""
    finished = Signal(dict, object)   # emits ({ext: [name, ...], ...}, rm)
    error    = Signal(str)

    def __init__(self, game_dir: Path, parent=None):
        super().__init__(parent)
        self._game_dir = game_dir

    def run(self):
        try:
            from ghostscripter.core.resource_manager.resource_manager import ResourceManager
            rm = ResourceManager()
            rm.load_game(Path(self._game_dir))
            result = {}
            for ext in (".dlg", ".nss", ".2da", ".ncs", ".mdl", ".tga", ".tpc",
                        ".uti", ".utc", ".utp", ".utt", ".utm", ".uts", ".utw",
                        ".jrl"):
                entries = rm.list_by_type(ext)
                result[ext] = sorted(set(
                    e.resref + ext for e in entries
                ), key=str.lower)
            self.finished.emit(result, rm)
        except Exception as exc:
            self.error.emit(str(exc))


class AssetLibraryWidget(QWidget):
    # Emitted when the user double-clicks a game asset that should open in an editor.
    # Args: resref (str), ext (str, e.g. '.dlg'), raw_data (bytes or None)
    open_asset_requested = Signal(str, str, object)

    def __init__(self, project=None, parent=None, game_dir=None,
                 target_game: str | None = None):
        super().__init__(parent)
        self.project = project
        self._target_game = self._normalise_game(target_game)
        # Always store as Path so .exists() calls and Path comparisons work correctly
        self._game_dir: Path | None = Path(game_dir) if game_dir else None
        self._game_assets: dict = {}   # ext -> [filename, ...]
        self._resource_manager = None  # ResourceManager instance (set after game load)
        self._loader: _GameAssetLoader | None = None
        self._setup_ui()
        if project:
            self._populate(project)
        if game_dir and Path(game_dir).exists():
            self._load_game_assets(Path(game_dir))

    def set_game_dir(self, game_dir) -> None:
        """Receive the KotOR game directory from the main window."""
        gd = Path(game_dir) if game_dir else None
        if gd == self._game_dir:
            return
        self._game_dir = gd
        if gd and gd.exists():
            self._load_game_assets(gd)

    @staticmethod
    def _normalise_game(game: str | None) -> str:
        """Return a supported game identifier without inventing a third mode."""
        return "K2" if str(game).upper() == "K2" else "K1"

    def set_target_game(self, game: str) -> None:
        """Update the non-project game context supplied by the main window."""
        self._target_game = self._normalise_game(game)

    def _current_target_game(self) -> str:
        """Use the live project target when available, otherwise the UI context."""
        if self.project is not None:
            project_game = getattr(self.project, "target_game", None)
            if project_game:
                return self._normalise_game(project_game)
        return self._target_game

    # ── Game asset loading ────────────────────────────────────

    def _load_game_assets(self, game_dir: Path):
        """Kick off background ResourceManager scan."""
        if self._loader and self._loader.isRunning():
            self._loader.terminate()
            self._loader.wait()

        self._set_game_loading(True)
        self._loader = _GameAssetLoader(game_dir, self)
        self._loader.finished.connect(self._on_game_assets_loaded)
        self._loader.error.connect(self._on_game_assets_error)
        self._loader.start()

    def _set_game_loading(self, loading: bool):
        if loading:
            self.game_status_label.setText("⏳ Loading game assets…")
            self.game_status_label.setStyleSheet("color:#dcdcaa; font-size:8pt; padding:2px 8px;")
        else:
            self.game_status_label.setText("")

    def _on_game_assets_loaded(self, assets: dict, rm=None):
        self._game_assets = assets
        if rm is not None:
            self._resource_manager = rm
        self._set_game_loading(False)
        total = sum(len(v) for v in assets.values())
        self.game_status_label.setText(
            f"✓ {total:,} game assets loaded from: {self._game_dir}"
        )
        self.game_status_label.setStyleSheet("color:#4ec9b0; font-size:8pt; padding:2px 8px;")
        self._populate_game_asset_tab()

    def _on_game_assets_error(self, msg: str):
        self._set_game_loading(False)
        self.game_status_label.setText(f"⚠ Could not load game assets: {msg}")
        self.game_status_label.setStyleSheet("color:#f48771; font-size:8pt; padding:2px 8px;")

    def _populate_game_asset_tab(self):
        """Fill the 'Game Assets' tree with everything from ResourceManager."""
        self.game_tree.clear()

        # Type display info: (label, icon, color)
        type_meta = {
            ".dlg":  ("Dialogues (.dlg)",   "🗨", "#4ec9b0"),
            ".nss":  ("Scripts (.nss)",      "📜", "#dcdcaa"),
            ".2da":  ("2DA Tables (.2da)",   "📊", "#9cdcfe"),
            ".ncs":  ("Compiled Scripts",    "⚙", "#858585"),
            ".mdl":  ("Models (.mdl)",       "◉", "#ce9178"),
            ".tga":  ("Textures (.tga)",     "🖼", "#c586c0"),
            ".tpc":  ("Textures (.tpc)",     "🖼", "#c586c0"),
            ".uti":  ("Items (.uti)",        "⚔", "#569cd6"),
            ".utc":  ("Creatures (.utc)",    "👤", "#f48771"),
            ".utp":  ("Placeables (.utp)",   "🏛", "#9cdcfe"),
            ".utt":  ("Triggers (.utt)",     "⚡", "#dcdcaa"),
            ".utm":  ("Merchants (.utm)",    "🏪", "#4ec9b0"),
            ".uts":  ("Sounds (.uts)",       "🔊", "#ce9178"),
            ".utw":  ("Waypoints (.utw)",    "📍", "#569cd6"),
            ".jrl":  ("Journals (.jrl)",     "📖", "#c586c0"),
        }

        for ext, (label, icon, color) in type_meta.items():
            names = self._game_assets.get(ext, [])
            if not names:
                continue
            cat = QTreeWidgetItem([f"{icon} {label}  ({len(names):,})"])
            cat.setForeground(0, QColor(color))
            cat.setFont(0, QFont("Segoe UI", 9, QFont.Bold))
            for name in names:
                # name is the full filename e.g. "kor35_utharwynn.dlg"
                # Strip the extension to get the bare resref for rm.read() calls
                resref = name[: -len(ext)] if name.lower().endswith(ext) else name
                item = QTreeWidgetItem([name])
                item.setForeground(0, QColor("#cccccc"))
                item.setData(0, Qt.UserRole, {"name": resref, "ext": ext})
                cat.addChild(item)
            self.game_tree.addTopLevelItem(cat)

        # Apply current filter
        ftext = self.game_filter.text().strip()
        if ftext:
            self._filter_game_tree(ftext)

    # ── UI setup ─────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar / search bar
        tb = self._build_toolbar()
        layout.addWidget(tb)

        # Game asset status bar
        self.game_status_label = QLabel("")
        self.game_status_label.setStyleSheet("color:#4ec9b0; font-size:8pt; padding:2px 8px;")
        self.game_status_label.setWordWrap(True)
        layout.addWidget(self.game_status_label)

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
        self.asset_tabs.addTab(self._build_game_assets_tab(), "🎮 Game Assets")
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
        self.type_filter.addItems(["All Types", "Game Assets", "Scripts", "Quests", "Dialogues", "Models"])
        self.type_filter.setFixedWidth(130)
        self.type_filter.setStyleSheet("""
            QComboBox { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                        border-radius:3px; padding:3px 8px; }
        """)
        self.type_filter.currentTextChanged.connect(self._on_type_filter)
        lay.addWidget(self.type_filter)

        lay.addStretch()

        refresh_btn = QPushButton("⟳ Refresh")
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

    def _build_game_assets_tab(self) -> QWidget:
        """Tab showing all assets found in the KotOR game installation."""
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Filter bar
        filter_bar = QWidget()
        filter_bar.setStyleSheet("background:#252526; border-bottom:1px solid #3c3c3c;")
        fb_lay = QHBoxLayout(filter_bar)
        fb_lay.setContentsMargins(6, 3, 6, 3)
        fb_lay.setSpacing(4)
        self.game_filter = QLineEdit()
        self.game_filter.setPlaceholderText("Filter game assets…")
        self.game_filter.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            " border-radius:3px; padding:2px 6px; }"
        )
        self.game_filter.textChanged.connect(self._filter_game_tree)
        fb_lay.addWidget(QLabel("Filter:"))
        fb_lay.addWidget(self.game_filter, 1)
        reload_btn = QPushButton("⟳ Reload")
        reload_btn.setFixedHeight(22)
        reload_btn.setStyleSheet(
            "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            " border-radius:3px; padding:1px 6px; font-size:8pt; }"
            "QPushButton:hover { background:#505050; }"
        )
        reload_btn.clicked.connect(self._reload_game_assets)
        fb_lay.addWidget(reload_btn)
        lay.addWidget(filter_bar)

        self.game_tree = QTreeWidget()
        self.game_tree.setHeaderHidden(True)
        self.game_tree.setStyleSheet(self._tree_style())
        self.game_tree.itemDoubleClicked.connect(self._on_game_asset_double_click)
        self.game_tree.itemClicked.connect(self._on_game_asset_clicked)
        lay.addWidget(self.game_tree)

        # Placeholder when no game is loaded
        self.game_placeholder = QLabel(
            "No game directory set.\n\n"
            "Use File → Set KotOR Game Directory… to load game assets.\n\n"
            "Once set, all dialogues, scripts, 2DA tables, textures,\n"
            "items, creatures, and placeables will appear here."
        )
        self.game_placeholder.setAlignment(Qt.AlignCenter)
        self.game_placeholder.setStyleSheet(
            "color:#666666; font-size:9pt; padding:20px;"
        )
        self.game_placeholder.setWordWrap(True)
        lay.addWidget(self.game_placeholder)
        return widget

    def _build_scripts_tab(self) -> QWidget:
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

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
        lay.setSpacing(0)

        action = self._mini_action_bar([
            ("Import Model", self._import_model),
            ("Scan Folder…", self._scan_folder_for_models),
            ("Edit in GhostRigger", self._launch_ghostrigger),
        ])
        lay.addWidget(action)

        # Filter bar for the models list
        filter_bar = QWidget()
        filter_bar.setStyleSheet("background:#252526; border-bottom:1px solid #3c3c3c;")
        fb_lay = QHBoxLayout(filter_bar)
        fb_lay.setContentsMargins(6, 3, 6, 3)
        fb_lay.setSpacing(4)
        self.model_filter = QLineEdit()
        self.model_filter.setPlaceholderText("Filter models…")
        self.model_filter.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            " border-radius:3px; padding:2px 6px; }"
        )
        self.model_filter.textChanged.connect(self._filter_models)
        fb_lay.addWidget(QLabel("Filter:"))
        fb_lay.addWidget(self.model_filter, 1)
        lay.addWidget(filter_bar)

        self.models_list = QListWidget()
        self.models_list.setStyleSheet(self._list_style())
        self.models_list.itemClicked.connect(self._on_model_clicked)
        self.models_list.setToolTip("Double-click a model to view details")
        lay.addWidget(self.models_list, 1)

        # Info banner — explains how to get models
        self.models_info = QLabel(
            "Tip: Use 'Scan Folder…' to find extracted MDL/MDX files in your project "
            "or override folder. Models inside game BIF archives require extraction "
            "first (use xoreos-tools, KotOR Tool, or Extract game resources)."
        )
        self.models_info.setStyleSheet(
            "color:#666666; font-size:8pt; padding:6px 8px; "
            "background:#1e1e1e; border-top:1px solid #3c3c3c;"
        )
        self.models_info.setWordWrap(True)
        lay.addWidget(self.models_info)
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
            ("Greeting Dialogue (2 nodes)", "dialogue_greeting"),
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
        from qtpy.QtWidgets import QStackedWidget, QScrollArea
        from qtpy.QtCore import Qt as _Qt

        panel = QWidget()
        panel.setStyleSheet("background:#252526;")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        header = QLabel("Details")
        header.setStyleSheet("background:#2d2d30; color:#cccccc; font-weight:bold; "
                              "padding:5px 8px; border-bottom:1px solid #3c3c3c;")
        lay.addWidget(header)

        # Stacked widget: page 0 = text detail, page 1 = image preview
        self._detail_stack = QStackedWidget()

        self.detail_text = QPlainTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setObjectName("outputConsole")
        self.detail_text.setPlaceholderText("Select an asset to view details…")
        self._detail_stack.addWidget(self.detail_text)  # page 0

        # Texture preview page
        preview_scroll = QScrollArea()
        preview_scroll.setWidgetResizable(True)
        preview_scroll.setStyleSheet("background:#1e1e1e; border:none;")
        preview_container = QWidget()
        preview_container.setStyleSheet("background:#1e1e1e;")
        preview_vlay = QVBoxLayout(preview_container)
        preview_vlay.setAlignment(_Qt.AlignCenter)

        self._texture_preview_label = QLabel()
        self._texture_preview_label.setAlignment(_Qt.AlignCenter)
        self._texture_preview_label.setStyleSheet("background:#1e1e1e; color:#cccccc;")
        self._texture_preview_label.setWordWrap(True)
        preview_vlay.addWidget(self._texture_preview_label)

        self._texture_info_label = QLabel()
        self._texture_info_label.setAlignment(_Qt.AlignCenter)
        self._texture_info_label.setStyleSheet(
            "color:#888888; font-size:8pt; padding:4px;"
        )
        preview_vlay.addWidget(self._texture_info_label)

        back_btn = QPushButton("← Back to Details")
        back_btn.setFixedHeight(22)
        back_btn.setStyleSheet(
            "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            " border-radius:3px; padding:2px 8px; font-size:8pt; }"
            "QPushButton:hover { background:#505050; }"
        )
        back_btn.clicked.connect(lambda: self._detail_stack.setCurrentIndex(0))
        preview_vlay.addWidget(back_btn, 0, _Qt.AlignCenter)
        preview_scroll.setWidget(preview_container)
        self._detail_stack.addWidget(preview_scroll)  # page 1

        lay.addWidget(self._detail_stack)
        return panel

    # ------------------------------------------------------------------
    # Internal helpers for texture decoding
    # ------------------------------------------------------------------

    @staticmethod
    def _pil_to_qimage(pil_img) -> "QImage | None":
        """Convert a PIL Image (any mode) to a QImage.

        Uses PIL tobytes() → QImage.Format_RGBA8888 to avoid any
        intermediate file I/O.  Returns None on failure.
        """
        try:
            from qtpy.QtGui import QImage
            rgba = pil_img.convert("RGBA")
            raw  = rgba.tobytes("raw", "RGBA")
            # QImage does NOT own the Python buffer, so .copy() detaches it.
            qimg = QImage(raw, rgba.width, rgba.height, QImage.Format_RGBA8888)
            return qimg.copy()
        except Exception:
            return None

    @staticmethod
    def _decode_tga_with_pil(data: bytes) -> "QImage | None":
        """Decode a KotOR TGA file using Pillow.

        Qt's TGA handler only accepts TrueVision-2.0 files (those with
        the 'TRUEVISION-XFILE' footer).  KotOR TGA files are plain
        TGA-1 files and are rejected by Qt with the message
        'Image type (non-TrueVision 2.0) not supported'.
        Pillow handles both TGA variants correctly.
        """
        try:
            import io as _io
            from PIL import Image as _PIL
            pil_img = _PIL.open(_io.BytesIO(data))
            return AssetLibraryWidget._pil_to_qimage(pil_img)
        except Exception:
            return None

    def _show_texture_preview(self, name: str, data: bytes, ext: str = ".tga"):
        """Display a TGA, TPC, or TPA texture in the detail preview panel.

        Decoding strategy
        -----------------
        .tga / .png / .bmp  — Pillow (PIL) decode → QImage.
                              Qt's native TGA handler only supports
                              TrueVision-2.0 TGA files; KotOR TGA files
                              are plain TGA-1 and are rejected.  Pillow
                              handles both, so it is always used here.
        .tpc / .tpa         — PyKotor read_tpc() → TPCMipmap.to_qimage().
                              Falls back to Pillow if to_qimage() fails.
        """
        from qtpy.QtGui import QPixmap, QImage
        from qtpy.QtCore import Qt as _Qt

        pixmap     = None
        extra_info = ""
        _ext = ext.lower()

        try:
            if _ext in (".tga", ".png", ".bmp"):
                # --- Pillow path (handles KotOR TGA-1 files correctly) -------
                pixmap = None
                qimg = self._decode_tga_with_pil(data)
                if qimg and not qimg.isNull():
                    pixmap = QPixmap.fromImage(qimg)

                # Fallback: try Qt native (works for PNG/BMP and TV2.0 TGA)
                if pixmap is None:
                    img = QImage()
                    if img.loadFromData(data):
                        pixmap = QPixmap.fromImage(img)

            elif _ext in (".tpc", ".tpa"):
                # --- PyKotor path (KotOR proprietary texture) ----------------
                try:
                    import importlib.util
                    if importlib.util.find_spec("pykotor"):
                        from pykotor.resource.formats.tpc import read_tpc
                        tpc  = read_tpc(data)
                        w, h = tpc.dimensions()
                        layer_count = len(tpc.layers)
                        mip  = tpc.get(0, 0)      # first layer, first mipmap
                        qimg = mip.to_qimage()    # direct QImage — no file I/O
                        if qimg and not qimg.isNull():
                            pixmap = QPixmap.fromImage(qimg)
                        is_anim = tpc.is_animated()
                        fmt     = tpc.format()
                        extra_info = (
                            f"  Format: {fmt.name if hasattr(fmt, 'name') else fmt}"
                            + (f"  Layers: {layer_count}" if layer_count > 1 else "")
                            + ("  [animated]" if is_anim else "")
                        )
                except Exception:
                    pass   # fall through to PIL fallback

                # PIL fallback for TPC (in case to_qimage fails)
                if pixmap is None:
                    qimg = self._decode_tga_with_pil(data)
                    if qimg and not qimg.isNull():
                        pixmap = QPixmap.fromImage(qimg)

                if pixmap is None:
                    ext_upper = _ext.upper().lstrip(".")
                    self._texture_info_label.setText(
                        f"{ext_upper} texture: {name}\n"
                        f"Size: {len(data):,} bytes\n\n"
                        "pykotor could not decode this texture.\n"
                        "Try: pip install pykotor"
                    )
                    self._texture_preview_label.setText(
                        f"🖼  {name}\n({ext_upper} decode failed)"
                    )
                    self._detail_stack.setCurrentIndex(1)
                    return
        except Exception:
            pass

        if pixmap and not pixmap.isNull():
            # Scale to fit the panel (max 512 × 512 so large textures still show)
            max_side = 512
            scaled = pixmap.scaled(
                max_side, max_side, _Qt.KeepAspectRatio, _Qt.SmoothTransformation
            )
            self._texture_preview_label.setPixmap(scaled)
            self._texture_info_label.setText(
                f"{name}  •  {pixmap.width()}×{pixmap.height()} px"
                f"  •  {len(data):,} bytes{extra_info}"
            )
        else:
            self._texture_preview_label.setText(f"🖼  {name}\n(preview not available)")
            self._texture_info_label.setText(f"{len(data):,} bytes  •  {ext}")

        self._detail_stack.setCurrentIndex(1)

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

    def _set_detail_text(self, text: str):
        """Switch to the text detail page and set its content."""
        self._detail_stack.setCurrentIndex(0)
        self.detail_text.setPlainText(text)

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

        # Models — show project-registered models AND auto-scan project dir
        self.models_list.clear()
        seen_names: set = set()
        for m in project.models:
            item = QListWidgetItem(f"◉  {m.name}.mdl")
            item.setData(Qt.UserRole, {"path": str(getattr(m, "file_path", "")), "name": m.name})
            item.setForeground(QColor("#ce9178"))
            self.models_list.addItem(item)
            seen_names.add(m.name.lower())
        # Auto-scan project root for extracted MDL/MDX files not already listed
        if hasattr(project, "root_directory") and project.root_directory:
            root = Path(project.root_directory)
            if root.exists():
                self._scan_dir_for_models(root, seen_names, project_scan=True)

    # ── Game asset tab actions ────────────────────────────────

    def _reload_game_assets(self):
        if self._game_dir and Path(self._game_dir).exists():
            self._load_game_assets(Path(self._game_dir))
        else:
            self.game_status_label.setText("⚠ No game directory set. Use File → Set KotOR Game Directory…")
            self.game_status_label.setStyleSheet("color:#f48771; font-size:8pt; padding:2px 8px;")

    def _filter_game_tree(self, text: str):
        t = text.lower()
        for i in range(self.game_tree.topLevelItemCount()):
            cat = self.game_tree.topLevelItem(i)
            visible_children = 0
            for j in range(cat.childCount()):
                child = cat.child(j)
                matches = not t or t in child.text(0).lower()
                child.setHidden(not matches)
                if matches:
                    visible_children += 1
            # Hide entire category if no children match
            cat.setHidden(visible_children == 0)

    def _on_game_asset_clicked(self, item: "QTreeWidgetItem", col: int):
        data = item.data(0, Qt.UserRole)
        if not data or not isinstance(data, dict):
            return
        name = data.get("name", "")
        ext = data.get("ext", "")

        # For texture files, try to show a preview
        texture_exts = {".tga", ".tpc", ".png"}
        if ext.lower() in texture_exts:
            # Try to extract and preview the texture from the resource manager
            rm = getattr(self, "_resource_manager", None)
            if rm is not None:
                try:
                    raw = rm.read(name + ext)
                    if raw:
                        self._show_texture_preview(name + ext, raw, ext)
                        return
                except Exception:
                    pass

        # Default: show text info
        self._detail_stack.setCurrentIndex(0)
        self.detail_text.setPlainText(
            f"Name:  {name}\n"
            f"Type:  {ext} (game asset)\n\n"
            f"This asset is stored inside the game's BIF archives.\n"
            f"Double-click to open it in the appropriate editor.\n\n"
            f"Source: KotOR KEY/BIF archive"
        )

    def _on_game_asset_double_click(self, item: "QTreeWidgetItem", col: int):
        """Open the double-clicked game asset in the appropriate editor."""
        data = item.data(0, Qt.UserRole)
        if not data or not isinstance(data, dict):
            return
        name = data.get("name", "")
        ext  = data.get("ext", "").lower()
        if not name or not ext:
            return

        rm = getattr(self, "_resource_manager", None)

        # ── Texture files: show inline preview, don't open an editor ──────────
        texture_exts = {".tga", ".tpc", ".png"}
        if ext in texture_exts:
            if rm is not None:
                try:
                    raw = rm.read(name + ext)
                    if raw:
                        self._show_texture_preview(name + ext, raw, ext)
                        return
                except Exception:
                    pass
            # No RM or read failed — still emit so main window can try
            self.open_asset_requested.emit(name, ext, None)
            return

        # ── All other types: read bytes then emit to the main window ──────────
        raw_data: bytes | None = None
        if rm is not None:
            try:
                raw_data = rm.read(name + ext)
            except Exception:
                pass

        # Signal main window — it handles routing to the correct editor tab
        self.open_asset_requested.emit(name, ext, raw_data)

        # Give inline feedback if the resource couldn't be read
        if raw_data is None:
            self._detail_stack.setCurrentIndex(0)
            self.detail_text.setPlainText(
                f"Could not read '{name}{ext}' from the game archives.\n\n"
                "The resource manager may not be loaded yet, or the file is not "
                "present in the current game library.\n\n"
                "Try clicking '⟳ Reload' in the Game Assets tab."
            )


    # ── Actions ───────────────────────────────────────────────

    def _new_script(self):
        name, ok = QInputDialog.getText(self, "New Script", "Script name (without .nss):")
        if ok and name:
            script = ScriptFile(name=name, script_type="quest")
            if self.project:
                self.project.scripts.append(script)
                self._populate(self.project)
            self._set_detail_text(f"Created script: {name}.nss")

    def _open_script_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Script", "", "NWScript (*.nss)"
        )
        if path:
            self._set_detail_text(f"Opened: {path}")

    def _new_quest(self):
        name, ok = QInputDialog.getText(self, "New Quest", "Quest name:")
        if ok and name:
            from ghostscripter.core.models.quest import create_quest_from_template
            quest = create_quest_from_template(
                "SIMPLE_QUEST", name, self._current_target_game()
            )
            if self.project:
                self.project.quests.append(quest)
                self._populate(self.project)
                self._set_detail_text(
                    f"Created {quest.target_game} quest: {quest.quest_name}"
                )

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
            self._set_detail_text(f"Opened: {path}\n(DLG parser not yet connected)")

    def _import_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Model", "", "KotOR Model Files (*.mdl *.mdx);;All Files (*)"
        )
        if path:
            from ghostscripter.core.models.project import ModelReference
            model = ModelReference(name=Path(path).stem, file_path=Path(path))
            if self.project:
                self.project.models.append(model)
                self._populate(self.project)
            self._set_detail_text(
                f"Imported model: {Path(path).name}\n"
                f"Path: {path}\n"
                f"Size: {Path(path).stat().st_size:,} bytes"
            )

    def _scan_folder_for_models(self):
        """Scan a user-chosen folder for MDL/MDX files and populate the models list."""
        # Default start dir: project root → game dir → home
        start = str(Path.home())
        if self._game_dir and Path(self._game_dir).exists():
            start = str(self._game_dir)
        if self.project and hasattr(self.project, "root_directory") and self.project.root_directory:
            if Path(self.project.root_directory).exists():
                start = str(self.project.root_directory)

        folder = QFileDialog.getExistingDirectory(
            self, "Scan Folder for Extracted MDL/MDX Files", start
        )
        if not folder:
            return

        self.models_list.clear()
        seen: set = set()
        count = self._scan_dir_for_models(Path(folder), seen)
        if count == 0:
            self.models_info.setText(
                f"No MDL/MDX files found in:\n{folder}\n\n"
                "KotOR model files must be extracted from the game BIFs first.\n"
                "Use KotOR Tool, xoreos-tools, or Extract game resources to unpack them."
            )
        else:
            self.models_info.setText(
                f"Found {count} model file(s) in: {folder}"
            )

    def _scan_dir_for_models(self, folder: Path, seen: set, *, project_scan: bool = False) -> int:
        """Recursively scan folder for MDL/MDX files; add new ones to models_list. Returns count added."""
        extensions = {".mdl", ".mdx", ".tpc", ".txi"}
        count = 0
        try:
            # Non-recursive scan of top-level folder to keep it fast
            entries = sorted(folder.iterdir(), key=lambda p: p.name.lower())
            for p in entries:
                if p.is_file() and p.suffix.lower() in extensions:
                    key = p.name.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    icon = "◉" if p.suffix.lower() == ".mdl" else "◈"
                    size_kb = p.stat().st_size / 1024
                    label = f"{icon}  {p.name}  ({size_kb:.1f} KB)"
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, {"path": str(p), "name": p.stem})
                    item.setForeground(QColor("#ce9178" if p.suffix.lower() == ".mdl" else "#9cdcfe"))
                    if project_scan:
                        item.setToolTip(f"Auto-scanned from project folder:\n{p}")
                    else:
                        item.setToolTip(str(p))
                    self.models_list.addItem(item)
                    count += 1
        except PermissionError:
            pass
        return count

    def _on_model_clicked(self, item: "QListWidgetItem"):
        """Show model details in the detail panel."""
        data = item.data(Qt.UserRole)
        if not data:
            return
        path_str = data.get("path", "") if isinstance(data, dict) else str(getattr(data, "file_path", ""))
        name = data.get("name", item.text()) if isinstance(data, dict) else getattr(data, "name", "?")
        p = Path(path_str) if path_str else None
        lines = [f"Name:  {name}"]
        if p and p.exists():
            lines.append(f"File:  {p.name}")
            lines.append(f"Path:  {p}")
            lines.append(f"Size:  {p.stat().st_size:,} bytes  ({p.stat().st_size / 1024:.1f} KB)")
            lines.append(f"Type:  {p.suffix.upper().lstrip('.')} file")
            # Check for companion MDX
            mdx = p.with_suffix(".mdx")
            if p.suffix.lower() == ".mdl" and mdx.exists():
                lines.append(f"MDX:   {mdx.name} found ({mdx.stat().st_size / 1024:.1f} KB)")
        elif path_str:
            lines.append(f"Path:  {path_str}")
            lines.append("(file not found on disk)")
        self._set_detail_text("\n".join(lines))

    def _launch_ghostrigger(self):
        item = self.models_list.currentItem()
        data = item.data(Qt.UserRole) if item else None
        path_str = data.get("path", "") if isinstance(data, dict) else ""
        msg = (
            "Launch GhostRigger-K1-K2 to edit the selected model.\n\n"
            + (f"Selected: {path_str}\n\n" if path_str else "")
            + "IPC bridge will connect when GhostRigger is running.\n"
            "Use GhostRigger → File → Open to load the model there."
        )
        QMessageBox.information(self, "Open in GhostRigger", msg)

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
            self._set_detail_text(json.dumps(data.to_dict(), indent=2, default=str))

    def _on_quest_clicked(self, item):
        q = item.data(Qt.UserRole)
        if q and hasattr(q, "to_dict"):
            import json
            self._set_detail_text(json.dumps(q.to_dict(), indent=2, default=str))

    def _use_template(self, item):
        if not item:
            return
        key = item.data(Qt.UserRole)
        if not self.project:
            QMessageBox.warning(
                self,
                "Template",
                "Open or create a project before using an asset template.",
            )
            return

        if key in {"NPC_COMPANION_QUEST", "SIMPLE_QUEST", "BRANCHING_QUEST"}:
            name, ok = QInputDialog.getText(self, "Quest Template", "Quest name:")
            if not ok or not name.strip():
                return
            from ghostscripter.core.models.quest import create_quest_from_template
            asset = create_quest_from_template(
                key, name.strip(), self._current_target_game()
            )
            self.project.quests.append(asset)
            description = f"Created {asset.target_game} quest: {asset.quest_name}"
        elif key == "dialogue_greeting":
            name, ok = QInputDialog.getText(
                self, "Dialogue Template", "Dialogue name (without .dlg):"
            )
            if not ok or not name.strip():
                return
            from ghostscripter.core.models.dialogue import create_simple_dialogue
            asset = create_simple_dialogue(name.strip(), "npc_001")
            self.project.dialogues.append(asset)
            description = (
                f"Created dialogue: {asset.name}.dlg "
                f"({len(asset.entries) + len(asset.replies)} nodes)"
            )
        elif key in {"script_void_main", "script_conditional"}:
            name, ok = QInputDialog.getText(
                self, "Script Template", "Script name (without .nss):"
            )
            if not ok or not name.strip():
                return
            script_name = name.strip()
            if script_name.lower().endswith(".nss"):
                script_name = script_name[:-4]
            source = (
                make_void_main_template()
                if key == "script_void_main"
                else make_starting_conditional_template()
            )
            asset = ScriptFile(name=script_name, source_code=source)
            script_dir = getattr(self.project, "script_dir", None)
            if script_dir:
                asset.file_path = Path(script_dir) / f"{script_name}.nss"
            self.project.scripts.append(asset)
            description = f"Created script: {script_name}.nss"
        else:
            QMessageBox.warning(
                self, "Template", f"Unknown asset template: {key!r}"
            )
            return

        self._populate(self.project)
        self._set_detail_text(description)

    def _filter_models(self, text: str):
        """Filter models list by name."""
        t = text.lower()
        for i in range(self.models_list.count()):
            item = self.models_list.item(i)
            item.setHidden(bool(t and t not in item.text().lower()))

    def _filter_all(self, text: str):
        t = text.lower()
        for i in range(self.quests_list.count()):
            item = self.quests_list.item(i)
            item.setHidden(bool(t and t not in item.text().lower()))
        for i in range(self.dialogues_list.count()):
            item = self.dialogues_list.item(i)
            item.setHidden(bool(t and t not in item.text().lower()))
        for i in range(self.models_list.count()):
            item = self.models_list.item(i)
            item.setHidden(bool(t and t not in item.text().lower()))
        # Also filter game tree
        self._filter_game_tree(text)

    def _on_type_filter(self, text: str):
        tab_map = {
            "Game Assets": 0, "Scripts": 1, "Quests": 2,
            "Dialogues": 3, "Models": 4,
        }
        if text in tab_map:
            self.asset_tabs.setCurrentIndex(tab_map[text])

    def _refresh(self):
        if self.project:
            self._populate(self.project)
        if self._game_dir and Path(self._game_dir).exists():
            self._load_game_assets(Path(self._game_dir))
