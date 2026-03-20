# GhostScripter-K1-K2 — Tester Guide

**Repository:** https://github.com/YOUR_USERNAME/GhostScripter-K1-K2

---

## Table of Contents

1. [What You Are Testing](#1-what-you-are-testing)
2. [System Requirements](#2-system-requirements)
3. [Setting Up the Development Environment](#3-setting-up-the-development-environment)
4. [Loading KotOR Game Data](#4-loading-kotor-game-data)
5. [Using the Editors](#5-using-the-editors)
   - [2DA Editor](#51-2da-editor)
   - [Dialogue (DLG) Editor](#52-dialogue-dlg-editor)
   - [Script Editor](#53-script-editor)
   - [ERF Packer](#54-erf-packer)
   - [TLK Editor](#55-tlk-editor)
   - [Quest Builder](#56-quest-builder)
   - [Asset Library & Texture Preview](#57-asset-library--texture-preview)
6. [Running the Test Suite](#6-running-the-test-suite)
7. [Key Numbers to Verify](#7-key-numbers-to-verify)
8. [Reporting Bugs](#8-reporting-bugs)
9. [Known Limitations](#9-known-limitations)

---

## 1. What You Are Testing

GhostScripter-K1-K2 is an all-in-one modding IDE for *Star Wars: Knights of the Old Republic* (K1) and *KotOR II: The Sith Lords* (K2 TSL). It provides:

- A full **NWScript editor** with syntax highlighting, real autocomplete from `nwscript.nss` (Ctrl+Space), function reference panel, and compiler integration
- **NCS Decompilation** — auto-detects and invokes DeNCS CLI (`NCSDecompCLI.jar`), xoreos-tools `ncsdecomp`, or pykotor; opens result directly in the Script Editor; shows a helpful install dialog when no tool is found
- A **Dialogue (DLG) editor** — visual node graph, full GFF field inspector, NPC picker from `appearance.2da`, StrRef lookup via `dialog.tlk`, and **full DLG round-trip** (open any existing `.dlg` file from your game or a mod); supports VECTOR/ORIENTATION fields for blueprints
- A **2DA Manager** that loads all 209 game 2DA files, with TSLPatcher-style `AddRow` / `CopyRow` / `ModifyRow` operations and one-click `changes.ini` export
- An **ERF / MOD / RIM Packer** — drag-and-drop builder, can pull resources directly from your game library
- A **TLK Editor** for browsing, searching, editing, and saving `dialog.tlk` talk tables
- A **Quest Builder** for structured quest design with template scaffolding and script stub generation
- A **Journal Editor** for reading and editing KotOR JRL journal files
- An **Asset Library** with a Game Assets tab that indexes all ~25,836 resources from BIF/ERF/RIM archives; **texture preview** panel for TGA files (Qt native) and TPC files (via `pykotor`)

Your job is to verify that each editor opens without crashing, loads game data correctly, and produces valid output files.

---

## 2. System Requirements

| Component | Minimum |
|-----------|---------|
| OS | Windows 10 / Linux (Ubuntu 20.04+) / macOS 12+ |
| Python | 3.10 or higher |
| PyQt5 | 5.15+ |
| RAM | 4 GB (8 GB recommended for full game data) |
| Disk | ~500 MB for app + ~3 GB if using a local KotOR install |
| KotOR game | KotOR 1 (Steam, GOG, or disc install) |

---

## 3. Setting Up the Development Environment

### 3.1 Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/GhostScripter-K1-K2.git
cd GhostScripter-K1-K2
```

### 3.2 Create and activate a virtual environment

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3.3 Install dependencies

```bash
pip install -r requirements.txt
```

### 3.4 Launch the application

```bash
python3 ghostscripter/main.py
```

A splash screen appears briefly, then the main IDE window opens.

---

## 4. Loading KotOR Game Data

Most editor features require pointing GhostScripter at your KotOR installation. This lets the ResourceManager index the ~25,836 resources across BIF, ERF, RIM, and Override archives.

### 4.1 Where to find your KotOR install

| Platform | Default path |
|----------|-------------|
| Steam (Windows) | `C:\Program Files (x86)\Steam\steamapps\common\swkotor` |
| GOG (Windows) | `C:\GOG Games\Star Wars KotOR` |
| macOS (Steam) | `~/Library/Application Support/Steam/steamapps/common/swkotor` |
| Linux (Steam/Proton) | `~/.steam/steam/steamapps/common/swkotor` |
| Linux (custom) | `~/games/swkotor` (or wherever you installed it) |

The folder you select **must contain `chitin.key`** at its root.

### 4.2 Setting the game directory

1. From the menu bar choose **File → Set Game Directory…**
2. Navigate to your KotOR root folder (the one containing `chitin.key`) and select it.
3. The status bar updates to show the folder name (e.g., `swkotor`).
4. All open editor tabs immediately gain access to the game library.

### 4.3 What gets indexed

| Archive type | Example files |
|-------------|--------------|
| BIF (via chitin.key) | `data/2da.bif`, `data/scripts.bif`, `data/items.bif`, … |
| ERF / MOD | `modules/*.mod`, `modules/*.erf` |
| RIM | `rims/*.rim` |
| Override | `Override/*.*` |
| TLK | `dialog.tlk` (loaded separately per-widget) |

---

## 5. Using the Editors

All editors open from the **menu bar** or **toolbar**. Multiple editors can be open simultaneously as tabs.

---

### 5.1 2DA Editor

**Menu path:** `Tools → 2DA Manager`

1. Open the 2DA Manager. If no game directory is set you'll be prompted.
2. The left panel shows a tree of all 209 game 2DA files.
3. Click any file (e.g., `appearance`) to load it in the table.
4. Test **Search / Filter** — type a partial name and rows should filter live.
5. Test **Edit a cell** — double-click, change a value, press Enter.
6. Test **Undo/Redo** — `Ctrl+Z` / `Ctrl+Y` should revert/re-apply the change.
7. Test **Export** — `File → Export 2DA…` → save to disk and verify the file looks correct.

**What to verify:**
- All 209 files listed with no parse errors on stock files.
- Edited cells persist until explicitly saved or discarded.

---

### 5.2 Dialogue (DLG) Editor

**Menu path:** `Tools → Dialogue Editor` (new) or `File → Open DLG…` (existing file)

**Opening an existing dialogue:**
1. `Dialog → Open .DLG File…` (or `Ctrl+Shift+D`) and choose any `.dlg` from your KotOR install or a mod.
2. The node graph renders NPC nodes (dark red) and Player nodes (dark blue) with Bezier edges.
3. Click a node to populate the Inspector on the right — check that speaker, text, VO ResRef, scripts, and branch list all populate.
4. Verify the **StrRef** field: if a node has a non-`-1` StrRef and the game directory is set, the node card on the graph should show the English string from `dialog.tlk`.

**Creating a new dialogue:**
5. `Dialog → New Dialogue` — starts with an empty graph.
6. Click `+ NPC Node` and `+ Player Node`, add branches between them in the Inspector.
7. Click **Validate** and confirm no errors are reported.
8. Click **Export DLG** — a binary `.dlg` file should be written to your project's `dialogues/` folder.

**NPC Picker (requires game directory):**
9. Click the NPC Picker button in the Inspector — it should list NPCs from `appearance.2da`.

**What to verify:**
- Round-trip: open a stock game `.dlg`, export it, and compare file sizes (should be within a few bytes).
- StrRef lookup returns readable English strings from `dialog.tlk`.

---

### 5.3 Script Editor

**Menu path:** `Tools → Script Editor` or `File → Open Script…`

1. Open a new script — `Script → New Script` or `Ctrl+N`. A `void main() {}` template appears.
2. Check syntax highlighting on keywords (`void`, `int`, `string`, `if`, `return`).
3. Test autocomplete — type `Get` and press `Ctrl+Space`; a popup of matching NWScript functions should appear; Tab or Enter to insert.
4. Test **2DA Lookup** in the toolbar — should show game 2DA files when game directory is set.
5. Test **Find / Replace** — `Ctrl+F` opens the find bar; `Ctrl+H` opens find+replace.
6. If `nwnnsscomp` is on PATH (or in `resources/tools/`), click **⚙ Compile** and check the compiler output console.
7. Click **Decompile NCS** — it opens a file dialog, then automatically tries the following tools in order:
   1. **DeNCS CLI** (`NCSDecompCLI.jar` from [OldRepublicDevs/DeNCS](https://github.com/OldRepublicDevs/DeNCS)) — place the JAR in `tools/`, requires Java
   2. **xoreos-tools** `ncsdecomp` — if found on `PATH`
   3. **pykotor CLI** — if `pip install pykotor` is present

   On success the decompiled `.nss` source appears directly in the editor. If no tool is detected, a dialog appears with step-by-step installation instructions for each option.

---

### 5.4 ERF Packer

**Menu path:** `Tools → ERF Packer`

1. Click **Add Files…** and add any mod files (`.utc`, `.dlg`, `.2da`, etc.).
2. Set the output path (e.g., `~/Desktop/test_mod.mod`).
3. Click **Build MOD** / **Build ERF**.
4. Verify the output file is created on disk.
5. Optionally open the file in a hex editor — confirm `ERF ` magic bytes at offset 0.

---

### 5.5 TLK Editor

**Menu path:** `Tools → TLK Editor` or `File → Open TLK…`

1. Open `dialog.tlk` from your KotOR install.
2. Verify the table populates with StrRef IDs and English strings.
3. Test **Search** — type `Revan` and matching rows should appear.
4. Edit a cell, then **Save As** to a temp path to test round-trip.
5. Test **StrRef Jump** — type a number in the jump field and press Enter.

**What to verify:**
- K1 `dialog.tlk` loads without error (it has 49,000+ entries).
- Save round-trip preserves all unchanged strings.

---

### 5.6 Quest Builder

**Menu path:** `Tools → Quest Builder`

1. Click **New Quest**, enter a name and description.
2. Add stages with IDs and journal text.
3. Click **Generate Scripts** — stub `.nss` files should appear in the script list.
4. Save (`File → Save Quest…`) and reload to verify round-trip.

---

### 5.7 Asset Library & Texture Preview

**Menu path:** `Tools → Asset Library` (or the Assets tab in the left panel)

**Game assets tab (requires game directory):**
1. Set your game directory (`File → Set Game Directory…`) if not already done.
2. Switch to the **Asset Library** and click the **Game Assets** tab.
3. Verify the status bar shows a resource count (expected: ~25,836 for KotOR 1).
4. Expand the **Textures (.tga)** category and click any TGA entry.
5. The right panel should switch to the **texture preview** and render the image.
6. Expand **Textures (.tpc)** and click a TPC entry:
   - If `pykotor` is installed: the texture is decoded and displayed.
   - If not: a message appears explaining how to install `pykotor` for TPC support.
7. Test the **Filter** box — type part of a texture name to narrow down results.
8. Double-click any `.dlg` or `.nss` entry — the panel should show instructions for opening in the appropriate editor.

**What to verify:**
- TGA textures render without crashing.
- TPC textures either display (with pykotor) or show a clear install prompt (without).
- Filtering works across all asset types.

---

## 6. Running the Test Suite

```bash
python3 -m pytest tests/ -v
```

Expected: **594 tests pass**. The suite covers:
- Resource loading and KEY/BIF indexing
- 2DA parsing, editing, and round-trip
- DLG GFF binary round-trips including all node fields and AnimList
- GFF writing for all field types including **VECTOR** (3-float position) and **ORIENTATION** (4-float quaternion)
- IPC bridge and server
- Dialogue model edge cases
- TLK parsing
- Journal editor (JRL round-trip)
- Game asset integration
- Script compiler and syntax checking
- And more — 14 test files total

```bash
# Run a specific file
python3 -m pytest tests/test_2da_editor.py -v
python3 -m pytest tests/test_dlg_roundtrip.py -v
```

---

## 7. Key Numbers to Verify

After loading the game directory, these counts confirm the resource indexer is working correctly:

| Metric | Expected (KotOR 1) |
|--------|-------------------|
| 2DA files indexed | **209** |
| DLG dialogue files | 32 |
| Compiled scripts (NCS) | 1,784 |
| NWScript source (NSS) | 1,774 |
| Model files (MDL) | 2,832 |
| TGA textures | 5,601 |
| WAV audio files | 1,928 |
| **Total indexed resources** | **25,836** |
| TLK entries (`dialog.tlk`) | 49,265 |

---

## 8. Reporting Bugs

Open an issue at:
**https://github.com/YOUR_USERNAME/GhostScripter-K1-K2/issues**

Please include:
1. Steps to reproduce
2. Expected vs actual behaviour
3. OS and Python version (`python3 --version`)
4. The crash log at `ghostscripter_crash.log` (next to wherever you launched from)
5. A screenshot if it's visual

---

## 9. Known Limitations

| Area | Limitation |
|------|-----------|
| Compiler | Requires `nwnnsscomp` on PATH — not bundled (see `tools/README.md`) |
| Decompiler | Auto-detects DeNCS CLI (`NCSDecompCLI.jar`), xoreos-tools `ncsdecomp`, and pykotor — none bundled; easiest setup: download `NCSDecompCLI.jar` from [OldRepublicDevs/DeNCS](https://github.com/OldRepublicDevs/DeNCS) and place it in `tools/` (requires Java) |
| Texture Preview (TPC) | Requires `pip install pykotor` — TGA textures preview natively via Qt without extra installs |
| Texture Preview (TGA) | Works out of the box — Qt loads TGA files directly |
| K2 TSL | Partially integrated; some 2DA names differ from K1 |
| ERF Build | Large archives (>500 files) may be slow on first pack |
| macOS | Dark theme may render slightly differently on macOS 13+ |
