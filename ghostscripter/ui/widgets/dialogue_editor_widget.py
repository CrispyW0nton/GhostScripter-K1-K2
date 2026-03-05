"""
GhostScripter-K1-K2 — Visual Dialogue Tree Editor
Node graph view with inspector panel.
"""
import math
from typing import Optional, List, Dict

from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal, QTimer
from PyQt5.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QPainterPath,
    QLinearGradient,
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGraphicsView,
    QGraphicsScene, QGraphicsItem, QGraphicsRectItem, QGraphicsLineItem,
    QGraphicsTextItem, QGraphicsPathItem, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTreeWidget, QTreeWidgetItem, QGroupBox,
    QFormLayout, QScrollArea, QListWidget, QListWidgetItem,
    QComboBox, QFrame, QInputDialog, QMessageBox,
)

from ghostscripter.core.models.dialogue import (
    DialogueFile, DialogueNode, DialogueBranch,
    DialogueConditional, DialogueAction, create_simple_dialogue,
)


# ── Node Graphics Item ────────────────────────────────────────

class DialogueNodeItem(QGraphicsItem):
    """Visual card for a single dialogue node."""

    WIDTH = 220
    HEIGHT = 80

    def __init__(self, node: DialogueNode):
        super().__init__()
        self.node = node
        self.is_selected_node = False
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self._hover = False
        self.setPos(node.position_x, node.position_y)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def paint(self, painter: QPainter, option, widget):
        rect = QRectF(0, 0, self.WIDTH, self.HEIGHT)

        # Background color by speaker type
        if self.node.speaker == "Player":
            bg_color = QColor("#1a3a5c")
            header_color = QColor("#094771")
            header_text_color = QColor("#9cdcfe")
        elif self.node.speaker == "":
            bg_color = QColor("#2d2d30")
            header_color = QColor("#3c3c3c")
            header_text_color = QColor("#969696")
        else:
            bg_color = QColor("#2d1a1a")
            header_color = QColor("#4a1a1a")
            header_text_color = QColor("#f48771")

        painter.setRenderHint(QPainter.Antialiasing)

        # Shadow
        shadow_rect = rect.adjusted(3, 3, 3, 3)
        painter.fillPath(self._rounded_rect(shadow_rect, 6), QColor(0, 0, 0, 60))

        # Main body
        painter.fillPath(self._rounded_rect(rect, 5), bg_color)

        # Border
        if self.isSelected() or self.is_selected_node:
            painter.setPen(QPen(QColor("#0078d4"), 2))
        elif self._hover:
            painter.setPen(QPen(QColor("#555555"), 1))
        else:
            painter.setPen(QPen(QColor("#3c3c3c"), 1))
        painter.drawPath(self._rounded_rect(rect, 5))

        # Header bar
        header_rect = QRectF(0, 0, self.WIDTH, 22)
        header_path = QPainterPath()
        header_path.addRoundedRect(header_rect, 5, 5)
        # Clip to only top rounded corners
        clip_path = QPainterPath()
        clip_path.addRect(QRectF(0, 11, self.WIDTH, 11))
        combined = header_path.united(clip_path)
        painter.fillPath(combined, header_color)

        # Node ID badge
        painter.setPen(QColor(header_text_color.name()))
        painter.setFont(QFont("Consolas", 7, QFont.Bold))
        painter.drawText(QRectF(6, 4, 50, 14), Qt.AlignLeft,
                         f"#{self.node.node_id}")

        # Speaker label
        speaker = self.node.speaker or "—"
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.drawText(QRectF(30, 4, self.WIDTH - 40, 14), Qt.AlignCenter, speaker)

        # Dialogue text
        painter.setPen(QColor("#d4d4d4"))
        painter.setFont(QFont("Segoe UI", 8))
        text = self.node.short_text() or "(empty)"
        painter.drawText(QRectF(8, 26, self.WIDTH - 16, self.HEIGHT - 32),
                         Qt.AlignTop | Qt.TextWordWrap, text)

        # Branch count indicator
        if self.node.branches:
            painter.setPen(QColor("#4ec9b0"))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(QRectF(0, self.HEIGHT - 16, self.WIDTH - 6, 14),
                             Qt.AlignRight, f"↳ {len(self.node.branches)} branch(es)")

    def _rounded_rect(self, rect: QRectF, radius: float) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            self.node.position_x = value.x()
            self.node.position_y = value.y()
        return super().itemChange(change, value)


