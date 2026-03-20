"""
ghostscripter/ui/dialogs/tutorial_dialog.py
============================================
GhostScripter — Interactive Tutorial / Quick-Start Guide

A toggleable floating helper window with:
  • Tabbed sections: Getting Started, Dialogue Editor, Script Editor,
    2DA / Tables, Keyboard Shortcuts, Tips & Tricks
  • Collapsible topic cards inside each tab
  • Persistent "show on startup" checkbox (saved to QSettings)
  • "?" button shortcut in toolbar and Help menu item

Users can keep it open alongside their work or dismiss it.
"""

from __future__ import annotations

from typing import List, Tuple

from qtpy.QtCore import Qt, QSettings, Signal
from qtpy.QtGui import QFont, QColor, QIcon, QKeySequence
from qtpy.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QScrollArea, QFrame,
    QCheckBox, QSizePolicy, QToolButton, QApplication,
    QTextBrowser, QSplitter,
)


# ── Palette (matches dark.qss) ────────────────────────────────────────────────

_DARK   = "#1e1e1e"
_PANEL  = "#252526"
_CARD   = "#2d2d30"
_BORDER = "#3c3c3c"
_TEAL   = "#4ec9b0"
_BLUE   = "#569cd6"
_LTBLUE = "#9cdcfe"
_ORANGE = "#ce9178"
_YELLOW = "#dcdcaa"
_GREEN  = "#6a9955"
_WHITE  = "#cccccc"
_DIM    = "#858585"
_RED    = "#f48771"


# ── Tutorial content ──────────────────────────────────────────────────────────
# Each section is (tab_title, [(card_title, html_body), ...])

