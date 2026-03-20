"""GIT (Game Instance Table) node-graph area editor widget.

Provides a 2-D spatial view of all GIT instances in a KotOR area:
  - Creatures, doors, placeables, waypoints, triggers, stores, sounds, encounters
  - Cameras (area cutscenes)
  - Path nodes from the matching PTH file

Design references:
    PyKotor HolocronToolset GIT editor:
        Tools/HolocronToolset/src/toolset/gui/editors/git/
    GIT format docstring (PyKotor):
        Libraries/PyKotor/src/pykotor/resource/generics/git.py
    GIT C# implementation:
        https://github.com/th3w1zard1/Kotor.NET/tree/master/Kotor.NET/Resources/KotorGIT/GIT.cs
    GIT instance sections:
        Creature List, Door List, Placeable List, Waypoint List, TriggerList,
        StoreList, SoundList, EncounterList, CameraList

Runs headlessly when Qt is unavailable (pure data model + render-to-image path).
"""
from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

# ── Colour table (one per instance type) ─────────────────────────────────────
_TYPE_COLORS: dict[str, tuple[int, int, int]] = {
    "creature":   (0x4C, 0xAF, 0x50),   # green
    "door":       (0x21, 0x96, 0xF3),   # blue
    "placeable":  (0xFF, 0x98, 0x00),   # amber
    "waypoint":   (0xE9, 0x1E, 0x63),   # pink
    "trigger":    (0x9C, 0x27, 0xB0),   # purple
    "store":      (0x00, 0x96, 0x88),   # teal
    "sound":      (0x03, 0xA9, 0xF4),   # light blue
    "encounter":  (0xF4, 0x43, 0x36),   # red
    "camera":     (0xFF, 0xEB, 0x3B),   # yellow
    "path_node":  (0x78, 0x90, 0x9C),   # blue-grey
}

# Node radius in world units
_NODE_RADIUS = 0.6

# ── Instance data model ───────────────────────────────────────────────────────

class GITNode:
    """Single positioned node extracted from a GIT instance list."""

    __slots__ = ("kind", "tag", "resref", "x", "y", "z", "camera_id",
                 "pitch", "selected", "connections")

    def __init__(
        self,
        kind: str,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        tag: str = "",
        resref: str = "",
        camera_id: int | None = None,
        pitch: float | None = None,
    ) -> None:
        self.kind = kind
        self.x = x
        self.y = y
        self.z = z
        self.tag = tag
        self.resref = resref
        self.camera_id = camera_id
        self.pitch = pitch
        self.selected: bool = False
        self.connections: list[int] = []   # indices for path nodes

    def to_dict(self) -> dict:
        d: dict = {
            "kind": self.kind,
            "x": self.x,
            "y": self.y,
            "z": self.z,
        }
        if self.tag:    d["tag"]    = self.tag
        if self.resref: d["resref"] = self.resref
        if self.camera_id is not None: d["camera_id"] = self.camera_id
        if self.pitch    is not None: d["pitch"]     = self.pitch
        if self.connections:          d["connections"] = self.connections
        return d


# ── Scene model ───────────────────────────────────────────────────────────────

