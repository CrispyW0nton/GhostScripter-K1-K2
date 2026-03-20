"""
GhostScripter-K1-K2 — Visual Dialogue Tree Editor  (v2)
=========================================================
Full field set matching KotOR 1 & 2 GFF DLG spec:

Node Inspector exposes:
  Text, Speaker, Listener, VO_ResRef, Sound, SoundExists
  Script (Script1), Script2 (TSL), Script params (TSL)
  Delay, WaitFlags, Quest, QuestEntry, PlotIndex, PlotXP%
  CameraAngle; TSL: CameraID, CameraAnimation, CamFOV,
    CamHeight, CamVidEffect, TarHeightOffset
  NodeUnskippable, AlienRaceNode, Emotion, FacialAnim (TSL)
  RecordVO, RecordNoVOOverride, VOTextChanged (TSL)
  Comment, Branches (full link fields), AnimList

Dialogue Properties Panel exposes all DialogueFile top-level
  fields: EndConversation, EndConverAbort, Skippable,
  DelayEntry, DelayReply, AmbientTrack, AnimatedCut,
  CameraModel, ConversationType, ComputerType, OldHitCheck,
  UnequipItems, UnequipHItem
"""
from __future__ import annotations

import math
from typing import List, Dict, Set

from qtpy.QtCore import Qt, QRectF, QPointF, Signal, QTimer, QObject
from qtpy.QtGui import (
    QColor, QPainter, QPen, QBrush, QFont, QPainterPath,
    QLinearGradient, QTransform, QWheelEvent,
)
from qtpy.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGraphicsView,
    QGraphicsScene, QGraphicsItem, QGraphicsObject, QGraphicsRectItem, QGraphicsLineItem,
    QGraphicsTextItem, QGraphicsPathItem, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTreeWidget, QTreeWidgetItem, QGroupBox,
    QFormLayout, QScrollArea, QListWidget, QListWidgetItem,
    QComboBox, QFrame, QInputDialog, QMessageBox, QTabWidget,
    QCheckBox, QSpinBox, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QToolButton,
    QSizePolicy, QStackedWidget,
)

import logging
import time as _time
from pathlib import Path

from ghostscripter.core.models.dialogue import (
    DialogueFile, DialogueNode, DialogueBranch,
    DialogueConditional, DialogueAction, DLGAnimation,
    create_simple_dialogue,
)

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Shared style helpers
# ─────────────────────────────────────────────────────────────────

_DARK = "#252526"
_PANEL = "#2d2d30"
_BORDER = "#3c3c3c"
_BLUE = "#0078d4"
_TEAL = "#4ec9b0"
_ORANGE = "#f48771"
_LTBLUE = "#9cdcfe"
_GREY = "#969696"
_WHITE = "#cccccc"
_DARK2 = "#1e1e1e"

_BTN_STYLE = """
QPushButton { background:#3c3c3c; color:#cccccc; border:1px solid #555;
              border-radius:3px; padding:2px 8px; }
QPushButton:hover { background:#4a4a4a; color:white; }
QPushButton:pressed { background:#2a2a2a; }
"""
_BTN_PRIMARY = """
QPushButton { background:#0078d4; color:white; border:1px solid #1a8fe0;
              border-radius:3px; padding:2px 10px; font-weight:bold; }
QPushButton:hover { background:#1a8fe0; }
QPushButton:pressed { background:#006cbf; }
"""
_INPUT_STYLE = """
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background:#1e1e1e; color:#cccccc; border:1px solid #3c3c3c;
    border-radius:2px; padding:2px 4px; selection-background-color:#094771;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus { border-color:#0078d4; }
QComboBox::drop-down { border:none; }
QComboBox QAbstractItemView { background:#2d2d30; color:#cccccc;
    selection-background-color:#094771; border:1px solid #3c3c3c; }
"""
_CHECK_STYLE = """
QCheckBox { color:#cccccc; spacing:5px; }
QCheckBox::indicator { width:14px; height:14px; border:1px solid #555;
    border-radius:2px; background:#1e1e1e; }
QCheckBox::indicator:checked { background:#0078d4; border-color:#1a8fe0; }
"""
_TABLE_STYLE = """
QTableWidget { background:#1e1e1e; color:#cccccc; border:1px solid #3c3c3c;
    gridline-color:#3c3c3c; selection-background-color:#094771; }
QTableWidget::item { padding:2px 4px; }
QHeaderView::section { background:#2d2d30; color:#969696; border:none;
    border-right:1px solid #3c3c3c; padding:3px; }
"""
_LIST_STYLE = """
QListWidget { background:#1e1e1e; border:1px solid #3c3c3c; }
QListWidget::item { color:#cccccc; padding:3px 6px; }
QListWidget::item:hover { background:#2a2d2e; }
QListWidget::item:selected { background:#094771; }
"""
_SCROLL_STYLE = "QScrollArea { border:none; background:#252526; }"


def _lbl(text, color=_GREY, bold=False):
    l = QLabel(text)
    style = f"color:{color}; font-size:8pt;"
    if bold:
        style += " font-weight:bold;"
    l.setStyleSheet(style)
    return l


def _section_lbl(text):
    l = QLabel(text)
    l.setStyleSheet(
        f"color:{_TEAL}; font-weight:bold; font-size:8pt; "
        f"padding-top:6px; padding-bottom:2px; border-bottom:1px solid {_BORDER};"
    )
    return l


def _make_line_edit(placeholder="", style=True) -> QLineEdit:
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    if style:
        w.setStyleSheet(_INPUT_STYLE)
    return w


def _make_spin(minimum=-99999, maximum=99999, val=0) -> QSpinBox:
    w = QSpinBox()
    w.setRange(minimum, maximum)
    w.setValue(val)
    w.setStyleSheet(_INPUT_STYLE)
    return w


def _make_dspin(minimum=-9999.0, maximum=9999.0, val=0.0, decimals=3) -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(minimum, maximum)
    w.setValue(val)
    w.setDecimals(decimals)
    w.setStyleSheet(_INPUT_STYLE)
    return w


# ─────────────────────────────────────────────────────────────────
# Node Graphics Items
# ─────────────────────────────────────────────────────────────────

def _node_key(node: "DialogueNode") -> str:
    """Unique scene key for a node — 'e{id}' for entries, 'r{id}' for replies.

    CRITICAL: entries and replies both use 0-based indices so node_id alone
    is NOT unique.  Always use this key when keying dicts or looking up items.
    """
    prefix = "r" if node.node_type == "reply" else "e"
    return f"{prefix}{node.node_id}"


class DialogueNodeItem(QGraphicsObject):
    """Visual card for a single dialogue node.

    Uses QGraphicsObject (not QGraphicsItem) so that itemChange fires
    signals, which EdgeItem objects listen to for live position updates.
    """

    # Emitted whenever this node is moved so connected EdgeItems can
    # immediately repaint their paths (Blueprint-style live wires).
    position_changed = Signal()

    WIDTH = 230
    HEIGHT = 82
    PORT_R = 6   # port circle radius

    def __init__(self, node: "DialogueNode", tlk=None):
        super().__init__()
        self.node = node
        self.key = _node_key(node)   # unique scene key
        self.tlk = tlk  # Optional TLKFile for resolving text_strrefs
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self._hover = False
        self.setPos(node.position_x, node.position_y)

    def boundingRect(self) -> QRectF:
        # extend bounding rect to include port circles that stick outside the card
        r = self.PORT_R
        return QRectF(-r, 0, self.WIDTH + r * 2, self.HEIGHT)

    def out_port_scene(self) -> "QPointF":
        """Scene-coordinate centre of the output port (right side).

        Uses item.x()/y() (the actual QGraphicsItem scene position) so this
        is always correct even after the node has been dragged.
        """
        return QPointF(self.x() + self.WIDTH,
                       self.y() + self.HEIGHT / 2)

    def in_port_scene(self) -> "QPointF":
        """Scene-coordinate centre of the input port (left side)."""
        return QPointF(self.x(),
                       self.y() + self.HEIGHT / 2)

    def paint(self, painter: QPainter, option, widget):
        rect = QRectF(0, 0, self.WIDTH, self.HEIGHT)

        if self.node.speaker == "Player":
            bg_color = QColor("#1a3a5c")
            header_color = QColor("#094771")
            header_text_color = QColor("#9cdcfe")
            type_badge = "REPLY"
        elif self.node.speaker == "":
            bg_color = QColor("#2d2d30")
            header_color = QColor("#3c3c3c")
            header_text_color = QColor("#969696")
            type_badge = "?"
        else:
            bg_color = QColor("#2d1a1a")
            header_color = QColor("#4a1a1a")
            header_text_color = QColor("#f48771")
            type_badge = "ENTRY"

        painter.setRenderHint(QPainter.Antialiasing)

        # Shadow
        shadow_rect = rect.adjusted(3, 3, 3, 3)
        painter.fillPath(self._rounded_rect(shadow_rect, 6), QColor(0, 0, 0, 60))

        # Main body
        painter.fillPath(self._rounded_rect(rect, 5), bg_color)

        # Border
        if self.isSelected():
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
        clip_path = QPainterPath()
        clip_path.addRect(QRectF(0, 11, self.WIDTH, 11))
        painter.fillPath(header_path.united(clip_path), header_color)

        # Node ID badge
        painter.setPen(QColor(header_text_color.name()))
        painter.setFont(QFont("Consolas", 7, QFont.Bold))
        painter.drawText(QRectF(6, 4, 60, 14), Qt.AlignLeft,
                         f"#{self.node.node_id}")

        # Type badge
        painter.drawText(QRectF(self.WIDTH - 55, 4, 50, 14), Qt.AlignRight,
                         type_badge)

        # Speaker
        painter.setPen(QColor(header_text_color.name()))
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        spk = self.node.speaker or "—"
        painter.drawText(QRectF(6, 24, self.WIDTH - 12, 16), Qt.AlignLeft,
                         spk[:30])

        # Text — resolved via TLK if available (real game DLG files use strrefs)
        painter.setPen(QColor("#cccccc"))
        painter.setFont(QFont("Segoe UI", 7))
        short = self.node.short_text(45, tlk=self.tlk)
        painter.drawText(QRectF(6, 42, self.WIDTH - 12, 32),
                         Qt.AlignLeft | Qt.TextWordWrap, short)

        # Script indicator
        if self.node.script1:
            painter.setPen(QColor("#4ec9b0"))
            painter.setFont(QFont("Consolas", 6))
            painter.drawText(QRectF(6, self.HEIGHT - 12, self.WIDTH - 42, 10),
                             Qt.AlignLeft, f"▷ {self.node.script1[:20]}")

        # Audio indicator — shown when VO resref is set
        if self.node.vo_resref:
            painter.setPen(QColor("#dcdcaa"))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(QRectF(self.WIDTH - 38, self.HEIGHT - 12, 32, 10),
                             Qt.AlignRight, "🔊 VO")

        # ── Connection ports (like Unreal Blueprint pins) ──────────────
        r = self.PORT_R
        # Input port (left edge, centre)
        in_pt = QPointF(0, self.HEIGHT / 2)
        painter.setPen(QPen(QColor("#555555"), 1.5))
        painter.setBrush(QBrush(QColor("#1e1e1e")))
        painter.drawEllipse(in_pt, r, r)
        # Output port (right edge, centre)
        out_pt = QPointF(self.WIDTH, self.HEIGHT / 2)
        painter.setPen(QPen(QColor("#555555"), 1.5))
        # Colour output port by type
        if self.node.node_type == "reply":
            painter.setBrush(QBrush(QColor("#094771")))   # player blue
        else:
            painter.setBrush(QBrush(QColor("#4a1a1a")))   # npc red
        painter.drawEllipse(out_pt, r, r)

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

    # ── Grid snapping ──────────────────────────────────────────────────
    # UE NodeSnappingManager snaps to a configurable grid (default 16 px).
    # We use the same 16-px grid so nodes align cleanly.
    SNAP_GRID = 16

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            # Snap to 16-px grid — mirrors UE NodeSnappingManager behaviour
            g = self.SNAP_GRID
            snapped_x = round(value.x() / g) * g
            snapped_y = round(value.y() / g) * g
            return QPointF(snapped_x, snapped_y)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.node.position_x = value.x()
            self.node.position_y = value.y()
            # Notify connected EdgeItems to repaint in real-time
            self.position_changed.emit()
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        """Right-click context menu — mirrors UE Blueprint node context menu."""
        from qtpy.QtWidgets import QMenu, QAction
        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu {{ background:{_DARK}; color:{_WHITE}; border:1px solid {_BORDER}; }}"
            f"QMenu::item:selected {{ background:{_BLUE}; }}"
        )
        scene = self.scene()

        # ── Connect to … ──────────────────────────────────────────────
        connect_menu = menu.addMenu("🔗 Connect to…")
        connect_menu.setStyleSheet(menu.styleSheet())
        if scene and hasattr(scene, 'dialogue'):
            dlg = scene.dialogue
            is_entry = (self.node.node_type == "entry")
            # Entry nodes connect to reply nodes, and vice-versa
            candidates = dlg.replies if is_entry else dlg.entries
            # Filter out already-connected targets
            connected_ids = {b.target_node_id for b in self.node.branches}
            for cand in candidates:
                if cand.node_id in connected_ids:
                    continue  # already wired
                snippet = (cand.text or "")[:40]
                lbl = f"{'Reply' if is_entry else 'Entry'} #{cand.node_id}  {cand.speaker}  — {snippet}"
                act = connect_menu.addAction(lbl)
                act.setData(cand.node_id)
            if not connect_menu.actions():
                connect_menu.addAction("(no available targets)").setEnabled(False)

        menu.addSeparator()
        add_branch_act  = menu.addAction("➕ Add Branch")
        del_node_act    = menu.addAction("🗑 Delete Node")

        chosen = menu.exec_(event.screenPos())
        if chosen is None:
            return

        if scene and hasattr(scene, 'dialogue'):
            dlg = scene.dialogue
            if chosen == add_branch_act:
                # Delegate to the inspector-level add_branch via scene signal
                scene.node_selected.emit(self.node)
                # Emit a secondary signal that the widget listens to
                scene.add_branch_requested.emit(self.node)
            elif chosen == del_node_act:
                scene.delete_node_requested.emit(self.node)
            elif chosen.data() is not None:
                # Connect-to chosen
                tid = chosen.data()
                self.node.add_branch("", tid)
                scene.refresh()
                scene.node_selected.emit(self.node)


# -----------------------------------------------------------------
# Zoom-able, pannable graph view
# -----------------------------------------------------------------

