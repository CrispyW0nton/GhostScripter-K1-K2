# GhostScripter-K1-K2

**All-in-one IDE for KotOR 1 & 2 TSL Modding**

Version 1.0.0 • GPL-3.0 License

---

## Overview

GhostScripter-K1-K2 is a comprehensive modding IDE for Star Wars: Knights of the Old Republic (K1) and The Sith Lords (K2/TSL). It provides an integrated environment for all aspects of mod development, styled after the KotorModTools / GhostRigger dark theme aesthetic.

**Color Theme:** Dark charcoal IDE (VS Code / KotorModTools style)
- Background: `#1e1e1e` / Panels: `#252526` / Headers: `#2d2d30`
- Accent Blue: `#0078d4` (Active buttons, selection highlights)
- Status Bar: `#007acc`
- Borders: `#3c3c3c`

---

## Features (MVP)

| Module | Description |
|--------|-------------|
| **Script Editor** | NSS syntax highlighting, line numbers, function reference sidebar, compile/decompile |
| **Dialogue Editor** | Visual node graph dialogue tree editor with inspector |
| **Quest Builder** | Template-based quest scaffolding with globalcat.2da generation |
| **2DA Manager** | Parse, view, and edit 2DA files with search/filter |
| **Asset Library** | Browse and manage all mod assets (scripts, quests, dialogues, models) |
| **Export Manager** | Export to /override/, ERF, or MOD package |
| **IPC Bridge** | GhostRigger-K1-K2 integration via REST callbacks |
| **Project Manager** | Create/load/save mod projects with folder structure |

---

## Installation

```bash
git clone <repo>
cd GhostScripter-K1-K2
pip install -r requirements.txt
python ghostscripter/main.py
```

### Dependencies
- Python 3.10+
- PyQt5 >= 5.15
- SQLAlchemy >= 2.0
- Flask >= 2.3 (IPC server)

---

## Project Structure

```
ghostscripter/
├── core/
│   ├── models/          # Project, Script, Quest, Dialogue data models
│   ├── 2da_manager/     # 2DA file parser and editor
│   ├── script_system/   # NSS compilation interface
│   ├── quest_system/    # Quest template scaffolding
│   ├── dialogue_system/ # DLG file parser
│   ├── export/          # ERF/MOD export manager
│   └── resource_manager/# BIF/KEY extraction
├── ui/
│   ├── main_window.py   # Primary IDE window
│   ├── widgets/         # Script, Dialogue, Quest, 2DA, Asset editors
│   ├── dialogs/         # New Project, New Quest dialogs
│   └── styles/
│       └── dark.qss     # KotorModTools-style dark theme
├── ipc/
│   └── ghostrigger_bridge.py  # IPC REST server
└── documentation/       # Built-in help engine
```

---

## Usage

### Creating a Quest
1. Click **+ Quest** or use **Quest Builder** tab
2. Select a template (Simple, Branching, NPC Companion)
3. Fill in quest name and target game (K1/K2)
4. System generates: folder structure, globalcat.2da entries, script stubs, dialogue placeholder
5. Open each script stub in the **Script Editor** to add logic

### NSS Script Editor
- Full NWScript syntax highlighting (keywords, functions, types, constants)
- Line number gutter
- Function reference sidebar with all K1/K2 functions
- Double-click a function to insert it at cursor
- Click **⚙ Compile → NCS** to compile via nwnnsscomp

### Dialogue Editor
- Visual node graph with drag-and-drop
- NPC nodes (red) and Player response nodes (blue)
- Inspector panel for editing node text, speaker, branches
- Tree validation

---

## Attribution & Credits

- **KotorModTools / GhostRigger** — aesthetic inspiration
- **Fred Tetra** — KOTOR Tool (BIF/KEY extraction patterns)
- **xoreos-tools** (GPL-3.0) — file format parsing
- **TK102** — K-GFF Editor (GFF UI patterns)
- **Fair Strides & TK102** — DLG Editor (dialogue parsing)
- **Cortisol** — Holocron Toolset (module editing patterns)
- **Deadly Stream community** — modding knowledge base

---

## License

GPL-3.0 — See LICENSE.md