# ── Dialogue Graph Scene ──────────────────────────────────────

class DialogueGraphScene(QGraphicsScene):

    node_selected = pyqtSignal(object)  # DialogueNode

    def __init__(self, dialogue: DialogueFile):
        super().__init__()
        self.dialogue = dialogue
        self.node_items: Dict[int, DialogueNodeItem] = {}
        self.edge_items: List[QGraphicsPathItem] = []
        self._render()

    def _render(self):
        self.clear()
        self.node_items.clear()
        self.edge_items.clear()

        if not self.dialogue:
            return

        # Layout nodes if no positions set
        self._auto_layout()

        # Create node items
        for node in self.dialogue.nodes:
            item = DialogueNodeItem(node)
            self.node_items[node.node_id] = item
            self.addItem(item)

        # Draw edges
        self._draw_edges()

    def _auto_layout(self):
        """Assign positions for nodes with no position."""
        nodes_no_pos = [
            n for n in self.dialogue.nodes
            if n.position_x == 0 and n.position_y == 0
        ]
        if not nodes_no_pos:
            return

        # Simple layered layout
        col_width = DialogueNodeItem.WIDTH + 40
        row_height = DialogueNodeItem.HEIGHT + 40

        for i, node in enumerate(self.dialogue.nodes):
            if node.position_x == 0 and node.position_y == 0:
                col = 0
                row = i
                node.position_x = col * col_width + 20
                node.position_y = row * row_height + 20

    def _draw_edges(self):
        for node in self.dialogue.nodes:
            source_item = self.node_items.get(node.node_id)
            if not source_item:
                continue
            for branch in node.branches:
                target_item = self.node_items.get(branch.target_node_id)
                if not target_item:
                    continue
                path_item = self._make_edge(source_item, target_item,
                                             branch.text)
                self.edge_items.append(path_item)
                self.addItem(path_item)

    def _make_edge(self, source: DialogueNodeItem,
                   target: DialogueNodeItem, label: str = "") -> QGraphicsPathItem:
        sx = source.pos().x() + DialogueNodeItem.WIDTH / 2
        sy = source.pos().y() + DialogueNodeItem.HEIGHT
        tx = target.pos().x() + DialogueNodeItem.WIDTH / 2
        ty = target.pos().y()

        path = QPainterPath()
        path.moveTo(sx, sy)
        # Bezier curve
        ctrl_y = (sy + ty) / 2
        path.cubicTo(sx, ctrl_y, tx, ctrl_y, tx, ty)

        item = QGraphicsPathItem(path)
        item.setPen(QPen(QColor("#3c6e8c"), 1.5, Qt.SolidLine,
                         Qt.RoundCap, Qt.RoundJoin))
        item.setZValue(-1)
        return item

    def refresh(self):
        self._render()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        items = self.selectedItems()
        for item in items:
            if isinstance(item, DialogueNodeItem):
                self.node_selected.emit(item.node)
                return


# ── Inspector Panel ───────────────────────────────────────────