class ZoomableGraphView(QGraphicsView):
    """QGraphicsView with mouse-wheel zoom and middle/space-bar pan.

    Controls
    --------
    Zoom:       Scroll wheel (anchored to cursor position)
    Pan:        Middle-click drag  OR  Space + left-drag
    Select:     Left-click on node
    Move node:  Left-drag on node
    Fit view:   Double-click on empty canvas  OR  toolbar button
    Reset zoom: Ctrl+0
    """

    _MIN_ZOOM   = 0.04   # 4 % — fits very large trees
    _MAX_ZOOM   = 4.0
    _ZOOM_FACTOR = 1.12  # gentler per-notch step

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._zoom_level = 1.0
        self._panning    = False
        self._pan_last   = None
        self._space_held = False

        # ── Rendering ──────────────────────────────────────────────
        self.setRenderHints(
            QPainter.Antialiasing |
            QPainter.SmoothPixmapTransform |
            QPainter.TextAntialiasing
        )
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        # ── Background ─────────────────────────────────────────────
        self.setBackgroundBrush(QBrush(QColor("#1a1a1a")))
        self.setStyleSheet("border: none;")

        # ── Scroll bars — always visible so the user can see position ──
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # ── Transform anchors ──────────────────────────────────────
        # AnchorUnderMouse for zoom; AnchorViewCenter for resize
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

        # ── Drag mode: rubber-band for empty-area drag select ──────
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setRubberBandSelectionMode(Qt.IntersectsItemShape)

        # ── Scene rect: let Qt track item bounds but give generous margin ──
        self.setScene(scene)

    # ── Zoom ───────────────────────────────────────────────────────

    def wheelEvent(self, event):
        """Zoom in/out centred on the cursor, never letting scroll
        bars steal the event."""
        # Only zoom on vertical wheel; ignore horizontal (trackpad side-scroll)
        dy = event.angleDelta().y()
        if dy == 0:
            # Horizontal scroll — pass through
            super().wheelEvent(event)
            return

        factor = self._ZOOM_FACTOR if dy > 0 else 1.0 / self._ZOOM_FACTOR
        new_zoom = self._zoom_level * factor
        new_zoom = max(self._MIN_ZOOM, min(self._MAX_ZOOM, new_zoom))
        # Compute actual factor after clamping
        actual = new_zoom / self._zoom_level
        self._zoom_level = new_zoom
        self.scale(actual, actual)
        event.accept()   # prevent parent scrollArea stealing the event

    # ── Pan ────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._start_pan(event.pos())
            event.accept()
            return
        if event.button() == Qt.LeftButton and self._space_held:
            self._start_pan(event.pos())
            event.accept()
            return
        # Left-click on empty canvas → deselect; on node → let base handle
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_last is not None:
            delta = event.pos() - self._pan_last
            self._pan_last = event.pos()
            # Translate by scrolling (works at any zoom level)
            hsb = self.horizontalScrollBar()
            vsb = self.verticalScrollBar()
            hsb.setValue(hsb.value() - delta.x())
            vsb.setValue(vsb.value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() in (Qt.MiddleButton, Qt.LeftButton):
            self._stop_pan()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click on empty canvas → fit all."""
        item = self.itemAt(event.pos())
        if item is None and event.button() == Qt.LeftButton:
            self.fit_all()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _start_pan(self, pos):
        self._panning  = True
        self._pan_last = pos
        self.setDragMode(QGraphicsView.NoDrag)
        self.viewport().setCursor(Qt.ClosedHandCursor)

    def _stop_pan(self):
        self._panning  = False
        self._pan_last = None
        self.setDragMode(QGraphicsView.RubberBandDrag)
        cursor = Qt.OpenHandCursor if self._space_held else Qt.ArrowCursor
        self.viewport().setCursor(cursor)

    # ── Space-bar hold to enter pan mode (like Photoshop / Blender) ──

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.viewport().setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        # Ctrl+0 → reset zoom
        if event.key() == Qt.Key_0 and event.modifiers() & Qt.ControlModifier:
            self.reset_zoom()
            event.accept()
            return
        # F → fit view
        if event.key() == Qt.Key_F:
            self.fit_all()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.viewport().setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    # ── Fit / reset ────────────────────────────────────────────────

    def fit_all(self):
        """Fit all scene items into the viewport with padding."""
        sc = self.scene()
        if sc is None:
            return
        items = sc.items()
        if not items:
            return
        br = sc.itemsBoundingRect().adjusted(-60, -60, 60, 60)
        # Update the scene rect so scrollbars reflect reality
        sc.setSceneRect(br)
        self.fitInView(br, Qt.KeepAspectRatio)
        self._zoom_level = self.transform().m11()

    def reset_zoom(self):
        """Reset to 1:1 zoom."""
        self.resetTransform()
        self._zoom_level = 1.0


# -----------------------------------------------------------------
# Hierarchical layout helper (Sugiyama-style BFS layering)
# -----------------------------------------------------------------

class _HierarchicalLayout:
    """
    Assigns grid positions to dialogue nodes using a proper
    Sugiyama-style layered layout.

    Key design decisions for KotOR DLG structure:
    - Entries (NPC lines) and Replies (Player lines) have SEPARATE 0-based
      index spaces.  We use _node_key() throughout to avoid collisions.
    - Starters always point to Entry nodes.
    - Entry branches always point to Reply nodes.
    - Reply branches always point to Entry nodes.
    - So the natural layer assignment is:
        Layer 0 = starter entries (NPC)
        Layer 1 = their reply children (Player)
        Layer 2 = entries reached from those replies (NPC)
        ...alternating NPC / Player columns left to right.
    - Orphaned nodes go in a column after the main graph.
    """

    # Column width must give enough horizontal gap so Bezier control
    # points never cross (cx1 < cx2).  With ctrl_len = gap * 0.55 we need
    # gap > 0 → gap = COL_W - NODE_W.  We want cx1 = sx + ctrl_len and
    # cx2 = dx - ctrl_len to satisfy cx1 < cx2, i.e. 2*ctrl_len < gap.
    # With ctrl_len = 0.55*gap that means 1.1*gap < gap which is never
    # true for small gaps.  Solution: use a fixed generous gap of 160 px
    # so the Bezier arc is always visible and smooth.
    COL_W   = DialogueNodeItem.WIDTH + 160  # 390 px per column (160 px gap)
    ROW_H   = DialogueNodeItem.HEIGHT + 30  # 112 px per row
    X_ORIGIN = 40
    Y_ORIGIN = 40

    def __init__(self, dialogue: "DialogueFile"):
        self.dlg = dialogue

    def assign(self) -> Dict[str, QPointF]:
        """Return dict of node_key → QPointF position.

        Uses a strict O(V+E) BFS — each node is enqueued and visited
        EXACTLY ONCE.  Back-edges (is_child cross-links common in KotOR
        DLG files) are skipped the moment the destination has already been
        visited, so this can never loop regardless of the graph structure.
        """
        if not self.dlg.nodes:
            return {}

        # Build lookup maps keyed by node_id
        entry_map: Dict[int, "DialogueNode"] = {n.node_id: n for n in self.dlg.entries}
        reply_map: Dict[int, "DialogueNode"] = {n.node_id: n for n in self.dlg.replies}

        # Adjacency: node_key → [child node_key]  (deduplicated, no self-loops)
        children: Dict[str, List[str]] = {}
        for e in self.dlg.entries:
            ek = _node_key(e)
            seen_local: set = set()
            children[ek] = []
            for b in e.branches:
                if b.target_node_id >= 0:
                    rn = reply_map.get(b.target_node_id)
                    if rn:
                        rk = _node_key(rn)
                        if rk != ek and rk not in seen_local:
                            children[ek].append(rk)
                            seen_local.add(rk)
        for r in self.dlg.replies:
            rk = _node_key(r)
            seen_local = set()
            children[rk] = []
            for b in r.branches:
                if b.target_node_id >= 0:
                    en = entry_map.get(b.target_node_id)
                    if en:
                        ek = _node_key(en)
                        if ek != rk and ek not in seen_local:
                            children[rk].append(ek)
                            seen_local.add(ek)

        # Find starter entry keys
        starter_keys: List[str] = []
        for s in self.dlg.starters:
            if s.target_node_id >= 0:
                en = entry_map.get(s.target_node_id)
                if en:
                    k = _node_key(en)
                    if k not in starter_keys:
                        starter_keys.append(k)
        if not starter_keys and self.dlg.entries:
            starter_keys = [_node_key(self.dlg.entries[0])]

        # ── Strict O(V+E) BFS layer assignment ───────────────────────
        # Each node is visited EXACTLY ONCE — we use a `visited` set and
        # never re-enqueue.  This guarantees termination on any graph,
        # including KotOR DLGs that have cycles / back-edges (is_child).
        # Layer is assigned on first discovery (breadth-first order from
        # the starter entries), giving a clean left-to-right column layout.
        from collections import deque
        node_layer: Dict[str, int] = {}
        visited: set = set()

        queue: deque = deque()
        for k in starter_keys:
            if k not in visited:
                visited.add(k)
                node_layer[k] = 0
                queue.append(k)

        bfs_order: List[str] = []

        while queue:
            k = queue.popleft()   # O(1) with deque, unlike list.pop(0)
            bfs_order.append(k)
            current_layer = node_layer[k]
            for ck in children.get(k, []):
                if ck not in visited:          # visit each node exactly once
                    visited.add(ck)
                    node_layer[ck] = current_layer + 1
                    queue.append(ck)

        # Orphaned nodes (unreachable from starters) — place in extra column
        max_layer = max(node_layer.values(), default=0)
        orphan_keys = [_node_key(n) for n in self.dlg.nodes
                       if _node_key(n) not in node_layer]

        # Build layer → [node_key] preserving BFS order
        layer_nodes: Dict[int, List[str]] = {}
        for k in bfs_order:
            lay = node_layer[k]
            layer_nodes.setdefault(lay, []).append(k)

        positions: Dict[str, QPointF] = {}
        for lay, keys in sorted(layer_nodes.items()):
            x = self.X_ORIGIN + lay * self.COL_W
            for row_idx, k in enumerate(keys):
                y = self.Y_ORIGIN + row_idx * self.ROW_H
                positions[k] = QPointF(x, y)

        if orphan_keys:
            orphan_col = max_layer + 1
            orphan_x = self.X_ORIGIN + orphan_col * self.COL_W
            for row_idx, k in enumerate(orphan_keys):
                y = self.Y_ORIGIN + row_idx * self.ROW_H
                positions[k] = QPointF(orphan_x, y)

        return positions


# -----------------------------------------------------------------
# Dynamic edge (wire) item — updates in real-time when nodes move
# -----------------------------------------------------------------

class EdgeItem(QGraphicsPathItem):
    """A Bezier wire connecting one DialogueNodeItem output port to another's
    input port.  Subscribes to both nodes' position_changed signals so the
    path repaints instantly whenever either endpoint is dragged, exactly like
    Unreal Engine Blueprint wires.

    Arrowhead is drawn as a small filled child item at the tip.
    Branch labels are drawn as child QGraphicsTextItems.
    """

    def __init__(
        self,
        source: "DialogueNodeItem",
        dest: "DialogueNodeItem",
        pen: QPen,
        branch_index: int = 0,
        total_branches: int = 1,
        parent=None,
    ):
        super().__init__(parent)
        self.source = source
        self.dest = dest
        self._pen = pen
        self.branch_index = branch_index
        self.total_branches = total_branches

        self.setPen(pen)
        self.setZValue(-1)
        # Enable hover so we can highlight the wire on mouse-over
        self.setAcceptHoverEvents(True)
        self._hovered = False

        # Arrow-head child item
        self._arrow = QGraphicsPathItem(self)
        self._arrow.setPen(QPen(pen.color(), 1))
        self._arrow.setBrush(QBrush(pen.color()))
        self._arrow.setZValue(-1)

        # Optional branch label
        self._label: QGraphicsTextItem | None = None
        if total_branches > 1:
            lbl = QGraphicsTextItem(str(branch_index + 1), self)
            lbl.setDefaultTextColor(pen.color())
            lbl.setFont(QFont("Consolas", 6))
            lbl.setZValue(0)
            self._label = lbl

        # Connect to live position updates
        source.position_changed.connect(self._update_path)
        dest.position_changed.connect(self._update_path)

        # Build initial path
        self._update_path()

    # ── UE GraphEditorSettings spline tangent constants ──────────────────
    # Ported directly from Unreal Engine GraphEditorSettings.cpp defaults.
    # Forward wire  (dest is to the right of source):
    _FWD_H_RANGE  = 1000.0          # ForwardSplineHorizontalDeltaRange
    _FWD_V_RANGE  = 1000.0          # ForwardSplineVerticalDeltaRange
    _FWD_TAN_H    = (1.0, 0.0)      # ForwardSplineTangentFromHorizontalDelta
    _FWD_TAN_V    = (1.0, 0.0)      # ForwardSplineTangentFromVerticalDelta
    # Backward wire (dest is to the left — back-edge / loop):
    _BWD_H_RANGE  = 200.0           # BackwardSplineHorizontalDeltaRange
    _BWD_V_RANGE  = 200.0           # BackwardSplineVerticalDeltaRange
    _BWD_TAN_H    = (2.0, 0.0)      # BackwardSplineTangentFromHorizontalDelta
    _BWD_TAN_V    = (1.5, 0.0)      # BackwardSplineTangentFromVerticalDelta

    @staticmethod
    def _ue_spline_tangent(sx: float, sy: float, dx: float, dy: float):
        """Compute a cubic Bézier tangent vector using the exact UE
        GraphEditorSettings::ComputeSplineTangent algorithm.

        Returns (tx, ty) — a 2-D tangent that is applied symmetrically at
        both ends of the wire (positive for the start, negative for the end).
        This matches Unreal Blueprint wire appearance closely.
        """
        delta_x = dx - sx
        delta_y = dy - sy
        going_forward = delta_x >= 0.0

        if going_forward:
            clamped_x = min(abs(delta_x), EdgeItem._FWD_H_RANGE)
            clamped_y = min(abs(delta_y), EdgeItem._FWD_V_RANGE)
            hx, hy = EdgeItem._FWD_TAN_H
            vx, vy = EdgeItem._FWD_TAN_V
        else:
            clamped_x = min(abs(delta_x), EdgeItem._BWD_H_RANGE)
            clamped_y = min(abs(delta_y), EdgeItem._BWD_V_RANGE)
            hx, hy = EdgeItem._BWD_TAN_H
            vx, vy = EdgeItem._BWD_TAN_V

        tx = clamped_x * hx + clamped_y * vx
        ty = clamped_x * hy + clamped_y * vy
        return tx, ty

    def _update_path(self):
        """Recompute and repaint the Bezier wire from source→dest.

        Uses the same ComputeSplineTangent algorithm as Unreal Engine's
        Blueprint editor (ported from GraphEditorSettings.cpp) so that
        wires look identical to UE graph wires.
        """
        W = DialogueNodeItem.WIDTH
        H = DialogueNodeItem.HEIGHT

        # Vertical spread for parallel branches
        if self.total_branches > 1:
            spread_range = min(H * 0.55, self.total_branches * 10)
            step = spread_range / (self.total_branches - 1)
            v_spread = -spread_range / 2 + self.branch_index * step
        else:
            v_spread = 0.0

        src_out = self.source.out_port_scene()
        dst_in  = self.dest.in_port_scene()

        sx = src_out.x()
        sy = src_out.y() + v_spread
        dx = dst_in.x()
        dy = dst_in.y()

        # UE-style tangent (forward or backward path)
        tx, ty = self._ue_spline_tangent(sx, sy, dx, dy)

        forward = dx >= sx - W * 0.25   # going forward or nearly so

        path = QPainterPath(QPointF(sx, sy))

        if forward:
            # Cubic Bézier: start tangent points right, end tangent points left
            cx1 = sx + tx
            cy1 = sy + ty
            cx2 = dx - tx
            cy2 = dy - ty

            path.cubicTo(QPointF(cx1, cy1), QPointF(cx2, cy2), QPointF(dx, dy))
            arr_angle = math.atan2(dy - cy2, dx - cx2)
            arr_tip = QPointF(dx, dy)

            if self._label:
                self._label.setPos(sx + 6, sy - 14)

        else:
            # Back-edge: loop arc above or below using UE backward tangents
            H_node = DialogueNodeItem.HEIGHT
            above  = (self.branch_index % 2 == 0)
            margin = 30 + self.branch_index * 15
            src_top    = self.source.y()
            src_bottom = self.source.y() + H_node
            dst_top    = self.dest.y()
            dst_bottom = self.dest.y() + H_node

            if above:
                arc_y_src = src_top    - margin
                arc_y_dst = dst_top    - margin
                arc_end_y = dst_top
            else:
                arc_y_src = src_bottom + margin
                arc_y_dst = dst_bottom + margin
                arc_end_y = dst_bottom

            # UE back-edge: control points pulled sharply outward (tx can be large)
            path.cubicTo(
                QPointF(sx,  arc_y_src),
                QPointF(dx,  arc_y_dst),
                QPointF(dx,  arc_end_y),
            )
            arr_angle = math.pi / 2 if above else -math.pi / 2
            arr_tip = QPointF(dx, arc_end_y)

            if self._label:
                lx = (sx + dx) / 2
                ly = arc_y_src - 10 if above else arc_y_src + 2
                self._label.setPos(lx, ly)

        self.setPath(path)

        # Rebuild arrowhead — size 10 for execution-style, 8 for data-style
        size = 10 if self._pen.widthF() >= 2.0 else 8
        p1 = QPointF(
            arr_tip.x() - size * math.cos(arr_angle - 0.45),
            arr_tip.y() - size * math.sin(arr_angle - 0.45),
        )
        p2 = QPointF(
            arr_tip.x() - size * math.cos(arr_angle + 0.45),
            arr_tip.y() - size * math.sin(arr_angle + 0.45),
        )
        arr_path = QPainterPath(arr_tip)
        arr_path.lineTo(p1)
        arr_path.lineTo(p2)
        arr_path.closeSubpath()
        self._arrow.setPath(arr_path)

    def hoverEnterEvent(self, event):
        """Highlight wire on hover — mirrors UE Blueprint hover behaviour."""
        self._hovered = True
        base_color = self._pen.color()
        bright = base_color.lighter(160)
        hover_pen = QPen(bright, self._pen.widthF() + 1.0, self._pen.style())
        hover_pen.setCapStyle(Qt.RoundCap)
        hover_pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(hover_pen)
        self._arrow.setPen(QPen(bright, 1))
        self._arrow.setBrush(QBrush(bright))
        self.setZValue(0)   # bring to front on hover
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        """Restore original wire appearance on mouse-leave."""
        self._hovered = False
        self.setPen(self._pen)
        self._arrow.setPen(QPen(self._pen.color(), 1))
        self._arrow.setBrush(QBrush(self._pen.color()))
        self.setZValue(-1)
        super().hoverLeaveEvent(event)

    def disconnect_signals(self):
        """Cleanly detach from node signals (call before removing from scene)."""
        try:
            self.source.position_changed.disconnect(self._update_path)
        except Exception:
            pass
        try:
            self.dest.position_changed.disconnect(self._update_path)
        except Exception:
            pass


# -----------------------------------------------------------------
# Graph scene
# -----------------------------------------------------------------

class DialogueGraphScene(QGraphicsScene):

    node_selected         = Signal(object)  # DialogueNode
    add_branch_requested  = Signal(object)  # DialogueNode
    delete_node_requested = Signal(object)  # DialogueNode

    def __init__(self, dialogue: "DialogueFile", tlk=None):
        super().__init__()
        self.dialogue = dialogue
        self.tlk = tlk  # Optional TLKFile for resolving text_strrefs
        # node_items keyed by _node_key(node) — NOT by node_id alone
        # because entries and replies share the same 0-based ID space.
        self.node_items: Dict[str, DialogueNodeItem] = {}
        self._edge_items: List[EdgeItem] = []
        self._layout_done = False
        self._render()

    def _render(self):
        n_nodes = len(self.dialogue.nodes)
        log.debug("DialogueGraphScene._render: start (%d nodes)", n_nodes)
        t0 = _time.monotonic()
        # Disconnect all EdgeItem signals before clearing so there are no
        # dangling references to already-deleted node items.
        for edge in self._edge_items:
            edge.disconnect_signals()
        self._edge_items = []

        self.clear()
        self.node_items = {}
        self._auto_layout()
        for node in self.dialogue.nodes:
            item = DialogueNodeItem(node, tlk=self.tlk)
            self.addItem(item)
            self.node_items[item.key] = item   # key = "e0", "r0", "e1", …
        self._draw_edges()

        # Update scene rect explicitly so QGraphicsView scrollbars reflect the
        # actual content bounds immediately (without this, Qt uses a stale rect
        # and the viewport may be blank / unscrollable after loading a new DLG).
        if self.items():
            padded = self.itemsBoundingRect().adjusted(-80, -80, 80, 80)
            self.setSceneRect(padded)

        elapsed = (_time.monotonic() - t0) * 1000
        log.debug(
            "DialogueGraphScene._render: done in %.1fms (%d nodes, %d edges)",
            elapsed, n_nodes, len(self._edge_items),
        )

    def _auto_layout(self):
        """Assign positions using hierarchical layout.

        On the very first render every node is placed by the layout engine.
        On subsequent renders only truly new/unpositioned nodes are placed so
        user-dragged positions are preserved.
        """
        t0 = _time.monotonic()
        n_nodes = len(self.dialogue.nodes)
        log.debug("_auto_layout: start (%d nodes, layout_done=%s)",
                  n_nodes, self._layout_done)
        try:
            layout = _HierarchicalLayout(self.dialogue)
            positions = layout.assign()   # Dict[str, QPointF]
        except Exception:
            log.exception("_auto_layout: _HierarchicalLayout.assign() raised an exception")
            return

        if not self._layout_done:
            for node in self.dialogue.nodes:
                pos = positions.get(_node_key(node))
                if pos:
                    node.position_x = pos.x()
                    node.position_y = pos.y()
            self._layout_done = True
        else:
            placed_keys = {
                _node_key(n) for n in self.dialogue.nodes
                if not (n.position_x == 0 and n.position_y == 0)
            }
            for node in self.dialogue.nodes:
                k = _node_key(node)
                if k not in placed_keys:
                    pos = positions.get(k)
                    if pos:
                        node.position_x = pos.x()
                        node.position_y = pos.y()

        elapsed = (_time.monotonic() - t0) * 1000
        log.debug("_auto_layout: done in %.1fms (%d positions assigned)",
                  elapsed, len(positions))

    def force_relayout(self):
        """Reset all node positions and run a fresh layout."""
        self._layout_done = False
        for node in self.dialogue.nodes:
            node.position_x = 0
            node.position_y = 0
        self._render()

    # ------------------------------------------------------------------
    # Edge drawing — uses dynamic EdgeItem objects so wires follow nodes
    # ------------------------------------------------------------------

    def _draw_edges(self):
        """Create dynamic EdgeItem wires for every connection.

        EdgeItems subscribe to both endpoint nodes' position_changed signals,
        so wires repaint in real-time as nodes are dragged — just like
        Unreal Engine Blueprint wires.

        Node lookup uses _node_key to avoid the entry#0 / reply#0 collision.
        """
        t0 = _time.monotonic()
        entry_map: Dict[int, "DialogueNode"] = {n.node_id: n for n in self.dialogue.entries}
        reply_map: Dict[int, "DialogueNode"] = {n.node_id: n for n in self.dialogue.replies}
        missing_src = 0
        missing_dst = 0

        # UE Blueprint wire conventions:
        #   Execution wires (NPC) = 2.5 px solid teal
        #   Data wires (Player reply) = 1.5 px dashed blue
        pen_npc    = QPen(QColor("#4ec9b0"), 2.5, Qt.SolidLine)
        pen_npc.setCapStyle(Qt.RoundCap)
        pen_npc.setJoinStyle(Qt.RoundJoin)
        pen_player = QPen(QColor("#9cdcfe"), 1.5, Qt.DashLine)
        pen_player.setCapStyle(Qt.RoundCap)
        pen_player.setJoinStyle(Qt.RoundJoin)

        for node in self.dialogue.nodes:
            src_key = _node_key(node)
            src = self.node_items.get(src_key)
            if not src:
                missing_src += 1
                log.debug("_draw_edges: no scene item for src key %r", src_key)
                continue
            is_entry = (node.node_type == "entry")

            # Collect only drawable branches (skip END sentinel tid < 0)
            drawable: list = []
            for branch in node.branches:
                tid = branch.target_node_id
                if tid < 0:
                    continue  # -1 = END, no edge to draw
                if is_entry:
                    target_node = reply_map.get(tid)
                    dst_key = f"r{tid}" if target_node else None
                else:
                    target_node = entry_map.get(tid)
                    dst_key = f"e{tid}" if target_node else None
                if not dst_key:
                    missing_dst += 1
                    log.debug(
                        "_draw_edges: branch target_node_id=%d not found "
                        "(node %s, is_entry=%s)", tid, src_key, is_entry,
                    )
                    continue
                dst = self.node_items.get(dst_key)
                if not dst:
                    missing_dst += 1
                    log.debug("_draw_edges: no scene item for dst key %r", dst_key)
                    continue
                drawable.append((dst, dst_key))

            n_drawable = len(drawable)
            pen = pen_npc if is_entry else pen_player
            for branch_idx, (dst, _dst_key) in enumerate(drawable):
                edge = EdgeItem(src, dst, pen, branch_idx, n_drawable)
                self.addItem(edge)
                self._edge_items.append(edge)

        elapsed = (_time.monotonic() - t0) * 1000
        log.debug(
            "_draw_edges: %d edges created in %.1fms "
            "(missing_src=%d missing_dst=%d)",
            len(self._edge_items), elapsed, missing_src, missing_dst,
        )

    def refresh(self):
        self._render()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        for item in self.selectedItems():
            if isinstance(item, DialogueNodeItem):
                self.node_selected.emit(item.node)
                return



# -----------------------------------------------------------------
# Legacy tree-list view (mirrors DLGEditor v2.3.2 style)
# -----------------------------------------------------------------

class LegacyDialogueView(QWidget):
    """
    Tree-list dialogue editor modelled on the DLGEditor v2.3.2 layout:
      - Collapsible QTreeWidget showing the full conversation tree
        (NPC lines indented, player replies further indented)
      - Colour coding: NPC lines in orange/red, player replies in blue
      - Orphaned nodes grouped in a separate warning section
      - Circular references shown with a loop-back marker
    """

    node_selected = Signal(object)  # DialogueNode

    def __init__(self, dialogue: DialogueFile, parent=None):
        super().__init__(parent)
        self.dialogue = dialogue
        self.tlk = None  # Optional TLKFile for strref resolution
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background:#1a1a1a; border:none;
                font-family: 'Segoe UI'; font-size:9pt;
            }
            QTreeWidget::item { padding:3px 4px; color:#cccccc; }
            QTreeWidget::item:hover { background:#2a2d2e; }
            QTreeWidget::item:selected { background:#094771; color:white; }
        """)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        layout.addWidget(self.tree)

    def refresh(self):
        """Rebuild the entire tree from the dialogue model.

        IMPORTANT: entries and replies both use 0-based IDs, so a flat
        {node_id: node} dict causes collisions.  We keep separate maps.
        - Starters always point into the EntryList (NPC lines).
        - Entry branches always point into the ReplyList (Player choices).
        - Reply branches always point into the EntryList (back to NPC).
        """
        self.tree.clear()
        if not self.dialogue:
            return

        # Type-safe maps: never collide between entries and replies
        entry_map: Dict[int, object] = {n.node_id: n for n in self.dialogue.entries}
        reply_map: Dict[int, object] = {n.node_id: n for n in self.dialogue.replies}

        # visited tracks (node_type, node_id) pairs to detect real cycles
        def _add_node(parent_item, node, depth, visited):
            spk = node.speaker or "?"
            short = node.short_text(60, tlk=self.tlk)
            type_icon = "▶" if node.node_type == "reply" else "◆"
            label = f"{type_icon} {spk}  —  {short}" if short else f"{type_icon} {spk}  —  (empty)"

            if parent_item is None:
                item = QTreeWidgetItem(self.tree, [label])
            else:
                item = QTreeWidgetItem(parent_item, [label])

            # Store (type, id) tuple so selection can resolve unambiguously
            item.setData(0, Qt.UserRole, (node.node_type, node.node_id))

            if node.speaker == "Player":
                item.setForeground(0, QColor("#9cdcfe"))
            elif node.speaker:
                item.setForeground(0, QColor("#f48771"))
            else:
                item.setForeground(0, QColor("#858585"))

            if getattr(node, "script1", None) or getattr(node, "script2", None):
                item.setForeground(0, QColor("#4ec9b0"))

            item.setExpanded(depth < 3)

            node_key = (node.node_type, node.node_id)
            if node_key in visited:
                loop_item = QTreeWidgetItem(item, ["↩ (circular reference)"])
                loop_item.setForeground(0, QColor("#858585"))
                return

            visited = visited | {node_key}
            is_entry = (node.node_type == "entry")
            for branch in node.branches:
                tid = branch.target_node_id
                if tid < 0:
                    # -1 = END OF CONVERSATION
                    end_item = QTreeWidgetItem(item, ["⏹ [End of conversation]"])
                    end_item.setForeground(0, QColor("#858585"))
                    continue
                # Entries branch to replies; replies branch to entries
                child_node = reply_map.get(tid) if is_entry else entry_map.get(tid)
                if child_node:
                    _add_node(item, child_node, depth + 1, visited)
                else:
                    dead = QTreeWidgetItem(
                        item, [f"⚠ broken ref → #{tid}"]
                    )
                    dead.setForeground(0, QColor("#f48771"))

        # Track which entries+replies were shown (use node_key tuples)
        shown: Set[tuple] = set()
        for starter in self.dialogue.starters:
            # Starters always point to entry nodes
            root_node = entry_map.get(starter.target_node_id)
            if root_node:
                _add_node(None, root_node, 0, set())
                # BFS to collect all reachable nodes (entry/reply alternating)
                q = [("entry", root_node.node_id)]
                while q:
                    ntype, nid = q.pop(0)
                    key = (ntype, nid)
                    if key in shown:
                        continue
                    shown.add(key)
                    if ntype == "entry":
                        n = entry_map.get(nid)
                        if n:
                            for b in n.branches:
                                if b.target_node_id >= 0:
                                    q.append(("reply", b.target_node_id))
                    else:
                        n = reply_map.get(nid)
                        if n:
                            for b in n.branches:
                                if b.target_node_id >= 0:
                                    q.append(("entry", b.target_node_id))

        # Orphans: any entry or reply not reached from starters
        orphan_entries = [n for n in self.dialogue.entries
                          if ("entry", n.node_id) not in shown]
        orphan_replies = [n for n in self.dialogue.replies
                          if ("reply", n.node_id) not in shown]
        orphans = orphan_entries + orphan_replies
        if orphans:
            orphan_root = QTreeWidgetItem(
                self.tree, [f"⚠ Orphaned Nodes ({len(orphans)} not connected)"]
            )
            orphan_root.setForeground(0, QColor("#dcdcaa"))
            orphan_root.setExpanded(False)
            for n in orphans:
                _add_node(orphan_root, n, 0, set())

        self.tree.resizeColumnToContents(0)

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, Qt.UserRole)
        if data is None:
            return
        # data is a (node_type, node_id) tuple stored by refresh()
        if isinstance(data, tuple):
            ntype, nid = data
            if ntype == "entry":
                node = self.dialogue.get_entry(nid)
            else:
                node = self.dialogue.get_reply(nid)
        else:
            # Legacy fallback for any old stored int IDs
            node = self.dialogue.get_node(data)
        if node:
            self.node_selected.emit(node)

    def select_node(self, node_id: int, node_type: str = ""):
        """Scroll to and highlight the tree item for the given node.

        node_type should be 'entry' or 'reply' to disambiguate when both an
        entry and a reply share the same node_id (which is normal in KotOR DLG).
        If node_type is empty the first match is used.
        """
        def _find(item, target_id, target_type):
            data = item.data(0, Qt.UserRole)
            if isinstance(data, tuple):
                dtype, did = data
                if did == target_id and (not target_type or dtype == target_type):
                    self.tree.setCurrentItem(item)
                    self.tree.scrollToItem(item)
                    return True
            for i in range(item.childCount()):
                if _find(item.child(i), target_id, target_type):
                    return True
            return False
        for i in range(self.tree.topLevelItemCount()):
            if _find(self.tree.topLevelItem(i), node_id, node_type):
                break