class GITScene:
    """Holds all nodes for one area's GIT data."""

    def __init__(self, resref: str = "", game: str = "K1") -> None:
        self.resref = resref
        self.game = game
        self.nodes: list[GITNode] = []
        self.parse_errors: list[str] = []

    # ── Loaders ───────────────────────────────────────────────────────────────

    def load_from_area_dict(self, area: dict) -> None:
        """Populate from a dict returned by the getArea MCP tool."""
        self.nodes.clear()
        self.parse_errors = area.get("parse_errors", [])

        _MAP = {
            "creature":   ("creatures",  "creature"),
            "door":       ("doors",      "door"),
            "placeable":  ("placeables", "placeable"),
            "waypoint":   ("waypoints",  "waypoint"),
            "trigger":    ("triggers",   "trigger"),
            "store":      ("stores",     "store"),
            "sound":      ("sounds",     "sound"),
            "encounter":  ("encounters", "encounter"),
        }
        for list_key, kind in _MAP.values():
            for item in area.get(list_key, []):
                self.nodes.append(GITNode(
                    kind=kind,
                    x=float(item.get("x") or 0),
                    y=float(item.get("y") or 0),
                    z=float(item.get("z") or 0),
                    tag=item.get("tag", ""),
                    resref=item.get("resref", ""),
                ))

        for cam in area.get("cameras", []):
            self.nodes.append(GITNode(
                kind="camera",
                x=float(cam.get("x") or 0),
                y=float(cam.get("y") or 0),
                z=float(cam.get("z") or 0),
                camera_id=cam.get("camera_id"),
                pitch=cam.get("pitch"),
            ))

    def load_from_pth_dict(self, pth: dict) -> None:
        """Overlay path-node data from a readPTH tool response."""
        points = pth.get("points", [])
        offset = len(self.nodes)
        for pt in points:
            node = GITNode(
                kind="path_node",
                x=float(pt.get("x") or 0),
                y=float(pt.get("y") or 0),
            )
            node.connections = [c + offset for c in (pt.get("connections") or [])]
            self.nodes.append(node)

    def load_from_json_bytes(self, data: bytes) -> None:
        """Load from a JSON export produced by to_json()."""
        obj = json.loads(data)
        self.resref = obj.get("resref", self.resref)
        self.game   = obj.get("game",   self.game)
        self.nodes  = [
            GITNode(**{k: v for k, v in n.items() if k != "connections"})
            for n in obj.get("nodes", [])
        ]
        for i, n_dict in enumerate(obj.get("nodes", [])):
            self.nodes[i].connections = n_dict.get("connections", [])
        self.parse_errors = obj.get("parse_errors", [])

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps({
            "resref": self.resref,
            "game":   self.game,
            "node_count": len(self.nodes),
            "parse_errors": self.parse_errors,
            "nodes": [n.to_dict() for n in self.nodes],
        }, indent=indent)

    # ── Queries ───────────────────────────────────────────────────────────────

    def node_at(self, wx: float, wy: float, radius: float = _NODE_RADIUS) -> GITNode | None:
        """Return the first node within *radius* world units of (wx, wy)."""
        best: GITNode | None = None
        best_dist = radius
        for node in self.nodes:
            d = math.hypot(node.x - wx, node.y - wy)
            if d < best_dist:
                best_dist = d
                best = node
        return best

    def bounds(self) -> tuple[float, float, float, float]:
        """Return (min_x, min_y, max_x, max_y) for all nodes."""
        if not self.nodes:
            return (-10.0, -10.0, 10.0, 10.0)
        xs = [n.x for n in self.nodes]
        ys = [n.y for n in self.nodes]
        pad = 5.0
        return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad

    def summary(self) -> dict:
        """Return per-type counts."""
        counts: dict[str, int] = {}
        for node in self.nodes:
            counts[node.kind] = counts.get(node.kind, 0) + 1
        return counts


# ── ASCII renderer (headless) ─────────────────────────────────────────────────

_ASCII_GLYPHS: dict[str, str] = {
    "creature":  "C",
    "door":      "D",
    "placeable": "P",
    "waypoint":  "W",
    "trigger":   "T",
    "store":     "S",
    "sound":     "A",  # Audio
    "encounter": "E",
    "camera":    "K",  # Kamera
    "path_node": "·",
}