class NodeInspector(QWidget):

    node_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._node: Optional[DialogueNode] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("Node Inspector")
        header.setStyleSheet("background:#2d2d30; color:#cccccc; font-weight:bold; "
                              "padding:5px 8px; border-bottom:1px solid #3c3c3c;")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; background:#252526; }")
        content = QWidget()
        content.setStyleSheet("background:#252526;")
        self.form_layout = QVBoxLayout(content)
        self.form_layout.setContentsMargins(8, 8, 8, 8)
        self.form_layout.setSpacing(8)

        # Node ID (read-only)
        id_row = QWidget()
        id_row.setStyleSheet("background:transparent;")
        id_lay = QHBoxLayout(id_row)
        id_lay.setContentsMargins(0, 0, 0, 0)
        id_lay.addWidget(QLabel("Node ID:"))
        self.node_id_label = QLabel("—")
        self.node_id_label.setStyleSheet("color:#569cd6; font-family:Consolas;")
        id_lay.addWidget(self.node_id_label)
        id_lay.addStretch()
        self.form_layout.addWidget(id_row)

        # Speaker
        self.form_layout.addWidget(self._lbl("Speaker:"))
        self.speaker_input = QLineEdit()
        self.speaker_input.setPlaceholderText("NPC tag or 'Player'")
        self.speaker_input.textChanged.connect(self._on_changed)
        self.form_layout.addWidget(self.speaker_input)

        # Text
        self.form_layout.addWidget(self._lbl("Dialogue Text:"))
        self.text_input = QTextEdit()
        self.text_input.setFixedHeight(80)
        self.text_input.textChanged.connect(self._on_changed)
        self.form_layout.addWidget(self.text_input)

        # Branches section
        self.form_layout.addWidget(self._section("Branches"))
        self.branches_list = QListWidget()
        self.branches_list.setStyleSheet("""
            QListWidget { background:#1e1e1e; border:1px solid #3c3c3c; min-height:60px; }
            QListWidget::item { color:#cccccc; padding:3px; }
            QListWidget::item:selected { background:#094771; }
        """)
        self.form_layout.addWidget(self.branches_list)

        add_branch_btn = QPushButton("+ Add Branch")
        add_branch_btn.clicked.connect(self._add_branch)
        add_branch_btn.setStyleSheet("""
            QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;
                          border-radius:3px; padding:4px 8px; }
            QPushButton:hover { background:#4a4a4a; }
        """)
        self.form_layout.addWidget(add_branch_btn)

        # Conditionals
        self.form_layout.addWidget(self._section("Conditionals"))
        self.cond_label = QLabel("None")
        self.cond_label.setStyleSheet("color:#666666; font-size:8pt; padding:4px;")
        self.form_layout.addWidget(self.cond_label)

        # Actions
        self.form_layout.addWidget(self._section("Actions"))
        self.action_label = QLabel("None")
        self.action_label.setStyleSheet("color:#666666; font-size:8pt; padding:4px;")
        self.form_layout.addWidget(self.action_label)

        self.form_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

    def _lbl(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet("color:#969696; font-size:8pt;")
        return l

    def _section(self, text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet("color:#4ec9b0; font-weight:bold; font-size:8pt; "
                        "padding-top:6px; padding-bottom:2px; "
                        "border-bottom:1px solid #3c3c3c;")
        return l

    def load_node(self, node: DialogueNode):
        self._node = node
        self.node_id_label.setText(str(node.node_id))
        self.speaker_input.setText(node.speaker)
        self.text_input.setPlainText(node.text)

        self.branches_list.clear()
        for b in node.branches:
            target = f"→ Node {b.target_node_id}" if b.target_node_id >= 0 else "→ End"
            self.branches_list.addItem(f'[{b.branch_id}] "{b.text[:30]}…" {target}')

        if node.conditionals:
            self.cond_label.setText(
                "\n".join(c.describe() for c in node.conditionals)
            )
        else:
            self.cond_label.setText("None")

        if node.script_actions:
            self.action_label.setText(
                "\n".join(a.describe() for a in node.script_actions)
            )
        else:
            self.action_label.setText("None")

    def _on_changed(self):
        if self._node:
            self._node.speaker = self.speaker_input.text()
            self._node.text = self.text_input.toPlainText()
            self.node_changed.emit()

    def _add_branch(self):
        if not self._node:
            return
        text, ok = QInputDialog.getText(
            self, "New Branch", "Response text:"
        )
        if ok and text:
            self._node.add_branch(text)
            self.load_node(self._node)
            self.node_changed.emit()


# ── Dialogue Editor Widget ────────────────────────────────────

class DialogueEditorWidget(QWidget):

    def __init__(self, dialogue: Optional[DialogueFile] = None, parent=None):
        super().__init__(parent)
        self.dialogue = dialogue or create_simple_dialogue("new_dialogue", "npc_001")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        tb = self._build_toolbar()
        layout.addWidget(tb)

        # Horizontal splitter: graph | node list | inspector
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(2)

        # Graph view
        self.scene = DialogueGraphScene(self.dialogue)
        self.scene.node_selected.connect(self._on_node_selected)
        self.graph_view = QGraphicsView(self.scene)
        self.graph_view.setRenderHint(QPainter.Antialiasing)
        self.graph_view.setDragMode(QGraphicsView.RubberBandDrag)
        self.graph_view.setBackgroundBrush(QBrush(QColor("#1a1a1a")))
        self.graph_view.setStyleSheet("border:none;")
        split.addWidget(self.graph_view)

        # Node list
        list_panel = self._build_node_list()
        split.addWidget(list_panel)

        # Inspector
        self.inspector = NodeInspector()
        self.inspector.node_changed.connect(self._on_node_changed)
        split.addWidget(self.inspector)

        split.setSizes([550, 180, 240])
        layout.addWidget(split)

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

        lay.addWidget(btn("+ NPC Node", self._add_npc_node, True))
        lay.addWidget(btn("+ Player Node", self._add_player_node))
        lay.addWidget(btn("Delete Node", self._delete_selected_node))
        lay.addWidget(btn("Refresh Layout", self._refresh))
        lay.addWidget(btn("Validate", self._validate))
        lay.addStretch()

        self.dlg_name_label = QLabel(self.dialogue.name or "untitled.dlg")
        self.dlg_name_label.setStyleSheet("color:#569cd6;")
        lay.addWidget(self.dlg_name_label)

        return tb

    def _build_node_list(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background:#252526;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("Nodes")
        header.setStyleSheet("background:#2d2d30; color:#cccccc; font-weight:bold; "
                              "padding:5px 8px; border-bottom:1px solid #3c3c3c;")
        layout.addWidget(header)

        self.node_list = QListWidget()
        self.node_list.setStyleSheet("""
            QListWidget { background:#252526; border:none; }
            QListWidget::item { color:#cccccc; padding:4px 6px; }
            QListWidget::item:hover { background:#2a2d2e; }
            QListWidget::item:selected { background:#094771; }
        """)
        self.node_list.itemClicked.connect(self._on_list_node_clicked)
        layout.addWidget(self.node_list)

        self._refresh_node_list()
        return panel

    def _refresh_node_list(self):
        self.node_list.clear()
        for node in self.dialogue.nodes:
            speaker = node.speaker or "—"
            icon = "►" if speaker == "Player" else "◆"
            item = QListWidgetItem(f"{icon} [{node.node_id}] {speaker}: {node.short_text()}")
            item.setData(Qt.UserRole, node.node_id)
            if node.speaker == "Player":
                item.setForeground(QColor("#9cdcfe"))
            else:
                item.setForeground(QColor("#f48771"))
            self.node_list.addItem(item)

    # ── Actions ───────────────────────────────────────────────

    def _add_npc_node(self):
        text, ok = QInputDialog.getText(self, "New NPC Node", "NPC tag:")
        if ok:
            node = DialogueNode(
                node_id=len(self.dialogue.nodes),
                speaker=text or "npc_001",
                text="[NPC dialogue text here]",
                position_x=50 + len(self.dialogue.nodes) * 30,
                position_y=50 + len(self.dialogue.nodes) * 120,
            )
            self.dialogue.add_node(node)
            self._refresh()

    def _add_player_node(self):
        node = DialogueNode(
            node_id=len(self.dialogue.nodes),
            speaker="Player",
            text="[Player response here]",
            position_x=300 + len(self.dialogue.nodes) * 30,
            position_y=50 + len(self.dialogue.nodes) * 120,
        )
        self.dialogue.add_node(node)
        self._refresh()

    def _delete_selected_node(self):
        items = self.node_list.selectedItems()
        if not items:
            return
        node_id = items[0].data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "Delete Node",
            f"Delete node #{node_id}? All branches targeting it will be removed.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.dialogue.remove_node(node_id)
            self._refresh()

    def _refresh(self):
        self.scene.refresh()
        self._refresh_node_list()

    def _validate(self):
        issues = self.dialogue.validate_tree()
        if issues:
            msg = "\n".join(f"• {i}" for i in issues)
            QMessageBox.warning(self, "Validation Issues", msg)
        else:
            QMessageBox.information(self, "Validation", "✓ Dialogue tree is valid!")

    def _on_node_selected(self, node: DialogueNode):
        self.inspector.load_node(node)
        # Highlight in list
        for i in range(self.node_list.count()):
            item = self.node_list.item(i)
            if item.data(Qt.UserRole) == node.node_id:
                self.node_list.setCurrentItem(item)
                break

    def _on_list_node_clicked(self, item: QListWidgetItem):
        node_id = item.data(Qt.UserRole)
        node = self.dialogue.get_node(node_id)
        if node:
            self.inspector.load_node(node)
            # Center view on node
            node_item = self.scene.node_items.get(node_id)
            if node_item:
                self.graph_view.centerOn(node_item)
                node_item.setSelected(True)

    def _on_node_changed(self):
        self.scene.refresh()
        self._refresh_node_list()
