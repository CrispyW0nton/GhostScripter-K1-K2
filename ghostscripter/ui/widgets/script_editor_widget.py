"""
GhostScripter-K1-K2 — NSS Script Editor Widget
Syntax highlighting, line numbers, compile/decompile, function reference.
"""
import re
import subprocess
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, QRect, QSize, pyqtSignal
from PyQt5.QtGui import (
    QColor, QFont, QSyntaxHighlighter, QTextCharFormat,
    QPainter, QTextCursor, QPalette,
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QPlainTextEdit,
    QLabel, QPushButton, QToolBar, QAction, QLineEdit, QTreeWidget,
    QTreeWidgetItem, QMessageBox, QFileDialog, QTabWidget,
    QTextEdit, QComboBox, QFrame,
)

from ghostscripter.core.models.script import (
    ScriptFile, CompilationError,
    make_void_main_template, make_starting_conditional_template,
)
from ghostscripter.core.constants import (
    NWSCRIPT_KEYWORDS, NWSCRIPT_TYPES, KOTOR_COMMON_FUNCTIONS,
    COLOR_NSS_KEYWORD, COLOR_NSS_FUNCTION, COLOR_NSS_COMMENT,
    COLOR_NSS_STRING, COLOR_NSS_NUMBER, COLOR_NSS_TYPE, COLOR_NSS_CONSTANT,
)


# ── Line Number Area ──────────────────────────────────────────

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


# ── Code Editor ───────────────────────────────────────────────

