"""
GhostScripter-K1-K2 — NSS Script Editor Widget
Full-featured NSS editor with:
  - Syntax highlighting (keywords, types, constants, functions, strings, comments)
  - Line numbers + current-line highlight
  - Real autocomplete popup from nwscript.nss (Ctrl+Space or typing)
  - Parameter signature tooltip after '('
  - Function reference panel (full DB from nwscript.nss, searchable)
  - Real compilation via bundled nwnnsscomp.exe
  - NCS decompilation: auto-detects DeNCS CLI (JAR), xoreos-tools ncsdecomp, or pykotor
  - Template insertion (void main / StartingConditional)
  - Compiler output console
  - Find/Replace bar (Ctrl+F / Ctrl+H)
  - Go-to-line dialog (Ctrl+G)
  - Cursor position indicator (line:col)
  - Auto-indent on Enter key
  - Bracket/brace matching highlight
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


from qtpy.QtCore import (
    Qt, QRect, QSize, Signal, QTimer, QStringListModel, QThread, QObject,
)
from qtpy.QtGui import (
    QColor, QFont, QSyntaxHighlighter, QTextCharFormat,
    QPainter, QTextCursor, QPalette, QKeySequence, QTextDocument,
)
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QPlainTextEdit,
    QLabel, QPushButton, QToolBar, QAction, QLineEdit, QTreeWidget,
    QTreeWidgetItem, QMessageBox, QFileDialog, QTabWidget,
    QTextEdit, QComboBox, QFrame, QCompleter, QShortcut,
    QListWidget, QListWidgetItem, QAbstractItemView,
    QToolTip, QInputDialog, QCheckBox,
    QDialog, QDialogButtonBox,
)

from ghostscripter.core.models.script import (
    ScriptFile, CompilationError,
    make_void_main_template, make_starting_conditional_template,
)
from ghostscripter.core.constants import (
    NWSCRIPT_KEYWORDS, NWSCRIPT_TYPES,
    COLOR_NSS_KEYWORD, COLOR_NSS_FUNCTION, COLOR_NSS_COMMENT,
    COLOR_NSS_STRING, COLOR_NSS_NUMBER, COLOR_NSS_TYPE, COLOR_NSS_CONSTANT,
)
from ghostscripter.core.nwscript.parser import get_nwscript_db, NWScriptDB


# ── Line Number Area ──────────────────────────────────────────

# ── Background NWScript DB Loader ─────────────────────────────

class _DBLoaderWorker(QObject):
    """
    Loads the NWScript function/constant database in a background QThread
    so the main thread is never blocked during parsing.
    """
    finished = Signal(object)   # emits NWScriptDB on success
    error    = Signal(str)      # emits error message on failure

    def __init__(self, game: str):
        super().__init__()
        self._game = game

    def run(self):
        try:
            from ghostscripter.core.nwscript.parser import get_nwscript_db
            db = get_nwscript_db(self._game)
            self.finished.emit(db)
        except Exception as e:
            self.error.emit(str(e))


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


# ── Autocomplete Popup ────────────────────────────────────────

class AutocompletePopup(QListWidget):
    """
    Floating popup list for autocomplete.
    Appears below the cursor when triggered by Ctrl+Space or typing.
    """
    item_selected = Signal(str)   # emits the chosen completion

    def __init__(self, parent=None):
        super().__init__(parent)
        # WA_ShowWithoutActivating keeps keyboard focus on the editor,
        # so typing/backspace always goes to the code editor, not the popup.
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet("""
            QListWidget {
                background:#1e2a3a; border:1px solid #0078d4;
                color:#cccccc; font-family:Consolas; font-size:9pt;
                padding:2px; outline:none;
            }
            QListWidget::item { padding:3px 8px; }
            QListWidget::item:selected { background:#094771; color:white; }
            QListWidget::item:hover   { background:#1a3a5e; }
        """)
        # Tall enough to show ~12 items; scrollbar appears automatically
        self.setMinimumHeight(40)
        self.setMaximumHeight(320)
        self.setMinimumWidth(280)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.itemActivated.connect(self._on_activated)
        self.itemClicked.connect(self._on_activated)

    def _on_activated(self, item: QListWidgetItem):
        self.item_selected.emit(item.text())
        self.hide()

    def populate(self, items: list[str]):
        self.clear()
        for text in items:
            self.addItem(text)
        if self.count():
            self.setCurrentRow(0)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            cur = self.currentItem()
            if cur:
                self.item_selected.emit(cur.text())
            self.hide()
        elif key == Qt.Key_Escape:
            self.hide()
        elif key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown):
            # Navigation within the popup list
            super().keyPressEvent(event)
        else:
            # All other keys (including Backspace, Delete, letters) go to the
            # parent editor so the user can keep typing/deleting normally.
            self.hide()
            if self.parent():
                self.parent().keyPressEvent(event)


# ── Code Editor ───────────────────────────────────────────────

class CodeEditor(QPlainTextEdit):
    """
    Plain-text code editor with:
    - Line numbers
    - Current-line highlight
    - Autocomplete integration (Ctrl+Space triggers popup)
    - Signature tooltip on '('
    - Auto-indent on Enter
    - Bracket/brace matching
    """

    cursor_position_changed = Signal(int, int)   # line, col

    autocomplete_requested = Signal(str)   # emits current word prefix
    signature_requested = Signal(str)      # emits function name before '('
    popup_navigate = Signal(int)           # +1 down / -1 up in popup
    popup_confirm = Signal()               # Tab/Enter confirms popup
    popup_hide = Signal()                  # Escape or space hides popup

    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()

        font = QFont("Consolas", 10)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setObjectName("scriptEditor")
        self.setTabStopDistance(28)

        # Autocomplete timer — fire 300 ms after last keystroke
        self._ac_timer = QTimer()
        self._ac_timer.setSingleShot(True)
        self._ac_timer.timeout.connect(self._trigger_autocomplete)
        self.textChanged.connect(self._on_text_changed)
        self.cursorPositionChanged.connect(self._emit_cursor_pos)

        # Bracket matching
        self._match_selections: list = []

    def _emit_cursor_pos(self):
        cursor = self.textCursor()
        line = cursor.blockNumber() + 1
        col  = cursor.positionInBlock() + 1
        self.cursor_position_changed.emit(line, col)

    def _match_brackets(self):
        """Highlight the bracket/brace pair under the cursor."""
        self.setExtraSelections(self._build_line_selection() + self._find_bracket_match())

    def _build_line_selection(self) -> list:
        """Return the current-line highlight extra selection."""
        extra = []
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor("#2d2d30"))
            sel.format.setProperty(0x100001, True)
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            extra.append(sel)
        return extra

    def _find_bracket_match(self) -> list:
        """Find and highlight matching bracket/brace/paren pair."""
        OPEN  = {'(': ')', '{': '}', '[': ']'}
        CLOSE = {')': '(', '}': '{', ']': '['}
        cursor = self.textCursor()
        doc    = self.document()
        pos    = cursor.position()
        text   = doc.toPlainText()
        n      = len(text)
        result = []
        match_format = QTextCharFormat()
        match_format.setBackground(QColor("#3a5a3a"))
        match_format.setForeground(QColor("#4ec9b0"))

        def make_sel(p):
            sel = QTextEdit.ExtraSelection()
            sel.format = match_format
            c = self.textCursor()
            c.setPosition(p)
            c.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
            sel.cursor = c
            return sel

        # Check char at cursor and just before it
        for check_pos in [pos, pos - 1]:
            if 0 <= check_pos < n:
                ch = text[check_pos]
                if ch in OPEN:
                    depth, i = 1, check_pos + 1
                    while i < n and depth:
                        if text[i] == ch:         depth += 1
                        elif text[i] == OPEN[ch]: depth -= 1
                        i += 1
                    if depth == 0:
                        result = [make_sel(check_pos), make_sel(i - 1)]
                        break
                elif ch in CLOSE:
                    depth, i = 1, check_pos - 1
                    while i >= 0 and depth:
                        if text[i] == ch:          depth += 1
                        elif text[i] == CLOSE[ch]: depth -= 1
                        i -= 1
                    if depth == 0:
                        result = [make_sel(i + 1), make_sel(check_pos)]
                        break
        return result

    # ── Line numbers ──────────────────────────────────────────

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 8 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(
                0, rect.y(), self.line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def highlight_current_line(self):
        self.setExtraSelections(self._build_line_selection() + self._find_bracket_match())

    def paint_line_numbers(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#1e1e1e"))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(
            self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        )
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#858585"))
                painter.setFont(self.font())
                painter.drawText(
                    0, top,
                    self.line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignRight, str(block_number + 1)
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    # ── Autocomplete integration ──────────────────────────────

    def _on_text_changed(self):
        """Schedule autocomplete check 300 ms after typing."""
        self._ac_timer.stop()
        self._ac_timer.start(300)

    def _trigger_autocomplete(self):
        prefix = self._current_word_prefix()
        if len(prefix) >= 3:
            self.autocomplete_requested.emit(prefix)

    def _current_word_prefix(self) -> str:
        """Return the identifier fragment to the left of the cursor."""
        cursor = self.textCursor()
        text = cursor.block().text()
        col = cursor.positionInBlock()
        # Walk left gathering identifier chars
        i = col
        while i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_"):
            i -= 1
        return text[i:col]

    def keyPressEvent(self, event):
        key = event.key()

        # Ctrl+Space → manual autocomplete trigger
        if key == Qt.Key_Space and event.modifiers() & Qt.ControlModifier:
            prefix = self._current_word_prefix()
            self.autocomplete_requested.emit(prefix or "")
            return

        # Escape → hide popup, don't insert anything
        if key == Qt.Key_Escape:
            self.popup_hide.emit()
            return

        # Tab / Enter → if popup visible, confirm selection; else normal
        if key in (Qt.Key_Tab, Qt.Key_Return, Qt.Key_Enter):
            self.popup_confirm.emit()
            # Only suppress Tab; let Enter pass through as a newline
            if key == Qt.Key_Tab:
                return

            # Auto-indent on Enter — replicate leading whitespace of current line
            if key in (Qt.Key_Return, Qt.Key_Enter):
                cursor = self.textCursor()
                line   = cursor.block().text()
                indent = len(line) - len(line.lstrip())
                # Extra indent after an opening brace
                stripped = line.rstrip()
                if stripped.endswith("{"):
                    indent += 4
                super().keyPressEvent(event)
                self.insertPlainText(" " * indent)
                return

        # Up/Down arrows → navigate popup if it's visible
        if key in (Qt.Key_Up, Qt.Key_Down):
            self.popup_navigate.emit(-1 if key == Qt.Key_Up else 1)
            return

        # ')' and ';' → hide tooltip
        if key in (Qt.Key_ParenRight, Qt.Key_Semicolon):
            QToolTip.hideText()

        super().keyPressEvent(event)

        # After '(' → emit signature request
        cursor = self.textCursor()
        text = cursor.block().text()
        col = cursor.positionInBlock()
        if col > 0 and text[col - 1] == "(":
            j = col - 1
            while j > 0 and (text[j - 1].isalnum() or text[j - 1] == "_"):
                j -= 1
            fname = text[j:col - 1]
            if fname:
                self.signature_requested.emit(fname)

    def cursor_global_pos(self) -> "QPoint":
        """Return global position of the text cursor for popup placement."""
        rect = self.cursorRect()
        return self.viewport().mapToGlobal(rect.bottomLeft())

    def replace_current_word(self, completion: str):
        """Replace the current partial identifier with the completion."""
        cursor = self.textCursor()
        text = cursor.block().text()
        col = cursor.positionInBlock()
        # Find start of the partial word
        i = col
        while i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_"):
            i -= 1
        # Select from word start to current position
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, i)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, col - i)
        cursor.insertText(completion)
        self.setTextCursor(cursor)


# ── NSS Syntax Highlighter ────────────────────────────────────

class NSSSyntaxHighlighter(QSyntaxHighlighter):

    def __init__(self, document, db: NWScriptDB | None = None):
        super().__init__(document)
        self._db = db
        self.rules = self._build_rules()
        self._ml_comment_start = re.compile(r'/\*')
        self._ml_comment_end = re.compile(r'\*/')
        self._comment_fmt = self._fmt(COLOR_NSS_COMMENT, italic=True)   # cached

    def set_db(self, db: NWScriptDB):
        self._db = db
        self.rules = self._build_rules()
        self._comment_fmt = self._fmt(COLOR_NSS_COMMENT, italic=True)
        self.rehighlight()

    def _fmt(self, color_hex: str, bold=False, italic=False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color_hex))
        if bold:
            fmt.setFontWeight(700)
        if italic:
            fmt.setFontItalic(True)
        return fmt

    def _build_rules(self):
        rules = []

        # Types
        for kw in NWSCRIPT_TYPES:
            rules.append((re.compile(rf'\b{re.escape(kw)}\b'),
                          self._fmt(COLOR_NSS_TYPE, bold=True)))

        # Keywords
        for kw in NWSCRIPT_KEYWORDS:
            if kw not in NWSCRIPT_TYPES:
                rules.append((re.compile(rf'\b{re.escape(kw)}\b'),
                              self._fmt(COLOR_NSS_KEYWORD, bold=True)))

        # Constants from DB (ALL_CAPS with known names)
        if self._db and self._db.is_loaded:
            # Just match ALL_CAPS pattern — individual names would be too slow
            pass

        # ALL_CAPS constants
        rules.append((re.compile(r'\b[A-Z][A-Z0-9_]{2,}\b'),
                      self._fmt(COLOR_NSS_CONSTANT)))

        # Function calls (identifier followed by '(')
        rules.append((re.compile(r'\b[A-Z][a-zA-Z0-9_]*(?=\s*\()'),
                      self._fmt(COLOR_NSS_FUNCTION)))

        # Preprocessor directives
        rules.append((re.compile(r'#\w+'),
                      self._fmt("#c586c0")))

        # Strings
        rules.append((re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"'),
                      self._fmt(COLOR_NSS_STRING)))

        # Numbers (int / float / hex)
        rules.append((re.compile(r'\b(0x[0-9A-Fa-f]+|\d+\.?\d*[fF]?)\b'),
                      self._fmt(COLOR_NSS_NUMBER)))

        # Single-line comments
        rules.append((re.compile(r'//[^\n]*'),
                      self._fmt(COLOR_NSS_COMMENT, italic=True)))

        return rules

    def highlightBlock(self, text: str):
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

        # Multi-line comments — use cached format object
        self.setCurrentBlockState(0)
        start_index = 0
        if self.previousBlockState() != 1:
            m = self._ml_comment_start.search(text)
            start_index = m.start() if m else -1

        comment_fmt = self._comment_fmt   # no allocation per block
        while start_index >= 0:
            end_m = self._ml_comment_end.search(text, start_index)
            if end_m:
                length = end_m.end() - start_index
            else:
                self.setCurrentBlockState(1)
                length = len(text) - start_index
            self.setFormat(start_index, length, comment_fmt)
            next_m = self._ml_comment_start.search(text, start_index + length)
            start_index = next_m.start() if next_m else -1


# ── Script Editor Widget ──────────────────────────────────────

class ScriptEditorWidget(QWidget):
    """
    Full NSS script editor with real nwscript.nss autocomplete.
    """

    script_saved = Signal(str)   # emits script name

    def __init__(self, script: ScriptFile | None = None,
                 project=None, parent=None):
        super().__init__(parent)
        self.script = script or ScriptFile(
            name="untitled", source_code=make_void_main_template()
        )
        self.project = project
        self._game = "K1"
        self._game_dir = None  # Set via set_game_dir()
        self._db: NWScriptDB | None = None
        self._popup: AutocompletePopup | None = None
        # Background DB loader thread (kept as instance attr to prevent GC)
        self._db_thread: QThread | None = None
        self._db_worker: _DBLoaderWorker | None = None
        # IPC context (set by MainWindow.ipc_open_script)
        self._ipc_resref: str = getattr(script, 'name', '') if script else ''
        self._ipc_slot: str = ''
        self._ipc_object_tag: str = ''
        self._setup_ui()
        self._load_script()
        # Load DB asynchronously — small singleShot so the window renders first
        QTimer.singleShot(50, lambda: self._start_db_load(self._game))

    # ── DB init (background thread) ───────────────────────────

    def _start_db_load(self, game: str):
        """Spin up a background QThread to load the NWScript DB."""
        # If a previous load is still running, let it finish — its result
        # will be discarded when it arrives (game may have changed).
        if self._db_thread and self._db_thread.isRunning():
            return  # already loading; ignore duplicate request

        worker = _DBLoaderWorker(game)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_db_loaded)
        worker.error.connect(lambda msg: self._log(f"⚠ Could not load nwscript.nss: {msg}"))
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(thread.deleteLater)

        self._db_thread = thread
        self._db_worker = worker
        thread.start()

    def _on_db_loaded(self, db: NWScriptDB):
        """Called on the main thread when the background worker finishes."""
        self._db = db
        self.highlighter.set_db(db)
        self._populate_function_tree()
        self._log(
            f"✓ Loaded nwscript.nss ({self._game}): "
            f"{len(db.functions)} functions, "
            f"{len(db.constants)} constants"
        )

    # kept for backward compat / direct call from set_game
    def _init_db(self, game: str = None):
        g = game or self._game
        self._start_db_load(g)

    def set_game(self, game: str):
        """Switch between K1 and K2 databases."""
        new_game = game.upper()
        if new_game == self._game and self._db is not None:
            return   # already loaded for this game — nothing to do
        self._game = new_game
        self._start_db_load(self._game)

    def set_game_dir(self, game_dir):
        """Set game directory for 2DA lookups and resource browsing."""
        from pathlib import Path
        self._game_dir = Path(game_dir)
        self._log(f"Game directory set: {self._game_dir}")

    # ── UI setup ──────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tb = self._build_toolbar()
        layout.addWidget(tb)

        # Find/Replace bar (hidden by default)
        self._find_bar = self._build_find_bar()
        self._find_bar.setVisible(False)
        layout.addWidget(self._find_bar)

        # Horizontal: editor | function ref
        self.h_split = QSplitter(Qt.Horizontal)
        self.h_split.setHandleWidth(2)
        self.h_split.setChildrenCollapsible(False)

        self.editor = CodeEditor()
        self.highlighter = NSSSyntaxHighlighter(self.editor.document())
        self.h_split.addWidget(self.editor)

        func_panel = self._build_function_panel()
        self.h_split.addWidget(func_panel)
        # Give the Function Reference panel 380 px by default — wide enough
        # to actually read signatures without resizing every session.
        self.h_split.setSizes([640, 380])
        self.h_split.setStretchFactor(0, 1)
        self.h_split.setStretchFactor(1, 0)
        h_split = self.h_split  # keep local alias for v_split below

        # Vertical: editor | console
        v_split = QSplitter(Qt.Vertical)
        v_split.setHandleWidth(2)
        v_split.addWidget(self.h_split)

        console_panel = self._build_console()
        v_split.addWidget(console_panel)
        v_split.setSizes([560, 130])
        v_split.setStretchFactor(0, 1)
        v_split.setStretchFactor(1, 0)

        layout.addWidget(v_split)

        # Status bar (line:col + word count)
        self._status_bar = self._build_status_bar()
        layout.addWidget(self._status_bar)

        # Wire autocomplete
        self.editor.autocomplete_requested.connect(self._show_autocomplete)
        self.editor.signature_requested.connect(self._show_signature)
        self.editor.popup_navigate.connect(self._popup_navigate)
        self.editor.popup_confirm.connect(self._popup_confirm)
        self.editor.popup_hide.connect(self._popup_hide)
        self.editor.cursor_position_changed.connect(self._update_cursor_pos)

        # Shortcuts
        save_sc = QShortcut(QKeySequence("Ctrl+S"), self)
        save_sc.activated.connect(self._save_script)

        find_sc = QShortcut(QKeySequence("Ctrl+F"), self)
        find_sc.activated.connect(lambda: self._toggle_find_bar(replace=False))

        replace_sc = QShortcut(QKeySequence("Ctrl+H"), self)
        replace_sc.activated.connect(lambda: self._toggle_find_bar(replace=True))

        goto_sc = QShortcut(QKeySequence("Ctrl+G"), self)
        goto_sc.activated.connect(self._goto_line)

        find_next_sc = QShortcut(QKeySequence("F3"), self)
        find_next_sc.activated.connect(self._find_next)

    def _build_toolbar(self) -> QWidget:
        tb = QWidget()
        tb.setStyleSheet("background:#2d2d30; border-bottom:1px solid #3c3c3c;")
        layout = QHBoxLayout(tb)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(4)

        def btn(label, slot, tooltip="", primary=False):
            b = QPushButton(label)
            b.clicked.connect(slot)
            b.setToolTip(tooltip)
            b.setFixedHeight(24)
            if primary:
                b.setStyleSheet(
                    "QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;"
                    "  border-radius:3px; padding:2px 10px; font-weight:bold; }"
                    "QPushButton:hover { background:#1a8fe0; }"
                )
            else:
                b.setStyleSheet(
                    "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
                    "  border-radius:3px; padding:2px 8px; }"
                    "QPushButton:hover { background:#4a4a4a; color:white; }"
                )
            return b

        layout.addWidget(btn("Open",        self._open_script,  "Open NSS file"))
        layout.addWidget(btn("Save",        self._save_script,  "Save (Ctrl+S)"))

        sep = QFrame(); sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#3c3c3c;"); layout.addWidget(sep)

        layout.addWidget(btn("⚙ Compile → NCS", self._compile,   "Compile NSS → NCS", True))
        layout.addWidget(btn("Decompile NCS",    self._decompile, "Decompile NCS file"))
        layout.addWidget(btn("🎮 2DA Lookup",   self._browse_2da, "Browse game 2DA files for constants"))

        sep2 = QFrame(); sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color:#3c3c3c;"); layout.addWidget(sep2)

        layout.addWidget(btn("🔍 Find",   lambda: self._toggle_find_bar(False), "Find (Ctrl+F)"))
        layout.addWidget(btn("⇄ Replace", lambda: self._toggle_find_bar(True),  "Find & Replace (Ctrl+H)"))
        layout.addWidget(btn("↤ Go to Line", self._goto_line, "Go to line (Ctrl+G)"))

        sep3 = QFrame(); sep3.setFrameShape(QFrame.VLine)
        sep3.setStyleSheet("color:#3c3c3c;"); layout.addWidget(sep3)

        # Template picker
        layout.addWidget(QLabel("Template:"))
        self.template_combo = QComboBox()
        self.template_combo.addItems(["void main()", "StartingConditional()",
                                       "Quest Start", "Quest Complete", "Quest Check"])
        self.template_combo.currentTextChanged.connect(self._insert_template)
        self.template_combo.setFixedWidth(170)
        self.template_combo.setStyleSheet(
            "QComboBox { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            "  border-radius:3px; padding:2px 6px; }"
        )
        layout.addWidget(self.template_combo)

        sep4 = QFrame(); sep4.setFrameShape(QFrame.VLine)
        sep4.setStyleSheet("color:#3c3c3c;"); layout.addWidget(sep4)

        # Game selector
        layout.addWidget(QLabel("Game:"))
        self.game_combo = QComboBox()
        self.game_combo.addItems(["K1", "K2"])
        self.game_combo.setFixedWidth(60)
        self.game_combo.setStyleSheet(
            "QComboBox { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            "  border-radius:3px; padding:2px 6px; }"
        )
        self.game_combo.currentTextChanged.connect(self.set_game)
        layout.addWidget(self.game_combo)

        layout.addStretch()

        self.script_name_label = QLabel(self.script.name or "untitled")
        self.script_name_label.setStyleSheet("color:#569cd6; font-size:9pt;")
        layout.addWidget(self.script_name_label)

        return tb

    def _build_function_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#252526;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("Function Reference")
        header.setStyleSheet("background:#2d2d30; color:#cccccc; font-weight:bold;"
                              " padding:5px 8px; border-bottom:1px solid #3c3c3c;")
        layout.addWidget(header)

        self.func_search = QLineEdit()
        self.func_search.setPlaceholderText("Search functions & constants…")
        self.func_search.textChanged.connect(self._filter_functions)
        self.func_search.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:none;"
            "  border-bottom:1px solid #3c3c3c; padding:5px 8px; }"
        )
        layout.addWidget(self.func_search)

        self.func_tree = QTreeWidget()
        self.func_tree.setHeaderHidden(True)
        self.func_tree.setStyleSheet("""
            QTreeWidget { background:#252526; border:none; }
            QTreeWidget::item { color:#cccccc; padding:2px 4px; }
            QTreeWidget::item:hover { background:#2a2d2e; }
            QTreeWidget::item:selected { background:#094771; }
        """)
        self.func_tree.itemDoubleClicked.connect(self._insert_function)
        self.func_tree.itemClicked.connect(self._show_func_detail)
        self._populate_function_tree()
        layout.addWidget(self.func_tree)

        self.func_detail = QLabel()
        self.func_detail.setWordWrap(True)
        self.func_detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.func_detail.setStyleSheet(
            "color:#969696; font-size:8pt; padding:6px 8px;"
            " background:#1e1e1e; border-top:1px solid #3c3c3c;"
        )
        # Use a minimum height rather than a fixed height so the detail
        # area can expand when the user resizes the panel.
        self.func_detail.setMinimumHeight(80)
        layout.addWidget(self.func_detail)

        return panel

    def _populate_function_tree(self, filter_text: str = ""):
        self.func_tree.clear()
        ft = filter_text.lower()

        if self._db and self._db.is_loaded:
            # Use real nwscript.nss database
            cats = self._db.function_categories
            for cat in sorted(cats):
                funcs = cats[cat]
                if ft:
                    funcs = [f for f in funcs if ft in f.name.lower()
                             or ft in f.comment.lower()]
                if not funcs:
                    continue
                cat_item = QTreeWidgetItem([f"{cat} ({len(funcs)})"])
                cat_item.setForeground(0, QColor("#dcdcaa"))
                cat_item.setExpanded(True)   # always expanded so all entries are visible
                for func in funcs:
                    sig = func.signature
                    f_item = QTreeWidgetItem([func.name])
                    f_item.setForeground(0, QColor("#9cdcfe"))
                    f_item.setToolTip(0, sig)
                    f_item.setData(0, Qt.UserRole, {
                        "type": "function",
                        "name": func.name,
                        "returns": func.return_type,
                        "params": [str(p) for p in func.params],
                        "description": func.comment or f"Returns {func.return_type}.",
                        "signature": sig,
                        "snippet": func.call_snippet,
                    })
                    cat_item.addChild(f_item)
                self.func_tree.addTopLevelItem(cat_item)

            # Add constants section when searching
            if ft:
                const_matches = self._db.search_constants(filter_text)
                if const_matches:
                    c_item = QTreeWidgetItem([f"Constants ({len(const_matches)})"])
                    c_item.setForeground(0, QColor("#ce9178"))
                    c_item.setExpanded(True)
                    for const in const_matches[:50]:
                        ci = QTreeWidgetItem([f"{const.name} = {const.value}"])
                        ci.setForeground(0, QColor("#b5cea8"))
                        ci.setData(0, Qt.UserRole, {
                            "type": "constant",
                            "name": const.name,
                            "returns": const.type,
                            "value": const.value,
                            "description": f"{const.type} constant = {const.value}",
                        })
                        c_item.addChild(ci)
                    self.func_tree.addTopLevelItem(c_item)
        else:
            # A missing official include is safer than hand-written signatures
            # that can silently generate invalid scripts.
            unavailable = QTreeWidgetItem([
                "Official nwscript.nss database unavailable"
            ])
            unavailable.setForeground(0, QColor("#f48771"))
            self.func_tree.addTopLevelItem(unavailable)

    def _filter_functions(self, text: str):
        self._populate_function_tree(text)

    def _show_func_detail(self, item, col):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        if data.get("type") == "function":
            sig = data.get("signature") or f"{data['name']}({', '.join(data.get('params', []))})"
            self.func_detail.setText(
                f"<b style='color:#dcdcaa'>{data['name']}</b>"
                f" → <i style='color:#4ec9b0'>{data['returns']}</i><br>"
                f"<span style='color:#569cd6; font-size:7pt'>{sig}</span><br>"
                f"<span style='color:#969696'>{data.get('description', '')}</span>"
            )
        elif data.get("type") == "constant":
            self.func_detail.setText(
                f"<b style='color:#b5cea8'>{data['name']}</b>"
                f" = <span style='color:#ce9178'>{data.get('value', '')}</span>"
                f" <i style='color:#4ec9b0'>({data['returns']})</i><br>"
                f"<span style='color:#969696'>{data.get('description', '')}</span>"
            )

    def _insert_function(self, item, col):
        data = item.data(0, Qt.UserRole)
        if data:
            snippet = data.get("snippet") or data.get("name", "")
            cursor = self.editor.textCursor()
            cursor.insertText(snippet)
            self.editor.setFocus()

    # ── Find / Replace Bar ────────────────────────────────────

    def _build_find_bar(self) -> QWidget:
        """Inline find/replace bar that appears below the toolbar."""
        bar = QWidget()
        bar.setStyleSheet("background:#2d2d30; border-bottom:1px solid #3c3c3c;")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(4)

        # Find field
        self._find_input = QLineEdit()
        self._find_input.setPlaceholderText("Find…")
        self._find_input.setFixedWidth(200)
        self._find_input.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            "  border-radius:3px; padding:2px 6px; }"
        )
        self._find_input.returnPressed.connect(self._find_next)
        lay.addWidget(self._find_input)

        # Replace field (hidden when not in replace mode)
        self._replace_input = QLineEdit()
        self._replace_input.setPlaceholderText("Replace with…")
        self._replace_input.setFixedWidth(200)
        self._replace_input.setStyleSheet(
            "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
            "  border-radius:3px; padding:2px 6px; }"
        )
        self._replace_input.returnPressed.connect(self._replace_one)
        lay.addWidget(self._replace_input)

        # Case-sensitive checkbox
        self._find_case_cb = QCheckBox("Aa")
        self._find_case_cb.setToolTip("Case-sensitive search")
        self._find_case_cb.setStyleSheet("color:#cccccc; font-size:8pt;")
        lay.addWidget(self._find_case_cb)

        # Regex checkbox
        self._find_regex_cb = QCheckBox(".*")
        self._find_regex_cb.setToolTip("Regular expression search")
        self._find_regex_cb.setStyleSheet("color:#cccccc; font-size:8pt;")
        lay.addWidget(self._find_regex_cb)

        def _tiny_btn(label, slot, tip=""):
            b = QPushButton(label)
            b.setFixedSize(60, 22)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            b.setStyleSheet(
                "QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
                "  border-radius:3px; font-size:8pt; }"
                "QPushButton:hover { background:#4a4a4a; }"
            )
            return b

        lay.addWidget(_tiny_btn("↓ Next",    self._find_next,    "Find next (F3)"))
        lay.addWidget(_tiny_btn("↑ Prev",    self._find_prev,    "Find previous (Shift+F3)"))
        self._replace_btn = _tiny_btn("Replace",  self._replace_one,  "Replace current match")
        self._replace_all_btn = _tiny_btn("All",  self._replace_all,  "Replace all occurrences")
        lay.addWidget(self._replace_btn)
        lay.addWidget(self._replace_all_btn)

        # Match counter label
        self._find_match_label = QLabel("")
        self._find_match_label.setStyleSheet("color:#969696; font-size:8pt;")
        lay.addWidget(self._find_match_label)
        lay.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#969696; border:none; font-size:10pt; }"
            "QPushButton:hover { color:#e04060; }"
        )
        close_btn.clicked.connect(lambda: self._find_bar.setVisible(False))
        lay.addWidget(close_btn)

        # Connect live search
        self._find_input.textChanged.connect(self._find_highlight_all)

        return bar

    def _build_status_bar(self) -> QWidget:
        """Thin status bar showing cursor line:col and selection info."""
        bar = QWidget()
        bar.setFixedHeight(20)
        bar.setStyleSheet("background:#007acc; border-top:1px solid #0060a0;")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(16)

        self._pos_label = QLabel("Ln 1, Col 1")
        self._pos_label.setStyleSheet("color:white; font-size:8pt;")
        lay.addWidget(self._pos_label)

        self._sel_label = QLabel("")
        self._sel_label.setStyleSheet("color:#cce8ff; font-size:8pt;")
        lay.addWidget(self._sel_label)

        lay.addStretch()

        self._enc_label = QLabel("NWScript  |  UTF-8")
        self._enc_label.setStyleSheet("color:#cce8ff; font-size:8pt;")
        lay.addWidget(self._enc_label)

        return bar

    def _update_cursor_pos(self, line: int, col: int):
        self._pos_label.setText(f"Ln {line}, Col {col}")
        cursor = self.editor.textCursor()
        sel_len = abs(cursor.selectionEnd() - cursor.selectionStart())
        if sel_len:
            self._sel_label.setText(f"({sel_len} chars selected)")
        else:
            self._sel_label.setText("")

    # ── Find / Replace actions ────────────────────────────────

    def _toggle_find_bar(self, replace: bool = False):
        """Show or toggle the find/replace bar."""
        visible = self._find_bar.isVisible()
        currently_replace = self._replace_input.isVisible()
        if visible and (currently_replace == replace):
            self._find_bar.setVisible(False)
            self.editor.setFocus()
            return
        self._replace_input.setVisible(replace)
        self._replace_btn.setVisible(replace)
        self._replace_all_btn.setVisible(replace)
        self._find_bar.setVisible(True)
        self._find_input.setFocus()
        self._find_input.selectAll()

    def _get_find_flags(self) -> "QTextDocument.FindFlags":
        flags = QTextDocument.FindFlag(0)
        if self._find_case_cb.isChecked():
            flags |= QTextDocument.FindCaseSensitively
        return flags

    def _find_next(self):
        text = self._find_input.text()
        if not text:
            return
        if self._find_regex_cb.isChecked():
            found = self.editor.find(re.compile(text), self._get_find_flags())
        else:
            found = self.editor.find(text, self._get_find_flags())
        if not found:
            # Wrap around
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.editor.setTextCursor(cursor)
            if self._find_regex_cb.isChecked():
                self.editor.find(re.compile(text), self._get_find_flags())
            else:
                self.editor.find(text, self._get_find_flags())
        self._find_highlight_all(text)

    def _find_prev(self):
        text = self._find_input.text()
        if not text:
            return
        flags = self._get_find_flags() | QTextDocument.FindBackward
        if self._find_regex_cb.isChecked():
            found = self.editor.find(re.compile(text), flags)
        else:
            found = self.editor.find(text, flags)
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.editor.setTextCursor(cursor)
            if self._find_regex_cb.isChecked():
                self.editor.find(re.compile(text), flags)
            else:
                self.editor.find(text, flags)

    def _find_highlight_all(self, text: str = ""):
        """Highlight all occurrences of the search term."""
        if not text:
            text = self._find_input.text()
        selections = []
        if text:
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#614a00"))
            fmt.setForeground(QColor("#ffd700"))
            find_flag = (QTextDocument.FindCaseSensitively
                         if self._find_case_cb.isChecked()
                         else QTextDocument.FindFlag(0))
            doc    = self.editor.document()
            cursor = doc.find(text, 0, find_flag)
            count  = 0
            while not cursor.isNull():
                sel = QTextEdit.ExtraSelection()
                sel.cursor = cursor
                sel.format = fmt
                selections.append(sel)
                count += 1
                cursor = doc.find(text, cursor, find_flag)
            self._find_match_label.setText(
                f"{count} match{'es' if count != 1 else ''}" if count else "No matches"
            )
            # Tint field red when no matches
            self._find_input.setStyleSheet(
                "QLineEdit { background:#3c3c3c; color:#cccccc; border:1px solid #555;"
                "  border-radius:3px; padding:2px 6px; }"
                if count or not text else
                "QLineEdit { background:#5a1a1a; color:#ff8888; border:1px solid #ff4444;"
                "  border-radius:3px; padding:2px 6px; }"
            )
        # Merge: keep line/bracket highlight, replace old search marks
        existing = [s for s in self.editor.extraSelections()
                    if s.format.background().color() not in (QColor("#614a00"),)]
        self.editor.setExtraSelections(existing + selections)

    def _replace_one(self):
        """Replace the current selection if it matches, else find next."""
        text    = self._find_input.text()
        replace = self._replace_input.text()
        if not text:
            return
        cursor = self.editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == text:
            cursor.insertText(replace)
        self._find_next()

    def _replace_all(self):
        """Replace all occurrences of the search term."""
        text    = self._find_input.text()
        replace = self._replace_input.text()
        if not text:
            return
        content = self.editor.toPlainText()
        flags   = 0 if self._find_case_cb.isChecked() else re.IGNORECASE
        if self._find_regex_cb.isChecked():
            new_content, count = re.subn(text, replace, content, flags=flags)
        else:
            new_content = content.replace(text, replace) if self._find_case_cb.isChecked() \
                          else re.sub(re.escape(text), replace, content, flags=re.IGNORECASE)
            count = len(content.split(text)) - 1 if self._find_case_cb.isChecked() \
                    else len(re.findall(re.escape(text), content, re.IGNORECASE))
        if new_content != content:
            self.editor.setPlainText(new_content)
        self._find_match_label.setText(f"Replaced {count} occurrence{'s' if count != 1 else ''}")

    # ── Go to line ────────────────────────────────────────────

    def _goto_line(self):
        """Show Go-to-line input dialog."""
        max_line = self.editor.document().blockCount()
        line, ok = QInputDialog.getInt(
            self, "Go to Line",
            f"Line number (1 – {max_line}):",
            value=self.editor.textCursor().blockNumber() + 1,
            min=1, max=max_line,
        )
        if ok:
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.MoveAnchor, line - 1)
            self.editor.setTextCursor(cursor)
            self.editor.centerCursor()
            self.editor.setFocus()

    def _build_console(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#1e1e1e;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        hdr = QWidget()
        hdr.setStyleSheet("background:#2d2d30; border-top:1px solid #3c3c3c;")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(8, 3, 8, 3)
        hdr_lay.addWidget(QLabel("Compiler Output"))
        hdr_lay.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedSize(40, 18)
        clear_btn.setStyleSheet("QPushButton { background:#3c3c3c; color:#969696;"
                                 " border:none; font-size:8pt; }")
        clear_btn.clicked.connect(lambda: self.console.clear())
        hdr_lay.addWidget(clear_btn)
        layout.addWidget(hdr)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setObjectName("outputConsole")
        layout.addWidget(self.console)
        return panel

    # ── Autocomplete ──────────────────────────────────────────

    def _show_autocomplete(self, prefix: str):
        """Display autocomplete popup for the given prefix."""
        if not self._db or not self._db.is_loaded:
            return

        results = self._db.autocomplete(prefix, max_results=50)
        if not results:
            if self._popup:
                self._popup.hide()
            return

        if self._popup is None:
            self._popup = AutocompletePopup(self)
            self._popup.item_selected.connect(self._apply_completion)

        self._popup.populate(results)

        # Position popup below cursor, constrained to screen
        pos = self.editor.cursor_global_pos()
        row_h = 25
        desired_h = min(320, max(80, self._popup.count() * row_h + 10))
        desired_w = max(280, self._popup.sizeHintForColumn(0) + 24)
        self._popup.resize(desired_w, desired_h)
        # Keep popup on screen
        from qtpy.QtWidgets import QApplication
        screen = QApplication.primaryScreen().availableGeometry()
        x = min(pos.x(), screen.right() - desired_w)
        y = pos.y()
        if y + desired_h > screen.bottom():
            y = pos.y() - desired_h - self.editor.fontMetrics().height()
        self._popup.move(x, y)
        self._popup.show()

    def _apply_completion(self, completion: str):
        """Insert the chosen completion, replacing the partial word."""
        self.editor.replace_current_word(completion)
        # If it's a function, add () and show signature
        if self._db:
            func = self._db.get_function(completion)
            if func:
                cursor = self.editor.textCursor()
                cursor.insertText("(")
                self.editor.setTextCursor(cursor)
                self._show_signature(completion)
        self.editor.setFocus()

    def _show_signature(self, func_name: str):
        """Show a tooltip with the function signature."""
        if not self._db:
            return
        func = self._db.get_function(func_name)
        if not func:
            return
        pos = self.editor.cursor_global_pos()
        sig = func.signature
        comment = func.comment or ""
        tip = f"<b>{sig}</b>"
        if comment:
            tip += f"<br><i style='color:#969696'>{comment[:120]}</i>"
        QToolTip.showText(pos, tip, self.editor)

    def _popup_navigate(self, direction: int):
        """Move selection up (-1) or down (+1) in the autocomplete popup."""
        if self._popup and self._popup.isVisible():
            cur = self._popup.currentRow()
            count = self._popup.count()
            if count == 0:
                return
            new_row = (cur + direction) % count
            self._popup.setCurrentRow(new_row)

    def _popup_confirm(self):
        """Confirm the currently highlighted autocomplete item (Tab/Enter)."""
        if self._popup and self._popup.isVisible():
            item = self._popup.currentItem()
            if item:
                self._apply_completion(item.text())
            self._popup.hide()

    def _popup_hide(self):
        """Hide the autocomplete popup (Escape)."""
        if self._popup and self._popup.isVisible():
            self._popup.hide()
        self.editor.setFocus()

    # ── Script I/O ────────────────────────────────────────────

    def _load_script(self):
        self.editor.setPlainText(self.script.source_code)
        self.script_name_label.setText(self.script.name or "untitled")

    def _open_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Script", "", "NWScript (*.nss);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                code = f.read()
            self.script.file_path = Path(path)
            self.script.name = Path(path).stem
            self.script.source_code = code
            self._load_script()
            self._log(f"📂 Opened: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _save_script(self):
        if not self.script.file_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Script",
                self.script.name + ".nss",
                "NWScript (*.nss);;All Files (*)"
            )
            if not path:
                return
            self.script.file_path = Path(path)
            self.script.name = Path(path).stem

        self.script.source_code = self.editor.toPlainText()
        if self.script.save_to_disk():
            self._log(f"✓ Saved: {self.script.file_path}")
            self.script_name_label.setText(self.script.name)
            # Update tab title in parent QTabWidget
            parent_tabs = self._find_parent_tab_widget()
            if parent_tabs is not None:
                idx = parent_tabs.indexOf(self)
                if idx >= 0:
                    parent_tabs.setTabText(idx, f"✎ {self.script.name}.nss")
            self.script_saved.emit(self.script.name)
        else:
            self._log("✗ Save failed")

    def _find_parent_tab_widget(self):
        """Walk up the widget tree to find the nearest QTabWidget."""
        w = self.parent()
        while w is not None:
            if isinstance(w, QTabWidget):
                return w
            w = w.parent() if hasattr(w, 'parent') else None
        return None

    # ── Compile ───────────────────────────────────────────────

    def _find_compiler(self) -> str | None:
        """
        Locate nwnnsscomp for the current game.
        Search only user-installed compilers on PATH/working directory.  The
        repository's legacy executables have no established provenance and are
        deliberately never auto-executed.
        """
        candidates = [
            Path("nwnnsscomp.exe"),
            Path("nwnnsscomp"),
        ]

        for cp in candidates:
            try:
                result = subprocess.run(
                    [str(cp)], capture_output=True, timeout=3
                )
                return str(cp)
            except (FileNotFoundError, PermissionError, OSError):
                pass
            except subprocess.TimeoutExpired:
                return str(cp)  # It exists, it just timed out waiting for input
        return None

    def _compile(self):
        """Compile the script using PyKotor InbuiltNCSCompiler (primary) or nwnnsscomp (fallback)."""
        self.script.source_code = self.editor.toPlainText()
        if not self.script.file_path:
            self._save_script()
        if not self.script.file_path:
            self._log("✗ Please save the script first.")
            return

        self._log(f"→ Compiling {self.script.name}.nss  [{self._game}]…")

        # ── Strategy 1: PyKotor InbuiltNCSCompiler (cross-platform, no Wine) ──
        try:
            from pykotor.resource.formats.ncs.compilers import InbuiltNCSCompiler  # type: ignore[import]
            from pykotor.common.misc import Game  # type: ignore[import]
            from ghostscripter.core.nwscript.compiler_defs import install_pykotor_definitions
            import shutil

            game_enum = Game.K1 if self._game.upper() == "K1" else Game.K2
            install_pykotor_definitions(self._game)
            resref = self.script.name or self.script.file_path.stem
            ncs_path = self.script.file_path.with_suffix(".ncs")

            # Locate nwscript.nss so #include "nwscript" resolves
            base = Path(__file__).parent.parent.parent.parent
            nwscript_src = base / "resources" / "scripts" / self._game.lower() / "nwscript.nss"
            script_dir = self.script.file_path.parent
            nwscript_local = script_dir / "nwscript.nss"
            _copied_nwscript = False
            if nwscript_src.exists() and not nwscript_local.exists():
                shutil.copy(nwscript_src, nwscript_local)
                _copied_nwscript = True

            try:
                compiler = InbuiltNCSCompiler()
                stdout_txt, stderr_txt = compiler.compile_script(
                    source_file=self.script.file_path,
                    output_file=ncs_path,
                    game=game_enum,
                )
                compiler_output = ((stdout_txt or "") + (stderr_txt or "")).strip()
            finally:
                # Clean up nwscript.nss if we copied it
                if _copied_nwscript and nwscript_local.exists():
                    try:
                        nwscript_local.unlink()
                    except OSError:
                        pass

            if ncs_path.exists() and ncs_path.stat().st_size > 0:
                self._log(f"✓ Compiled via PyKotor → {ncs_path.name}  ({ncs_path.stat().st_size} bytes)")
                if compiler_output:
                    for line in compiler_output.splitlines():
                        if line.strip():
                            self._log(f"  {line}")
                self.script.errors = []
                self._notify_script_compiled(str(ncs_path))
                return
            elif compiler_output:
                self._log("✗ Compilation failed (PyKotor):")
                for line in compiler_output.splitlines():
                    if line.strip():
                        self._log(f"  {line}")
                box = QMessageBox(self)
                box.setWindowTitle("Compilation Failed")
                box.setIcon(QMessageBox.Critical)
                box.setText(
                    f"<b style='color:#f48771'>Script compilation failed.</b><br>"
                    f"Script: <code>{self.script.name}.nss</code>"
                )
                box.setDetailedText(compiler_output[:2000])
                box.setStandardButtons(QMessageBox.Ok)
                box.exec()
                return

        except ImportError:
            self._log("  PyKotor not available — trying nwnnsscomp…")
        except Exception as pykotor_exc:
            err_str = str(pykotor_exc)
            self._log(f"✗ PyKotor compile error: {err_str}")
            box = QMessageBox(self)
            box.setWindowTitle("Compilation Failed")
            box.setIcon(QMessageBox.Critical)
            box.setText(
                f"<b style='color:#f48771'>Script compilation failed.</b><br>"
                f"Script: <code>{self.script.name}.nss</code>"
            )
            box.setDetailedText(err_str[:2000])
            box.setStandardButtons(QMessageBox.Ok)
            box.exec()
            return

        # ── Strategy 2: nwnnsscomp (bundled .exe, native binary, or Wine) ─────
        compiler = self._find_compiler()
        if not compiler:
            self._log("⚠ nwnnsscomp not found — falling back to syntax check.")
            self._syntax_check_only()
            return

        self._log(f"  Compiler: {compiler}")
        try:
            # nwnnsscomp -c <file> compiles to .ncs in same directory
            result = subprocess.run(
                [compiler, "-c", str(self.script.file_path)],
                capture_output=True, text=True, timeout=30,
                cwd=str(self.script.file_path.parent),
            )
            output = (result.stdout + result.stderr).strip()
            if result.returncode == 0 or (result.returncode != 0 and not output):
                ncs = self.script.file_path.with_suffix(".ncs")
                if ncs.exists():
                    self._log(f"✓ Compilation successful → {ncs.name}")
                    self.script.errors = []
                    # Notify GModular via the main window
                    self._notify_script_compiled(str(ncs))
                else:
                    msg = (
                        "The compiler finished without errors but the .ncs output "
                        "file was not created.\n\n"
                        "Possible causes:\n"
                        "• nwscript.nss is missing from the script directory\n"
                        "• The compiler requires a module directory (use ⚙ Compile → NCS "
                        "from within a module folder)\n"
                        "• Check the Compiler Output panel for details."
                    )
                    self._log("⚠ Compiler ran but .ncs not found. Check your nwscript.nss path.")
                    QMessageBox.warning(self, "Output File Missing", msg)
            else:
                self._log("✗ Compilation failed:")
                for line in output.splitlines():
                    if line.strip():
                        self._log(f"  {line}")
                # ── Error popup ──────────────────────────────────────
                err_lines = [l for l in output.splitlines() if l.strip()]
                preview = "\n".join(err_lines[:20])
                if len(err_lines) > 20:
                    preview += f"\n…and {len(err_lines) - 20} more line(s). See Compiler Output below."
                box = QMessageBox(self)
                box.setWindowTitle("Compilation Failed")
                box.setIcon(QMessageBox.Critical)
                box.setText(
                    f"<b style='color:#f48771'>Script compilation failed.</b><br>"
                    f"Script: <code>{self.script.name}.nss</code>"
                )
                box.setDetailedText(preview)
                box.setStandardButtons(QMessageBox.Ok)
                box.exec()
        except subprocess.TimeoutExpired:
            self._log("✗ Compiler timed out (>30 s).")
            QMessageBox.critical(
                self, "Compilation Timed Out",
                "The compiler did not finish within 30 seconds.\n"
                "Check that your script file path has no spaces, "
                "or that nwnnsscomp is not waiting for input."
            )
        except Exception as e:
            self._log(f"✗ Compiler error: {e}")
            QMessageBox.critical(
                self, "Compiler Error",
                f"An unexpected error occurred while running the compiler:\n\n{e}"
            )

    def _syntax_check_only(self):
        """Basic NSS syntax check without compiler."""
        code = self.editor.toPlainText()
        issues = []
        open_braces  = code.count("{")
        close_braces = code.count("}")
        open_parens  = code.count("(")
        close_parens = code.count(")")
        if open_braces != close_braces:
            issues.append(f"Brace mismatch: {open_braces}{{ vs {close_braces}}}")
        if open_parens != close_parens:
            issues.append(f"Paren mismatch: {open_parens}( vs {close_parens})")
        if issues:
            for i in issues:
                self._log(f"⚠ {i}")
            QMessageBox.warning(
                self, "Syntax Issues Found",
                "Basic syntax check found potential issues:\n\n"
                + "\n".join(f"• {i}" for i in issues)
                + "\n\nNote: nwnnsscomp was not found; "
                "this is a simplified check only."
            )
        else:
            self._log("✓ Basic syntax check passed (no compiler available).")

    def _notify_script_compiled(self, ncs_path: str) -> None:
        """
        After a successful compile, tell the MainWindow so it can
        forward a script_compiled IPC notification to GModular.
        """
        from qtpy.QtWidgets import QApplication
        mw = None
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, "notify_script_compiled"):
                mw = widget
                break
        if mw:
            mw.notify_script_compiled(
                resref=self._ipc_resref or self.script.name,
                ncs_path=ncs_path,
                slot=self._ipc_slot,
                object_tag=self._ipc_object_tag,
            )

    def _decompile(self):
        """
        Decompile a .ncs compiled script to .nss source.

        Tries the following tools in order:
          1. DeNCS CLI (NCSDecompCLI.jar) — OldRepublicDevs/DeNCS on GitHub
             java -jar NCSDecompCLI.jar <file>.ncs --stdout [--k1|--k2]
          2. xoreos-tools ncsdecomp — https://github.com/xoreos/xoreos-tools
             ncsdecomp <file>.ncs
          3. Pykotor CLI (if pykotor is installed)
             pykotor decompile <file>.ncs
        """
        import subprocess
        import tempfile
        import shutil

        path, _ = QFileDialog.getOpenFileName(
            self, "Open NCS File", "", "Compiled Script (*.ncs)"
        )
        if not path:
            return

        ncs_path = Path(path)
        self._log(f"→ Decompile: {ncs_path.name} ({ncs_path.stat().st_size} bytes)")

        # Determine K1 vs K2 based on game dir if set
        game_flag = "--k1"
        if hasattr(self, "_game_dir") and self._game_dir:
            gd = str(self._game_dir).lower()
            if "kotor2" in gd or "sith lords" in gd or "tsl" in gd or "kotor 2" in gd:
                game_flag = "--k2"

        source_text = None
        tool_used = None

        # ── Try DeNCS CLI (NCSDecompCLI.jar) ──────────────────────────
        # Check common locations: tools/ dir, PATH, same dir as app
        dencs_candidates = []
        tools_dir = Path(__file__).resolve().parent.parent.parent.parent / "tools"
        dencs_candidates.append(tools_dir / "NCSDecompCLI.jar")
        dencs_candidates.append(tools_dir / "nCSDecompCLI-1.0.2.jar")
        dencs_candidates.append(Path("NCSDecompCLI.jar"))
        # Also check if there's a dencs executable on PATH
        dencs_exe = shutil.which("NCSDecomp") or shutil.which("ncsdecomp_dencs")

        jar_path = None
        for candidate in dencs_candidates:
            if candidate.exists():
                jar_path = candidate
                break

        java_exe = shutil.which("java")

        if jar_path and java_exe:
            try:
                self._log(f"  Using DeNCS: {jar_path.name}")
                # Build nwscript path argument
                nwscript_arg = []
                nwscript_k1 = tools_dir / "k1_nwscript.nss"
                nwscript_k2 = tools_dir / "tsl_nwscript.nss"
                if game_flag == "--k2" and nwscript_k2.exists():
                    nwscript_arg = ["--nwscript", str(nwscript_k2)]
                elif nwscript_k1.exists():
                    nwscript_arg = ["--nwscript", str(nwscript_k1)]

                cmd = [java_exe, "-jar", str(jar_path),
                       "--input", str(ncs_path),
                       "--stdout", game_flag] + nwscript_arg
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=30
                )
                if result.returncode == 0 and result.stdout.strip():
                    source_text = result.stdout
                    tool_used = "DeNCS"
                else:
                    self._log(f"  ✗ DeNCS failed (rc={result.returncode}): {result.stderr[:200]}")
            except subprocess.TimeoutExpired:
                self._log("  ✗ DeNCS timed out")
            except Exception as ex:
                self._log(f"  ✗ DeNCS error: {ex}")

        # ── Try xoreos-tools ncsdecomp ─────────────────────────────────
        if source_text is None:
            ncsdecomp_exe = shutil.which("ncsdecomp")
            if ncsdecomp_exe:
                try:
                    self._log(f"  Using xoreos-tools: ncsdecomp")
                    with tempfile.TemporaryDirectory() as tmpdir:
                        out_nss = Path(tmpdir) / (ncs_path.stem + ".nss")
                        result = subprocess.run(
                            [ncsdecomp_exe, str(ncs_path), str(out_nss)],
                            capture_output=True, text=True, timeout=30
                        )
                        if out_nss.exists():
                            source_text = out_nss.read_text(encoding="cp1252", errors="replace")
                            tool_used = "xoreos-tools ncsdecomp"
                        elif result.returncode == 0:
                            source_text = result.stdout
                            tool_used = "xoreos-tools ncsdecomp"
                        else:
                            self._log(f"  ✗ xoreos-tools failed: {result.stderr[:200]}")
                except subprocess.TimeoutExpired:
                    self._log("  ✗ xoreos-tools timed out")
                except Exception as ex:
                    self._log(f"  ✗ xoreos-tools error: {ex}")

        # ── Try pykotor CLI ────────────────────────────────────────────
        if source_text is None:
            try:
                import importlib.util
                if importlib.util.find_spec("pykotor"):
                    import sys as _sys
                    pykotorcli = shutil.which("pykotorcli") or shutil.which("pykotor")
                    if pykotorcli:
                        with tempfile.TemporaryDirectory() as tmpdir:
                            out_nss = Path(tmpdir) / (ncs_path.stem + ".nss")
                            result = subprocess.run(
                                [pykotorcli, "decompile", str(ncs_path), "-o", str(out_nss)],
                                capture_output=True, text=True, timeout=30
                            )
                            if out_nss.exists():
                                source_text = out_nss.read_text(encoding="utf-8", errors="replace")
                                tool_used = "pykotor CLI"
            except Exception as ex:
                self._log(f"  ✗ pykotor error: {ex}")

        # ── Load result or show instructions ───────────────────────────
        if source_text:
            self._log(f"  ✓ Decompiled via {tool_used}")
            self.editor.setPlainText(source_text)
            # Set current file name for save
            self._current_file = ncs_path.with_suffix(".nss")
        else:
            self._log("⚠ No decompiler found. To enable NCS decompilation:")
            self._log("  Option 1: DeNCS CLI (OldRepublicDevs/DeNCS on GitHub)")
            self._log(f"    Download NCSDecompCLI.jar → place in: {tools_dir}")
            self._log(f"    Also place k1_nwscript.nss / tsl_nwscript.nss in same folder")
            self._log("    Requires Java runtime (java -version)")
            self._log("  Option 2: xoreos-tools (https://github.com/xoreos/xoreos-tools)")
            self._log("    Install and ensure 'ncsdecomp' is on PATH")
            self._log("  Option 3: pip install pykotor")
            from qtpy.QtWidgets import QMessageBox
            msg = QMessageBox(self)
            msg.setWindowTitle("No NCS Decompiler Found")
            msg.setText(
                "<b>No NCS decompiler detected.</b><br><br>"
                "<b>Option 1 — DeNCS CLI</b> (recommended):<br>"
                f"Download <code>NCSDecompCLI.jar</code> from<br>"
                "<a href='https://github.com/OldRepublicDevs/DeNCS'>github.com/OldRepublicDevs/DeNCS</a><br>"
                f"and place it in <code>{tools_dir}</code><br><br>"
                "<b>Option 2 — xoreos-tools</b>:<br>"
                "Install from <a href='https://github.com/xoreos/xoreos-tools'>github.com/xoreos/xoreos-tools</a><br><br>"
                "<b>Option 3 — PyKotor</b>:<br>"
                "<code>pip install pykotor</code>"
            )
            msg.setTextFormat(1)  # Qt.RichText
            msg.exec()

    # ── Templates ─────────────────────────────────────────────

    def _insert_template(self, name: str):
        from ghostscripter.core.models.script import (
            make_quest_start_template, make_quest_complete_template,
            make_quest_check_template,
        )
        code = None
        if name == "void main()":
            code = make_void_main_template()
        elif name == "StartingConditional()":
            code = make_starting_conditional_template()
        elif name == "Quest Start":
            code = make_quest_start_template("K_QUEST_VAR")
        elif name == "Quest Complete":
            code = make_quest_complete_template("K_QUEST_VAR")
        elif name == "Quest Check":
            code = make_quest_check_template("K_QUEST_VAR")
        if code:
            self.editor.setPlainText(code)

    # ── Game Integration ────────────────────────────────────────

    def _browse_2da(self):
        """Open a 2DA viewer to look up game constants (spell IDs, feat IDs, etc.)."""
        game_dir = getattr(self, "_game_dir", None)
        if not game_dir or not (game_dir / "chitin.key").exists():
            from qtpy.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "Game Directory Required",
                "Set the KotOR game directory in Settings → Set Game Directory first."
            )
            return

        from qtpy.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
            QLabel, QLineEdit, QComboBox, QListWidget, QDialogButtonBox,
            QListWidgetItem, QAbstractItemView)
        from qtpy.QtCore import Qt
        try:
            from ghostscripter.core.resource_manager.resource_manager import ResourceManager
            from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
            rm = ResourceManager()
            rm.load_game(game_dir)
        except Exception as e:
            self._log(f"✗ Failed to load resource manager: {e}")
            return

        # Key 2DA files useful for scripting
        USEFUL_2DAS = [
            "spells", "feat", "classes", "appearance", "baseitems",
            "soundset", "placeables", "globalcat", "nwscript",
        ]

        dlg = QDialog(self)
        dlg.setWindowTitle("🎮 Browse Game 2DA Files")
        dlg.setMinimumSize(640, 520)
        dlg.setStyleSheet("background:#252526; color:#cccccc;")
        lay = QVBoxLayout(dlg)

        # Top: 2DA file picker
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("2DA File:"))
        combo = QComboBox()
        combo.setStyleSheet("QComboBox{background:#3c3c3c;color:#ccc;border:1px solid #555;padding:2px 6px;}")
        # List all available 2DAs
        all_2das = sorted([e.resref for e in rm.list_by_type(".2da")])
        for name in all_2das:
            combo.addItem(name)
        # Prefer spells.2da as default
        if "spells" in all_2das:
            combo.setCurrentText("spells")
        row1.addWidget(combo)
        lay.addLayout(row1)

        # Filter row
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Filter:"))
        filter_edit = QLineEdit()
        filter_edit.setPlaceholderText("Filter rows…")
        filter_edit.setStyleSheet("QLineEdit{background:#3c3c3c;color:#ccc;border:1px solid #555;padding:2px 6px;}")
        row2.addWidget(filter_edit)
        lay.addLayout(row2)

        # Table display
        from qtpy.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        table = QTableWidget()
        table.setStyleSheet("""
            QTableWidget{background:#1e1e1e;color:#ccc;border:1px solid #3c3c3c;gridline-color:#333;}
            QHeaderView::section{background:#2d2d30;color:#9cdcfe;border:1px solid #3c3c3c;padding:2px 4px;}
        """)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(table)

        insert_info = QLabel("Double-click a cell to insert its value into the script editor.")
        insert_info.setStyleSheet("color:#666;font-size:8pt;")
        lay.addWidget(insert_info)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        _current_twoda = [None]

        def load_2da(name):
            try:
                data = rm.read(name + ".2da")
                if data is None:
                    return
                twoda = TwoDAFile.from_bytes(data)
                _current_twoda[0] = twoda
                refresh_table()
            except Exception as e:
                self._log(f"✗ Error loading {name}.2da: {e}")

        def refresh_table(ft=""):
            twoda = _current_twoda[0]
            if not twoda:
                return
            cols = twoda.columns
            table.setColumnCount(len(cols) + 1)
            table.setHorizontalHeaderLabels(["#"] + cols)
            rows = [r for r in twoda.rows if not ft or ft.lower() in
                    " ".join(str(v) for v in r.get_all_values()).lower()]
            table.setRowCount(len(rows))
            for ri, row in enumerate(rows):
                table.setItem(ri, 0, QTableWidgetItem(str(row.label)))
                for ci, col in enumerate(cols):
                    val = row.get(col, "") or ""
                    table.setItem(ri, ci + 1, QTableWidgetItem(str(val)))
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
            table.resizeColumnsToContents()

        def on_filter(text):
            refresh_table(text)

        def on_2da_changed(name):
            load_2da(name)

        def on_cell_dbl_click(row, col):
            item = table.item(row, col)
            if item:
                self.editor.insertPlainText(item.text())
                dlg.accept()

        combo.currentTextChanged.connect(on_2da_changed)
        filter_edit.textChanged.connect(on_filter)
        table.cellDoubleClicked.connect(on_cell_dbl_click)

        load_2da(combo.currentText())
        dlg.exec()

    # ── Logging ───────────────────────────────────────────────

    def _log(self, msg: str):
        self.console.appendPlainText(msg)