_CONTENT: List[Tuple[str, List[Tuple[str, str]]]] = [

    # ── Tab 0: Getting Started ────────────────────────────────────────────────
    ("🚀 Getting Started", [

        ("What is GhostScripter?", f"""
<p style='color:{_WHITE}'>
GhostScripter is a <b style='color:{_TEAL}'>KotOR 1 &amp; 2 TSL modding IDE</b> — an all-in-one
editor for the files that define your mod's conversations, scripts, items,
and quest logic.
</p>
<ul style='color:{_WHITE}'>
  <li><b style='color:{_LTBLUE}'>Dialogue Editor</b> — Visual node graph + Legacy tree view for .dlg files</li>
  <li><b style='color:{_LTBLUE}'>Script Editor</b> — NWScript (.nss) syntax highlighting &amp; compiler</li>
  <li><b style='color:{_LTBLUE}'>Quest Builder</b> — Journal entries and quest variables</li>
  <li><b style='color:{_LTBLUE}'>2DA Manager</b> — Browse and edit .2da tables</li>
  <li><b style='color:{_LTBLUE}'>TLK Editor</b> — Edit dialog.tlk string references</li>
  <li><b style='color:{_LTBLUE}'>ERF Packer</b> — Package your mod files</li>
</ul>
"""),

        ("First-Time Setup", f"""
<p style='color:{_WHITE}'>Set your KotOR game directory so GhostScripter can load game resources:</p>
<ol style='color:{_WHITE}'>
  <li>Open <b style='color:{_YELLOW}'>File → Set KotOR Game Directory…</b></li>
  <li>Navigate to your KotOR install folder
      (e.g. <code style='color:{_ORANGE}'>C:\\Program Files (x86)\\Steam\\steamapps\\common\\Knights of the Old Republic</code>)</li>
  <li>The status bar at the bottom will show
      <b style='color:{_TEAL}'>🎮 swkotor</b> when connected</li>
</ol>
<p style='color:{_DIM}'>
  ℹ️ Game directory is optional — you can edit files without it, but the
  NPC picker and 2DA browser need it to load appearance.2da and other tables.
</p>
"""),

        ("Creating Your First Project", f"""
<ol style='color:{_WHITE}'>
  <li>Click <b style='color:{_YELLOW}'>File → New Project</b>  <span style='color:{_DIM}'>(Ctrl+Shift+N)</span></li>
  <li>Enter a project name (e.g. <code style='color:{_ORANGE}'>my_mod</code>) and folder</li>
  <li>Select KotOR 1 or KotOR 2 (TSL) as the target game</li>
  <li>GhostScripter creates a folder structure with placeholder files</li>
</ol>
<p style='color:{_DIM}'>
  Tip: You can also open individual .dlg / .nss / .2da files directly via
  File → Open or the menu shortcuts without creating a project.
</p>
"""),

        ("Opening an Existing .DLG File", f"""
<ol style='color:{_WHITE}'>
  <li>Use <b style='color:{_YELLOW}'>Dialog → Open .DLG File…</b>  <span style='color:{_DIM}'>(Ctrl+Shift+D)</span></li>
  <li>Navigate to your <code style='color:{_ORANGE}'>override/</code> folder and pick a <code style='color:{_ORANGE}'>.dlg</code> file</li>
  <li>The Dialogue Editor opens automatically with the file loaded</li>
  <li>Switch between <b style='color:{_TEAL}'>Visual</b> and <b style='color:{_TEAL}'>Legacy</b> mode using the Mode selector in the toolbar</li>
</ol>
<p style='color:{_RED}'>
  ⚠️ Large files (80+ entries) may take a moment to lay out — this is normal.
</p>
"""),
    ]),

    # ── Tab 1: Dialogue Editor ────────────────────────────────────────────────
    ("💬 Dialogue Editor", [

        ("Visual Mode — Navigation", f"""
<table style='color:{_WHITE}; border-collapse:collapse; width:100%'>
  <tr><td style='color:{_TEAL}; padding:3px 8px; white-space:nowrap'><b>Scroll wheel</b></td>
      <td style='padding:3px 8px'>Zoom in / out (anchored to cursor)</td></tr>
  <tr style='background:{_CARD}'><td style='color:{_TEAL}; padding:3px 8px; white-space:nowrap'><b>Middle-click drag</b></td>
      <td style='padding:3px 8px'>Pan the canvas</td></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px; white-space:nowrap'><b>Space + left-drag</b></td>
      <td style='padding:3px 8px'>Pan the canvas (Photoshop style)</td></tr>
  <tr style='background:{_CARD}'><td style='color:{_TEAL}; padding:3px 8px; white-space:nowrap'><b>Left-click node</b></td>
      <td style='padding:3px 8px'>Select node — loads it in the inspector</td></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px; white-space:nowrap'><b>Left-drag node</b></td>
      <td style='padding:3px 8px'>Move node (snaps to 16 px grid)</td></tr>
  <tr style='background:{_CARD}'><td style='color:{_TEAL}; padding:3px 8px; white-space:nowrap'><b>Double-click canvas</b></td>
      <td style='padding:3px 8px'>Fit all nodes in view</td></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px; white-space:nowrap'><b>Right-click node</b></td>
      <td style='padding:3px 8px'>Context menu: Connect to…, Add Branch, Delete</td></tr>
  <tr style='background:{_CARD}'><td style='color:{_TEAL}; padding:3px 8px; white-space:nowrap'><b>F</b></td>
      <td style='padding:3px 8px'>Fit all nodes in view</td></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px; white-space:nowrap'><b>Ctrl+0</b></td>
      <td style='padding:3px 8px'>Reset zoom to 100%</td></tr>
</table>
"""),

        ("Visual Mode — Wires & Node Colours", f"""
<p style='color:{_WHITE}'>Wires use the Unreal Engine Blueprint colour convention:</p>
<ul style='color:{_WHITE}'>
  <li><span style='color:{_TEAL}'>━━━</span>  <b style='color:{_TEAL}'>Solid teal (2.5 px)</b> — NPC entry → player reply connection</li>
  <li><span style='color:{_LTBLUE}'>╌╌╌</span>  <b style='color:{_LTBLUE}'>Dashed blue (1.5 px)</b> — player reply → NPC entry connection</li>
</ul>
<p style='color:{_WHITE}'>Node card colours:</p>
<ul style='color:{_WHITE}'>
  <li><b style='color:{_LTBLUE}'>Blue header</b> — Player reply node</li>
  <li><b style='color:{_ORANGE}'>Orange/teal header</b> — NPC entry node</li>
</ul>
<p style='color:{_WHITE}'>Node card badges:</p>
<ul style='color:{_WHITE}'>
  <li><span style='color:{_TEAL}'>▷ script_name</span> — a script is attached to this node</li>
  <li><span style='color:{_YELLOW}'>🔊 VO</span> — a voice-over audio file is linked</li>
</ul>
<p style='color:{_DIM}'>
  Hover over a wire to highlight it.  Wires update in real-time as you drag nodes.
</p>
"""),

        ("Adding & Connecting Nodes", f"""
<p style='color:{_WHITE}'><b>To add a new NPC line:</b></p>
<ol style='color:{_WHITE}'>
  <li>Click <b style='color:{_YELLOW}'>+ NPC Entry</b> in the toolbar</li>
  <li>Enter the NPC speaker tag (e.g. <code style='color:{_ORANGE}'>dan13</code>)</li>
  <li>The new node appears in the graph — click it to edit its text</li>
</ol>
<p style='color:{_WHITE}'><b>To connect two nodes:</b></p>
<ul style='color:{_WHITE}'>
  <li><b>Right-click</b> the source node → <b style='color:{_TEAL}'>🔗 Connect to…</b> → pick target</li>
  <li>Or click source node → open <b>Links</b> tab in inspector → use <b>+</b> button</li>
</ul>
<p style='color:{_WHITE}'><b>To set the conversation starter:</b></p>
<ul style='color:{_WHITE}'>
  <li>Click <b style='color:{_YELLOW}'>⬆ Add Starter</b> in the toolbar</li>
  <li>Pick which entry node the conversation begins at</li>
</ul>
"""),

        ("Node Inspector Tabs", f"""
<p style='color:{_WHITE}'>Click any node to load it in the inspector on the right:</p>
<ul style='color:{_WHITE}'>
  <li><b style='color:{_LTBLUE}'>Basic</b> — Node ID, text, speaker, listener, TLK StrRef</li>
  <li><b style='color:{_LTBLUE}'>Scripts</b> — Script (OnEnter), Script2 (TSL), script parameters</li>
  <li><b style='color:{_LTBLUE}'>Audio/Anim</b> — VO ResRef, sound, animations</li>
  <li><b style='color:{_LTBLUE}'>Links</b> — Branches (targets, active conditions, is_child flag)</li>
  <li><b style='color:{_LTBLUE}'>Camera</b> — Camera angle, ID, FOV, height (KotOR 1 &amp; TSL)</li>
  <li><b style='color:{_LTBLUE}'>TSL</b> — NodeUnskippable, AlienRaceNode (TSL only)</li>
</ul>
<p style='color:{_DIM}'>Changes save automatically after a short debounce (80 ms).</p>
"""),

        ("Legacy Mode", f"""
<p style='color:{_WHITE}'>
Switch to <b style='color:{_TEAL}'>Legacy</b> mode using the Mode selector in the toolbar to get
a tree-list view modelled on DLGEditor v2.3.2:
</p>
<ul style='color:{_WHITE}'>
  <li><b style='color:{_ORANGE}'>Orange ◆</b> — NPC entry nodes</li>
  <li><b style='color:{_LTBLUE}'>Blue ►</b> — Player reply nodes</li>
  <li>⚠️ Orphaned nodes appear with a warning at the bottom</li>
  <li>🔁 Circular references show a loop-back marker</li>
</ul>
<p style='color:{_DIM}'>
  Legacy mode is read-only for structure; edit node content in the inspector.
</p>
"""),

        ("Audio Linking & Playback", f"""
<p style='color:{_WHITE}'>
Each dialogue node can reference a <b style='color:{_TEAL}'>Voice-Over (VO_ResRef)</b>
and/or a <b style='color:{_TEAL}'>Sound Effect</b>.  GhostScripter can
<b>preview these audio files</b> directly in the editor.
</p>
<p style='color:{_WHITE}'><b>To link and play audio:</b></p>
<ol style='color:{_WHITE}'>
  <li>Click a node to select it, then open the <b style='color:{_LTBLUE}'>Audio/Anim</b> tab in the inspector</li>
  <li>Type the resref name (e.g. <code style='color:{_ORANGE}'>dan13_dorak_001</code>) in the VO field</li>
  <li>Click <b style='color:{_TEAL}'>▶ Play</b> — GhostScripter searches these locations automatically:
    <ul style='color:{_WHITE}'>
      <li><code style='color:{_ORANGE}'>streamwaves/</code> and its subfolders</li>
      <li><code style='color:{_ORANGE}'>streamvoice/</code> and its subfolders</li>
      <li><code style='color:{_ORANGE}'>override/</code></li>
      <li>Your project folder and <code style='color:{_ORANGE}'>audio/</code> subfolder</li>
    </ul>
  </li>
  <li>If the file isn't found automatically, a file browser opens so you can locate it manually</li>
  <li>Or click <b style='color:{_LTBLUE}'>📂</b> to browse for the file first — the resref field is filled automatically from the filename</li>
</ol>
<p style='color:{_WHITE}'><b>Node card badge:</b> nodes with a VO resref show a
<span style='color:{_YELLOW}'>🔊 VO</span> badge in the bottom-right corner of the card.</p>
<p style='color:{_DIM}'>
  ℹ️ Requires the KotOR game directory to be set so GhostScripter knows where
  to look for <code style='color:{_ORANGE}'>streamwaves/</code> etc.
  WAV, MP3, OGG, and FLAC files are all supported.
</p>
"""),

        ("Exporting Your Dialogue", f"""
<ol style='color:{_WHITE}'>
  <li>Click <b style='color:{_YELLOW}'>💾 Export .DLG</b> in the toolbar</li>
  <li>Choose a save location (usually your
      <code style='color:{_ORANGE}'>override/</code> folder)</li>
  <li>Select K1 or K2 (TSL) as the target game</li>
  <li>GhostScripter writes a binary GFF3 .dlg file ready for the game</li>
</ol>
<p style='color:{_DIM}'>
  ℹ️ Make sure your dialogue file is named correctly — the game looks for it
  by resref (filename without extension, lowercase, max 16 chars).
</p>
"""),
    ]),

    # ── Tab 2: Script Editor ──────────────────────────────────────────────────
    ("📝 Script Editor", [

        ("Creating a Script", f"""
<ol style='color:{_WHITE}'>
  <li>Click <b style='color:{_YELLOW}'>Script → New Script</b>  <span style='color:{_DIM}'>(Ctrl+N)</span></li>
  <li>Enter a resref name (e.g. <code style='color:{_ORANGE}'>k_dan_enter</code>)</li>
  <li>The NWScript editor opens with a blank template</li>
  <li>Write your script — syntax highlighting, auto-indent, and
      bracket matching are active automatically</li>
  <li>Press <b style='color:{_TEAL}'>Ctrl+S</b> to save</li>
</ol>
"""),

        ("Compiling a Script", f"""
<ol style='color:{_WHITE}'>
  <li>With a script open, click <b style='color:{_YELLOW}'>Compile</b> in the toolbar
      or press <b style='color:{_TEAL}'>F5</b></li>
  <li>Errors appear in the output panel at the bottom with line numbers</li>
  <li>Compiled <code style='color:{_ORANGE}'>.ncs</code> files go to your project's
      <code style='color:{_ORANGE}'>scripts/</code> folder</li>
</ol>
<p style='color:{_DIM}'>
  ℹ️ The compiler targets NWScript v1.69 (the KotOR version).
  Standard bioware include files (nwscript.nss, k_inc_util.nss, etc.)
  are bundled with GhostScripter.
</p>
"""),

        ("Linking a Script to a Dialogue Node", f"""
<ol style='color:{_WHITE}'>
  <li>Open your dialogue in the Dialogue Editor</li>
  <li>Click the node you want to attach a script to</li>
  <li>In the inspector, open the <b style='color:{_LTBLUE}'>Scripts</b> tab</li>
  <li>Type (or paste) the script resref into the
      <b>Script</b> field (no .nss extension)</li>
  <li>For TSL: use the <b>Script2</b> field for a second script</li>
</ol>
<p style='color:{_DIM}'>
  The script fires when the dialogue reaches that node (OnEnter).
  For conditional active checks, set the script in the branch's
  <b>Active Script</b> field in the Links tab.
</p>
"""),
    ]),

    # ── Tab 3: 2DA & Tables ───────────────────────────────────────────────────
    ("📊 2DA & Tables", [

        ("Opening a 2DA File", f"""
<ol style='color:{_WHITE}'>
  <li>Click <b style='color:{_YELLOW}'>Tables → 2DA Manager</b></li>
  <li>Use <b>Open .2DA</b> to load a file from disk, or</li>
  <li>Use <b>Open with Game Library</b> to browse tables built into your
      KotOR install (requires game directory to be set)</li>
</ol>
<p style='color:{_DIM}'>
  Common tables: <code style='color:{_ORANGE}'>appearance.2da</code>,
  <code style='color:{_ORANGE}'>classes.2da</code>,
  <code style='color:{_ORANGE}'>spells.2da</code>,
  <code style='color:{_ORANGE}'>featsgrants.2da</code>
</p>
"""),

        ("Editing 2DA Data", f"""
<ul style='color:{_WHITE}'>
  <li><b>Double-click</b> a cell to edit its value</li>
  <li>Right-click a row → <b>Insert Row / Delete Row</b></li>
  <li>Use the search bar to filter rows by any column value</li>
  <li>Click <b style='color:{_YELLOW}'>Save</b> to write changes back to disk</li>
</ul>
<p style='color:{_DIM}'>
  ⚠️ Modifying base game .2da files directly will overwrite them.
  Copy them to your <code style='color:{_ORANGE}'>override/</code>
  folder first — the game loads override files first.
</p>
"""),
    ]),

    # ── Tab 4: Keyboard Shortcuts ─────────────────────────────────────────────
    ("⌨️ Shortcuts", [

        ("Global Shortcuts", f"""
<table style='color:{_WHITE}; border-collapse:collapse; width:100%'>
  <tr><th style='color:{_DIM}; text-align:left; padding:3px 8px'>Shortcut</th>
      <th style='color:{_DIM}; text-align:left; padding:3px 8px'>Action</th></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px'><b>Ctrl+N</b></td><td style='padding:3px 8px'>New Script</td></tr>
  <tr style='background:{_CARD}'><td style='color:{_TEAL}; padding:3px 8px'><b>Ctrl+Shift+N</b></td><td style='padding:3px 8px'>New Project</td></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px'><b>Ctrl+O</b></td><td style='padding:3px 8px'>Open Project</td></tr>
  <tr style='background:{_CARD}'><td style='color:{_TEAL}; padding:3px 8px'><b>Ctrl+Shift+D</b></td><td style='padding:3px 8px'>Open .DLG File</td></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px'><b>Ctrl+Shift+S</b></td><td style='padding:3px 8px'>Open .NSS File</td></tr>
  <tr style='background:{_CARD}'><td style='color:{_TEAL}; padding:3px 8px'><b>Ctrl+S</b></td><td style='padding:3px 8px'>Save Project / Script</td></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px'><b>Alt+F4</b></td><td style='padding:3px 8px'>Exit</td></tr>
</table>
"""),

        ("Visual Dialogue Editor", f"""
<table style='color:{_WHITE}; border-collapse:collapse; width:100%'>
  <tr><th style='color:{_DIM}; text-align:left; padding:3px 8px'>Shortcut</th>
      <th style='color:{_DIM}; text-align:left; padding:3px 8px'>Action</th></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px'><b>Scroll wheel</b></td><td style='padding:3px 8px'>Zoom in / out</td></tr>
  <tr style='background:{_CARD}'><td style='color:{_TEAL}; padding:3px 8px'><b>Middle-click drag</b></td><td style='padding:3px 8px'>Pan canvas</td></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px'><b>Space + drag</b></td><td style='padding:3px 8px'>Pan canvas</td></tr>
  <tr style='background:{_CARD}'><td style='color:{_TEAL}; padding:3px 8px'><b>F</b></td><td style='padding:3px 8px'>Fit all nodes in view</td></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px'><b>Ctrl+0</b></td><td style='padding:3px 8px'>Reset zoom to 100%</td></tr>
  <tr style='background:{_CARD}'><td style='color:{_TEAL}; padding:3px 8px'><b>Double-click canvas</b></td><td style='padding:3px 8px'>Fit all nodes in view</td></tr>
  <tr><td style='color:{_TEAL}; padding:3px 8px'><b>Right-click node</b></td><td style='padding:3px 8px'>Context menu</td></tr>
  <tr style='background:{_CARD}'><td style='color:{_TEAL}; padding:3px 8px'><b>Left-drag node</b></td><td style='padding:3px 8px'>Move node (16 px grid snap)</td></tr>
</table>
"""),
    ]),

    # ── Tab 5: Tips & Tricks ──────────────────────────────────────────────────
    ("💡 Tips & Tricks", [

        ("KotOR DLG Structure Explained", f"""
<p style='color:{_WHITE}'>KotOR dialogues alternate between two node types:</p>
<ul style='color:{_WHITE}'>
  <li><b style='color:{_TEAL}'>Entry nodes</b> — NPC lines.  Each entry can have multiple reply branches.</li>
  <li><b style='color:{_LTBLUE}'>Reply nodes</b> — Player choices.  Each reply leads back to an entry (or ends).</li>
</ul>
<p style='color:{_WHITE}'>
The conversation always starts at a <b style='color:{_YELLOW}'>Starter</b> —
an entry node designated as the opening line.
</p>
<p style='color:{_DIM}'>
Tip: A node with no outgoing branches ends the conversation.
Set a branch to index <code style='color:{_ORANGE}'>-1</code> (or use the END button)
to force termination mid-tree.
</p>
"""),

        ("is_child Branches (Shared Nodes)", f"""
<p style='color:{_WHITE}'>
The <b style='color:{_YELLOW}'>IsChild</b> flag on a branch means the target node is
<i>shared</i> — it appears in multiple places in the tree without being
duplicated in the file.  The visual editor shows these as back-edges
(wires that loop backwards).
</p>
<p style='color:{_DIM}'>
Use is_child sparingly.  It can cause confusing dialogue trees where
the same node appears in multiple contexts.  Always check your tree
with <b>Validate</b> to catch unreachable or circular references.
</p>
"""),

        ("Active Scripts (Conditions)", f"""
<p style='color:{_WHITE}'>
Each branch can have an <b style='color:{_YELLOW}'>Active Script</b> (and
<b style='color:{_YELLOW}'>Active2</b> in TSL).  These are NWScript functions that
return 1 (show branch) or 0 (hide branch) based on game state:
</p>
<pre style='background:{_DARK}; color:{_ORANGE}; padding:6px; border-radius:3px; font-size:9pt'>
// Example: only show if party member Jolee is present
int StartingConditional() {{
    return GetIsObjectValid(GetObjectByTag("jolee"));
}}
</pre>
<p style='color:{_DIM}'>
The function must be named <code style='color:{_ORANGE}'>StartingConditional</code>
and return an int.
</p>
"""),

        ("Naming Conventions", f"""
<p style='color:{_WHITE}'>KotOR file naming rules:</p>
<ul style='color:{_WHITE}'>
  <li><b>Max 16 characters</b> (resref limit) — lowercase letters, digits, underscores</li>
  <li><b>DLG files:</b> <code style='color:{_ORANGE}'>dan13_dorak.dlg</code>
      — module prefix + NPC tag</li>
  <li><b>Scripts:</b> <code style='color:{_ORANGE}'>k_dan_enter.nss</code>
      — prefix + module + purpose</li>
  <li><b>Common prefixes:</b>
      <code style='color:{_ORANGE}'>k_</code> KotOR 1,
      <code style='color:{_ORANGE}'>at_</code> TSL,
      <code style='color:{_ORANGE}'>dan</code> Dantooine module</li>
</ul>
"""),

        ("Output / Log Panel", f"""
<p style='color:{_WHITE}'>
The <b style='color:{_TEAL}'>Output / Log</b> panel at the bottom shows live application logs:
</p>
<ul style='color:{_WHITE}'>
  <li>Click <b style='color:{_TEAL}'>DEBUG / INFO / WARN / ERROR / CRIT</b> to filter by level</li>
  <li>Type in the <b>Filter</b> box to search by logger name or message text</li>
  <li>Click <b>📄 Open Log</b> to open <code style='color:{_ORANGE}'>ghostscripter.log</code>
      in your system text viewer</li>
  <li><code style='color:{_ORANGE}'>ghostscripter_crash.log</code> is written on any unhandled crash</li>
</ul>
<p style='color:{_DIM}'>
  Filter tip: type <code style='color:{_ORANGE}'>dlg_reader</code> to see only DLG import messages,
  or <code style='color:{_ORANGE}'>draw_edges</code> to debug wire rendering.
</p>
"""),
    ]),
]