class CodeEditor(QPlainTextEdit):
    """Plain text editor with line numbers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()

        # Font
        font = QFont("Consolas", 10)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setObjectName("scriptEditor")
        self.setTabStopDistance(28)

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 8 + self.fontMetrics().horizontalAdvance("9") * digits

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(),
                self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def highlight_current_line(self):
        extra = []
        if not self.isReadOnly():
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(QColor("#2d2d30"))
            sel.format.setProperty(0x100001, True)  # FullWidthSelection
            sel.cursor = self.textCursor()
            sel.cursor.clearSelection()
            extra.append(sel)
        self.setExtraSelections(extra)

    def paint_line_numbers(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#1e1e1e"))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#858585"))
                painter.setFont(self.font())
                painter.drawText(
                    0, top, self.line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignRight, str(block_number + 1)
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1


# ── NSS Syntax Highlighter ────────────────────────────────────

class NSSSyntaxHighlighter(QSyntaxHighlighter):

    def __init__(self, document):
        super().__init__(document)
        self.rules = self._build_rules()
        self._ml_comment_start = re.compile(r'/\*')
        self._ml_comment_end = re.compile(r'\*/')

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

        # Constants (ALL_CAPS identifiers)
        rules.append((re.compile(r'\b[A-Z][A-Z0-9_]{2,}\b'),
                      self._fmt(COLOR_NSS_CONSTANT)))

        # Function calls (CamelCase followed by '(')
        rules.append((re.compile(r'\b[A-Z][a-zA-Z0-9_]*(?=\s*\()'),
                      self._fmt(COLOR_NSS_FUNCTION)))

        # Preprocessor
        rules.append((re.compile(r'#\w+'),
                      self._fmt("#c586c0")))

        # Strings
        rules.append((re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"'),
                      self._fmt(COLOR_NSS_STRING)))

        # Numbers (int / float)
        rules.append((re.compile(r'\b\d+\.?\d*[fF]?\b'),
                      self._fmt(COLOR_NSS_NUMBER)))

        # Single-line comments
        rules.append((re.compile(r'//[^\n]*'),
                      self._fmt(COLOR_NSS_COMMENT, italic=True)))

        return rules

    def highlightBlock(self, text: str):
        # Apply inline rules
        for pattern, fmt in self.rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

        # Multi-line comments
        self.setCurrentBlockState(0)
        start_index = 0
        if self.previousBlockState() != 1:
            m = self._ml_comment_start.search(text)
            start_index = m.start() if m else -1

        comment_fmt = self._fmt(COLOR_NSS_COMMENT, italic=True)
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
    Full NSS script editor with:
    - Syntax-highlighted code editor with line numbers
    - Function reference sidebar
    - Compile / decompile toolbar
    - Output console
    """

    script_saved = pyqtSignal(str)   # emits script name

    def __init__(self, script: Optional[ScriptFile] = None,
                 project=None, parent=None):
        super().__init__(parent)
        self.script = script or ScriptFile(name="untitled",
                                            source_code=make_void_main_template())
        self.project = project
        self._setup_ui()
        self._load_script()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ──────────────────────────────────────────
        tb = self._build_toolbar()
        layout.addWidget(tb)

        # ── Horizontal splitter: editor | function ref ──────
        h_split = QSplitter(Qt.Horizontal)
        h_split.setHandleWidth(2)

        # Code editor
        self.editor = CodeEditor()
        self.highlighter = NSSSyntaxHighlighter(self.editor.document())
        h_split.addWidget(self.editor)

        # Function reference panel
        func_panel = self._build_function_panel()
        h_split.addWidget(func_panel)
        h_split.setSizes([750, 280])
        h_split.setStretchFactor(0, 1)
        h_split.setStretchFactor(1, 0)

        # ── Vertical splitter: editor+ref | console ─────────
        v_split = QSplitter(Qt.Vertical)
        v_split.setHandleWidth(2)
        v_split.addWidget(h_split)

        # Output console
        console_panel = self._build_console()
        v_split.addWidget(console_panel)
        v_split.setSizes([550, 130])
        v_split.setStretchFactor(0, 1)
        v_split.setStretchFactor(1, 0)

        layout.addWidget(v_split)

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
                b.setStyleSheet("""
                    QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;
                                  border-radius:3px; padding:2px 10px; font-weight:bold; }
                    QPushButton:hover { background:#1a8fe0; }
                """)
            else:
                b.setStyleSheet("""
                    QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                                  border-radius:3px; padding:2px 8px; }
                    QPushButton:hover { background:#4a4a4a; color:white; }
                """)
            return b

        layout.addWidget(btn("Open", self._open_script, "Open NSS file"))
        layout.addWidget(btn("Save", self._save_script, "Save file (Ctrl+S)"))

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#3c3c3c;")
        layout.addWidget(sep)

        layout.addWidget(btn("⚙ Compile → NCS", self._compile, "Compile NSS to NCS", True))
        layout.addWidget(btn("Decompile NCS", self._decompile, "Decompile NCS file"))

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color:#3c3c3c;")
        layout.addWidget(sep2)

        # Template picker
        layout.addWidget(QLabel("Template:"))
        self.template_combo = QComboBox()
        self.template_combo.addItems(["void main()", "StartingConditional()"])
        self.template_combo.currentTextChanged.connect(self._insert_template)
        self.template_combo.setFixedWidth(160)
        self.template_combo.setStyleSheet("""
            QComboBox { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                        border-radius:3px; padding:2px 6px; }
        """)
        layout.addWidget(self.template_combo)

        layout.addStretch()

        # Script info
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

        # Header
        header = QLabel("Function Reference")
        header.setStyleSheet("background:#2d2d30; color:#cccccc; font-weight:bold; "
                              "padding:5px 8px; border-bottom:1px solid #3c3c3c;")
        layout.addWidget(header)

        # Search
        self.func_search = QLineEdit()
        self.func_search.setPlaceholderText("Search functions…")
        self.func_search.textChanged.connect(self._filter_functions)
        self.func_search.setStyleSheet("""
            QLineEdit { background:#3c3c3c; color:#cccccc; border:none;
                        border-bottom:1px solid #3c3c3c; padding:5px 8px; }
        """)
        layout.addWidget(self.func_search)

        # Tree
        self.func_tree = QTreeWidget()
        self.func_tree.setHeaderHidden(True)
        self.func_tree.setStyleSheet("""
            QTreeWidget { background:#252526; border:none; }
            QTreeWidget::item { color:#cccccc; padding:2px 4px; }
            QTreeWidget::item:hover { background:#2a2d2e; }
            QTreeWidget::item:selected { background:#094771; }
        """)
        self.func_tree.itemDoubleClicked.connect(self._insert_function)
        self._populate_function_tree()
        layout.addWidget(self.func_tree)

        # Detail label
        self.func_detail = QLabel()
        self.func_detail.setWordWrap(True)
        self.func_detail.setStyleSheet("color:#969696; font-size:8pt; padding:4px 8px; "
                                        "background:#1e1e1e; border-top:1px solid #3c3c3c;")
        self.func_detail.setFixedHeight(60)
        layout.addWidget(self.func_detail)

        self.func_tree.itemClicked.connect(self._show_func_detail)
        return panel

    def _populate_function_tree(self, filter_text: str = ""):
        self.func_tree.clear()
        ft = filter_text.lower()
        for category, funcs in KOTOR_COMMON_FUNCTIONS.items():
            filtered = [f for f in funcs if not ft or ft in f["name"].lower()]
            if not filtered:
                continue
            cat_item = QTreeWidgetItem([category])
            cat_item.setForeground(0, QColor("#dcdcaa"))
            cat_item.setExpanded(True)
            for func in filtered:
                sig = f"{func['name']}({', '.join(func['params'])})"
                f_item = QTreeWidgetItem([sig])
                f_item.setForeground(0, QColor("#9cdcfe"))
                f_item.setData(0, Qt.UserRole, func)
                cat_item.addChild(f_item)
            self.func_tree.addTopLevelItem(cat_item)

    def _filter_functions(self, text: str):
        self._populate_function_tree(text)

    def _show_func_detail(self, item, col):
        data = item.data(0, Qt.UserRole)
        if data:
            self.func_detail.setText(
                f"<b style='color:#dcdcaa'>{data['name']}</b>"
                f" → <i style='color:#4ec9b0'>{data['returns']}</i><br>"
                f"<span style='color:#969696'>{data['description']}</span>"
            )

    def _insert_function(self, item, col):
        data = item.data(0, Qt.UserRole)
        if data:
            params = ", ".join(data["params"])
            snippet = f"{data['name']}({params})"
            cursor = self.editor.textCursor()
            cursor.insertText(snippet)
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
        clear_btn.setStyleSheet("QPushButton { background:#3c3c3c; color:#969696; "
                                 "border:none; font-size:8pt; }")
        clear_btn.clicked.connect(lambda: self.console.clear())
        hdr_lay.addWidget(clear_btn)
        layout.addWidget(hdr)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setObjectName("outputConsole")
        layout.addWidget(self.console)
        return panel

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
            self._log(f"Opened: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _save_script(self):
        if not self.script.file_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Script", self.script.name + ".nss",
                "NWScript (*.nss);;All Files (*)"
            )
            if not path:
                return
            self.script.file_path = Path(path)
            self.script.name = Path(path).stem

        self.script.source_code = self.editor.toPlainText()
        if self.script.save_to_disk():
            self._log(f"✓ Saved: {self.script.file_path}")
            self.script_saved.emit(self.script.name)
        else:
            self._log("✗ Save failed")

    # ── Compile ───────────────────────────────────────────────

    def _compile(self):
        """Attempt NSS compilation via nwnnsscomp."""
        self.script.source_code = self.editor.toPlainText()
        if not self.script.file_path:
            self._save_script()

        if not self.script.file_path:
            self._log("✗ Please save the script first.")
            return

        self._log("→ Compiling...")

        # Try to find compiler
        compiler_paths = [
            "nwnnsscomp.exe", "nwnnsscomp",
            Path(__file__).parent.parent.parent / "tools" / "nwnnsscomp.exe"
        ]
        compiler = None
        for cp in compiler_paths:
            try:
                result = subprocess.run([str(cp), "--help"],
                                         capture_output=True, timeout=2)
                compiler = str(cp)
                break
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        if not compiler:
            self._log("⚠ nwnnsscomp not found — showing syntax check only.")
            self._syntax_check_only()
            return

        try:
            result = subprocess.run(
                [compiler, "-c", str(self.script.file_path)],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                self._log("✓ Compilation successful!")
                self.script.errors = []
            else:
                self._log("✗ Compilation failed:")
                for line in result.stderr.splitlines():
                    self._log(f"  {line}")
        except subprocess.TimeoutExpired:
            self._log("✗ Compilation timed out.")
        except Exception as e:
            self._log(f"✗ Error: {e}")

    def _syntax_check_only(self):
        """Basic NSS syntax check without compiler."""
        code = self.editor.toPlainText()
        issues = []
        open_braces = code.count("{")
        close_braces = code.count("}")
        if open_braces != close_braces:
            issues.append(f"Brace mismatch: {open_braces} open, {close_braces} close")
        open_parens = code.count("(")
        close_parens = code.count(")")
        if open_parens != close_parens:
            issues.append(f"Parenthesis mismatch: {open_parens} open, {close_parens} close")
        if issues:
            for i in issues:
                self._log(f"⚠ {i}")
        else:
            self._log("✓ Basic syntax check passed (no compiler available)")

    def _decompile(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open NCS File", "", "Compiled Script (*.ncs)"
        )
        if not path:
            return
        self._log(f"→ Decompile: {path}")
        self._log("⚠ External decompiler not found. Showing file info.")
        size = Path(path).stat().st_size
        self._log(f"  File size: {size} bytes")
        self._log("  Tip: Use xoreos-tools ncsdecomp for decompilation.")

    def _insert_template(self, name: str):
        if "StartingConditional" in name:
            self.editor.setPlainText(make_starting_conditional_template())
        else:
            self.editor.setPlainText(make_void_main_template())

    def _log(self, msg: str):
        self.console.appendPlainText(msg)