def render_ascii(scene: GITScene, cols: int = 80, rows: int = 30) -> str:
    """Render a GIT scene to an ASCII grid for terminal / test output."""
    min_x, min_y, max_x, max_y = scene.bounds()
    w = max(max_x - min_x, 0.001)
    h = max(max_y - min_y, 0.001)

    grid = [[" "] * cols for _ in range(rows)]

    def _grid_pos(x: float, y: float) -> tuple[int, int]:
        col = int((x - min_x) / w * (cols - 1))
        row = int((1.0 - (y - min_y) / h) * (rows - 1))
        return (
            max(0, min(cols - 1, col)),
            max(0, min(rows - 1, row)),
        )

    # Draw path connections first
    for node in scene.nodes:
        if node.kind == "path_node":
            for ci in node.connections:
                if ci < len(scene.nodes):
                    other = scene.nodes[ci]
                    c1, r1 = _grid_pos(node.x, node.y)
                    c2, r2 = _grid_pos(other.x, other.y)
                    # Bresenham
                    dc, dr = abs(c2 - c1), abs(r2 - r1)
                    sc = 1 if c1 < c2 else -1
                    sr = 1 if r1 < r2 else -1
                    err = dc - dr
                    cc, cr = c1, r1
                    while True:
                        if grid[cr][cc] == " ":
                            grid[cr][cc] = "─" if dc >= dr else "│"
                        if cc == c2 and cr == r2:
                            break
                        e2 = 2 * err
                        if e2 > -dr:
                            err -= dr
                            cc += sc
                        if e2 < dc:
                            err += dc
                            cr += sr

    # Draw nodes
    for node in scene.nodes:
        glyph = _ASCII_GLYPHS.get(node.kind, "?")
        col, row = _grid_pos(node.x, node.y)
        grid[row][col] = glyph

    lines = ["".join(row) for row in grid]
    legend = "  ".join(f"{g}={k}" for k, g in _ASCII_GLYPHS.items())
    summary = "  ".join(f"{k}:{v}" for k, v in sorted(scene.summary().items()))
    header = f"GIT area={scene.resref!r} game={scene.game}"
    return "\n".join([header, summary, "─" * cols, *lines, "─" * cols, legend])


# ── Qt widget (optional) ──────────────────────────────────────────────────────

try:
    from qtpy.QtCore import Qt, QPointF, QRectF, pyqtSignal   # type: ignore[import]
    from qtpy.QtGui import (                                    # type: ignore[import]
        QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
        QResizeEvent, QWheelEvent, QMouseEvent,
    )
    from qtpy.QtWidgets import (                                # type: ignore[import]
        QFrame, QLabel, QSizePolicy, QSplitter, QTableWidget,
        QTableWidgetItem, QVBoxLayout, QWidget,
    )
    _QT_AVAILABLE = True
except Exception:
    _QT_AVAILABLE = False