# ── Collapsible card widget ────────────────────────────────────────────────────

class _CollapsibleCard(QWidget):
    """A titled section that can be expanded/collapsed."""

    def __init__(self, title: str, html_body: str, parent=None, start_expanded=True):
        super().__init__(parent)
        self._expanded = start_expanded

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(0)

        # Header row
        header = QWidget()
        header.setStyleSheet(f"""
            QWidget {{
                background: {_CARD};
                border: 1px solid {_BORDER};
                border-radius: 3px;
            }}
            QWidget:hover {{ background: #333337; }}
        """)
        header.setCursor(Qt.PointingHandCursor)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 5, 8, 5)
        header_layout.setSpacing(6)

        self._toggle_lbl = QLabel("▼" if start_expanded else "▶")
        self._toggle_lbl.setStyleSheet(f"color:{_TEAL}; font-size:9pt;")
        self._toggle_lbl.setFixedWidth(14)
        header_layout.addWidget(self._toggle_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color:{_WHITE}; font-weight:bold; font-size:9pt;"
        )
        header_layout.addWidget(title_lbl, 1)

        layout.addWidget(header)

        # Body
        self._body = QTextBrowser()
        self._body.setHtml(html_body)
        self._body.setReadOnly(True)
        self._body.setOpenExternalLinks(True)
        self._body.setStyleSheet(f"""
            QTextBrowser {{
                background: {_DARK};
                color: {_WHITE};
                border: 1px solid {_BORDER};
                border-top: none;
                border-radius: 0 0 3px 3px;
                font-family: "Segoe UI", sans-serif;
                font-size: 9pt;
                padding: 4px;
            }}
        """)
        # Auto-size to content
        self._body.document().setTextWidth(self._body.viewport().width())
        self._body.setMinimumHeight(60)
        self._body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout.addWidget(self._body)

        if not start_expanded:
            self._body.setVisible(False)

        # Click anywhere on header to toggle
        header.mousePressEvent = lambda _e: self._toggle()

    def _toggle(self):
        self._expanded = not self._expanded
        self._toggle_lbl.setText("▼" if self._expanded else "▶")
        self._body.setVisible(self._expanded)