# ─────────────────────────────────────────────────────────────────
# Node Inspector — full field set
# ─────────────────────────────────────────────────────────────────

class NodeInspector(QWidget):
    """Full-featured inspector for a single DialogueNode."""

    node_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._node: DialogueNode | None = None
        self._updating = False
        self.setMinimumWidth(260)
        # Debounce inspector saves — coalesces rapid signal bursts (spinner
        # arrow held down, paste into text field, etc.) into one flush.
        self._save_timer = QTimer(self)
        # Game/project dirs for audio file resolution
        self._audio_game_dir: Path | None = None
        self._audio_project_dir: Path | None = None
        # Audio player (lazy import so tests don't need soundfile installed)
        self._audio_player = None
        self._audio_player_field: str = ""   # "vo" or "sound"
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(80)   # ms — imperceptible to the user
        self._save_timer.timeout.connect(self._flush_changes)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("Node Inspector")
        header.setStyleSheet(
            f"background:{_PANEL}; color:{_WHITE}; font-weight:bold; "
            f"padding:5px 8px; border-bottom:1px solid {_BORDER};"
        )
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border:none; background:{_DARK}; }}
            QTabBar::tab {{ background:{_PANEL}; color:{_GREY}; padding:4px 10px;
                border-top:2px solid transparent; }}
            QTabBar::tab:selected {{ color:{_WHITE}; border-top:2px solid {_BLUE}; }}
            QTabBar::tab:hover {{ color:{_WHITE}; }}
        """)
        layout.addWidget(self.tabs)

        self.tabs.addTab(self._build_basic_tab(), "Basic")
        self.tabs.addTab(self._build_scripts_tab(), "Scripts")
        self.tabs.addTab(self._build_media_tab(), "Audio/Anim")
        self.tabs.addTab(self._build_links_tab(), "Links")
        self.tabs.addTab(self._build_camera_tab(), "Camera")
        self.tabs.addTab(self._build_tsl_tab(), "TSL")

    # ── Helpers ─────────────────────────────────────────────────

    def _scrollable(self, inner: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(_SCROLL_STYLE)
        inner.setStyleSheet(f"background:{_DARK};")
        scroll.setWidget(inner)
        return scroll

    def _connect_all(self):
        """Connect all inputs to _on_changed after filling them."""
        for w in self.findChildren(QLineEdit):
            try:
                w.textChanged.connect(self._on_changed)
            except Exception:
                pass
        for w in self.findChildren(QTextEdit):
            try:
                w.textChanged.connect(self._on_changed)
            except Exception:
                pass
        for w in self.findChildren(QSpinBox):
            try:
                w.valueChanged.connect(self._on_changed)
            except Exception:
                pass
        for w in self.findChildren(QDoubleSpinBox):
            try:
                w.valueChanged.connect(self._on_changed)
            except Exception:
                pass
        for w in self.findChildren(QCheckBox):
            try:
                w.stateChanged.connect(self._on_changed)
            except Exception:
                pass
        for w in self.findChildren(QComboBox):
            try:
                w.currentIndexChanged.connect(self._on_changed)
            except Exception:
                pass

    # ── Tab: Basic ──────────────────────────────────────────────

    def _build_basic_tab(self) -> QScrollArea:
        c = QWidget()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)

        # Node ID (read-only)
        row = QHBoxLayout()
        row.addWidget(_lbl("Node ID:"))
        self.node_id_lbl = QLabel("—")
        self.node_id_lbl.setStyleSheet(f"color:{_LTBLUE}; font-family:Consolas;")
        row.addWidget(self.node_id_lbl)
        self.node_type_lbl = QLabel("—")
        self.node_type_lbl.setStyleSheet(f"color:{_TEAL}; font-family:Consolas;")
        row.addWidget(self.node_type_lbl)
        row.addStretch()
        lay.addLayout(row)

        lay.addWidget(_section_lbl("Identity"))

        lay.addWidget(_lbl("Speaker (NPC tag or 'Player'):"))
        self.speaker_input = _make_line_edit("NPC tag or 'Player'")
        lay.addWidget(self.speaker_input)

        lay.addWidget(_lbl("Listener:"))
        self.listener_input = _make_line_edit("Listener tag")
        lay.addWidget(self.listener_input)

        lay.addWidget(_section_lbl("Dialogue Text"))
        self.text_input = QTextEdit()
        self.text_input.setFixedHeight(90)
        self.text_input.setStyleSheet(_INPUT_STYLE)
        self.text_input.setPlaceholderText("Node dialogue text…")
        lay.addWidget(self.text_input)

        lay.addWidget(_lbl("TLK StrRef (–1 = inline text):"))
        self.strref_spin = _make_spin(-1, 999999, -1)
        lay.addWidget(self.strref_spin)

        lay.addWidget(_section_lbl("Quest / Plot"))

        row2 = QHBoxLayout()
        row2.addWidget(_lbl("Quest var:"))
        self.quest_input = _make_line_edit("globalcat variable")
        row2.addWidget(self.quest_input)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(_lbl("Quest entry:"))
        self.quest_entry_spin = _make_spin(0, 9999, 0)
        row3.addWidget(self.quest_entry_spin)
        lay.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(_lbl("Plot index (–1 = none):"))
        self.plot_index_spin = _make_spin(-1, 9999, -1)
        row4.addWidget(self.plot_index_spin)
        lay.addLayout(row4)

        row5 = QHBoxLayout()
        row5.addWidget(_lbl("Plot XP %:"))
        self.plot_xp_spin = _make_dspin(0.0, 1.0, 1.0, 2)
        row5.addWidget(self.plot_xp_spin)
        lay.addLayout(row5)

        lay.addWidget(_section_lbl("Timing"))

        row6 = QHBoxLayout()
        row6.addWidget(_lbl("Delay (ms, –1=default):"))
        self.delay_spin = _make_spin(-1, 2147483647, -1)
        row6.addWidget(self.delay_spin)
        lay.addLayout(row6)

        row7 = QHBoxLayout()
        row7.addWidget(_lbl("Wait flags:"))
        self.wait_flags_spin = _make_spin(0, 255, 0)
        row7.addWidget(self.wait_flags_spin)
        lay.addLayout(row7)

        lay.addWidget(_section_lbl("Comment"))
        self.comment_input = _make_line_edit("Editor-only note")
        lay.addWidget(self.comment_input)

        lay.addStretch()
        return self._scrollable(c)

    # ── Tab: Scripts ─────────────────────────────────────────────

    def _build_scripts_tab(self) -> QScrollArea:
        c = QWidget()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)

        lay.addWidget(_section_lbl("Script 1 (on-enter)"))
        self.script1_input = _make_line_edit("script_name (no .nss)")
        lay.addWidget(self.script1_input)

        lay.addWidget(_section_lbl("Script 1 Parameters (TSL)"))
        for i in range(1, 6):
            row = QHBoxLayout()
            row.addWidget(_lbl(f"  Param {i}:"))
            sp = _make_spin(-99999, 99999, 0)
            setattr(self, f"s1p{i}_spin", sp)
            row.addWidget(sp)
            lay.addLayout(row)

        lay.addWidget(_lbl("Param string (TSL):"))
        self.s1p_str_input = _make_line_edit()
        lay.addWidget(self.s1p_str_input)

        lay.addWidget(_section_lbl("Script 2 (TSL only)"))
        self.script2_input = _make_line_edit("script2_name (no .nss)")
        lay.addWidget(self.script2_input)

        lay.addWidget(_section_lbl("Script 2 Parameters (TSL)"))
        for i in range(1, 6):
            row = QHBoxLayout()
            row.addWidget(_lbl(f"  Param {i}:"))
            sp = _make_spin(-99999, 99999, 0)
            setattr(self, f"s2p{i}_spin", sp)
            row.addWidget(sp)
            lay.addLayout(row)

        lay.addWidget(_lbl("Param string (TSL):"))
        self.s2p_str_input = _make_line_edit()
        lay.addWidget(self.s2p_str_input)

        lay.addStretch()
        return self._scrollable(c)

    # ── Audio player helpers ──────────────────────────────────────

    def _get_audio_player(self):
        """Lazy-init the AudioPlayerService."""
        if self._audio_player is None:
            try:
                from ghostscripter.utils.audio_player import AudioPlayerService
                self._audio_player = AudioPlayerService(self)
                self._audio_player.state_changed.connect(self._on_audio_state)
                self._audio_player.duration_ready.connect(self._on_audio_duration)
                self._audio_player.progress_changed.connect(self._on_audio_progress)
                self._audio_player.error_occurred.connect(self._on_audio_error)
            except Exception as e:
                log.warning("AudioPlayerService unavailable: %s", e)
        return self._audio_player

    def set_audio_dirs(self, game_dir: Path | None = None,
                       project_dir: Path | None = None):
        """Called by the parent editor when directories are known."""
        self._audio_game_dir = game_dir
        self._audio_project_dir = project_dir

    def _play_resref(self, field: str) -> None:
        """Attempt to play the VO or sound resref for the current node."""
        resref = (self.vo_input.text() if field == "vo"
                  else self.sound_input.text()).strip()
        if not resref:
            QMessageBox.information(self, "No Resref",
                "Enter a VO/Sound resref in the field above first.")
            return

        from ghostscripter.utils.audio_player import find_audio_file
        path = find_audio_file(resref,
                               game_dir=self._audio_game_dir,
                               project_dir=self._audio_project_dir)
        if path is None:
            # Offer to browse
            from qtpy.QtWidgets import QFileDialog
            p, _ = QFileDialog.getOpenFileName(
                self, f"Locate audio for '{resref}'",
                str(self._audio_game_dir or Path.home()),
                "Audio Files (*.wav *.mp3 *.ogg *.flac);;All Files (*)"
            )
            if not p:
                self._set_audio_status(field, "not found", error=True)
                return
            path = Path(p)

        player = self._get_audio_player()
        if player is None:
            QMessageBox.warning(self, "Audio Unavailable",
                "Audio playback is not available in this environment.")
            return

        self._audio_player_field = field
        self._update_play_btn(field, playing=True)
        player.play(path)

    def _toggle_vo_play(self) -> None:
        if self._audio_player and self._audio_player.is_playing and self._audio_player_field == "vo":
            self._stop_audio()
        else:
            self._play_resref("vo")

    def _toggle_sound_play(self) -> None:
        if self._audio_player and self._audio_player.is_playing and self._audio_player_field == "sound":
            self._stop_audio()
        else:
            self._play_resref("sound")

    def _stop_audio(self) -> None:
        if self._audio_player is not None:
            self._audio_player.stop()
        self._update_play_btn("vo", playing=False)
        self._update_play_btn("sound", playing=False)

    def _update_play_btn(self, field: str, playing: bool) -> None:
        btn = self.vo_play_btn if field == "vo" else self.sound_play_btn
        btn.setText("■ Stop" if playing else "▶ Play")
        btn.setProperty("playing", playing)
        # Refresh stylesheet to reflect state
        btn.setStyleSheet(self._play_btn_style(playing))

    @staticmethod
    def _play_btn_style(playing: bool) -> str:
        if playing:
            return ("QPushButton { background:#6b1d1d; color:#f48771; "
                    "border:1px solid #a03030; border-radius:2px; "
                    "font-size:8pt; padding:1px 6px; } "
                    "QPushButton:hover { background:#8b2020; }")
        return ("QPushButton { background:#1a3a1a; color:#4ec9b0; "
                "border:1px solid #2a6a2a; border-radius:2px; "
                "font-size:8pt; padding:1px 6px; } "
                "QPushButton:hover { background:#1f4a1f; }")

    def _browse_audio_file(self, field: str) -> None:
        """Browse for an audio file and set the resref field."""
        from qtpy.QtWidgets import QFileDialog
        start = str(self._audio_game_dir or Path.home())
        p, _ = QFileDialog.getOpenFileName(
            self, "Select Audio File", start,
            "Audio Files (*.wav *.mp3 *.ogg *.flac);;All Files (*)"
        )
        if not p:
            return
        stem = Path(p).stem.lower()
        if field == "vo":
            self.vo_input.setText(stem)
        else:
            self.sound_input.setText(stem)
        self._set_audio_status(field, f"Linked: {Path(p).name}", error=False)

    def _set_audio_status(self, field: str, msg: str, error: bool = False) -> None:
        lbl = self.vo_status_lbl if field == "vo" else self.sound_status_lbl
        color = "#f48771" if error else "#858585"
        lbl.setStyleSheet(f"color:{color}; font-size:7pt;")
        lbl.setText(msg)

    def _on_audio_state(self, state: str) -> None:
        from ghostscripter.utils.audio_player import (
            STATE_PLAYING, STATE_STOPPED, STATE_IDLE, STATE_ERROR
        )
        field = self._audio_player_field
        if state == STATE_PLAYING:
            self._update_play_btn(field, playing=True)
            self._set_audio_status(field, "Playing…")
            # Start progress bar timer
            if self._audio_player:
                self._audio_player._timer.start()
        elif state in (STATE_STOPPED, STATE_IDLE):
            self._update_play_btn(field, playing=False)
            self._set_audio_status(field, "")
            self._reset_audio_progress(field)
        elif state == STATE_ERROR:
            self._update_play_btn(field, playing=False)

    def _on_audio_duration(self, dur: float) -> None:
        field = self._audio_player_field
        if dur > 0:
            m, s = int(dur) // 60, int(dur) % 60
            self._set_audio_status(field, f"Duration: {m}:{s:02d}")

    def _on_audio_progress(self, frac: float) -> None:
        field = self._audio_player_field
        bar = self.vo_progress if field == "vo" else self.sound_progress
        bar.setValue(int(frac * 1000))

    def _on_audio_error(self, msg: str) -> None:
        field = self._audio_player_field
        self._set_audio_status(field, msg, error=True)
        self._update_play_btn(field, playing=False)

    def _reset_audio_progress(self, field: str) -> None:
        bar = self.vo_progress if field == "vo" else self.sound_progress
        bar.setValue(0)

    def closeEvent(self, event):
        if self._audio_player is not None:
            self._audio_player.cleanup()
        super().closeEvent(event)

    # ── Tab: Audio / Animations ──────────────────────────────────

    def _build_media_tab(self) -> QScrollArea:
        c = QWidget()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)

        # ── Voice-Over section ────────────────────────────────────
        lay.addWidget(_section_lbl("Voice-Over (VO_ResRef)"))

        vo_row = QHBoxLayout()
        self.vo_input = _make_line_edit("VO resref — wav/mp3/ogg filename without extension")
        vo_row.addWidget(self.vo_input, 1)
        browse_vo_btn = QPushButton("📂")
        browse_vo_btn.setFixedSize(24, 22)
        browse_vo_btn.setToolTip("Browse for audio file and auto-fill resref")
        browse_vo_btn.setStyleSheet(
            "QPushButton { background:#2d2d30; color:#9cdcfe; border:1px solid #3c3c3c; "
            "border-radius:2px; font-size:10pt; } "
            "QPushButton:hover { background:#3a3a3a; }"
        )
        browse_vo_btn.clicked.connect(lambda: self._browse_audio_file("vo"))
        vo_row.addWidget(browse_vo_btn)
        lay.addLayout(vo_row)

        vo_ctrl_row = QHBoxLayout()
        self.vo_play_btn = QPushButton("▶ Play")
        self.vo_play_btn.setFixedHeight(22)
        self.vo_play_btn.setStyleSheet(self._play_btn_style(False))
        self.vo_play_btn.setToolTip("Play voice-over (searches game streamwaves/streamvoice)")
        self.vo_play_btn.clicked.connect(self._toggle_vo_play)
        vo_ctrl_row.addWidget(self.vo_play_btn)
        self.vo_status_lbl = QLabel("")
        self.vo_status_lbl.setStyleSheet("color:#858585; font-size:7pt;")
        vo_ctrl_row.addWidget(self.vo_status_lbl, 1)
        lay.addLayout(vo_ctrl_row)

        # Thin progress bar (using QSlider range 0-1000, read-only)
        from qtpy.QtWidgets import QProgressBar
        self.vo_progress = QProgressBar()
        self.vo_progress.setRange(0, 1000)
        self.vo_progress.setValue(0)
        self.vo_progress.setFixedHeight(4)
        self.vo_progress.setTextVisible(False)
        self.vo_progress.setStyleSheet(
            "QProgressBar { background:#2d2d30; border:none; border-radius:2px; } "
            "QProgressBar::chunk { background:#4ec9b0; border-radius:2px; }"
        )
        lay.addWidget(self.vo_progress)

        # ── Sound section ─────────────────────────────────────────
        lay.addWidget(_section_lbl("Sound Effect (Sound)"))

        snd_row = QHBoxLayout()
        self.sound_input = _make_line_edit("Sound resref")
        snd_row.addWidget(self.sound_input, 1)
        browse_snd_btn = QPushButton("📂")
        browse_snd_btn.setFixedSize(24, 22)
        browse_snd_btn.setToolTip("Browse for audio file and auto-fill resref")
        browse_snd_btn.setStyleSheet(
            "QPushButton { background:#2d2d30; color:#9cdcfe; border:1px solid #3c3c3c; "
            "border-radius:2px; font-size:10pt; } "
            "QPushButton:hover { background:#3a3a3a; }"
        )
        browse_snd_btn.clicked.connect(lambda: self._browse_audio_file("sound"))
        snd_row.addWidget(browse_snd_btn)
        lay.addLayout(snd_row)

        snd_ctrl_row = QHBoxLayout()
        self.sound_play_btn = QPushButton("▶ Play")
        self.sound_play_btn.setFixedHeight(22)
        self.sound_play_btn.setStyleSheet(self._play_btn_style(False))
        self.sound_play_btn.setToolTip("Play sound effect")
        self.sound_play_btn.clicked.connect(self._toggle_sound_play)
        snd_ctrl_row.addWidget(self.sound_play_btn)
        self.sound_status_lbl = QLabel("")
        self.sound_status_lbl.setStyleSheet("color:#858585; font-size:7pt;")
        snd_ctrl_row.addWidget(self.sound_status_lbl, 1)
        lay.addLayout(snd_ctrl_row)

        self.sound_progress = QProgressBar()
        self.sound_progress.setRange(0, 1000)
        self.sound_progress.setValue(0)
        self.sound_progress.setFixedHeight(4)
        self.sound_progress.setTextVisible(False)
        self.sound_progress.setStyleSheet(
            "QProgressBar { background:#2d2d30; border:none; border-radius:2px; } "
            "QProgressBar::chunk { background:#9cdcfe; border-radius:2px; }"
        )
        lay.addWidget(self.sound_progress)

        row = QHBoxLayout()
        self.sound_exists_chk = QCheckBox("SoundExists")
        self.sound_exists_chk.setStyleSheet(_CHECK_STYLE)
        row.addWidget(self.sound_exists_chk)
        row.addStretch()
        lay.addLayout(row)

        lay.addWidget(_section_lbl("Animations (AnimList)"))
        lay.addWidget(_lbl("Participant → Animation ID:"))

        self.anim_table = QTableWidget(0, 2)
        self.anim_table.setHorizontalHeaderLabels(["Participant", "Anim ID"])
        self.anim_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.anim_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.anim_table.setStyleSheet(_TABLE_STYLE)
        self.anim_table.setFixedHeight(120)
        lay.addWidget(self.anim_table)

        anim_btns = QHBoxLayout()
        add_anim = QPushButton("+ Add")
        add_anim.setStyleSheet(_BTN_STYLE)
        add_anim.clicked.connect(self._add_anim_row)
        rem_anim = QPushButton("Remove")
        rem_anim.setStyleSheet(_BTN_STYLE)
        rem_anim.clicked.connect(self._remove_anim_row)
        anim_btns.addWidget(add_anim)
        anim_btns.addWidget(rem_anim)
        anim_btns.addStretch()
        lay.addLayout(anim_btns)

        lay.addWidget(_section_lbl("Fade"))
        fade_row = QHBoxLayout()
        fade_row.addWidget(_lbl("Fade type:"))
        self.fade_type_spin = _make_spin(0, 15, 0)
        fade_row.addWidget(self.fade_type_spin)
        lay.addLayout(fade_row)

        rgb_row = QHBoxLayout()
        rgb_row.addWidget(_lbl("R:"))
        self.fade_r_spin = _make_dspin(0.0, 1.0, 0.0, 2)
        rgb_row.addWidget(self.fade_r_spin)
        rgb_row.addWidget(_lbl("G:"))
        self.fade_g_spin = _make_dspin(0.0, 1.0, 0.0, 2)
        rgb_row.addWidget(self.fade_g_spin)
        rgb_row.addWidget(_lbl("B:"))
        self.fade_b_spin = _make_dspin(0.0, 1.0, 0.0, 2)
        rgb_row.addWidget(self.fade_b_spin)
        lay.addLayout(rgb_row)

        fd_row = QHBoxLayout()
        fd_row.addWidget(_lbl("Delay:"))
        self.fade_delay_spin = _make_dspin(0.0, 9999.0, 0.0)
        fd_row.addWidget(self.fade_delay_spin)
        fd_row.addWidget(_lbl("Length:"))
        self.fade_length_spin = _make_dspin(0.0, 9999.0, 0.0)
        fd_row.addWidget(self.fade_length_spin)
        lay.addLayout(fd_row)

        lay.addStretch()
        return self._scrollable(c)

    # ── Tab: Links (branches) ────────────────────────────────────

    def _build_links_tab(self) -> QScrollArea:
        c = QWidget()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)

        lay.addWidget(_section_lbl("Branches (outgoing links)"))
        lay.addWidget(_lbl(
            "Each branch links to a child node.  "
            "Active = conditional script (show/hide).",
            color=_GREY
        ))

        self.branch_table = QTableWidget(0, 4)
        self.branch_table.setHorizontalHeaderLabels(
            ["Target", "Active Script", "IsChild", "Active2 (TSL)"]
        )
        self.branch_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.branch_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.branch_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.branch_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.branch_table.setStyleSheet(_TABLE_STYLE)
        lay.addWidget(self.branch_table)

        btns = QHBoxLayout()
        add_b = QPushButton("+ Add Branch")
        add_b.setStyleSheet(_BTN_PRIMARY)
        add_b.clicked.connect(self._add_branch)
        rem_b = QPushButton("Remove")
        rem_b.setStyleSheet(_BTN_STYLE)
        rem_b.clicked.connect(self._remove_branch)
        btns.addWidget(add_b)
        btns.addWidget(rem_b)
        btns.addStretch()
        lay.addLayout(btns)

        lay.addWidget(_section_lbl("Link comment (editor only)"))
        self.link_comment_input = _make_line_edit("Branch annotation…")
        lay.addWidget(self.link_comment_input)

        lay.addStretch()
        return self._scrollable(c)

    # ── Tab: Camera ──────────────────────────────────────────────

    def _build_camera_tab(self) -> QScrollArea:
        c = QWidget()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)

        lay.addWidget(_section_lbl("Camera (KotOR 1 + 2)"))

        row = QHBoxLayout()
        row.addWidget(_lbl("Camera angle:"))
        self.cam_angle_spin = _make_spin(-1, 359, 0)
        row.addWidget(self.cam_angle_spin)
        lay.addLayout(row)

        lay.addWidget(_section_lbl("Camera (TSL only)"))

        row2 = QHBoxLayout()
        row2.addWidget(_lbl("Camera ID:"))
        self.cam_id_spin = _make_spin(-1, 9999, -1)
        row2.addWidget(self.cam_id_spin)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(_lbl("Camera animation:"))
        self.cam_anim_spin = _make_spin(0, 9999, 0)
        row3.addWidget(self.cam_anim_spin)
        lay.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(_lbl("Field of view:"))
        self.cam_fov_spin = _make_dspin(0.0, 180.0, 55.0)
        row4.addWidget(self.cam_fov_spin)
        lay.addLayout(row4)

        row5 = QHBoxLayout()
        row5.addWidget(_lbl("Height offset:"))
        self.cam_height_spin = _make_dspin(-999.0, 999.0, 0.0)
        row5.addWidget(self.cam_height_spin)
        lay.addLayout(row5)

        row6 = QHBoxLayout()
        row6.addWidget(_lbl("Vid effect (CamVidEffect):"))
        self.cam_effect_spin = _make_spin(-1, 9999, -1)
        row6.addWidget(self.cam_effect_spin)
        lay.addLayout(row6)

        row7 = QHBoxLayout()
        row7.addWidget(_lbl("Target height offset:"))
        self.tar_height_spin = _make_dspin(-999.0, 999.0, 0.0)
        row7.addWidget(self.tar_height_spin)
        lay.addLayout(row7)

        lay.addStretch()
        return self._scrollable(c)

    # ── Tab: TSL Extended ────────────────────────────────────────

    def _build_tsl_tab(self) -> QScrollArea:
        c = QWidget()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)

        lay.addWidget(_section_lbl("TSL Node Flags"))

        self.unskippable_chk = QCheckBox("NodeUnskippable")
        self.unskippable_chk.setStyleSheet(_CHECK_STYLE)
        lay.addWidget(self.unskippable_chk)

        row = QHBoxLayout()
        row.addWidget(_lbl("AlienRaceNode:"))
        self.alien_race_spin = _make_spin(0, 99, 0)
        row.addWidget(self.alien_race_spin)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(_lbl("Emotion ID:"))
        self.emotion_spin = _make_spin(0, 99, 0)
        row2.addWidget(self.emotion_spin)
        lay.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(_lbl("FacialAnim ID:"))
        self.facial_spin = _make_spin(0, 99, 0)
        row3.addWidget(self.facial_spin)
        lay.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(_lbl("NodeID (TSL field):"))
        self.node_id_tsl_spin = _make_spin(0, 99999, 0)
        row4.addWidget(self.node_id_tsl_spin)
        lay.addLayout(row4)

        row5 = QHBoxLayout()
        row5.addWidget(_lbl("PostProcNode:"))
        self.post_proc_spin = _make_spin(0, 99, 0)
        row5.addWidget(self.post_proc_spin)
        lay.addLayout(row5)

        lay.addWidget(_section_lbl("Voice Recording (TSL)"))

        self.record_vo_chk = QCheckBox("RecordVO")
        self.record_vo_chk.setStyleSheet(_CHECK_STYLE)
        lay.addWidget(self.record_vo_chk)

        self.record_no_override_chk = QCheckBox("RecordNoVOOverride")
        self.record_no_override_chk.setStyleSheet(_CHECK_STYLE)
        lay.addWidget(self.record_no_override_chk)

        self.vo_text_changed_chk = QCheckBox("VOTextChanged")
        self.vo_text_changed_chk.setStyleSheet(_CHECK_STYLE)
        lay.addWidget(self.vo_text_changed_chk)

        lay.addStretch()
        return self._scrollable(c)

    # ── Load node → populate all fields ─────────────────────────

    def load_node(self, node: DialogueNode):
        self._node = node
        self._updating = True

        # Basic tab
        self.node_id_lbl.setText(str(node.node_id))
        self.node_type_lbl.setText(node.node_type.upper())
        self.speaker_input.setText(node.speaker)
        self.listener_input.setText(node.listener)
        self.text_input.setPlainText(node.text)
        self.strref_spin.setValue(node.text_strref if node.text_strref is not None else -1)
        self.quest_input.setText(node.quest)
        self.quest_entry_spin.setValue(node.quest_entry)
        self.plot_index_spin.setValue(node.plot_index)
        self.plot_xp_spin.setValue(node.plot_xp_percentage)
        self.delay_spin.setValue(max(-1, min(node.delay, 2147483647)))
        self.wait_flags_spin.setValue(node.wait_flags)
        self.comment_input.setText(node.comment)

        # Scripts tab
        self.script1_input.setText(node.script1)
        self.s1p1_spin.setValue(node.script1_param1)
        self.s1p2_spin.setValue(node.script1_param2)
        self.s1p3_spin.setValue(node.script1_param3)
        self.s1p4_spin.setValue(node.script1_param4)
        self.s1p5_spin.setValue(node.script1_param5)
        self.s1p_str_input.setText(node.script1_param_str)
        self.script2_input.setText(node.script2)
        self.s2p1_spin.setValue(node.script2_param1)
        self.s2p2_spin.setValue(node.script2_param2)
        self.s2p3_spin.setValue(node.script2_param3)
        self.s2p4_spin.setValue(node.script2_param4)
        self.s2p5_spin.setValue(node.script2_param5)
        self.s2p_str_input.setText(node.script2_param_str)

        # Media tab
        self.vo_input.setText(node.vo_resref)
        self.sound_input.setText(node.sound)
        self.sound_exists_chk.setChecked(bool(node.sound_exists))
        # Stop any playing audio and reset UI when a new node is selected
        self._stop_audio()
        self._set_audio_status("vo", "")
        self._set_audio_status("sound", "")
        self._load_anim_table(node.animations)
        self.fade_type_spin.setValue(node.fade_type)
        self.fade_r_spin.setValue(node.fade_color_r)
        self.fade_g_spin.setValue(node.fade_color_g)
        self.fade_b_spin.setValue(node.fade_color_b)
        self.fade_delay_spin.setValue(node.fade_delay)
        self.fade_length_spin.setValue(node.fade_length)

        # Links tab
        self._load_branch_table(node.branches)

        # Camera tab
        self.cam_angle_spin.setValue(node.camera_angle)
        self.cam_id_spin.setValue(node.camera_id if node.camera_id is not None else -1)
        self.cam_anim_spin.setValue(node.camera_animation or 0)
        self.cam_fov_spin.setValue(node.camera_fov if node.camera_fov is not None else 55.0)
        self.cam_height_spin.setValue(node.camera_height if node.camera_height is not None else 0.0)
        self.cam_effect_spin.setValue(node.camera_effect if node.camera_effect is not None else -1)
        self.tar_height_spin.setValue(node.target_height if node.target_height is not None else 0.0)

        # TSL tab
        self.unskippable_chk.setChecked(bool(node.node_unskippable))
        self.alien_race_spin.setValue(node.alien_race_node)
        self.emotion_spin.setValue(node.emotion_id)
        self.facial_spin.setValue(node.facial_id)
        self.node_id_tsl_spin.setValue(node.node_id_tsl)
        self.post_proc_spin.setValue(node.post_proc_node)
        self.record_vo_chk.setChecked(bool(node.record_vo))
        self.record_no_override_chk.setChecked(bool(node.record_no_vo_override))
        self.vo_text_changed_chk.setChecked(bool(node.vo_text_changed))

        self._updating = False

    def _load_anim_table(self, anims: List[DLGAnimation]):
        self.anim_table.setRowCount(0)
        for a in anims:
            row = self.anim_table.rowCount()
            self.anim_table.insertRow(row)
            self.anim_table.setItem(row, 0, QTableWidgetItem(a.participant))
            self.anim_table.setItem(row, 1, QTableWidgetItem(str(a.animation_id)))

    def _load_branch_table(self, branches: List[DialogueBranch]):
        self.branch_table.setRowCount(0)
        for b in branches:
            row = self.branch_table.rowCount()
            self.branch_table.insertRow(row)
            target = str(b.target_node_id) if b.target_node_id >= 0 else "END"
            self.branch_table.setItem(row, 0, QTableWidgetItem(target))
            self.branch_table.setItem(row, 1, QTableWidgetItem(b.active_script))
            child_item = QTableWidgetItem("✓" if b.is_child else "")
            child_item.setTextAlignment(Qt.AlignCenter)
            self.branch_table.setItem(row, 2, child_item)
            self.branch_table.setItem(row, 3, QTableWidgetItem(b.active_script2))

    # ── On-change → save to node (debounced) ────────────────────

    def _on_changed(self):
        """Debounce guard — schedule a flush 80 ms after the last signal."""
        if not self._updating and self._node:
            self._save_timer.start()

    def _flush_changes(self):
        """Write all widget values back to the node model (actual work)."""
        if self._updating or not self._node:
            return
        n = self._node

        # Basic
        n.speaker = self.speaker_input.text()
        n.listener = self.listener_input.text()
        n.text = self.text_input.toPlainText()
        n.text_strref = self.strref_spin.value()
        n.quest = self.quest_input.text()
        n.quest_entry = self.quest_entry_spin.value()
        n.plot_index = self.plot_index_spin.value()
        n.plot_xp_percentage = self.plot_xp_spin.value()
        n.delay = self.delay_spin.value()
        n.wait_flags = self.wait_flags_spin.value()
        n.comment = self.comment_input.text()

        # Scripts
        n.script1 = self.script1_input.text()
        n.script1_param1 = self.s1p1_spin.value()
        n.script1_param2 = self.s1p2_spin.value()
        n.script1_param3 = self.s1p3_spin.value()
        n.script1_param4 = self.s1p4_spin.value()
        n.script1_param5 = self.s1p5_spin.value()
        n.script1_param_str = self.s1p_str_input.text()
        n.script2 = self.script2_input.text()
        n.script2_param1 = self.s2p1_spin.value()
        n.script2_param2 = self.s2p2_spin.value()
        n.script2_param3 = self.s2p3_spin.value()
        n.script2_param4 = self.s2p4_spin.value()
        n.script2_param5 = self.s2p5_spin.value()
        n.script2_param_str = self.s2p_str_input.text()

        # Media
        n.vo_resref = self.vo_input.text()
        n.sound = self.sound_input.text()
        n.sound_exists = 1 if self.sound_exists_chk.isChecked() else 0
        n.fade_type = self.fade_type_spin.value()
        n.fade_color_r = self.fade_r_spin.value()
        n.fade_color_g = self.fade_g_spin.value()
        n.fade_color_b = self.fade_b_spin.value()
        n.fade_delay = self.fade_delay_spin.value()
        n.fade_length = self.fade_length_spin.value()

        # Camera
        n.camera_angle = self.cam_angle_spin.value()
        cam_id = self.cam_id_spin.value()
        n.camera_id = cam_id if cam_id >= 0 else None
        n.camera_animation = self.cam_anim_spin.value()
        n.camera_fov = self.cam_fov_spin.value()
        n.camera_height = self.cam_height_spin.value()
        cam_eff = self.cam_effect_spin.value()
        n.camera_effect = cam_eff if cam_eff >= 0 else None
        n.target_height = self.tar_height_spin.value()

        # TSL
        n.node_unskippable = self.unskippable_chk.isChecked()
        n.alien_race_node = self.alien_race_spin.value()
        n.emotion_id = self.emotion_spin.value()
        n.facial_id = self.facial_spin.value()
        n.node_id_tsl = self.node_id_tsl_spin.value()
        n.post_proc_node = self.post_proc_spin.value()
        n.record_vo = self.record_vo_chk.isChecked()
        n.record_no_vo_override = self.record_no_override_chk.isChecked()
        n.vo_text_changed = self.vo_text_changed_chk.isChecked()

        self.node_changed.emit()

    def _add_anim_row(self):
        if not self._node:
            return
        row = self.anim_table.rowCount()
        self.anim_table.insertRow(row)
        self.anim_table.setItem(row, 0, QTableWidgetItem("PLAYER"))
        self.anim_table.setItem(row, 1, QTableWidgetItem("0"))
        self._sync_anims()

    def _remove_anim_row(self):
        rows = {i.row() for i in self.anim_table.selectedItems()}
        for r in sorted(rows, reverse=True):
            self.anim_table.removeRow(r)
        self._sync_anims()

    def _sync_anims(self):
        if not self._node:
            return
        anims = []
        for r in range(self.anim_table.rowCount()):
            p = (self.anim_table.item(r, 0) or QTableWidgetItem("")).text()
            try:
                aid = int((self.anim_table.item(r, 1) or QTableWidgetItem("0")).text())
            except ValueError:
                aid = 0
            anims.append(DLGAnimation(participant=p, animation_id=aid))
        self._node.animations = anims
        self.node_changed.emit()

    def _add_branch(self):
        """Quick Connect branch picker — shows available target nodes in a list
        instead of requiring the user to type a raw integer ID.

        Falls back to a text-input dialog if no dialogue context is available
        (e.g. in tests or when called directly).
        """
        if not self._node:
            return

        # Try to get the parent dialogue for the quick-connect picker
        parent_widget = self.parent()
        while parent_widget and not hasattr(parent_widget, 'dialogue'):
            parent_widget = parent_widget.parent() if hasattr(parent_widget, 'parent') else None

        dialogue = getattr(parent_widget, 'dialogue', None)

        if dialogue is not None:
            from qtpy.QtWidgets import QDialog, QDialogButtonBox, QListWidget
            is_entry = (self._node.node_type == "entry")
            candidates = dialogue.replies if is_entry else dialogue.entries
            connected = {b.target_node_id for b in self._node.branches}
            available = [c for c in candidates if c.node_id not in connected]

            if not available:
                # Offer END branch or raw-ID fallback
                tid_str, ok = QInputDialog.getText(
                    self, "Add Branch",
                    "No unconnected targets found.\nEnter target node ID (-1 = END):",
                    text="-1"
                )
                if not ok:
                    return
                try:
                    tid = int(tid_str)
                except ValueError:
                    tid = -1
                self._node.add_branch("", tid)
            else:
                dlg = QDialog(self)
                dlg.setWindowTitle("Add Branch — Pick Target")
                dlg.setStyleSheet(f"background:{_DARK}; color:{_WHITE};")
                lay = QVBoxLayout(dlg)
                lay.addWidget(_lbl(
                    f"Connect  {'Entry' if is_entry else 'Reply'} #{self._node.node_id}  →:",
                ))
                lst = QListWidget()
                lst.setStyleSheet(_LIST_STYLE)
                for c in available:
                    snippet = (c.text or "")[:50]
                    lst.addItem(
                        f"{'Reply' if is_entry else 'Entry'} #{c.node_id}  "
                        f"{c.speaker}  —  {snippet}"
                    )
                # Also allow an explicit END option
                lst.addItem("── [End of Conversation] (target -1) ──")
                lst.setCurrentRow(0)
                lay.addWidget(lst)
                btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                btns.accepted.connect(dlg.accept)
                btns.rejected.connect(dlg.reject)
                lay.addWidget(btns)
                if dlg.exec() != QDialog.Accepted:
                    return
                row = lst.currentRow()
                if row < 0:
                    return
                if row < len(available):
                    tid = available[row].node_id
                else:
                    tid = -1
                self._node.add_branch("", tid)
        else:
            # Fallback: plain text input
            text, ok = QInputDialog.getText(self, "New Branch",
                                            "Target node ID (integer) or 'END':")
            if not ok:
                return
            try:
                tid = int(text)
            except ValueError:
                tid = -1
            self._node.add_branch("", tid)

        self._load_branch_table(self._node.branches)
        self.node_changed.emit()

    def _remove_branch(self):
        if not self._node:
            return
        rows = sorted({i.row() for i in self.branch_table.selectedItems()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self._node.branches):
                self._node.branches.pop(r)
        self._load_branch_table(self._node.branches)
        self.node_changed.emit()


# ─────────────────────────────────────────────────────────────────
# Dialogue Properties Panel (top-level DLG fields)
# ─────────────────────────────────────────────────────────────────

class DialoguePropertiesPanel(QWidget):
    """Panel for editing top-level DialogueFile properties."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dlg: DialogueFile | None = None
        self._updating = False
        # Debounce DLG property saves
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(80)
        self._save_timer.timeout.connect(self._flush_changes)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("Dialogue Properties")
        header.setStyleSheet(
            f"background:{_PANEL}; color:{_WHITE}; font-weight:bold; "
            f"padding:5px 8px; border-bottom:1px solid {_BORDER};"
        )
        layout.addWidget(header)

        c = QWidget()
        c.setStyleSheet(f"background:{_DARK};")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(_SCROLL_STYLE)
        scroll.setWidget(c)
        layout.addWidget(scroll)

        lay = QVBoxLayout(c)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        lay.addWidget(_section_lbl("Identification"))
        lay.addWidget(_lbl("DLG name (resref):"))
        self.name_input = _make_line_edit("conversation_name")
        lay.addWidget(self.name_input)

        lay.addWidget(_section_lbl("End / Abort Scripts"))
        lay.addWidget(_lbl("EndConversation script:"))
        self.on_end_input = _make_line_edit("on_end_script")
        lay.addWidget(self.on_end_input)

        lay.addWidget(_lbl("EndConverAbort script:"))
        self.on_abort_input = _make_line_edit("on_abort_script")
        lay.addWidget(self.on_abort_input)

        lay.addWidget(_section_lbl("Playback Settings"))

        self.skippable_chk = QCheckBox("Skippable")
        self.skippable_chk.setStyleSheet(_CHECK_STYLE)
        lay.addWidget(self.skippable_chk)

        d_row = QHBoxLayout()
        d_row.addWidget(_lbl("Delay entry (ms):"))
        self.delay_entry_spin = _make_spin(0, 99999, 0)
        d_row.addWidget(self.delay_entry_spin)
        lay.addLayout(d_row)

        d_row2 = QHBoxLayout()
        d_row2.addWidget(_lbl("Delay reply (ms):"))
        self.delay_reply_spin = _make_spin(0, 99999, 0)
        d_row2.addWidget(self.delay_reply_spin)
        lay.addLayout(d_row2)

        lay.addWidget(_section_lbl("Audio / Camera"))
        lay.addWidget(_lbl("Ambient track (resref):"))
        self.ambient_input = _make_line_edit("mus_ambient")
        lay.addWidget(self.ambient_input)

        self.animated_cut_chk = QCheckBox("AnimatedCut")
        self.animated_cut_chk.setStyleSheet(_CHECK_STYLE)
        lay.addWidget(self.animated_cut_chk)

        lay.addWidget(_lbl("Camera model (resref):"))
        self.camera_model_input = _make_line_edit("camera_model")
        lay.addWidget(self.camera_model_input)

        lay.addWidget(_section_lbl("Conversation Type"))
        self.conv_type_combo = QComboBox()
        self.conv_type_combo.addItems(["0 — Human (default)", "1 — Computer", "2 — Other"])
        self.conv_type_combo.setStyleSheet(_INPUT_STYLE)
        lay.addWidget(self.conv_type_combo)

        comp_row = QHBoxLayout()
        comp_row.addWidget(_lbl("ComputerType:"))
        self.comp_type_combo = QComboBox()
        self.comp_type_combo.addItems(["0 — Modern", "1 — Ancient"])
        self.comp_type_combo.setStyleSheet(_INPUT_STYLE)
        comp_row.addWidget(self.comp_type_combo)
        lay.addLayout(comp_row)

        lay.addWidget(_section_lbl("Flags"))
        self.old_hit_chk = QCheckBox("OldHitCheck")
        self.old_hit_chk.setStyleSheet(_CHECK_STYLE)
        lay.addWidget(self.old_hit_chk)
        self.unequip_chk = QCheckBox("UnequipItems")
        self.unequip_chk.setStyleSheet(_CHECK_STYLE)
        lay.addWidget(self.unequip_chk)
        self.unequip_h_chk = QCheckBox("UnequipHItem (offhand)")
        self.unequip_h_chk.setStyleSheet(_CHECK_STYLE)
        lay.addWidget(self.unequip_h_chk)

        lay.addStretch()

        # Connect
        for w in [self.name_input, self.on_end_input, self.on_abort_input,
                  self.ambient_input, self.camera_model_input]:
            w.textChanged.connect(self._on_changed)
        for w in [self.delay_entry_spin, self.delay_reply_spin]:
            w.valueChanged.connect(self._on_changed)
        for w in [self.skippable_chk, self.animated_cut_chk,
                  self.old_hit_chk, self.unequip_chk, self.unequip_h_chk]:
            w.stateChanged.connect(self._on_changed)
        for w in [self.conv_type_combo, self.comp_type_combo]:
            w.currentIndexChanged.connect(self._on_changed)

    def load_dialogue(self, dlg: DialogueFile):
        self._dlg = dlg
        self._updating = True
        self.name_input.setText(dlg.name)
        self.on_end_input.setText(dlg.on_end)
        self.on_abort_input.setText(dlg.on_abort)
        self.skippable_chk.setChecked(dlg.skippable)
        self.delay_entry_spin.setValue(dlg.delay_entry)
        self.delay_reply_spin.setValue(dlg.delay_reply)
        self.ambient_input.setText(dlg.ambient_track)
        self.animated_cut_chk.setChecked(dlg.animated_cut)
        self.camera_model_input.setText(dlg.camera_model)
        self.conv_type_combo.setCurrentIndex(min(dlg.conversation_type, 2))
        self.comp_type_combo.setCurrentIndex(min(dlg.computer_type, 1))
        self.old_hit_chk.setChecked(dlg.old_hit_check)
        self.unequip_chk.setChecked(dlg.unequip_items)
        self.unequip_h_chk.setChecked(dlg.unequip_h_item)
        self._updating = False

    def _on_changed(self):
        """Debounce guard — schedule a flush 80 ms after the last signal."""
        if not self._updating and self._dlg:
            self._save_timer.start()

    def _flush_changes(self):
        """Write all widget values back to the DLG model."""
        if self._updating or not self._dlg:
            return
        self._dlg.name = self.name_input.text()
        self._dlg.on_end = self.on_end_input.text()
        self._dlg.on_abort = self.on_abort_input.text()
        self._dlg.skippable = self.skippable_chk.isChecked()
        self._dlg.delay_entry = self.delay_entry_spin.value()
        self._dlg.delay_reply = self.delay_reply_spin.value()
        self._dlg.ambient_track = self.ambient_input.text()
        self._dlg.animated_cut = self.animated_cut_chk.isChecked()
        self._dlg.camera_model = self.camera_model_input.text()
        self._dlg.conversation_type = self.conv_type_combo.currentIndex()
        self._dlg.computer_type = self.comp_type_combo.currentIndex()
        self._dlg.old_hit_check = self.old_hit_chk.isChecked()
        self._dlg.unequip_items = self.unequip_chk.isChecked()
        self._dlg.unequip_h_item = self.unequip_h_chk.isChecked()
        self.changed.emit()


