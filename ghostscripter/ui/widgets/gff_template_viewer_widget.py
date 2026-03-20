"""
GhostScripter-K1-K2 — GFF Template Viewer Widget
==================================================
Displays KotOR GFF template files (.utc, .uti, .utp, .utt, .utm, .uts, .utw)
in a structured, read-only form with clearly labelled sections.

Supported types
---------------
.utc  — Creature template
.uti  — Item template
.utp  — Placeable template
.utt  — Trigger template
.utm  — Merchant template
.uts  — Sound template
.utw  — Waypoint template
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

try:
    from qtpy.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
        QFrame, QSizePolicy, QGroupBox, QFormLayout, QSplitter,
        QTreeWidget, QTreeWidgetItem, QTabWidget, QTextEdit,
    )
    from qtpy.QtCore import Qt
    from qtpy.QtGui import QFont, QColor
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False

# ── Styling constants ─────────────────────────────────────────────────────────

_DARK_BG    = "#1e1e1e"
_PANEL_BG   = "#252526"
_BORDER     = "#3f3f46"
_TEXT       = "#d4d4d4"
_LABEL      = "#9cdcfe"   # light-blue like VSCode identifier
_VALUE      = "#ce9178"   # orange-ish string value
_SECTION_FG = "#4ec9b0"   # teal for section headings
_SCRIPTS_FG = "#dcdcaa"   # yellow for script fields

_STYLE_TREE = (
    f"QTreeWidget {{ background:{_DARK_BG}; color:{_TEXT}; border:1px solid {_BORDER};"
    f"  font-size:12px; }}"
    f"QTreeWidget::item:selected {{ background:#094771; }}"
    f"QHeaderView::section {{ background:{_PANEL_BG}; color:{_TEXT}; padding:4px;"
    f"  border:1px solid {_BORDER}; }}"
)
_STYLE_SCROLL = (
    f"QScrollArea {{ background:{_DARK_BG}; border:none; }}"
    f"QWidget {{ background:{_DARK_BG}; }}"
)
_STYLE_GROUP = (
    f"QGroupBox {{ color:{_SECTION_FG}; border:1px solid {_BORDER}; border-radius:4px;"
    f"  margin-top:8px; font-weight:bold; font-size:12px; padding-top:6px; }}"
    f"QGroupBox::title {{ subcontrol-origin:margin; left:8px; padding:0 4px; }}"
)
_STYLE_LABEL_KEY = (
    f"color:{_LABEL}; font-size:11px;"
)
_STYLE_LABEL_VAL = (
    f"color:{_VALUE}; font-size:11px; font-family:monospace;"
)
_STYLE_LABEL_SCRIPT = (
    f"color:{_SCRIPTS_FG}; font-size:11px; font-family:monospace;"
)
_STYLE_HEADER = (
    f"color:{_SECTION_FG}; font-size:14px; font-weight:bold;"
)

# ── Type metadata ─────────────────────────────────────────────────────────────

_TYPE_META: dict[str, dict] = {
    ".utc": {
        "label": "Creature Template",
        "icon": "👾",
        "loader": "read_utc",
        "module": "pykotor.resource.generics.utc",
        "sections": [
            ("Identity", ["resref", "tag", "first_name", "last_name", "subrace_name",
                          "race_id", "gender_id", "alignment", "lawfulness",
                          "portrait_id", "portrait_resref", "comment"]),
            ("Appearance", ["appearance_id", "body_variation", "texture_variation",
                            "phenotype_id", "walkrate_id", "soundset_id",
                            "faction_id", "perception_id", "palette_id",
                            "bodybag_id", "deity"]),
            ("Stats", ["strength", "dexterity", "constitution", "intelligence",
                       "wisdom", "charisma", "challenge_rating", "natural_ac",
                       "reflex_bonus", "willpower_bonus", "fortitude_bonus",
                       "save_will", "save_fortitude"]),
            ("Health / Force", ["current_hp", "max_hp", "hp", "fp", "max_fp",
                                "morale", "morale_recovery", "morale_breakpoint"]),
            ("Skills", ["computer_use", "demolitions", "stealth", "awareness",
                        "persuade", "repair", "security", "treat_injury"]),
            ("Flags", ["is_pc", "plot", "no_perm_death", "min1_hp", "disarmable",
                       "interruptable", "party_interact", "not_reorienting",
                       "ignore_cre_path", "hologram", "will_not_render",
                       "blindspot", "multiplier_set"]),
            ("Conversation", ["conversation", "description"]),
            ("Scripts", ["on_end_dialog", "on_blocked", "on_heartbeat", "on_notice",
                         "on_spell", "on_attacked", "on_damaged", "on_disturbed",
                         "on_end_round", "on_dialog", "on_spawn", "on_rested",
                         "on_death", "on_user_defined"]),
        ],
        "list_sections": [
            ("Classes", "classes"),
            ("Feats", "feats"),
            ("Inventory", "inventory"),
            ("Equipment", "equipment"),
        ],
    },
    ".uti": {
        "label": "Item Template",
        "icon": "🗡️",
        "loader": "read_uti",
        "module": "pykotor.resource.generics.uti",
        "sections": [
            ("Identity", ["resref", "tag", "name", "description", "description2",
                          "base_item", "comment"]),
            ("Stats", ["charges", "cost", "add_cost", "stack_size",
                       "upgrade_level", "palette_id"]),
            ("Appearance", ["body_variation", "model_variation", "texture_variation"]),
            ("Flags", ["plot", "identified", "stolen"]),
        ],
        "list_sections": [
            ("Properties", "properties"),
        ],
    },
    ".utp": {
        "label": "Placeable Template",
        "icon": "📦",
        "loader": "read_utp",
        "module": "pykotor.resource.generics.utp",
        "sections": [
            ("Identity", ["resref", "tag", "name", "description", "comment"]),
            ("Appearance", ["appearance_id", "portrait_id", "faction_id",
                            "animation_state", "palette_id", "bodybag_id"]),
            ("Health", ["current_hp", "maximum_hp", "hardness", "fortitude",
                        "will", "reflex"]),
            ("Lock / Key", ["locked", "lockable", "lock_dc", "unlock_dc",
                            "unlock_diff", "unlock_diff_mod",
                            "auto_remove_key", "key_name", "key_required"]),
            ("Trap", ["trap_flag", "trap_type", "trap_detectable", "trap_detect_dc",
                      "trap_disarmable", "trap_disarm_dc", "trap_one_shot"]),
            ("Flags", ["plot", "static", "useable", "party_interact",
                       "interruptable", "min1_hp", "not_blastable",
                       "has_inventory", "type_id"]),
            ("Conversation", ["conversation"]),
            ("Scripts", ["on_closed", "on_open", "on_damaged", "on_death",
                         "on_end_dialog", "on_open_failed", "on_heartbeat",
                         "on_inventory", "on_melee_attack", "on_force_power",
                         "on_lock", "on_unlock", "on_used", "on_user_defined",
                         "on_disarm", "on_trap_triggered"]),
        ],
        "list_sections": [
            ("Inventory", "inventory"),
        ],
    },
    ".utt": {
        "label": "Trigger Template",
        "icon": "⚡",
        "loader": "read_utt",
        "module": "pykotor.resource.generics.utt",
        "sections": [
            ("Identity", ["resref", "tag", "name", "comment"]),
            ("Properties", ["faction_id", "cursor_id", "type_id",
                            "highlight_height", "portrait_id",
                            "loadscreen_id", "palette_id"]),
            ("Key", ["auto_remove_key", "key_name"]),
            ("Trap", ["is_trap", "trap_type", "trap_once",
                      "trap_detectable", "trap_detect_dc",
                      "trap_disarmable", "trap_disarm_dc"]),
            ("Scripts", ["on_click", "on_enter", "on_exit", "on_heartbeat",
                         "on_disarm", "on_trap_triggered", "on_user_defined"]),
        ],
        "list_sections": [],
    },
    ".utm": {
        "label": "Merchant / Store Template",
        "icon": "🏪",
        "loader": "read_utm",
        "module": "pykotor.resource.generics.utm",
        "sections": [
            ("Identity", ["resref", "tag", "name", "id", "comment"]),
            ("Trade", ["can_buy", "can_sell", "mark_up", "mark_down"]),
            ("Scripts", ["on_open"]),
        ],
        "list_sections": [
            ("Inventory", "inventory"),
        ],
    },
    ".uts": {
        "label": "Sound Template",
        "icon": "🔊",
        "loader": "read_uts",
        "module": "pykotor.resource.generics.uts",
        "sections": [
            ("Identity", ["resref", "tag", "name", "comment", "palette_id"]),
            ("Playback", ["active", "continuous", "looping", "random_pick",
                          "positional", "random_position",
                          "random_range_x", "random_range_y", "elevation"]),
            ("Volume / Pitch", ["volume", "volume_variation",
                                "pitch_variation", "priority"]),
            ("Distance", ["min_distance", "max_distance"]),
            ("Timing", ["interval", "interval_variation", "times", "hours"]),
        ],
        "list_sections": [
            ("Sound Files", "sounds"),
        ],
    },
    ".utw": {
        "label": "Waypoint Template",
        "icon": "📍",
        "loader": "read_utw",
        "module": "pykotor.resource.generics.utw",
        "sections": [
            ("Identity", ["resref", "tag", "name", "description",
                          "comment", "appearance_id", "palette_id"]),
            ("Map Note", ["has_map_note", "map_note_enabled", "map_note"]),
            ("Link", ["linked_to"]),
        ],
        "list_sections": [],
    },
}

# ── Widget ─────────────────────────────────────────────────────────────────────

class GFFTemplateViewerWidget(QWidget):
    """
    Read-only viewer for a KotOR GFF template file.

    Parameters
    ----------
    resref : str
        Base name of the resource (without extension).
    ext : str
        File extension including the dot, e.g. ``".utc"``.
    raw_data : bytes
        Raw GFF binary bytes.
    parent : QWidget | None
    """

    def __init__(
        self,
        resref: str,
        ext: str,
        raw_data: bytes,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._resref   = resref
        self._ext      = ext.lower()
        self._raw_data = raw_data

        if not _QT_AVAILABLE:
            return

        self._setup_ui()
        self._load_template()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── header bar ──────────────────────────────────────────────
        header_frame = QFrame()
        header_frame.setStyleSheet(
            f"QFrame {{ background:{_PANEL_BG}; border-bottom:1px solid {_BORDER}; }}"
        )
        header_frame.setFixedHeight(36)
        hl = QHBoxLayout(header_frame)
        hl.setContentsMargins(10, 0, 10, 0)

        meta  = _TYPE_META.get(self._ext, {})
        icon  = meta.get("icon", "📄")
        label = meta.get("label", self._ext.upper().lstrip(".") + " File")

        title = QLabel(f"{icon}  {self._resref}{self._ext}  —  {label}")
        title.setStyleSheet(_STYLE_HEADER)
        hl.addWidget(title)
        hl.addStretch()

        self._status_label = QLabel("Loading…")
        self._status_label.setStyleSheet(f"color:#808080; font-size:11px;")
        hl.addWidget(self._status_label)

        root.addWidget(header_frame)

        # ── splitter: form on left, raw hex on right ─────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background:{_BORDER}; width:1px; }}"
        )

        # Form scroll area
        self._form_tabs = QTabWidget()
        self._form_tabs.setStyleSheet(
            f"QTabWidget::pane {{ border:1px solid {_BORDER}; background:{_DARK_BG}; }}"
            f"QTabBar::tab {{ background:{_PANEL_BG}; color:{_TEXT}; padding:4px 10px;"
            f"  border:1px solid {_BORDER}; border-bottom:none; }}"
            f"QTabBar::tab:selected {{ background:{_DARK_BG}; }}"
        )
        splitter.addWidget(self._form_tabs)

        # Raw view (right panel)
        raw_frame = QWidget()
        raw_vl = QVBoxLayout(raw_frame)
        raw_vl.setContentsMargins(4, 4, 4, 4)
        raw_lbl = QLabel("Raw Data")
        raw_lbl.setStyleSheet(f"color:{_SECTION_FG}; font-weight:bold; font-size:11px;")
        raw_vl.addWidget(raw_lbl)
        self._raw_text = QTextEdit()
        self._raw_text.setReadOnly(True)
        self._raw_text.setStyleSheet(
            f"QTextEdit {{ background:{_DARK_BG}; color:#808080; border:none;"
            f"  font-family:monospace; font-size:10px; }}"
        )
        raw_vl.addWidget(self._raw_text)
        splitter.addWidget(raw_frame)
        splitter.setSizes([700, 300])

        root.addWidget(splitter)

    # ── Template loading ──────────────────────────────────────────────────────

    def _load_template(self) -> None:
        meta = _TYPE_META.get(self._ext)
        if not meta:
            self._show_raw_fallback()
            return

        loader_name = meta["loader"]
        module_name = meta["module"]

        try:
            mod    = __import__(module_name, fromlist=[loader_name])
            loader = getattr(mod, loader_name)
            obj    = loader(self._raw_data)
        except Exception as exc:
            log.warning("GFFTemplateViewer: could not parse %s%s: %s",
                        self._resref, self._ext, exc)
            self._show_raw_fallback(str(exc))
            return

        # ── populate form tabs ────────────────────────────────────────
        self._populate_sections(obj, meta["sections"])
        self._populate_list_sections(obj, meta.get("list_sections", []))

        # ── raw hex dump (just the first 512 bytes) ───────────────────
        hex_lines = []
        chunk_size = 16
        for i in range(0, min(512, len(self._raw_data)), chunk_size):
            chunk = self._raw_data[i:i+chunk_size]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            asc_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            hex_lines.append(f"{i:04x}  {hex_part:<48}  {asc_part}")
        if len(self._raw_data) > 512:
            hex_lines.append(f"… ({len(self._raw_data):,} bytes total)")
        self._raw_text.setPlainText("\n".join(hex_lines))

        size_kb = len(self._raw_data) / 1024
        self._status_label.setText(f"{size_kb:.1f} KB  •  {self._ext.lstrip('.')} parsed OK")

    def _populate_sections(self, obj: Any, sections: list) -> None:
        """Add one QScrollArea tab per section of fields."""
        for section_name, fields in sections:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet(_STYLE_SCROLL)

            container = QWidget()
            vl = QVBoxLayout(container)
            vl.setContentsMargins(8, 8, 8, 8)
            vl.setSpacing(4)
            vl.setAlignment(Qt.AlignTop)

            is_scripts = section_name.lower() == "scripts"
            has_any = False

            for field in fields:
                val = getattr(obj, field, None)
                if val is None:
                    continue
                has_any = True
                row = QHBoxLayout()
                row.setSpacing(8)

                key_lbl = QLabel(field.replace("_", " ").title() + ":")
                key_lbl.setStyleSheet(_STYLE_LABEL_KEY)
                key_lbl.setFixedWidth(160)
                key_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                row.addWidget(key_lbl)

                val_str = self._format_value(val)
                val_lbl = QLabel(val_str)
                val_lbl.setStyleSheet(
                    _STYLE_LABEL_SCRIPT if is_scripts else _STYLE_LABEL_VAL
                )
                val_lbl.setWordWrap(True)
                val_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                row.addWidget(val_lbl, 1)

                vl.addLayout(row)

            if not has_any:
                empty_lbl = QLabel("(no fields)")
                empty_lbl.setStyleSheet("color:#606060; font-size:11px;")
                vl.addWidget(empty_lbl)

            vl.addStretch()
            scroll.setWidget(container)
            self._form_tabs.addTab(scroll, section_name)

    def _populate_list_sections(self, obj: Any, list_sections: list) -> None:
        """Add one QTreeWidget tab per list-type field (inventory, feats, etc.)."""
        for section_name, attr in list_sections:
            items = getattr(obj, attr, None)
            if not items:
                continue

            tree = QTreeWidget()
            tree.setStyleSheet(_STYLE_TREE)
            tree.setHeaderHidden(False)
            tree.setRootIsDecorated(False)
            tree.setAlternatingRowColors(True)
            tree.setColumnCount(2)
            tree.setHeaderLabels(["#", "Value"])
            tree.header().setStretchLastSection(True)

            for i, item in enumerate(items):
                it = QTreeWidgetItem([str(i), self._format_value(item)])
                it.setForeground(0, QColor("#808080"))
                it.setForeground(1, QColor(_VALUE))
                tree.addTopLevelItem(it)

            tree.resizeColumnToContents(0)
            self._form_tabs.addTab(tree, f"{section_name} ({len(items)})")

    # ── Fallback ──────────────────────────────────────────────────────────────

    def _show_raw_fallback(self, error_msg: str = "") -> None:
        """Show a raw hex-dump tab when parsing fails."""
        if error_msg:
            self._status_label.setText(f"Parse failed: {error_msg}")
        else:
            self._status_label.setText("Unknown type — raw view only")

        file_type = self._raw_data[:4].decode("ascii", errors="replace").strip() if self._raw_data else "?"
        version   = self._raw_data[4:8].decode("ascii", errors="replace").strip() if len(self._raw_data) >= 8 else "?"
        info_lbl  = QLabel(
            f"File type: {file_type}  Version: {version}\n"
            f"Size: {len(self._raw_data):,} bytes\n"
            + (f"\nError: {error_msg}" if error_msg else "")
        )
        info_lbl.setStyleSheet(f"color:{_TEXT}; font-size:12px; padding:12px;")
        info_lbl.setWordWrap(True)
        self._form_tabs.addTab(info_lbl, "Info")

        hex_lines = []
        for i in range(0, min(1024, len(self._raw_data)), 16):
            chunk = self._raw_data[i:i+16]
            hex_part = " ".join(f"{b:02x}" for b in chunk)
            asc_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            hex_lines.append(f"{i:04x}  {hex_part:<48}  {asc_part}")
        self._raw_text.setPlainText("\n".join(hex_lines))

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _format_value(val: Any) -> str:
        """Convert a template field value to a display string."""
        if val is None:
            return "(none)"
        if isinstance(val, bool):
            return "✓  Yes" if val else "✗  No"
        if isinstance(val, int):
            return str(val)
        if isinstance(val, float):
            return f"{val:.4f}"
        if isinstance(val, (list, tuple)):
            return f"[{len(val)} items]"
        s = str(val)
        return s if s else "(empty)"