# ── Main Tutorial Dialog ──────────────────────────────────────────────────────

class TutorialDialog(QDialog):
    """
    Floating tutorial / quick-start guide.

    Can be shown/hidden via Help → Tutorial, or the ? toolbar button.
    Position and visibility-on-startup are persisted in QSettings.
    """

    # Class-level singleton reference
    _instance = None

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)   # Qt.Window → independent window
        self.setWindowTitle("GhostScripter — Quick-Start Guide")
        self.setMinimumSize(560, 500)
        self.resize(640, 700)

        self._build_ui()
        self._restore_geometry()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.setStyleSheet(f"""
            QDialog {{
                background: {_PANEL};
            }}
            QTabWidget::pane {{
                background: {_PANEL};
                border: 1px solid {_BORDER};
            }}
            QTabBar::tab {{
                background: {_DARK};
                color: {_DIM};
                padding: 5px 10px;
                border: 1px solid {_BORDER};
                border-bottom: none;
                font-size: 8pt;
            }}
            QTabBar::tab:selected {{
                background: {_PANEL};
                color: {_WHITE};
                border-bottom: 2px solid {_TEAL};
            }}
            QTabBar::tab:hover {{
                color: {_WHITE};
                background: #2a2a2a;
            }}
            QScrollBar:vertical {{
                background: {_DARK}; width: 10px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: #555; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        # ── Header bar ─────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 #0f3460, stop:1 #1a1a2e); border-bottom:1px solid {_BORDER};"
        )
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(14, 10, 14, 10)

        title_lbl = QLabel("GhostScripter — Quick-Start Guide")
        title_lbl.setStyleSheet(
            f"color: {_TEAL}; font-size: 13pt; font-weight: bold;"
        )
        h_lay.addWidget(title_lbl)
        h_lay.addStretch()

        ver_lbl = QLabel("v2.4+")
        ver_lbl.setStyleSheet(f"color: {_DIM}; font-size: 8pt;")
        h_lay.addWidget(ver_lbl)

        root.addWidget(header)

        # ── Tab widget ──────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        for tab_title, cards in _CONTENT:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setStyleSheet(f"QScrollArea {{ background:{_PANEL}; border:none; }}")

            container = QWidget()
            container.setStyleSheet(f"background:{_PANEL};")
            c_lay = QVBoxLayout(container)
            c_lay.setContentsMargins(10, 10, 10, 10)
            c_lay.setSpacing(6)

            for i, (card_title, card_body) in enumerate(cards):
                card = _CollapsibleCard(
                    card_title, card_body,
                    parent=container,
                    start_expanded=(i == 0),   # first card open, rest collapsed
                )
                c_lay.addWidget(card)

            c_lay.addStretch()
            scroll.setWidget(container)

            self._tabs.addTab(scroll, tab_title)

        root.addWidget(self._tabs, 1)

        # ── Footer ──────────────────────────────────────────────────
        footer = QWidget()
        footer.setStyleSheet(
            f"background:{_DARK}; border-top:1px solid {_BORDER};"
        )
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(10, 6, 10, 6)
        f_lay.setSpacing(8)

        self._startup_chk = QCheckBox("Show this guide on startup")
        self._startup_chk.setStyleSheet(f"color:{_DIM}; font-size:8pt;")
        settings = QSettings("GhostScripter", "GhostScripter")
        show_on_startup = settings.value("tutorial/show_on_startup", True, type=bool)
        self._startup_chk.setChecked(show_on_startup)
        self._startup_chk.stateChanged.connect(self._save_startup_pref)
        f_lay.addWidget(self._startup_chk)

        f_lay.addStretch()

        expand_btn = QPushButton("Expand All")
        expand_btn.setFixedHeight(22)
        expand_btn.setStyleSheet(f"""
            QPushButton {{ background:{_CARD}; color:{_DIM};
                border:1px solid {_BORDER}; border-radius:2px;
                font-size:8pt; padding:0 8px; }}
            QPushButton:hover {{ color:{_WHITE}; background:#3a3a3a; }}
        """)
        expand_btn.clicked.connect(self._expand_all)
        f_lay.addWidget(expand_btn)

        collapse_btn = QPushButton("Collapse All")
        collapse_btn.setFixedHeight(22)
        collapse_btn.setStyleSheet(expand_btn.styleSheet())
        collapse_btn.clicked.connect(self._collapse_all)
        f_lay.addWidget(collapse_btn)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(22)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background:{_TEAL}; color:#000;
                border:none; border-radius:2px;
                font-size:8pt; font-weight:bold; padding:0 12px; }}
            QPushButton:hover {{ background:#5fd9c4; }}
        """)
        close_btn.clicked.connect(self.close)
        close_btn.setDefault(True)
        f_lay.addWidget(close_btn)

        root.addWidget(footer)

    # ── Expand / Collapse all ─────────────────────────────────────────────────

    def _get_all_cards(self):
        cards = []
        for i in range(self._tabs.count()):
            scroll = self._tabs.widget(i)
            container = scroll.widget()
            for child in container.findChildren(_CollapsibleCard):
                cards.append(child)
        return cards

    def _expand_all(self):
        for card in self._get_all_cards():
            if not card._expanded:
                card._toggle()

    def _collapse_all(self):
        for card in self._get_all_cards():
            if card._expanded:
                card._toggle()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_startup_pref(self):
        settings = QSettings("GhostScripter", "GhostScripter")
        settings.setValue(
            "tutorial/show_on_startup",
            self._startup_chk.isChecked()
        )

    def _restore_geometry(self):
        settings = QSettings("GhostScripter", "GhostScripter")
        geom = settings.value("tutorial/geometry")
        if geom:
            self.restoreGeometry(geom)

    def closeEvent(self, event):
        # Save window position/size
        settings = QSettings("GhostScripter", "GhostScripter")
        settings.setValue("tutorial/geometry", self.saveGeometry())
        super().closeEvent(event)

    # ── Singleton helper ──────────────────────────────────────────────────────

    @classmethod
    def show_tutorial(cls, parent=None):
        """Show the tutorial window (create or raise)."""
        if cls._instance is None or not cls._instance.isVisible():
            cls._instance = cls(parent)
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()

    @classmethod
    def should_show_on_startup(cls) -> bool:
        settings = QSettings("GhostScripter", "GhostScripter")
        return settings.value("tutorial/show_on_startup", True, type=bool)