# ─────────────────────────────────────────────────────────────────
# Main Dialogue Editor Widget
# ─────────────────────────────────────────────────────────────────

class DialogueEditorWidget(QWidget):

    def __init__(self, dialogue: DialogueFile | None = None, parent=None):
        super().__init__(parent)
        self.dialogue = dialogue or create_simple_dialogue("new_dialogue", "npc_001")
        self._game_dir = None  # Set via set_game_dir() when game directory is configured
        self._tlk = None      # TLKFile loaded from game_dir for strref display

        # Debounce node-list filter — avoids clearing+rebuilding on every keystroke
        self._node_filter_timer = QTimer(self)
        self._node_filter_timer.setSingleShot(True)
        self._node_filter_timer.setInterval(150)
        self._node_filter_timer.timeout.connect(self._apply_filter_node_list)
        self._pending_node_filter = ""

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_toolbar())

        # ── Central stacked widget (Visual / Legacy) ─────────────
        self._stack = QStackedWidget()

        # ── PAGE 0: Visual graph mode ─────────────────────────────
        visual_page = QWidget()
        vis_lay = QVBoxLayout(visual_page)
        vis_lay.setContentsMargins(0, 0, 0, 0)
        vis_lay.setSpacing(0)

        outer_split = QSplitter(Qt.Horizontal)
        outer_split.setHandleWidth(2)
        outer_split.addWidget(self._build_node_list())

        mid_split = QSplitter(Qt.Vertical)
        mid_split.setHandleWidth(2)

        self.scene = DialogueGraphScene(self.dialogue, tlk=self._tlk)
        self.scene.node_selected.connect(self._on_node_selected)
        self.scene.add_branch_requested.connect(self._on_add_branch_from_context)
        self.scene.delete_node_requested.connect(self._on_delete_node_from_context)
        self.graph_view = ZoomableGraphView(self.scene)
        self.graph_view.setFocusPolicy(Qt.StrongFocus)   # ensure keyboard events work
        mid_split.addWidget(self.graph_view)

        self.dlg_props = DialoguePropertiesPanel()
        self.dlg_props.load_dialogue(self.dialogue)
        self.dlg_props.changed.connect(self._on_dlg_props_changed)
        self.dlg_props.setMaximumHeight(200)
        mid_split.addWidget(self.dlg_props)
        mid_split.setSizes([420, 180])

        outer_split.addWidget(mid_split)

        self.inspector = NodeInspector()
        self.inspector.node_changed.connect(self._on_node_changed)
        outer_split.addWidget(self.inspector)
        outer_split.setSizes([165, 600, 300])

        vis_lay.addWidget(outer_split)
        self._stack.addWidget(visual_page)   # index 0
        # Auto-fit the graph once the widget is actually shown
        QTimer.singleShot(120, self._fit_view)

        # ── PAGE 1: Legacy tree-list mode ─────────────────────────
        legacy_page = QWidget()
        leg_lay = QHBoxLayout(legacy_page)
        leg_lay.setContentsMargins(0, 0, 0, 0)
        leg_lay.setSpacing(0)

        self.legacy_view = LegacyDialogueView(self.dialogue)
        self.legacy_view.node_selected.connect(self._on_node_selected)

        self._legacy_inspector = NodeInspector()
        self._legacy_inspector.node_changed.connect(self._on_node_changed_legacy)

        leg_split = QSplitter(Qt.Horizontal)
        leg_split.setHandleWidth(2)
        leg_split.addWidget(self.legacy_view)
        leg_split.addWidget(self._legacy_inspector)
        leg_split.setSizes([700, 350])
        leg_lay.addWidget(leg_split)
        self._stack.addWidget(legacy_page)   # index 1

        layout.addWidget(self._stack)

    def _build_toolbar(self) -> QWidget:
        tb = QWidget()
        tb.setStyleSheet(f"background:{_PANEL}; border-bottom:1px solid {_BORDER};")
        lay = QHBoxLayout(tb)
        lay.setContentsMargins(6, 3, 6, 3)
        lay.setSpacing(4)

        def btn(label, slot, primary=False, tooltip=""):
            b = QPushButton(label)
            b.clicked.connect(slot)
            b.setFixedHeight(24)
            b.setStyleSheet(_BTN_PRIMARY if primary else _BTN_STYLE)
            if tooltip:
                b.setToolTip(tooltip)
            return b

        lay.addWidget(btn("+ NPC Entry", self._add_npc_node, True))
        lay.addWidget(btn("+ Player Reply", self._add_player_node))
        lay.addWidget(btn("⬆ Add Starter", self._add_starter))
        lay.addWidget(btn("🗑 Delete", self._delete_selected_node))
        lay.addWidget(btn("⟳ Re-layout", self._do_relayout,
                          tooltip="Reset positions and rerun hierarchical layout"))
        lay.addWidget(btn("⛶ Fit View", self._fit_view,
                          tooltip="Zoom to show all nodes  [F or double-click canvas]"))
        lay.addWidget(btn("1:1 Zoom", self._reset_zoom,
                          tooltip="Reset to 100% zoom  [Ctrl+0]"))
        lay.addWidget(btn("✓ Validate", self._validate))
        lay.addWidget(btn("🎮 NPCs", self._browse_npcs_from_game))
        lay.addWidget(btn("📂 Open .DLG", self._import_dlg))
        lay.addWidget(btn("💾 Export .DLG", self._export_dlg))

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color:#3c3c3c;")
        lay.addWidget(sep)

        # Mode selector
        mode_lbl = QLabel("Mode:")
        mode_lbl.setStyleSheet(f"color:{_GREY}; font-size:8pt;")
        lay.addWidget(mode_lbl)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("🗺 Visual", userData=0)
        self.mode_combo.addItem("📋 Legacy", userData=1)
        self.mode_combo.setFixedWidth(110)
        self.mode_combo.setFixedHeight(22)
        self.mode_combo.setStyleSheet(_INPUT_STYLE)
        self.mode_combo.setToolTip(
            "Visual: interactive node graph with zoom/pan\n"
            "Legacy: collapsible tree list (DLGEditor style)"
        )
        self.mode_combo.currentIndexChanged.connect(self._switch_mode)
        lay.addWidget(self.mode_combo)

        lay.addSpacing(4)
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.VLine)
        sep2.setStyleSheet("color:#3c3c3c;")
        lay.addWidget(sep2)

        game_lbl = QLabel("Game:")
        game_lbl.setStyleSheet(f"color:{_GREY}; font-size:8pt;")
        lay.addWidget(game_lbl)
        self.game_combo = QComboBox()
        self.game_combo.addItems(["K1", "K2"])
        self.game_combo.setFixedWidth(50)
        self.game_combo.setFixedHeight(22)
        self.game_combo.setStyleSheet(_INPUT_STYLE)
        lay.addWidget(self.game_combo)
        lay.addStretch()

        self.dlg_name_label = QLabel(self.dialogue.name or "untitled.dlg")
        self.dlg_name_label.setStyleSheet(f"color:{_LTBLUE}; font-weight:bold;")
        lay.addWidget(self.dlg_name_label)

        return tb

    def _build_node_list(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(f"background:{_DARK};")
        panel.setMinimumWidth(155)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QLabel("Nodes")
        header.setStyleSheet(
            f"background:{_PANEL}; color:{_WHITE}; font-weight:bold; "
            f"padding:5px 8px; border-bottom:1px solid {_BORDER};"
        )
        layout.addWidget(header)

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(4, 4, 4, 2)
        self.node_filter = QLineEdit()
        self.node_filter.setPlaceholderText("Filter…")
        self.node_filter.setStyleSheet(_INPUT_STYLE)
        self.node_filter.textChanged.connect(self._filter_node_list)
        filter_row.addWidget(self.node_filter)
        layout.addLayout(filter_row)

        self.node_list = QListWidget()
        self.node_list.setStyleSheet(_LIST_STYLE)
        self.node_list.itemClicked.connect(self._on_list_node_clicked)
        layout.addWidget(self.node_list)

        self._refresh_node_list()
        return panel

    def _refresh_node_list(self, filter_text=""):
        ft = filter_text.lower()
        blue   = QColor(_LTBLUE)
        orange = QColor(_ORANGE)
        self.node_list.setUpdatesEnabled(False)
        self.node_list.clear()
        for node in self.dialogue.nodes:
            spk = node.speaker or "—"
            short = node.short_text(24, tlk=self._tlk)
            type_tag = "R" if node.node_type == "reply" else "E"
            label = f"{'►' if spk=='Player' else '◆'} [{type_tag}{node.node_id}] {spk}: {short}"
            if ft and ft not in label.lower():
                continue
            item = QListWidgetItem(label)
            # Store the unique node key ("e0", "r0", etc.) not the bare int ID
            item.setData(Qt.UserRole, _node_key(node))
            item.setForeground(blue if spk == "Player" else orange)
            self.node_list.addItem(item)
        self.node_list.setUpdatesEnabled(True)

    def _schedule_filter_node_list(self, text: str):
        self._pending_node_filter = text
        self._node_filter_timer.start()

    def _apply_filter_node_list(self):
        self._refresh_node_list(self._pending_node_filter)

    def _filter_node_list(self, text):
        """Direct filter — delegates to debounced version."""
        self._schedule_filter_node_list(text)

    # ── Node actions ────────────────────────────────────────────

    def _add_npc_node(self):
        tag, ok = QInputDialog.getText(self, "New NPC Entry", "NPC speaker tag:")
        if not ok:
            return
        node = DialogueNode(
            node_type="entry",
            speaker=tag or "npc_001",
            text="[Enter NPC dialogue here]",
            # position (0,0) so _auto_layout will place it on next refresh
        )
        self.dialogue.add_node(node)
        self._refresh()

    def _add_player_node(self):
        node = DialogueNode(
            node_type="reply",
            speaker="Player",
            text="[Player response]",
            # position (0,0) so _auto_layout will place it on next refresh
        )
        self.dialogue.add_node(node)
        self._refresh()

    def _add_starter(self):
        """Add a starting link pointing to an entry node by node_id."""
        if not self.dialogue.entries:
            QMessageBox.information(self, "No entries",
                                    "Add at least one NPC entry first.")
            return

        # Build a picker so the user selects from actual node IDs, not indices
        from qtpy.QtWidgets import QDialog, QDialogButtonBox, QListWidget
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Starter — Pick Entry Node")
        dlg.setStyleSheet(f"background:{_DARK}; color:{_WHITE};")
        dlg_lay = QVBoxLayout(dlg)
        dlg_lay.addWidget(_lbl("Select the entry node to start from:"))
        lst = QListWidget()
        lst.setStyleSheet(_LIST_STYLE)
        for e in self.dialogue.entries:
            snippet = (e.text or "")[:50]
            lst.addItem(f"[Entry #{e.node_id}]  {e.speaker}  —  {snippet}")
        if lst.count():
            lst.setCurrentRow(0)
        dlg_lay.addWidget(lst)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dlg_lay.addWidget(btns)
        if dlg.exec() != QDialog.Accepted:
            return

        row = lst.currentRow()
        if row < 0:
            return
        chosen_entry = self.dialogue.entries[row]
        b = DialogueBranch(
            branch_id=len(self.dialogue.starters),
            target_node_id=chosen_entry.node_id,
            text="",
        )
        self.dialogue.starters.append(b)
        QMessageBox.information(self, "Starter added",
                                f"Starting link → Entry #{chosen_entry.node_id} "
                                f"({chosen_entry.speaker}) added.")

    def _delete_selected_node(self):
        items = self.node_list.selectedItems()
        if not items:
            return
        node_key = items[0].data(Qt.UserRole)   # "e0" or "r0"
        node = self._node_from_key(node_key)
        if not node:
            return
        node_id = node.node_id
        if QMessageBox.question(
            self, "Delete Node",
            f"Delete node {node_key} (#{node_id})? All branches targeting it will be removed.",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self.dialogue.remove_node(node_id)
            self._refresh()

    # ── Mode switching ──────────────────────────────────────────

    def _switch_mode(self, index: int):
        """Switch between Visual (0) and Legacy (1) mode."""
        self._stack.setCurrentIndex(index)
        if index == 1:
            self.legacy_view.dialogue = self.dialogue
            self.legacy_view.refresh()

    def _fit_view(self):
        """Fit the entire graph into the viewport (Visual mode).

        Called both on initial load and after re-layout.  We wait one event
        loop tick so Qt has processed the layout geometry before calling
        fitInView — otherwise the viewport size may not be known yet and
        fitInView scales to 0×0.
        """
        if not hasattr(self, "graph_view"):
            return
        # Only fit when the visual page is actually visible
        if hasattr(self, "_stack") and self._stack.currentIndex() != 0:
            return
        self.graph_view.fit_all()

    def _reset_zoom(self):
        """Reset visual-mode zoom to 1:1."""
        if hasattr(self, "graph_view"):
            self.graph_view.reset_zoom()

    def _do_relayout(self):
        """Force a full hierarchical re-layout, resetting manual positions."""
        if self._stack.currentIndex() == 0:
            self.scene.force_relayout()
            self._refresh_node_list(self.node_filter.text())
            self.dlg_name_label.setText(self.dialogue.name or "untitled.dlg")
            QTimer.singleShot(60, self._fit_view)
        else:
            self.legacy_view.refresh()

    def _refresh(self):
        self.scene.refresh()
        self._refresh_node_list(self.node_filter.text())
        self.dlg_name_label.setText(self.dialogue.name or "untitled.dlg")
        if hasattr(self, "_stack") and self._stack.currentIndex() == 1:
            self.legacy_view.dialogue = self.dialogue
            self.legacy_view.refresh()

    def _validate(self):
        issues = self.dialogue.validate_tree()
        if issues:
            QMessageBox.warning(self, "Validation Issues",
                                "\n".join(f"• {i}" for i in issues))
        else:
            QMessageBox.information(self, "Validation",
                                    "✓ Dialogue tree is valid!")

    def _import_dlg(self):
        """Open and import an existing .dlg GFF3 binary file."""
        from qtpy.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open DLG File", "",
            "KotOR Dialogue (*.dlg);;All files (*)"
        )
        if not path:
            return
        log.info("_import_dlg: user selected path=%r", path)
        t_total = _time.monotonic()
        try:
            from ghostscripter.core.export.dlg_reader import DLGImporter
            importer = DLGImporter()
            log.debug("_import_dlg: calling DLGImporter.import_from_file()")
            new_dlg = importer.import_from_file(path)
            log.info(
                "_import_dlg: import_from_file OK — entries=%d replies=%d starters=%d",
                len(new_dlg.entries), len(new_dlg.replies), len(new_dlg.starters),
            )

            self.dialogue = new_dlg
            self.scene.dialogue = new_dlg
            self.scene._layout_done = False   # force fresh layout for new file
            log.debug("_import_dlg: loading into dlg_props panel")
            self.dlg_props.load_dialogue(new_dlg)

            log.debug("_import_dlg: calling _refresh() → scene._render()")
            self._refresh()

            elapsed = (_time.monotonic() - t_total) * 1000
            log.info("_import_dlg: fully loaded in %.1fms", elapsed)

            QTimer.singleShot(150, self._fit_view)   # give Qt time to finish layout
            QMessageBox.information(
                self, "Import OK",
                f"Loaded: {new_dlg.name}\n"
                f"Entries: {len(new_dlg.entries)}, "
                f"Replies: {len(new_dlg.replies)}, "
                f"Starters: {len(new_dlg.starters)}"
            )
        except Exception as e:
            log.exception("_import_dlg: FAILED for path=%r", path)
            QMessageBox.critical(
                self, "Import Error",
                f"Failed to read .dlg file:\n{e}\n\n"
                f"See ghostscripter.log for the full traceback."
            )

    def _export_dlg(self):
        """Export this dialogue to a .dlg binary."""
        from qtpy.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(
            self, "Export DLG", f"{self.dialogue.name}.dlg",
            "KotOR Dialogue (*.dlg);;All files (*)"
        )
        if not path:
            return
        try:
            from ghostscripter.core.export.dlg_writer import DLGExporter
            exporter = DLGExporter()
            game = self.game_combo.currentText() if hasattr(self, "game_combo") else "K1"
            data = exporter.export(self.dialogue, target_game=game)
            with open(path, "wb") as f:
                f.write(data)
            QMessageBox.information(self, "Export OK",
                                    f"Exported {len(data):,} bytes → {path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _on_dlg_props_changed(self):
        self.dlg_name_label.setText(self.dialogue.name or "untitled.dlg")

    def _node_from_key(self, key: str) -> "DialogueNode" | None:
        """Resolve an 'e0'/'r0' key back to the DialogueNode."""
        if not key:
            return None
        if key.startswith("r"):
            try:
                return self.dialogue.get_reply(int(key[1:]))
            except (ValueError, IndexError):
                return None
        else:
            try:
                return self.dialogue.get_entry(int(key[1:]))
            except (ValueError, IndexError):
                return None

    def _on_add_branch_from_context(self, node: "DialogueNode"):
        """Handle 'Add Branch' triggered from a node's right-click context menu.

        Opens a Quick Connect picker showing all valid target nodes (replies
        for NPC entries, entries for player replies), filtered to exclude
        already-connected targets.
        """
        from qtpy.QtWidgets import QDialog, QDialogButtonBox, QListWidget
        is_entry = (node.node_type == "entry")
        candidates = self.dialogue.replies if is_entry else self.dialogue.entries
        connected = {b.target_node_id for b in node.branches}
        available = [c for c in candidates if c.node_id not in connected]

        if not available:
            QMessageBox.information(self, "No Targets",
                                    "All available nodes are already connected.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Quick Connect — Pick Target Node")
        dlg.setStyleSheet(f"background:{_DARK}; color:{_WHITE};")
        lay = QVBoxLayout(dlg)
        lay.addWidget(_lbl(
            f"Connect  {'Entry' if is_entry else 'Reply'} #{node.node_id}  →  to:",
        ))
        lst = QListWidget()
        lst.setStyleSheet(_LIST_STYLE)
        for c in available:
            snippet = (c.text or "")[:50]
            lst.addItem(
                f"{'Reply' if is_entry else 'Entry'} #{c.node_id}  "
                f"{c.speaker}  —  {snippet}"
            )
        lst.setCurrentRow(0)
        lay.addWidget(lst)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        row = lst.currentRow()
        if row < 0:
            return
        target = available[row]
        node.add_branch("", target.node_id)
        self._refresh()
        # Re-select the node so the inspector updates its Links tab
        self.inspector.load_node(node)

    def _on_delete_node_from_context(self, node: "DialogueNode"):
        """Handle 'Delete Node' triggered from a node's right-click context menu."""
        node_key = _node_key(node)
        if QMessageBox.question(
            self, "Delete Node",
            f"Delete {node_key} (#{node.node_id})?\n"
            "All branches pointing to it will also be removed.",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self.dialogue.remove_node(node.node_id)
            self._refresh()

    def _on_node_selected(self, node: "DialogueNode"):
        mode = self._stack.currentIndex()
        if mode == 0:
            self.inspector.load_node(node)
        else:
            self._legacy_inspector.load_node(node)
        # Sync left-panel node list — compare by node_key, not bare int
        target_key = _node_key(node)
        for i in range(self.node_list.count()):
            item = self.node_list.item(i)
            if item.data(Qt.UserRole) == target_key:
                self.node_list.setCurrentItem(item)
                break
        # Sync legacy tree selection
        if mode == 1:
            self.legacy_view.select_node(node.node_id, node.node_type)

    def _on_list_node_clicked(self, item: QListWidgetItem):
        node_key = item.data(Qt.UserRole)   # e.g. "e0" or "r0"
        # Resolve key back to node
        node = self._node_from_key(node_key)
        if node:
            self.inspector.load_node(node)
            node_item = self.scene.node_items.get(node_key)
            if node_item:
                self.graph_view.centerOn(node_item)
                node_item.setSelected(True)

    def _on_node_changed(self):
        """Called when the visual-mode inspector edits a node."""
        self.scene.refresh()
        self._refresh_node_list(self.node_filter.text())
        if hasattr(self, "_stack") and self._stack.currentIndex() == 1:
            self.legacy_view.refresh()

    def _on_node_changed_legacy(self):
        """Called when the legacy-mode inspector edits a node."""
        self.legacy_view.refresh()
        self.scene.refresh()
        self._refresh_node_list(self.node_filter.text())

    # ── Game Integration ─────────────────────────────────────────

    def set_game_dir(self, game_dir: "Path"):
        """Set game directory for NPC/strref lookups and audio file resolution."""
        from pathlib import Path
        self._game_dir = Path(game_dir)
        # Pass to inspectors so they can resolve audio files
        self.inspector.set_audio_dirs(game_dir=self._game_dir)
        self._legacy_inspector.set_audio_dirs(game_dir=self._game_dir)
        # Auto-load dialog.tlk for strref resolution in node cards
        self._try_load_tlk()

    def _try_load_tlk(self):
        """Load dialog.tlk from the game directory to resolve text strrefs in node cards."""
        if not self._game_dir:
            return
        from pathlib import Path
        for name in ("dialog.tlk", "dialogF.tlk", "Dialog.tlk"):
            tlk_path = Path(self._game_dir) / name
            if tlk_path.exists():
                try:
                    from ghostscripter.ui.widgets.tlk_editor_widget import TLKFile
                    self._tlk = TLKFile.from_file(tlk_path)
                    log.info("Dialogue editor loaded TLK: %s (%d entries)",
                             tlk_path.name, len(self._tlk))
                    # Update existing scene with TLK so node cards show real text
                    if hasattr(self, 'scene') and self.scene is not None:
                        self.scene.tlk = self._tlk
                        for item in self.scene.node_items.values():
                            item.tlk = self._tlk
                        self.scene.update()
                    # Update legacy tree view
                    if hasattr(self, 'legacy_view') and self.legacy_view is not None:
                        self.legacy_view.tlk = self._tlk
                        self.legacy_view.refresh()
                except Exception as e:
                    log.warning("Could not load TLK for dialogue editor: %s", e)
                return

    def _browse_npcs_from_game(self):
        """Open a dialog to pick an NPC tag from appearance.2da."""
        game_dir = getattr(self, "_game_dir", None)
        if not game_dir or not (game_dir / "chitin.key").exists():
            QMessageBox.information(
                self, "Game Directory Required",
                "Set the KotOR game directory in Settings → Set Game Directory first."
            )
            return
        try:
            from ghostscripter.core.resource_manager.resource_manager import ResourceManager
            from ghostscripter.core.twoda_manager.twoda_manager import TwoDAFile
            rm = ResourceManager()
            rm.load_game(game_dir)
            data = rm.read("appearance.2da")
            if data is None:
                QMessageBox.warning(self, "Error", "appearance.2da not found in game archives.")
                return
            twoda = TwoDAFile.from_bytes(data)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load appearance.2da:\n{e}")
            return

        # Build picker dialog
        dlg = _NPCPickerDialog(twoda, parent=self)
        if dlg.exec() != dlg.Accepted:
            return
        tag = dlg.get_selected_tag()
        if tag:
            node = DialogueNode(
                node_type="entry",
                speaker=tag,
                text=f"[{tag} speaks]",
                position_x=60,
                position_y=len(self.dialogue.entries) * 110 + 40,
            )
            self.dialogue.add_node(node)
            self._refresh()


# ── NPC Picker Dialog ─────────────────────────────────────────────

class _NPCPickerDialog(QMessageBox if False else QWidget):
    """Lightweight dialog to pick an NPC tag from appearance.2da rows."""

    Accepted = 1

    def __init__(self, twoda, parent=None):
        # Use QDialog directly
        from qtpy.QtWidgets import QDialog, QDialogButtonBox, QListWidget
        self._dlg_class = QDialog
        self._dialog = QDialog(parent)
        self._dialog.setWindowTitle("Browse NPCs from appearance.2da")
        self._dialog.setMinimumSize(480, 420)
        self._dialog.setStyleSheet("background:#252526; color:#cccccc;")
        self._twoda = twoda
        self._selected = None
        self._result = 0

        lay = QVBoxLayout(self._dialog)

        info = QLabel("Select an NPC appearance (label = creature tag/model name):")
        info.setStyleSheet("color:#9cdcfe; padding:4px 0;")
        lay.addWidget(info)

        frow = QHBoxLayout()
        frow.addWidget(QLabel("Filter:"))
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("type to filter…")
        self._filter.setStyleSheet("QLineEdit{background:#3c3c3c;color:#ccc;border:1px solid #555;padding:2px 6px;}")
        self._filter.textChanged.connect(self._populate)
        frow.addWidget(self._filter)
        lay.addLayout(frow)

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget{background:#1e1e1e;border:1px solid #3c3c3c;color:#cccccc;}
            QListWidget::item{padding:3px 8px;font-family:Consolas;font-size:9pt;}
            QListWidget::item:selected{background:#094771;}
        """)
        self._list.itemDoubleClicked.connect(self._accept)
        lay.addWidget(self._list)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("Use Selected")
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self._dialog.reject)
        lay.addWidget(btns)

        self._populate()

    def _populate(self):
        self._list.clear()
        ft = self._filter.text().lower() if hasattr(self, "_filter") else ""
        label_col = "label"
        for row in self._twoda.rows:
            label = row.get(label_col, "") or row.get("Label", "")
            if not label or label == "****":
                continue
            if ft and ft not in label.lower():
                continue
            modeltype = row.get("modeltype", "") or row.get("ModelType", "")
            race = row.get("race", "") or row.get("Race", "")
            self._list.addItem(f"{label}  [{modeltype}/{race}]")

    def _accept(self):
        items = self._list.selectedItems()
        if items:
            # Extract the label (before the bracket)
            self._selected = items[0].text().split("  [")[0].strip()
        self._result = 1
        self._dialog.accept()

    def exec_(self) -> int:
        self._dialog.exec()
        return self._result

    def get_selected_tag(self):
        return self._selected