if _QT_AVAILABLE:

    class _GITCanvas(QFrame):
        """A 2-D OpenGL-less canvas that renders GITScene nodes via QPainter."""

        nodeSelected = pyqtSignal(object)   # emits GITNode | None

        def __init__(self, parent: "QWidget | None" = None) -> None:
            super().__init__(parent)
            self.setMinimumSize(300, 300)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.setStyleSheet("background-color: #1E1E2E;")

            self._scene = GITScene()
            self._zoom: float = 1.0
            self._pan_x: float = 0.0
            self._pan_y: float = 0.0
            self._drag_start: "QPointF | None" = None

        def set_scene(self, scene: GITScene) -> None:
            self._scene = scene
            self._fit()
            self.update()

        def _fit(self) -> None:
            """Fit the scene bounds into the viewport."""
            if not self._scene.nodes:
                return
            min_x, min_y, max_x, max_y = self._scene.bounds()
            scene_w = max(max_x - min_x, 1.0)
            scene_h = max(max_y - min_y, 1.0)
            vw, vh = self.width(), self.height()
            self._zoom = min(vw / scene_w, vh / scene_h) * 0.85
            cx = (min_x + max_x) / 2
            cy = (min_y + max_y) / 2
            self._pan_x = vw / 2 - cx * self._zoom
            self._pan_y = vh / 2 + cy * self._zoom   # y-flip

        def _world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
            return wx * self._zoom + self._pan_x, -wy * self._zoom + self._pan_y

        def _screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
            return (sx - self._pan_x) / self._zoom, -(sy - self._pan_y) / self._zoom

        def paintEvent(self, _event) -> None:          # type: ignore[override]
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)

            # Grid
            p.setPen(QPen(QColor("#2A2A3E"), 1))
            for gx in range(-20, 21):
                sx, _ = self._world_to_screen(gx * 5, 0)
                p.drawLine(int(sx), 0, int(sx), self.height())
            for gy in range(-20, 21):
                _, sy = self._world_to_screen(0, gy * 5)
                p.drawLine(0, int(sy), self.width(), int(sy))

            # Path connections
            pen_path = QPen(QColor("#607D8B"), 1, Qt.DashLine)
            p.setPen(pen_path)
            for node in self._scene.nodes:
                if node.kind == "path_node":
                    sx1, sy1 = self._world_to_screen(node.x, node.y)
                    for ci in node.connections:
                        if ci < len(self._scene.nodes):
                            other = self._scene.nodes[ci]
                            sx2, sy2 = self._world_to_screen(other.x, other.y)
                            p.drawLine(int(sx1), int(sy1), int(sx2), int(sy2))

            # Nodes
            font = QFont("monospace", 7)
            p.setFont(font)
            r = max(4, int(_NODE_RADIUS * self._zoom))

            for node in self._scene.nodes:
                sx, sy = self._world_to_screen(node.x, node.y)
                rgb = _TYPE_COLORS.get(node.kind, (128, 128, 128))
                color = QColor(*rgb)
                if node.selected:
                    p.setPen(QPen(QColor("white"), 2))
                    p.setBrush(QBrush(color.lighter(140)))
                else:
                    p.setPen(QPen(color.darker(150), 1))
                    p.setBrush(QBrush(color))

                p.drawEllipse(int(sx) - r, int(sy) - r, r * 2, r * 2)

                # Label (tag or type glyph)
                label = node.tag[:6] if node.tag else _ASCII_GLYPHS.get(node.kind, "?")
                p.setPen(QPen(QColor("white")))
                p.drawText(int(sx) + r + 2, int(sy) + 4, label)

            p.end()

        def wheelEvent(self, event: "QWheelEvent") -> None:   # type: ignore[override]
            delta = event.angleDelta().y()
            factor = 1.15 if delta > 0 else 1 / 1.15
            old_wx, old_wy = self._screen_to_world(event.position().x(), event.position().y())
            self._zoom *= factor
            new_sx, new_sy = self._world_to_screen(old_wx, old_wy)
            self._pan_x += event.position().x() - new_sx
            self._pan_y += event.position().y() - new_sy
            self.update()

        def mousePressEvent(self, event: "QMouseEvent") -> None:   # type: ignore[override]
            if event.button() == Qt.LeftButton:
                wx, wy = self._screen_to_world(event.position().x(), event.position().y())
                threshold = _NODE_RADIUS * 2
                hit = self._scene.node_at(wx, wy, radius=threshold)
                for node in self._scene.nodes:
                    node.selected = (node is hit)
                self.nodeSelected.emit(hit)
                self.update()
            elif event.button() == Qt.MiddleButton:
                self._drag_start = event.position()

        def mouseMoveEvent(self, event: "QMouseEvent") -> None:  # type: ignore[override]
            if self._drag_start is not None:
                dx = event.position().x() - self._drag_start.x()
                dy = event.position().y() - self._drag_start.y()
                self._pan_x += dx
                self._pan_y += dy
                self._drag_start = event.position()
                self.update()

        def mouseReleaseEvent(self, event: "QMouseEvent") -> None:  # type: ignore[override]
            if event.button() == Qt.MiddleButton:
                self._drag_start = None

        def resizeEvent(self, event: "QResizeEvent") -> None:    # type: ignore[override]
            super().resizeEvent(event)
            self._fit()


    class GITNodeGraphWidget(QWidget):
        """Two-pane widget: 2-D canvas (left) + node detail table (right).

        Usage::

            widget = GITNodeGraphWidget()
            widget.load_area_dict(area_data)   # dict from getArea MCP tool
            widget.load_pth_dict(pth_data)     # optional, from readPTH tool
        """

        def __init__(self, parent: "QWidget | None" = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("GIT Node-Graph Editor")

            self._scene = GITScene()

            # ── Layout ────────────────────────────────────────────────────────
            splitter = QSplitter(Qt.Horizontal, self)

            self._canvas = _GITCanvas()
            self._canvas.nodeSelected.connect(self._on_node_selected)

            right = QWidget()
            rlayout = QVBoxLayout(right)
            self._label_summary = QLabel("No area loaded.")
            self._label_summary.setStyleSheet("font-weight: bold;")
            rlayout.addWidget(self._label_summary)

            self._table = QTableWidget(0, 5)
            self._table.setHorizontalHeaderLabels(
                ["Kind", "Tag", "ResRef", "X", "Y"]
            )
            self._table.horizontalHeader().setStretchLastSection(True)
            self._table.setEditTriggers(QTableWidget.NoEditTriggers)
            self._table.setSelectionBehavior(QTableWidget.SelectRows)
            rlayout.addWidget(self._table)

            splitter.addWidget(self._canvas)
            splitter.addWidget(right)
            splitter.setSizes([600, 300])

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(splitter)

        # ── Public API ────────────────────────────────────────────────────────

        def load_area_dict(self, area: dict) -> None:
            """Populate the scene from a getArea tool response dict."""
            self._scene = GITScene(
                resref=area.get("resref", ""),
                game=area.get("game", "K1"),
            )
            self._scene.load_from_area_dict(area)
            self._canvas.set_scene(self._scene)
            self._refresh_table()
            summary = self._scene.summary()
            parts = [f"{k}: {v}" for k, v in sorted(summary.items())]
            self._label_summary.setText(
                f"Area: {self._scene.resref}  [{self._scene.game}]  "
                + "  ".join(parts)
            )

        def load_pth_dict(self, pth: dict) -> None:
            """Overlay path nodes from a readPTH tool response dict."""
            self._scene.load_from_pth_dict(pth)
            self._canvas.update()
            self._refresh_table()

        def clear(self) -> None:
            self._scene = GITScene()
            self._canvas.set_scene(self._scene)
            self._refresh_table()
            self._label_summary.setText("No area loaded.")

        def scene(self) -> GITScene:
            return self._scene

        # ── Private helpers ───────────────────────────────────────────────────

        def _refresh_table(self) -> None:
            self._table.setRowCount(len(self._scene.nodes))
            for row, node in enumerate(self._scene.nodes):
                self._table.setItem(row, 0, QTableWidgetItem(node.kind))
                self._table.setItem(row, 1, QTableWidgetItem(node.tag))
                self._table.setItem(row, 2, QTableWidgetItem(node.resref))
                self._table.setItem(row, 3, QTableWidgetItem(f"{node.x:.2f}"))
                self._table.setItem(row, 4, QTableWidgetItem(f"{node.y:.2f}"))
                # Colour the row
                rgb = _TYPE_COLORS.get(node.kind, (80, 80, 80))
                bg = QColor(*rgb, 60)
                for col in range(5):
                    item = self._table.item(row, col)
                    if item:
                        item.setBackground(QBrush(bg))

        def _on_node_selected(self, node: "GITNode | None") -> None:
            if node is None:
                self._table.clearSelection()
                return
            try:
                idx = self._scene.nodes.index(node)
                self._table.selectRow(idx)
                self._table.scrollTo(self._table.model().index(idx, 0))
            except ValueError:
                pass

else:
    # Headless stub — only GITScene + render_ascii are functional
    class GITNodeGraphWidget:   # type: ignore[no-redef]
        """Stub when Qt is unavailable — use GITScene + render_ascii directly."""

        def __init__(self, parent=None) -> None:
            self._scene = GITScene()

        def load_area_dict(self, area: dict) -> None:
            self._scene = GITScene(
                resref=area.get("resref", ""),
                game=area.get("game", "K1"),
            )
            self._scene.load_from_area_dict(area)

        def load_pth_dict(self, pth: dict) -> None:
            self._scene.load_from_pth_dict(pth)

        def clear(self) -> None:
            self._scene = GITScene()

        def scene(self) -> GITScene:
            return self._scene


__all__ = [
    "GITScene",
    "GITNode",
    "GITNodeGraphWidget",
    "render_ascii",
    "_TYPE_COLORS",
    "_ASCII_GLYPHS",
    "_QT_AVAILABLE",
]
