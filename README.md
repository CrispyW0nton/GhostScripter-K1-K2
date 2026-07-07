# GhostScripter-K1-K2

> **A modding IDE + AI agent backend for Star Wars: Knights of the Old Republic 1 & 2 (TSL)**

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-brightgreen)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-1422%20passed-brightgreen)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)]()
[![Version](https://img.shields.io/badge/version-3.6.1-orange)]()
[![Qt](https://img.shields.io/badge/Qt-qtpy%20%28PyQt5%2FPyQt6%2FPySide6%29-41cd52)]()
[![Monorepo](https://img.shields.io/badge/monorepo-OldRepublicDevs%2FPyKotor-informational)](https://github.com/OldRepublicDevs/PyKotor)

GhostScripter is a dark-themed modding IDE and MCP server built for KotOR 1 & 2. Rather than jumping between a half-dozen separate tools, everything lives in one place: NWScript editing with live syntax highlighting and autocomplete, a visual node-based dialogue editor, quest scaffolding, 2DA editing, asset browsing, and direct export to Override or ERF — all with the same aesthetic as GhostRigger.

It ships a full **Model Context Protocol (MCP) server** with **60 tools**, letting AI agents (Claude Desktop, Cursor, VS Code Copilot, etc.) directly query, modify, and reverse-engineer KotOR game assets as part of an agentic modding workflow. GhostScripter is part of the **Ghostworks Pipeline** alongside [GModular](https://github.com/CrispyW0nton/GModular) (3D module/world editor) and [GhostRigger-K1-K2](https://github.com/CrispyW0nton/GhostRigger-K1-K2) (model rigging pipeline).

> **Monorepo note:** This tool lives at `Tools/GhostScripter-K1-K2` inside the
> [OldRepublicDevs/PyKotor](https://github.com/OldRepublicDevs/PyKotor) monorepo.
> It is the **write + IDE layer**; [KotorMCP](https://github.com/OldRepublicDevs/KotorMCP)
> (`Tools/KotorMCP`) is the companion **read-only** MCP server built on the shared
> `Libraries/PyKotor` format library.  Run both for the full modding agent experience.

---

## Table of Contents

- [What's New](#whats-new)
- [⚡ Before You Start](#-before-you-start)
- [Screenshots](#screenshots)
- [Features](#features)
- [System Architecture](#system-architecture)
  - [Full System Diagram](#full-system-diagram)
  - [Layer Responsibilities](#layer-responsibilities)
  - [Data Flow Examples](#data-flow-examples)
- [MCP Server — AI Agent Backend](#mcp-server--ai-agent-backend)
  - [Quick Start](#mcp-quick-start)
  - [All 60 Tools](#all-60-tools)
  - [Example Agent Workflow](#example-agent-workflow)
- [Ghostworks Pipeline](#ghostworks-pipeline)
  - [Claude Desktop — combined config](#claude-desktop--combined-multi-server-config)
  - [Cursor / VS Code — combined config](#cursor--vs-code--combined-http-config)
  - [Example workflow](#example-agentic-workflow--reverse-engineering-a-gff-field)
- [Requirements](#requirements)
- [Installation](#installation)
- [GUI Quick Start](#gui-quick-start)
- [Module Reference](#module-reference)
  - [Script Editor](#script-editor)
  - [Dialogue Editor](#dialogue-editor)
  - [Quest Builder](#quest-builder)
  - [2DA Manager](#2da-manager)
  - [TLK Editor](#tlk-editor)
  - [ERF / MOD Packer](#erf--mod-packer)
  - [Journal Editor](#journal-editor)
  - [Asset Library](#asset-library)
  - [Export Pipeline](#export-pipeline)
  - [GhostRigger IPC Bridge](#ghostrigger-ipc-bridge)
  - [Resource Manager](#resource-manager)
  - [Database Layer](#database-layer)
- [Project Structure](#project-structure)
- [Workflow Guide](#workflow-guide)
  - [Creating Your First Quest Mod](#creating-your-first-quest-mod)
  - [Writing & Compiling Scripts](#writing--compiling-scripts)
  - [Building a Dialogue Tree](#building-a-dialogue-tree)
  - [Editing 2DA Files](#editing-2da-files)
  - [Exporting Your Mod](#exporting-your-mod)
  - [Working with GhostRigger](#working-with-ghostrigger)
- [Core Services Layer](#core-services-layer)
- [KotOR Modding Conventions](#kotor-modding-conventions)
- [Roadmap](#roadmap)
- [Building from Source](#building-ghostscripter-k1-k2exe)
- [Contributing](#contributing)
- [Credits](#credits)
- [License](#license)

---

## What's New

### v3.6.1 — Format-correctness audit against PyKotor + retail game data

The binary writers were cross-checked against PyKotor 2.3.12, retail K1 game
files, and the conventions of known-good community tools (KotOR Tool,
DLGEditor, TSLPatcher, HolocronToolset). Highlights:

- **MCP server harness restored** — `python -m ghostscripter.mcp` works again
  (the `server.py` entry point was missing from the repo); verified end-to-end
  with a live MCP handshake listing all 60 tools.
- **ERF resource-type table fixed** — 40 type IDs were off by one
  (`.utp`, `.utm`, `.uts`, `.utw`, `.jrl`, `.ssf`, `.fac`, `.mdx`, `.tpc`, …);
  archives containing those types were unreadable by the game. Verified
  against PyKotor **and** the IDs inside retail module RIMs. All three
  duplicate tables now derive from one verified source.
- **JRL journals are game-compatible** — entries are written under the
  retail `EntryList` label (was `Entries`, which the game ignores), and the
  importer now reads all 643 entries of K1's `global.jrl` (was 0).
- **Dialogue text encoding fixed** — CExoLocString substrings are written as
  windows-1252 like the game expects (was UTF-8 → mojibake for é/ü/…).
- **Setup actually works from scratch** — `mcp`, `uvicorn`, `networkx`, and
  `Pillow` added to `requirements.txt` (previously missing, breaking the MCP
  server, dialogue graph analysis, and texture preview on fresh installs).
- **1422 tests, 0 failures** — plus test-isolation fixes so the suite no
  longer writes into a detected real game installation.

Full details and prior releases: **[CHANGELOG.md](CHANGELOG.md)**

---

## Screenshots

> _Dark IDE layout — matching the GhostRigger color palette_

```
┌─────────────────────────────────────────────────────────────────────┐
│  File  Edit  View  Tools  Help                        [GhostScripter]│
│─────────────────────────────────────────────────────────────────────│
│ [+Project] [Open] [Save] │ [Script] [Dialogue] [Quest Builder] [2DA]│
│──────────────┬──────────────────────────────────┬───────────────────│
│ Project  ▼   │  Welcome  │ ✎ k_test.nss  │ ⚔ Q │  Properties       │
│  ▾ MyMod     │                                  │                   │
│   Scripts(2) │   [Editor / Graph / Table area]  │  { json props }   │
│   Quests(1)  │                                  │                   │
│   Dialogues  │                                  │  Quick Actions    │
│   Models(0)  │                                  │  + New Script     │
│              │──────────────────────────────────│  + New Quest      │
│  [+Project]  │  Output Log               [Clear]│  Export Override  │
│  [Open]      │  ✓ Project saved: MyMod          │                   │
└──────────────┴──────────────────────────────────┴───────────────────┘
```

---

## Features

| Feature | Details |
|---|---|
| **NSS Script Editor** | Syntax highlighting (keywords, types, functions, constants, strings, numbers, multi-line comments), line numbers, current-line highlight, real autocomplete from `nwscript.nss` (Ctrl+Space), 25+ KotOR function reference sidebar with search and double-click insert, `void main()` / `StartingConditional()` templates, compile via `nwnnsscomp` with fallback brace/parenthesis syntax check |
| **Visual Dialogue Editor** | QGraphicsView node graph with draggable nodes, Bezier curve edges, NPC nodes (dark red) / Player nodes (dark blue), node list sidebar, full GFF field inspector (VO, scripts, camera, TSL-specific fields), add/delete nodes, dialogue tree validation, center-on-select, NPC picker from `appearance.2da`, auto-load `dialog.tlk` for StrRef display |
| **DLG Round-Trip** | Binary GFF V3.2 reader (`dlg_reader.py`) parses existing `.dlg` files back into the visual editor; GFF V3.2 writer (`dlg_writer.py`) exports back to binary — full round-trip for any stock or modded KotOR dialogue |
| **Quest Builder** | 3 built-in templates (Simple 3-state, Branching Light/Dark, NPC Companion), editable overview/variables/states/scripts tabs, `globalcat.2da` preview + copy, auto script stub generation, `K_SWG_` naming convention validation |
| **2DA Manager** | Parse/display/edit KotOR 2DA V2.0 format, in-cell editing, add/delete rows and columns, real-time row search, save back to disk; full TSLPatcher-style operations: `AddRow`, `CopyRow`, `ModifyRow`, `ColumnAdd`; one-click `changes.ini` export for mod distribution |
| **TLK Editor** | Read, search, edit, and save KotOR `dialog.tlk` talk tables; supports round-trip save; StrRef jump; loads alongside the Dialogue Editor for automatic node-card text resolution. `TLKFile` model now lives in `core/models/tlk.py` — pure Python, no Qt dependency |
| **ERF / MOD / RIM Packer** | Drag-and-drop archive builder; real binary ERF V1.0 writer with correct ResRef/ResType/ResourceID encoding; `add_resource()` + `build()` API for programmatic use; browse and pull resources directly from your game library |
| **Journal Editor** | Read and edit KotOR JRL journal files (GFF-based); save back to binary JRL format |
| **Asset Library** | Tabbed browser (Scripts/Quests/Dialogues/Models/Templates), global search + type filter, create assets directly, import MDL models, GhostRigger model launch; **texture preview** for TGA (via Qt) and TPC (via `pykotor`) files in the game asset tab |
| **Override Export** | Copies compiled mod files to `<game dir>/override/` with full error reporting |
| **SQLite Database** | Persistent storage for recent projects, script revision history, quest/dialogue snapshots, export log, user preferences |
| **GhostRigger IPC** | Qt-integrated polling bridge to GhostRigger on port 7001, optional Flask callback server on 7002, `ModelPayload` push notifications |
| **Resource Manager** | Parse KotOR `chitin.key` / `.bif` archives, ERF/RIM reader, resource search by name or type, extract single resources to disk; override-only workspace mode (no `chitin.key` required) |
| **Project System** | Create/open/save projects with auto-created folder structure, `project.json` manifest |
| **MCP Server** | 60 tools over `stdio`, HTTP, or SSE; usable from Claude Desktop, Cursor, VS Code Copilot, or any MCP-compatible agent |
| **Dark Theme** | Full QSS stylesheet: `#1e1e1e` background, `#252526` panels, `#2d2d30` headers, `#0078d4` accent blue |

---

## MCP Server — AI Agent Backend

GhostScripter ships a full **Model Context Protocol server** so AI assistants can directly read, analyse, and write KotOR game assets. Think of it as a bridge between your game installation and any AI tool that speaks MCP.

> **Multi-server setup:** For the best agent experience, run GhostScripter MCP **alongside**
> [KotorMCP](https://github.com/OldRepublicDevs/KotorMCP) from the PyKotor monorepo.
> KotorMCP provides deep read-only access (walkmesh diagrams, cross-reference search, DLG
> structure descriptions) via `kotor_`-prefixed tools.  GhostScripter provides write-back,
> composite game-object queries, and write-back patching.  Together they cover the full
> modding workflow.

### MCP Quick Start

#### Claude Desktop — GhostScripter only (stdio)

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ghostscripter": {
      "command": "python",
      "args": ["-m", "ghostscripter.mcp"],
      "cwd": "/path/to/GhostScripter-K1-K2",
      "env": {
        "K1_PATH": "/path/to/swkotor",
        "K2_PATH": "/path/to/swkotor2"
      }
    }
  }
}
```

#### Claude Desktop — combined with KotorMCP (recommended)

```json
{
  "mcpServers": {
    "ghostscripter": {
      "command": "python",
      "args": ["-m", "ghostscripter.mcp"],
      "cwd": "/path/to/PyKotor/Tools/GhostScripter-K1-K2",
      "env": { "K1_PATH": "/path/to/swkotor", "K2_PATH": "/path/to/swkotor2" }
    },
    "kotormcp": {
      "command": "python",
      "args": ["-m", "kotormcp"],
      "cwd": "/path/to/PyKotor/Tools/KotorMCP",
      "env": { "K1_PATH": "/path/to/swkotor", "K2_PATH": "/path/to/swkotor2" }
    }
  }
}
```

#### Cursor / VS Code (HTTP)

```bash
# Start the server on port 6400
cd /path/to/GhostScripter-K1-K2
K1_PATH=/path/to/swkotor K2_PATH=/path/to/swkotor2 \
    python -m ghostscripter.mcp --mode http --port 6400
```

Add to `.cursor/mcp.json` or `.vscode/mcp.json`:

```json
{
  "servers": {
    "ghostscripter": {
      "url": "http://localhost:6400/mcp"
    }
  }
}
```

#### SSE (legacy clients)

```bash
python -m ghostscripter.mcp --mode sse --port 6400
```

#### Environment Variables

| Variable | Description | Example |
|---|---|---|
| `K1_PATH` | Path to KotOR 1 install root | `/home/user/.steam/swkotor` |
| `K2_PATH` | Path to KotOR 2 / TSL install root | `/home/user/.steam/swkotor2` |
| `KOTOR_PATH` | Alias for `K1_PATH` | same as `K1_PATH` |
| `TSL_PATH` | Alias for `K2_PATH` | same as `K2_PATH` |

#### Common Steam Paths

| OS | KotOR 1 | KotOR 2 |
|---|---|---|
| Linux | `~/.local/share/Steam/steamapps/common/swkotor` | `~/.local/share/Steam/steamapps/common/Knights of the Old Republic II` |
| macOS | `~/Library/Application Support/Steam/steamapps/common/swkotor` | `…/Knights of the Old Republic II` |
| Windows | `C:\Program Files (x86)\Steam\steamapps\common\swkotor` | `…\Knights of the Old Republic II` |

---

### All 60 Tools



| Tool | Description |
|---|---|
| `gsDetectInstallations` | Find K1/K2 game directories automatically; checks env vars and common Steam paths *(prefixed to avoid KotorMCP collision)* |
| `gsLoadInstallation` | Cache a game installation for the session (must call before GhostScripter write tools) *(prefixed)* |
| `gsListResources` | Browse resources by type, location, or name prefix *(prefixed)* |
| `gsDescribeResource` | Structured summary of any GFF / 2DA / TLK / JRL resource *(prefixed)* |
| `searchResources` | Full-text search across all 2DA tables and TLK strings |

#### Reading Resources

| Tool | Description |
|---|---|
| `readGFF` | Parse any GFF binary file (DLG, UTC, UTP, ARE, GIT, JRL…) into a JSON field tree |
| `readDLG` | Import a dialogue file as structured JSON with entries, replies, branches |
| `readTwoDA` | Read a 2DA table with optional column filter and row pagination |
| `readTLK` | Look up TLK strings by StrRef ID from `dialog.tlk` |
| `readJournal` / `journalOverview` | Structured overview of all `global.jrl` quests and states |
| `readSSF` | Decode a Sound Set File (SSF) — 28 canonical slots with StrRef + TLK text |
| `readLIP` | Decode a lip-sync animation file (LIP V1.0) — duration, keyframe count, time + mouth-shape per frame |

#### Targeted Lookups

| Tool | Description |
|---|---|
| `twoDALookup` | Look up a single row or cell by row label or index — faster than `readTwoDA` for spot checks |
| `moduleOverview` | List creatures, doors, placeables, waypoints, triggers in a `.rim`/`.erf` area |
| `nwscriptSignature` | Full signature + parameter list for one NWScript function |
| `nwscriptCategories` | All function/constant category names with per-category counts |
| `searchNWScript` | Autocomplete / search NWScript functions and constants with category filter |

#### Writing Resources

| Tool | Description |
|---|---|
| `writeDLG` | Export a dialogue JSON (as returned by `readDLG`) back to a binary `.dlg` file |
| `writeGFF` | Write a generic GFF binary from a JSON field dict; supports all GFF field types |
| `writeTwoDA` | Serialise a 2DA table (columns + rows, optional cell edits) to V2.0 text or V2.b binary; returns base64 |
| `writeERF` | Pack resource files into a binary ERF v1.0 archive (MOD/ERF/SAV); returns base64 |
| `compileScript` | Compile NWScript `.nss` source to binary `.ncs` via bundled nwnnsscomp; returns base64 |
| `writeOverride` | Write a base64 resource directly to the game's Override folder; updates in-session index |
| `writeLIP` | Encode a LIP V1.0 lip-sync binary from a keyframe list — shape names or integers; returns base64 |

#### Analysis & Patching

| Tool | Description |
|---|---|
| `compileSummary` | Static analysis of NWScript source — extracts functions, constants, detects brace mismatches, `int oXxx` type errors, and oversized ResRef strings |
| `twoDAChangesINI` | Generate a TSLPatcher-compatible `changes.ini` section from a 2DA diff |

#### Composite Game-Object Accessors *(context-free AI tools)*

These tools return structured composite views of game objects without requiring the AI to know which binary format to query. Designed following Yourdon/Constantine's **functional cohesion** principle — one tool, one game object type.

| Tool | Blueprint | Description |
|---|---|---|
| `getResource` | any | Retrieve any KotOR resource by `resref` + `type`; resolves format internally |
| `getQuest` | JRL | Composite quest view: all states with TLK text + scripts + DLG refs |
| `getNpc` | UTC | Composite NPC view: fields + appearance.2da row + dialogue summary + faction |
| `getCreature` | UTC | Detailed creature blueprint: stats, class/level, 6 abilities, HP/AC, equipment, feats, skills, scripts |
| `getScript` | NSS/NCS | Script source or decompiled NCS + static analysis |
| `listResType` | any | Paginated resource list by type with optional name pattern |
| `getArea` | ARE+GIT+LYT | Area properties + all placed instances (with XYZ) + room layout |
| `getDoor` | UTD | Tag, lock/trap props, script fields, conversation resref |
| `getPlaceable` | UTP | Tag, appearance, lock/trap, inventory list, scripts |
| `getItem` | UTI | Base item, cost, property list, TLK-resolved name/description |
| `searchAll` | — | Unified text search across 2DA + TLK + NSS + DLG in one call |
| `getModule` | IFO | Module snapshot: mod name, tag, entry area/XYZ, area list, all `Mod_On*` scripts |
| `getEncounter` | UTE | Tag, active, difficulty, faction, spawn list (resref + CR), scripts |
| `getTrigger` | UTT | Tag, trap type, one-shot, linked object, trap props, scripts |
| `getWaypoint` | UTW | Tag, localized name, XYZ, orientation, map note |
| `getStore` | UTM | Tag, name, markup/markdown %, inventory list, OnOpenStore script |
| `getSound` | UTS | Tag, flags, volume, distances, XYZ, sound resref list |
| `getFaction` | FAC | Faction table: name + mutual reputation matrix (0–100) for each faction pair |

---

### Example Agent Workflow

```python
# AI agent building a Mira companion quest — complete workflow

# 1. Check which functions are available
nwscriptSignature(func_name="AddJournalQuestEntry")
# → void AddJournalQuestEntry(string szPlotID, int nState, int bAllowOverrideHigher)

# 2. Find Mira's appearance row
twoDALookup(game="K1", resref="appearance", row="Mira", column="normalhead")
# → "12"

# 3. Check an existing dialogue
readDLG(game="K2", resref="hk47_01")
# → { entry_count: 4, reply_count: 6, entries: [...], replies: [...] }

# 4. Write a new dialogue
writeDLG(game="K2", dlg={
    "entries": [{"text": "I have you now.", "speaker": "mira", "branches": [{"index": 0, "is_reply": true}]}],
    "replies": [{"text": "Not today.", "branches": []}],
    "starters": [{"index": 0, "is_reply": false}]
})
# → { size: 2408, data_b64: "..." }

# 5. Analyse a script before export
compileSummary(source='void myFn(int oPC) { GiveXPToCreature(oPC, 500); }')
# → issues: ["Line 1: parameter 'oPC' uses 'int' — did you mean 'object oPC'?"]

# 6. Generate a TSLPatcher patch for an edited 2DA
twoDAChangesINI(original=orig_text, modified=new_text, twoDAName="appearance")
# → "[appearance.2da]\nAddRow 7=label=MiraContact, race=Human, ..."

```

---


## Ghostworks Pipeline

GhostScripter is one of three tightly-integrated tools that together form the **Ghostworks Pipeline** — the complete KotOR modding IDE suite.

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │                    GHOSTWORKS PIPELINE                               │
 │                                                                      │
 │   GhostScripter-K1-K2      GModular            GhostRigger-K1-K2   │
 │   ──────────────────────   ─────────────────   ──────────────────── │
 │   NWScript IDE             Module / World      MDL model pipeline    │
 │   Dialogue editor          Editor (3D)         Rigging, skinning     │
 │   Quest builder            Area/GIT/ARE/IFO    K1↔K2 porting        │
 │   2DA / TLK / JRL editor   Walkmesh editor     Texture pipeline      │
 │   MCP server (60 tools)    3D object placement GLTF/OBJ import       │
 │   Module packager          IPC bridges         MCP server (25 tools) │
 │   ERF/RIM/MOD packer       GhostRigger/GModular Write-back tooling     │
 │                                                                      │
 │   Port 7002 ◄─────────────────────────────────────────► Port 7001   │
 │                 IPC REST (Ghostworks event bus)                      │
 │                         Port 7003 (GModular CB)                      │
 └──────────────────────────────────────────────────────────────────────┘
```

All three tools are submodules of the **[OldRepublicDevs/PyKotor](https://github.com/OldRepublicDevs/PyKotor)** monorepo alongside **KotorMCP** — the canonical read-only MCP layer built on the shared `Libraries/PyKotor` format library.

```
 OldRepublicDevs/PyKotor (monorepo)
 ├── Libraries/PyKotor          ← shared binary-format library
 ├── Tools/KotorMCP             ← read-only MCP (kotor_ prefixed tools, pykotor-backed)
 ├── Tools/GhostScripter-K1-K2  ← this repo: IDE + write MCP (camelCase tools)
 ├── Tools/GModular             ← world editor
 ├── Tools/HolocronToolset      ← legacy GUI reference (HolocronToolset_old → merged)
 └── Tools/HoloPatcher          ← TSLPatcher replacement
```

**MCP tool namespace convention** (from `AGENTS.md`):

| Server | Tool style | Purpose |
|---|---|---|
| KotorMCP | `kotor_` snake_case | read-only; pykotor-backed; walkmesh, refs, DLG describe |
| GhostScripter | camelCase | read + write; IDE-integrated; composite queries |
| Shared | same name in both | `journalOverview` intentionally present in both — identical schema |

### What each tool owns exclusively

| Responsibility | GhostScripter | GModular | GhostRigger |
|---|---|---|---|
| NWScript edit/compile | ✓ | — | — |
| Dialogue tree (DLG) | ✓ | reads GFF | — |
| Quest / JRL | ✓ | — | — |
| 2DA editing | ✓ | reads 2DA | reads 2DA |
| TLK lookup | ✓ | — | — |
| Area/module world editor | — | ✓ | — |
| 3D GIT object placement | — | ✓ | — |
| LYT/VIS room layout | — | ✓ | — |
| MDL/MDX parse & render | — | renders | ✓ |
| Model rigging/skinning | — | — | ✓ |
| K1↔K2 model porting | — | — | ✓ |
| Walkmesh editing | — | ✓ | exports GWOK |
| Binary reverse engineering | bridge | — | bridge |

### IPC Ports

| Port | Service |
|---|---|
| 6400 | GhostScripter MCP (HTTP mode) |
| 7001 | GhostRigger IPC server |
| 7002 | GhostScripter IPC server |
| 7003 | GModular IPC callback server |
| 7010 | GhostRigger MCP (HTTP mode) |

### Repositories

- **GhostScripter-K1-K2** — https://github.com/CrispyW0nton/GhostScripter-K1-K2
- **GModular** — https://github.com/CrispyW0nton/GModular
- **GhostRigger-K1-K2** — https://github.com/CrispyW0nton/Kotor-3 *(GhostRigger)*
- **PyKotor monorepo** — https://github.com/OldRepublicDevs/PyKotor
- **KotorMCP** — https://github.com/OldRepublicDevs/KotorMCP

---

## ⚡ Before You Start

> **TL;DR — you need a copy of KotOR installed on your machine.** Most of GhostScripter's value comes from reading your game's actual files. Without a game installation the asset browser, all read/query tools, and the export pipeline are non-functional.

### Hard requirement: a KotOR game installation

GhostScripter is a **modding tool for a specific game**. It is not useful without that game. Before you open the GUI or connect an AI agent:

1. **Own and install KotOR 1 and/or KotOR 2 (TSL).** Steam, GOG, and disc installs all work. The game folder must contain `chitin.key`.
2. **Use an unmodded (vanilla) game library when building a new mod.** GhostScripter reads the base game files to resolve TLK strings, 2DA rows, resource references, blueprint templates, and area layouts. If your game folder already has Override files from other mods those will pollute the reference data and cause incorrect lookups. Keep a clean vanilla install (or a separate copy) as your reference library, and maintain a separate mod-development folder for your own Override files.
3. **Point GhostScripter at that folder.** It auto-detects Steam/GOG/standard paths on startup. If it doesn't find your install, do one of:

```bash
# Option A — environment variable (recommended for MCP/CI/headless use)
export K1_PATH="/path/to/kotor1"          # Linux/macOS — folder containing chitin.key
export K2_PATH="/path/to/kotor2"
set K1_PATH=C:\Knights of the Old Republic   # Windows CMD
set K2_PATH=C:\SWKotOR2

# Option B — GUI
# File → Set Game Directory… → browse to the folder containing chitin.key

# Option C — MCP tool (once per session)
# gsLoadInstallation({"game": "K1", "path": "/path/to/kotor1"})
```

### What works without a game installation

A small subset of tools work with **no game path configured** — useful for offline scripting or CI pipelines:

| Feature | Tool / Entry point |
|---------|--------------------|
| NWScript function lookup (772 K1 / 812 K2 functions) | `searchNWScript`, `nwscriptSignature`, `getNWScriptDB` |
| NWScript category browser | `nwscriptCategories` |
| Static script analysis | `compileSummary` |
| **Compile NWScript → NCS** | `compileScript` (PyKotor `InbuiltNCSCompiler`, pure Python) |
| **Decompile NCS → NWScript** | `decompileScript` (PyKotor `NCSDecompiler`) |
| Write tools (GFF, DLG, 2DA, ERF, SSF, LIP, PTH) | `writeGFF`, `writeDLG`, `writeTwoDA`, `writeSSF`, `writeLIP`, `writePTH` |
| Qt GUI launches & editors open | `python ghostscripter/main.py` |

Everything else — reading game assets, browsing modules, resolving TLK strings, looking up NPCs, areas, quests, blueprints, exporting to Override — **requires a game installation**.

### Relationship with GhostRigger

[GhostRigger-K1-K2](https://github.com/CrispyW0nton/GhostRigger-K1-K2) is a **separate, standalone application** (Tkinter-based MDL/rig pipeline). GhostScripter does **not** launch it. If GhostRigger is already running, GhostScripter will connect to it at `http://localhost:7001` and show `GR: ✓` in the status bar. Start GhostRigger independently with `python main.py` from its own directory.

---

## Requirements

### Software

| Dependency | Version | Purpose |
|---|---|---|
| Python | 3.10+ | Runtime |
| PyQt5 | 5.15+ | GUI framework (swap for PyQt6/PySide6 freely via qtpy) |
| Flask | 3.x | IPC callback server |
| requests | 2.x | GhostRigger HTTP polling |
| mcp | latest | MCP server framework |
| **pykotor** | **2.3+** | **NCS compile/decompile — required** |

### Game files (hard requirement)

| Game | Where to buy | Minimum version |
|------|-------------|-----------------|
| **Star Wars: KotOR** (K1) | [Steam](https://store.steampowered.com/app/32370/) · [GOG](https://www.gog.com/game/star_wars_knights_of_the_old_republic) | Any — unmodded preferred |
| **Star Wars: KotOR II — TSL** (K2) | [Steam](https://store.steampowered.com/app/208580/) · [GOG](https://www.gog.com/game/star_wars_kotor_ii) | Any — unmodded preferred |

> **Why unmodded?** GhostScripter reads `dialog.tlk`, `2da` files, and blueprint templates from your game folder to populate editors and resolve references. If another mod has already changed those files, the lookups will reflect that mod's data — not the base game. This makes it very hard to know what vanilla values are, and can cause your mod to produce incorrect results when run on a clean install. Keep one vanilla copy as your authoring reference.

**Optional external tools (not bundled):**

| Tool | Purpose | Where to get it |
|---|---|---|
| `nwnnsscomp` | Compile `.nss` → `.ncs` (fallback if PyKotor fails) | [KotOR Scripting Tool](https://github.com/nicowillis/KotOR-Scripting-Tool) |
| `xoreos-tools ncsdecomp` | Decompile `.ncs` (third fallback) | [xoreos-tools](https://github.com/xoreos/xoreos-tools) |
| GhostRigger-K1-K2 | Model rigging / appearance editing | Sister project |

---

## Installation

> **You must own and have installed KotOR 1 and/or KotOR 2 (TSL) before using GhostScripter.** See [⚡ Before You Start](#-before-you-start) for details, including why an unmodded install is strongly recommended.

### From source

```bash
git clone https://github.com/CrispyW0nton/GhostScripter-K1-K2.git
cd GhostScripter-K1-K2

python -m venv venv
source venv/bin/activate      # Linux/macOS
venv\Scripts\activate.bat     # Windows

pip install -r requirements.txt

# Point at your game (if auto-detect doesn't find it)
export K1_PATH="/path/to/kotor1"   # Linux/macOS
# set K1_PATH=C:\Knights of the Old Republic   # Windows

# Run the GUI
python ghostscripter/main.py

# Run the MCP server (stdio)
python -m ghostscripter.mcp
```

### Windows (no Python)

> Pre-built `.exe` releases aren't on GitHub yet — build your own in one double-click with `build.bat` (see [Building](#building-ghostscripter-k1-k2exe) below), or run from source.

### Running the test suite

```bash
python -m pytest tests/ -q
# 1422 passed, 65 skipped in ~25 seconds
# (skips cover optional externals: nwnnsscomp, xoreos-tools, live IPC peers)
```

---

## GUI Quick Start

> **Prerequisite**: KotOR 1 and/or KotOR 2 must be installed. An **unmodded** copy is strongly recommended — see [⚡ Before You Start](#-before-you-start).

1. **Launch** — `python ghostscripter/main.py`
2. **Set game directory** — `File → Set Game Directory…` → browse to the folder containing `chitin.key`. GhostScripter auto-detects Steam/GOG installs; use this only if auto-detect fails. **Point at a vanilla (unmodded) install** so reference data is clean.
3. **New Project** — `+ Project` in the toolbar → fill in name, author, target game (K1/K2), choose a save folder
4. **New Script** — `Edit → New Script` or `Ctrl+N` → name it → Script Editor opens with a `void main()` template
5. **New Quest** — `Edit → New Quest` → pick a template → Quest Builder opens with pre-filled variables and states
6. **New Dialogue** — `Edit → New Dialogue` → Dialogue Editor opens with a starter tree
7. **Export** — `Tools → Export to Override` → writes files to your game's `Override/` folder (or a staging folder of your choice)

---

## Module Reference

### Script Editor

Full NWScript development environment inside the IDE.

```
┌──────────────────────────────────────────────────────┬──────────────┐
│ [Open] [Save] | [⚙ Compile → NCS] [Decompile] | Template ▾  filename│
├─────────────────────────────────────────────────────┤ Function Ref │
│  1  void main() {                                   │ ─ Quest/Var  │
│  2      // Set quest state to Active                │  SetGlobal…  │
│  3      SetGlobalNumber("K_SWG_MYQUEST_STATE", 1);  │  GetGlobal…  │
│  4      SetGlobalBoolean("K_SWG_MYQUEST", TRUE);    │ ─ Object/NPC │
│  5  }                                               │  GetObjectBy │
│                                                     │  CreateObject│
├─────────────────────────────────────────────────────┴──────────────┤
│  Compiler Output:  ✓ Basic syntax check passed                      │
└────────────────────────────────────────────────────────────────────┘
```

- Full NSS syntax highlighting
- Function reference panel — search, click to see signature, double-click to insert
- **Compile NCS** — tries `InbuiltNCSCompiler` (PyKotor, pure Python, no Wine) first; falls back to `nwnnsscomp` binary if present
- **Decompile NCS** — uses `NCSDecompiler` (PyKotor); falls back to `xoreos-tools ncsdecomp` CLI if found on `PATH`
- Two script templates: `void main()` and `StartingConditional()`
- `compileSummary` MCP tool adds: brace balance, `int oXxx` type heuristic, and ResRef length warnings

**Shortcuts:**
| Key | Action |
|---|---|
| `Ctrl+N` | New script |
| `Ctrl+S` | Save script |
| `Ctrl+Space` | Autocomplete |

---

### Dialogue Editor

Visual node-graph editor for KotOR `.dlg` files.

```
┌───────────────────────────────────────────┬────────┬─────────────┐
│ [+ NPC Node] [+ Player Node] [Delete] [Validate]    dlg_name.dlg │
├───────────────────────────────────────────┤ Nodes  │ Inspector   │
│                                           │        │             │
│  ┌──────────────────────┐                 │ ► [1]  │ Node ID: 0  │
│  │ #0  npc_001          │                 │ ◆ [0]  │ Speaker:    │
│  │ Greetings, traveler. │                 │ ◆ [2]  │ [npc_001  ] │
│  │              ↳ 1     │                 │        │ Text:       │
│  └──────────┬───────────┘                 │        │ [Greetings..]│
│             │                             │        │ Branches:   │
│  ┌──────────▼───────────┐                 │        │ [0] Hello → 2│
│  │ #2  Player           │                 │        │             │
│  │ Hello.               │                 │        │ [+ Add Branch]│
│  └──────────────────────┘                 │        │             │
└───────────────────────────────────────────┴────────┴─────────────┘
```

- **Dark red** nodes = NPC lines (`EntryList`)
- **Dark blue** nodes = Player responses (`ReplyList`)
- Drag nodes freely, connect branches by ID in the Inspector
- Click **Validate** to catch broken branch refs, empty nodes, orphaned entries, or oversized script names
- Full GFF round-trip: open any stock or modded `.dlg`, edit it, save back to binary

**DLG data model** (`ghostscripter/core/models/dialogue.py`):
- `DialogueFile` — top-level container (`entries`, `replies`, `starters`)
- `DialogueNode` — one NPC or player line (50+ fields: text, speaker, scripts, camera, TSL fields)
- `DialogueBranch` — link to another node with optional conditional script

---

### Quest Builder

Scaffolds full KotOR quest structures with correct naming conventions.

**Templates:**

| Template | States | Variables |
|---|---|---|
| Simple Quest | Not Started → Active → Complete | `K_SWG_{NAME}` (Boolean), `K_SWG_{NAME}_STATE` (Number) |
| Branching Light/Dark | 5 states (2 paths) | 3 variables including `_CHOICE` |
| NPC Companion | 4 states (recruit → quest → complete) | 2 variables |

- **Overview** tab — quest name, ID, game target, type, description
- **Variables** tab — global variable table; generates `globalcat.2da` entries
- **States** tab — state ID + name + description
- **Scripts** tab — auto-named script stubs per state
- **globalcat.2da** tab — copy-ready entries to paste into your mod

---

### 2DA Manager

Spreadsheet editor for KotOR `.2da` files.

- Open any `.2da` from disk or your project's `2da/` folder
- Inline cell editing; `****` null values shown in gray
- Add/delete rows and columns
- Real-time row search
- Save back to disk in KotOR 2DA V2.0 format
- One-click **changes.ini** export for TSLPatcher mod distribution

`TwoDAService` API (for MCP and programmatic use):

```python
from ghostscripter.core.services import TwoDAService

tda = TwoDAService.parse_text(text)

# Look up a cell by label or numeric index
head = TwoDAService.get_cell(tda, "Mira", "normalhead")   # → "12"
head = TwoDAService.get_cell(tda, 3, "normalhead")         # same

# Paginated browse with column filter
page = TwoDAService.rows_to_dicts(tda, query="Human", columns=["label","race"], limit=10)

# TSLPatcher diff
ini = TwoDAService.diff_to_ini(original_tda, modified_tda)
```

---

### TLK Editor

Read, search, edit, and save KotOR `dialog.tlk` talk tables.

- StrRef jump — go directly to entry by number
- Search across all 49,000+ entries
- Edit text and sound ResRef
- Save back to binary (byte-for-byte round-trip, correct `cp1252` encoding)
- Auto-loads alongside the Dialogue Editor for automatic node-card text resolution

`TLKFile` is now a pure-Python core model in `ghostscripter/core/models/tlk.py` — no Qt dependency, usable without a GUI:

```python
from ghostscripter.core.models.tlk import TLKFile

tlk = TLKFile.from_file(Path("dialog.tlk"))
print(tlk.get_string(84))   # → "The Force will be with you, always."
```

---

### ERF / MOD Packer

Binary ERF V1.0 archive builder.

- Drag-and-drop interface in the GUI
- Programmatic API via `ERFWriter`:

```python
from ghostscripter.core.export.erf_writer import ERFWriter

writer = ERFWriter(file_type="ERF ")
writer.add_resource("mira_contact", "utc",  utc_bytes)
writer.add_resource("mira_contact", "dlg",  dlg_bytes)
writer.add_resource("k_mir_debt_st","nss",  script_bytes)

erf_bytes = writer.build()   # → complete ERF V1.0 binary
# or:
writer.write(entries, Path("my_mod.erf"))
```

---

### Journal Editor

Read and edit KotOR JRL journal files (GFF-based).

- Browse all quest categories and states
- Edit quest names, descriptions, and state text
- Save back to binary `.jrl` format
- `JournalService` provides `load()`, `parse_bytes()`, and `to_dict()` for programmatic use

---

### Asset Library

Tabbed browser for everything in your project — and your game installation when a game directory is set.

| Tab | What's in it | Actions |
|---|---|---|
| Game Assets | All resources indexed from your KotOR install (BIF/ERF/RIM) — DLG, NSS, 2DA, NCS, MDL, TGA, TPC, UTI, UTC, UTP | Click to preview; TGA/TPC textures render in a preview panel |
| Scripts | Categorized list (quest/dialogue/event/npc) | + New, Open file |
| Quests | List with game target badge | + New |
| Dialogues | `.dlg` files | + New, Open |
| Models | MDL/MDX references | Import, Edit in GhostRigger |
| Templates | 6 starter templates | Double-click or "Use Template" |

Global search filters across all asset types. Clicking a TGA or TPC texture in the **Game Assets** tab renders a live preview in the right panel (TPC requires `pykotor` — a graceful install prompt appears if it's missing).

---

### Export Pipeline

#### Override Export

`Tools → Export to Override`

Point it at your KotOR installation. GhostScripter copies compiled scripts, dialogues, 2DA edits, models, and textures straight to `<game>/override/`. A full file list prints to the output log.

#### ERF Export

`Tools → Export to ERF`

Packages everything into a proper binary ERF V1.0 archive. Compatible with TSLPatcher for structured installs.

#### DLG Export

`Tools → Export DLG Files`

Writes all open dialogues as GFF V3.2 binary `.dlg` files directly to `dialogues/` in your project.

---

### GhostRigger IPC Bridge

When GhostRigger-K1-K2 is running alongside GhostScripter:

1. GhostScripter polls port 7001 every 2 seconds — you'll see `🔗 GhostRigger connected` in the output log
2. Go to **Asset Library → Models**, select a model, click **Edit in GhostRigger**
3. GhostRigger processes it and sends the result back to GhostScripter's callback server (port 7002)
4. The model lands in your project's model list with its `appearance.2da` row filled in

Neither tool requires the other to be running.

**Ports:**
| Port | Direction | Purpose |
|---|---|---|
| 7001 | GhostScripter → GhostRigger | Polling, rig requests |
| 7002 | GhostRigger → GhostScripter | Model-complete callbacks |

---

### Resource Manager

Reads directly from a KotOR installation's binary archives without extracting anything.

```python
from ghostscripter.core.resource_manager import ResourceManager

rm = ResourceManager()
rm.load_game(Path("/path/to/swkotor"))   # also works without chitin.key (override-only mode)

# List all 2DA files (returns 209 entries from KotOR 1)
for entry in rm.list_by_type(".2da"):
    print(entry.resref)

# Search by name
results = rm.search("bastila")

# Pull raw bytes
data = rm.read("appearance.2da")

# Extract to disk
rm.extract_to("appearance.2da", Path("./extracted/"))
```

Supports `chitin.key` + `.bif`, `.erf`, `.mod`, and `.rim`. Falls back gracefully to override-only mode if `chitin.key` is absent (useful for workspace / patch-only setups).

---

### Database Layer

GhostScripter keeps a local SQLite database at `~/.ghostscripter/ghostscripter.db`.

| Table | Contents |
|---|---|
| `recent_projects` | Project name, path, game, last opened |
| `script_history` | Per-script revision log |
| `quest_snapshots` | JSON snapshots of quest definitions |
| `dialogue_snapshots` | JSON snapshots of dialogue files |
| `export_history` | Export type, output path, file count, timestamp |
| `user_prefs` | Key/value preferences |

```python
from ghostscripter.core.database import get_db

db = get_db()
db.set_pref("last_game", "K2")
revisions = db.get_script_revisions(project_id, "k_test_01")
```

---

## Project Structure

```
GhostScripter-K1-K2/
│
├── ghostscripter/
│   ├── main.py                        # GUI entry point
│   │
│   ├── core/
│   │   ├── constants.py               # Colors, keywords, NWScript reference data
│   │   │
│   │   ├── models/                    # Pure-Python data models (no Qt)
│   │   │   ├── project.py             # ModProject — create/load/save
│   │   │   ├── script.py              # ScriptFile
│   │   │   ├── quest.py               # QuestDefinition, GlobalVariable, QuestState
│   │   │   ├── dialogue.py            # DialogueFile, DialogueNode, DialogueBranch
│   │   │   ├── journal.py             # JournalFile, JournalCategory
│   │   │   └── tlk.py                 # TLKFile, TLKEntry (extracted from UI widget)
│   │   │
│   │   ├── ports/                     # Abstract Protocol interfaces (hexagonal arch)
│   │   │   └── __init__.py            # ResourceReaderPort, GFFReaderPort, TwoDAPort,
│   │   │                              #   DialoguePort, JournalPort, NWScriptDBPort,
│   │   │                              #   DLGSerialiserPort, GFFWriterPort
│   │   │
│   │   ├── services/                  # Stable service API (consumed by MCP + GUI)
│   │   │   └── __init__.py            # DialogueService, TwoDAService, JournalService,
│   │   │                              #   GFFService, TLKService, NWScriptService
│   │   │
│   │   ├── twoda_manager/
│   │   │   └── twoda_manager.py       # TwoDAFile — parse/edit/write V2.0
│   │   │
│   │   ├── export/
│   │   │   ├── erf_writer.py          # ERF V1.0 writer — add_resource() + build() API
│   │   │   ├── dlg_writer.py          # GFF V3.2 writer for .dlg (ResRef length warnings)
│   │   │   ├── dlg_reader.py          # GFF V3.2 binary reader + DLGImporter round-trip
│   │   │   ├── gff_writer.py          # Generic GFF V3.2 writer (all field types)
│   │   │   └── jrl_writer.py          # JRL journal writer
│   │   │
│   │   ├── validation/
│   │   │   └── dlg_validator.py       # DLGValidator — structure, links, cycles
│   │   │
│   │   ├── search/
│   │   │   └── resource_index.py      # ResourceIndex — fast full-text asset search
│   │   │
│   │   ├── database/
│   │   │   └── manager.py             # SQLite — projects, scripts, quests, prefs, log
│   │   │
│   │   ├── nwscript/
│   │   │   └── parser.py              # NWScriptDB — parse nwscript.nss (772 fn / 1489 const)
│   │   │
│   │   ├── dialogue_system/           # Dialogue scene management helpers
│   │   ├── quest_system/              # Quest template system
│   │   ├── script_system/             # Script template / compile integration
│   │   └── resource_manager/
│   │       └── resource_manager.py    # KEY/BIF/ERF/RIM reader; override-only mode
│   │
│   ├── mcp/                           # MCP Server (60 tools)
│   │   ├── __init__.py
│   │   ├── __main__.py                # Entry: python -m ghostscripter.mcp
│   │   ├── server.py                  # Transport setup (stdio / http / sse)
│   │   ├── tools.py                   # 25 tool handlers + _HANDLERS dispatch table
│   │   └── MCP_CONFIG.md              # Detailed MCP setup guide
│   │
│   ├── ipc/
│   │   ├── ghostrigger_bridge.py      # REST polling bridge to GhostRigger :7001
│   │   ├── ipc_server.py              # Flask callback server :7002 (daemon thread)
│   │   ├── server.py                  # Server lifecycle helpers
│   │   ├── client.py                  # HTTP client helpers
│   │   └── gmodular_client.py         # GModular API client
│   │
│   ├── ui/
│   │   ├── main_window.py             # Three-column IDE layout, menus, toolbar
│   │   ├── dialogs/                   # Modal dialogs (tutorial, about, settings)
│   │   ├── dialogue_editor/           # Node-graph dialogue editor sub-package
│   │   ├── script_editor/             # NWScript editor sub-package
│   │   └── widgets/
│   │       ├── script_editor_widget.py
│   │       ├── dialogue_editor_widget.py
│   │       ├── quest_builder_widget.py
│   │       ├── twoda_manager_widget.py
│   │       ├── tlk_editor_widget.py   # Imports TLKFile from core/models/tlk.py
│   │       ├── erf_packer_widget.py
│   │       ├── journal_editor_widget.py
│   │       └── asset_library_widget.py
│   │
│   └── utils/
│       ├── audio_player.py            # In-game audio preview helpers
│       └── log_setup.py               # Logging configuration
│
├── resources/
│   ├── icons/                         # App icons (PNG, ICO)
│   └── scripts/
│       ├── k1/nwscript.nss            # K1 NWScript header (772 functions, 1489 constants)
│       └── k2/nwscript.nss            # K2 NWScript header
│
├── tests/                             # 963-test pytest suite
│   ├── test_mcp_tools.py              # 137 MCP tool tests (incl. 14 AgDec bridge, 15 composite-tool tests)
│   ├── test_game_asset_integration.py # Integration tests vs real KotOR 1 files
│   ├── test_dlg_roundtrip.py
│   ├── test_gff_roundtrip.py
│   ├── test_kotor_formats.py
│   ├── test_2da_editor.py
│   └── ...                            # 16 test files total
│
├── tools/
│   └── README.md                      # nwnnsscomp + DeNCS setup instructions
├── build_tools/                       # PyInstaller / Inno Setup build scripts
├── requirements.txt
├── CREDITS.md
├── SECURITY.md
└── README.md
```

---

## Workflow Guide

### Creating Your First Quest Mod

**Goal:** A simple side quest where an NPC sends the player to retrieve something.

**1. Create the project**
```
+ Project → Name: "TestQuest" → Game: K1 → choose save folder
```

**2. Scaffold the quest**
```
Edit → New Quest → Simple Quest (3 states) → name: "retrieve_artifact"
```
Quest Builder generates:
- `K_SWG_RETRIEVE_ARTIFACT` (Boolean) and `K_SWG_RETRIEVE_ARTIFACT_STATE` (Number) variables
- States: Not Started → Active → Complete
- Script stub names: `k_swg_retrieve_artifact_00.nss`, `_01.nss`, `_02.nss`

**3. Write the trigger script**
```
Edit → New Script → k_swg_retrieve_artifact_01
```
```nwscript
void main() {
    SetGlobalBoolean("K_SWG_RETRIEVE_ARTIFACT", TRUE);
    SetGlobalNumber("K_SWG_RETRIEVE_ARTIFACT_STATE", 1);
    AddJournalQuestEntry("retrieve_artifact", 10, FALSE);
}
```
Click **⚙ Compile → NCS** (requires `nwnnsscomp`).

**4. Build the NPC dialogue**
```
Edit → New Dialogue → npc_questgiver
```
- NPC node: speaker `k_questgiver_001`, text: `"I need you to find something for me."`
- Branch: `"I'll do it."` → Player node: `"Where do I need to go?"`
- Attach script `k_swg_retrieve_01` to the NPC node (**note:** keep to ≤16 chars)

**5. Export**
```
Tools → Export to Override → select KotOR folder
```

---

### Writing & Compiling Scripts

**Templates:**
```nwscript
// void main() — actions, triggers, conversation scripts
void main() {
    object oPC = GetFirstPC();
    // your code here
}

// StartingConditional() — dialogue condition checks
int StartingConditional() {
    return GetGlobalBoolean("K_SWG_MYQUEST");
}
```

**Function reference** (right sidebar) — grouped by category:
- Quest / Global Variables (`SetGlobalNumber`, `GetGlobalBoolean`, `AddJournalQuestEntry`)
- Object / NPC (`GetObjectByTag`, `CreateObject`, `DestroyObject`)
- Conversation / Dialogue (`BeginConversation`, `ActionStartConversation`)
- Party (`AddPartyMember`, `RemovePartyMember`)
- Combat / Effects (`EffectDamage`, `ApplyEffectToObject`, `EffectHeal`)
- Alignment (`GetGoodEvilValue`, `AdjustAlignment`)

**Common mistakes the compiler checks catch:**

| Problem | Example | Warning |
|---|---|---|
| Wrong object type | `int oPC` | "parameter 'oPC' uses 'int' — did you mean 'object oPC'?" |
| ResRef too long | `ExecuteScript("this_script_name_is_too_long", OBJECT_SELF)` | "38 chars — KotOR ResRef limit is 16 chars" |
| Brace mismatch | unclosed `{` | "Brace mismatch: 2 '{' vs 3 '}'" |

---

### Building a Dialogue Tree

| Node color | Speaker | Use for |
|---|---|---|
| Dark red | NPC | What the NPC says |
| Dark blue | Player | What the player can choose |

1. Start with an NPC node (opening line)
2. Add branches from it — each branch = one player response option
3. Each branch's Target Node ID points to the next NPC node
4. Target = -1 ends the conversation
5. **Validate** checks for broken refs, empty text nodes, orphaned entries, and script name length

**KotOR DLG internals:**
- `EntryList` = NPC nodes
- `ReplyList` = Player nodes
- `StartingList` = branches from the root entry

---

### Editing 2DA Files

| File | What it controls |
|---|---|
| `globalcat.2da` | Global variable registry — required for quest variables |
| `appearance.2da` | NPC/creature model, texture, scale |
| `portraits.2da` | Party member portraits |
| `spells.2da` | Force powers |
| `feat.2da` | Feat definitions |

**Adding a quest variable to globalcat.2da:**
1. 2DA Manager → open `globalcat.2da`
2. `+ Add Row` → label: `K_SWG_MYQUEST`
3. Set `Type` to `Boolean`
4. Save → export to Override

Or use Quest Builder's **globalcat.2da** tab — it generates the correct rows and has a Copy to Clipboard button.

**TSLPatcher-compatible diff:**
```python
from ghostscripter.core.services import TwoDAService
ini = TwoDAService.diff_to_ini(original_tda, modified_tda)
# [appearance.2da]
# AddRow 7=label=MiraDebtContact, race=Human, modeltype=B, normalhead=41, backuphead=42
```

---

### Exporting Your Mod

**Override** (for testing while developing):
```
Tools → Export to Override → select KotOR folder
```

**ERF** (for distribution / TSLPatcher):
```
Tools → Export to ERF → pick a filename
```

**DLG only** (when you just need to push a dialogue update):
```
Tools → Export DLG Files
```

---

### Working with GhostRigger

GhostRigger-K1-K2 handles model rigging and appearance editing. When both are open:

1. GhostScripter polls 7001 for GhostRigger's status
2. **Asset Library → Models** → select a model → **Edit in GhostRigger** sends a rig request
3. GhostRigger finishes and POSTs the `ModelPayload` back to GhostScripter (port 7002)
4. Model lands in your project list with the `appearance.2da` row filled in

**Quick IPC check:**
```bash
curl http://localhost:7001/api/status
```

---

## System Architecture

GhostScripter is built as a **hexagonal (ports-and-adapters) architecture** with three independent
entry points — the PyQt5 GUI, the MCP server, and the IPC bridge — all of which communicate with
the same core layer through a stable service/port boundary.

> **Monorepo position:** `Tools/GhostScripter-K1-K2` in [OldRepublicDevs/PyKotor](https://github.com/OldRepublicDevs/PyKotor).
> GhostScripter is the **write + IDE** layer. [KotorMCP](https://github.com/OldRepublicDevs/KotorMCP)
> (`Tools/KotorMCP`, built on `Libraries/PyKotor`) is the companion **read-only** MCP layer.
> Both speak MCP/stdio and share the same `K1_PATH`/`K2_PATH` environment variables.

### Full System Diagram

```
 ╔══════════════════════════════════════════════════════════════════════════════════════╗
 ║                         ① EXTERNAL CLIENTS / AI AGENTS                              ║
 ║                                                                                      ║
 ║   ┌──────────────────┐   ┌────────────────────┐   ┌─────────────────────────────┐   ║
 ║   │  Claude Desktop  │   │  Cursor / VS Code  │   │  Any MCP-compatible agent   │   ║
 ║   │  stdio transport │   │  HTTP  :6400/mcp   │   │  SSE / streamable-HTTP      │   ║
 ║   └────────┬─────────┘   └─────────┬──────────┘   └──────────────┬──────────────┘   ║
 ╚════════════╪═════════════════════╪══════════════════════════════╪═══════════════════╝
              │                    │                              │
              └────────────────────┴──────────────────────────────┘
                                   │  MCP JSON-RPC  (tools/call, tools/list, …)
                                   ▼
 ╔══════════════════════════════════════════════════════════════════════════════════════╗
 ║                   ② MCP SERVER   ghostscripter/mcp/                                  ║
 ║                                                                                      ║
 ║   __main__.py  ──  entry point: python -m ghostscripter.mcp                          ║
 ║   server.py    ──  transport selector (stdio │ streamable-HTTP │ SSE via uvicorn)     ║
 ║                                                                                      ║
 ║   tools.py  ──  25 tool handlers + _HANDLERS dispatch table                          ║
 ║   ┌─────────────────────┬───────────────────┬──────────────────┬────────────────┐   ║
 ║   │  Installation &     │  Reading          │  Writing         │  Analysis &    │   ║
 ║   │  Discovery  (5)     │  Resources  (6)   │  Resources  (2)  │  Patching  (3) │   ║
 ║   │                     │                   │                  │                │   ║
 ║   │  detectInstalls     │  readGFF          │  writeGFF        │  compileSummary│   ║
 ║   │  loadInstallation   │  readDLG          │  writeDLG        │  searchNWScript│   ║
 ║   │  listResources      │  readTwoDA        │                  │  twoDAChanges  │   ║
 ║   │  describeResource   │  readTLK          │                  │  INI           │   ║
 ║   │  searchResources    │  readJournal      │                  │                │   ║
 ║   │                     │  journalOverview  │                  │                │   ║
 ║   └─────────────────────┴───────────────────┴──────────────────┴────────────────┘   ║
 ║   ┌────────────────────────────────────────────────────────────────────────────────┐ ║
 ║   │  Targeted Lookups  (4)                                                     │ ║
│  twoDALookup  moduleOverview  nwscriptSignature  nwscriptCategories         │ ║
 ║   └─────────────────────────────────┴──────────────────────────────────────────────┘ ║
 ║   ┌────────────────────────────────────────────────────────────────────────────────┐ ║
 ║   │  Write Tools  writeTwoDA  writeERF  compileScript  writeOverride  (4)             │ ║
 ║   │  Composite Game-Object Accessors  (5)  ← v2.2, context-free AI tools          │ ║
 ║   │                                                                                │ ║
 ║   │  getResource   getQuest   getNpc   getScript   listResType                     │ ║
 ║   │  (format-agnostic accessors; AI needs no knowledge of binary formats)          │ ║
 ║   └────────────────────────────────────────────────────────────────────────────────┘ ║
 ║                                                         │                            ║
 ║   ┌──────────────────────────────────────────────────────────────────────────────┐   ║
 ║   │  AgDecBridge (async HTTP client)                                             │   ║
 ║   │   • lazy httpx.AsyncClient  (optional dependency)                           │   ║
 ║   │   • MCP initialize / tools/call / tools/list  over HTTP JSON-RPC            │   ║
 ║   │   • SSE text/event-stream parser  (_parse_sse)                              │   ║
 ║   │   • Mcp-Session-Id header persistence across requests                       │   ║
 ║   │   • ping()  via GET / — reliable reachability check (no handshake needed)   │   ║
 ║   └────────────────────────────────────┬─────────────────────────────────────────┘   ║
 ╚════════════════════════════════════════╪═════════════════════════════════════════════╝
                                          │  HTTP POST  /mcp  (JSON-RPC 2.0)
 ║                                                                                      ║
 ║   ┌─────────────────────────────────────────────────────────────────────────────┐    ║
 ║   │  analyze-program  │  decompile-function  │  list-functions  │  get-refs     │    ║
 ║   │  search-symbols   │  list-strings        │  get-current-program             │    ║
 ║   │  import-binary    │  analyze-vtables     │  apply-data-type  │  …           │    ║
 ║   └──────────────────────────────┬──────────────────────────────────────────────┘    ║
 ║                                  ▼                                                    ║
 ╚══════════════════════════════════════════════════════════════════════════════════════╝

 ╔══════════════════════════════════════════════════════════════════════════════════════╗
 ║                          ③-A  CORE LAYER   ghostscripter/core/                       ║
 ║                                                                                      ║
 ║  ┌──────────────────────────────────────────────────────────────────────────────┐   ║
 ║  │  SERVICES   core/services/  ← stable public API; only layer MCP may call    │   ║
 ║  │                                                                              │   ║
 ║  │  DialogueService  ── load/parse/export/serialise .dlg; to_dict / from_dict  │   ║
 ║  │  TwoDAService     ── parse 2DA; get_cell; paginated rows; diff_to_ini        │   ║
 ║  │  JournalService   ── load/parse .jrl; filter by category                    │   ║
 ║  │  GFFService       ── any-GFF → dict → any-GFF binary                        │   ║
 ║  │  TLKService       ── load dialog.tlk; search; batch StrRef lookup           │   ║
 ║  │  NWScriptService  ── search functions/constants; full signature()            │   ║
 ║  └──────────────────────────────┬───────────────────────────────────────────────┘   ║
 ║                                 │  implements                                        ║
 ║  ┌──────────────────────────────▼───────────────────────────────────────────────┐   ║
 ║  │  PORTS   core/ports/  (8 typing.Protocol interfaces — hexagonal arch)        │   ║
 ║  │                                                                              │   ║
 ║  │  ResourceReaderPort   GFFReaderPort    TwoDAPort        DialoguePort         │   ║
 ║  │  JournalPort          NWScriptDBPort   DLGSerialiserPort  GFFWriterPort      │   ║
 ║  └──────────────────────────────┬───────────────────────────────────────────────┘   ║
 ║                                 │  uses                                              ║
 ║  ┌──────────────────────────────▼───────────────────────────────────────────────┐   ║
 ║  │  MODELS   core/models/  (pure-Python dataclasses — zero Qt, zero I/O)        │   ║
 ║  │                                                                              │   ║
 ║  │  dialogue.py  ── DialogueFile, DialogueNode, DialogueBranch                 │   ║
 ║  │  tlk.py       ── TLKFile, TLKEntry                                          │   ║
 ║  │  journal.py   ── JournalFile, JournalCategory                               │   ║
 ║  │  quest.py     ── QuestDefinition, QuestState, GlobalVariable                │   ║
 ║  │  script.py    ── ScriptFile                                                  │   ║
 ║  │  project.py   ── ModProject                                                  │   ║
 ║  └──────────────────────────────────────────────────────────────────────────────┘   ║
 ║                                                                                      ║
 ║  ┌──────────────────────────────────────────────────────────────────────────────┐   ║
 ║  │  SUBSYSTEMS  (called only through services or ResourceManager public API)    │   ║
 ║  │                                                                              │   ║
 ║  │  resource_manager/ ── KEY/BIF/ERF/RIM reader; list_by_type; override-only   │   ║
 ║  │  export/           ── dlg_writer · dlg_reader · gff_writer · erf_writer     │   ║
 ║  │                       jrl_writer  (all pure-Python struct, no C extensions)  │   ║
 ║  │  twoda_manager/    ── TwoDAFile: parse / edit / write V2.0 format           │   ║
 ║  │  nwscript/         ── NWScriptDB: parse nwscript.nss (772 fn / 1489 const)  │   ║
 ║  │  validation/       ── DLGValidator: structure, links, cycle detection        │   ║
 ║  │  search/           ── ResourceIndex: fast full-text search across assets    │   ║
 ║  │  database/         ── SQLite: projects, scripts, quests, prefs, export log  │   ║
 ║  └──────────────────────────────────────────────────────────────────────────────┘   ║
 ╚════════╪═════════════════════════════════════════════════════════╪═══════════════════╝
          │  PyQt5 widget calls  (GUI → services)                  │
          ▼                                                         ▼
 ╔══════════════════════════════════════╗  ╔═══════════════════════════════════════════╗
 ║   ④ GUI   ghostscripter/ui/          ║  ║  ⑤ IPC BRIDGE   ghostscripter/ipc/       ║
 ║                                      ║  ║                                           ║
 ║  main_window.py  ── 3-column layout  ║  ║  ghostrigger_bridge.py                   ║
 ║  widgets/:                           ║  ║    REST polling → GhostRigger :7001       ║
 ║   script_editor_widget               ║  ║  ipc_server.py                            ║
 ║   dialogue_editor_widget             ║  ║    Flask callback server :7002            ║
 ║   quest_builder_widget               ║  ║    (daemon thread; push notifications)    ║
 ║   twoda_manager_widget               ║  ║  server.py  ── server lifecycle helpers   ║
 ║   tlk_editor_widget                  ║  ║  client.py  ── HTTP client helpers        ║
 ║   erf_packer_widget                  ║  ║  gmodular_client.py ── GModular API       ║
 ║   journal_editor_widget              ║  ╚══════════════════╪══════════════════════╝
 ║   asset_library_widget               ║                     │  REST  :7001
 ╚══════════════════════════════════════╝                     ▼
              │  reads / writes                   ╔══════════════════════════════════╗
              ▼                                   ║  GhostRigger-K1-K2 (sister app) ║
 ╔══════════════════════════════════════════════════════════════════════════════════════╗
 ║  ⑥ KOTOR GAME DATA   (on disk)                                                      ║
 ║                                                                                      ║
 ║  chitin.key       ── resource index  (25 836 entries in K1)                         ║
 ║  data/*.bif       ── bulk binary archives  (2da.bif · scripts.bif · gui.bif · …)   ║
 ║  modules/*.rim    ── per-area modules (read-only game data)                          ║
 ║  modules/*.erf    ── packed area archives                                            ║
 ║  dialog.tlk       ── localized string table  (49 265 entries in K1)                 ║
 ║  Override/        ── loose files; highest load priority → mod distribution target    ║
 ║  saves/           ── savegame slots  (GFF-based binary format)                      ║
 ╚══════════════════════════════════════════════════════════════════════════════════════╝
```

---

### Layer Responsibilities

| # | Layer | Package | Responsibility |
|---|---|---|---|
| ① | **External Clients** | — | Claude Desktop, Cursor, VS Code, or any MCP-compatible AI agent. Never import GhostScripter Python directly — communicate only through MCP JSON-RPC. |
| ③-A | **Core Layer** | `ghostscripter/core/` | All game-format business logic. Subdivided into Services → Ports → Models → Subsystems. MCP tools and GUI widgets both call into this layer; they never call each other. |
| ④ | **GUI** | `ghostscripter/ui/` | PyQt5 three-column IDE. Calls core services for all data operations. Never calls MCP tools and never imports from `ghostscripter/mcp/`. |
| ⑤ | **IPC Bridge** | `ghostscripter/ipc/` | HTTP polling bridge to GhostRigger (port 7001). Flask daemon server receives push notifications on port 7002. |
| ⑥ | **Game Data** | disk | KotOR binary files. Read-only except `Override/`, which is the mod distribution target. |

**Architecture invariants enforced by 38 guard tests:**
- `tools.py` has zero direct imports from `core.export`, `core.twoda_manager`, `core.nwscript`, or `core.resource_manager` internals
- All MCP-to-core calls go through `core.services` or `core.resource_manager` public API
- `TLKFile` lives in `core.models`, not `ui`

---

### Data Flow Examples

**① Agent reads a KotOR dialogue:**
```
Claude  ──[MCP: readDLG(game="K1", resref="bas_p_bastila")]──►  tools.py::_read_dlg()
        ──►  DialogueService.load(rm, "bas_p_bastila")
        ──►  ResourceManager.read("bas_p_bastila.dlg")  ──►  KEY/BIF lookup
        ──►  DLGImporter.import_bytes()  ──►  DialogueFile dataclass
        ──►  to_dict()  ──►  MCP TextContent  ──►  Claude
```

**② Agent writes a new dialogue:**
```
Claude  ──[MCP: writeDLG(dlg={...})]──►  tools.py::_write_dlg()
        ──►  DialogueService.from_dict({...})  ──►  DialogueFile dataclass
        ──►  DialogueService.to_binary()  ──►  DLGExporter.build()
        ──►  bytes  ──►  base64  ──►  MCP TextContent  ──►  Claude
```

**③ Agent decompiles a KotOR engine function:**
```
Claude then calls GhostScripter:
        ──[MCP: readTwoDA + twoDALookup + writeDLG]──►  ghostscripter MCP server
        ◄──  game asset data
```

---

## Core Services Layer

The architecture follows Khononov's coupling principles — the MCP layer (high volatility, many callers) communicates with core subsystems only through a stable service/port boundary.  See the [System Architecture](#system-architecture) section for the full layer diagram.

### Services (`ghostscripter/core/services/`)

| Service | Key methods | Responsibility |
|---|---|---|
| `DialogueService` | `load()` · `to_dict()` · `from_dict()` · `to_binary()` | Load, parse, export, and serialise `.dlg` files; provides JSON interchange for MCP |
| `TwoDAService` | `get_cell()` · `rows_to_dicts()` · `diff_to_ini()` | Parse 2DA text/bytes, cell lookup by label or index, paginated rows, TSLPatcher diffs |
| `JournalService` | `load()` · `categories()` | Load and parse `.jrl` files; filter by category |
| `GFFService` | `to_dict()` · `from_dict()` | Parse any GFF binary to dict; write dict back to GFF binary |
| `TLKService` | `load()` · `search()` · `batch_lookup()` | Load and search `dialog.tlk`; multi-StrRef batch lookup |
| `NWScriptService` | `search()` · `signature()` | Search functions/constants by query and category; full signature with parameter types |

### Ports (`ghostscripter/core/ports/`)

8 `typing.Protocol` interfaces that define the contract between the service layer and adapters.
Any class that satisfies the protocol can be substituted — enabling dependency injection and easy testing:

| Port | Satisfied by |
|---|---|
| `ResourceReaderPort` | `ResourceManager` |
| `GFFReaderPort` | `DLGImporter` / `GFFService` |
| `TwoDAPort` | `TwoDAFile` / `TwoDAService` |
| `DialoguePort` | `DialogueService` |
| `JournalPort` | `JournalService` |
| `NWScriptDBPort` | `NWScriptDB` / `NWScriptService` |
| `DLGSerialiserPort` | `DLGExporter` |
| `GFFWriterPort` | `GFFWriter` |

### Architecture Guard Tests

1163 tests in `tests/test_mcp_tools.py` and `tests/test_improvements.py` enforce that:
- The MCP `tools.py` module has zero direct imports from `core.export`, `core.twoda_manager`, `core.nwscript`, or `core.resource_manager` internals
- All cross-layer calls go through `core.services` or `core.resource_manager` public API
- `TLKFile` and `TLKEntry` live in `core.models`, not in any UI widget

### Tech Stack

| Component | Technology | Notes |
|---|---|---|
| GUI framework | **PyQt5 5.15+** | QGraphicsView for dialogue node editor; full QSS dark theme (`#1e1e1e` palette) |
| MCP server | **mcp** (FastMCP) | stdio / streamable-HTTP / SSE transports |
| HTTP transport | **uvicorn** | ASGI server for HTTP/SSE modes |
| Binary formats | **Pure Python `struct`** | ERF V1.0 / GFF V3.2 / KEY / BIF / RIM / TLK — zero C extensions |
| Persistence | **SQLite** (stdlib) | Zero extra dependency; projects, scripts, prefs, export log |
| IPC callback server | **Flask 3.x** | Daemon thread; receives push notifications from GhostRigger |
| GhostRigger polling | **requests 2.x** | HTTP polling bridge to GhostRigger on port 7001 |
| Testing | **pytest** | 1163 tests; 0 external services required (AgDec tests use httpx mocks) |
| Build | **PyInstaller** + **Inno Setup** | Windows `.exe` installer; spec in `GhostScripter.spec` |

---

## KotOR Modding Conventions

GhostScripter follows and enforces these community conventions:

| Convention | Rule | Example |
|---|---|---|
| Global variable names | `K_SWG_` prefix, ALL_CAPS | `K_SWG_MYQUEST_STATE` |
| Quest IDs | `k_swg_` prefix, lowercase | `k_swg_retrieve_artifact` |
| Script names | `k_` prefix, lowercase, ≤16 chars | `k_swg_retrieve_01` |
| ResRef length | Max 16 ASCII chars (enforced at export) | `k_mir_debt_st` (13 chars ✓) |
| NPC tags | Lowercase, underscores | `k_npc_questgiver` |

Every Boolean/Number global you add to your scripts needs a row in `globalcat.2da`. Quest Builder generates those entries automatically.

> **Why 16 chars?** KotOR's binary ResRef fields are exactly 16 bytes. Anything longer is **silently truncated** by the engine. GhostScripter warns you at both the script analysis stage (`compileSummary`) and the DLG export stage if any script name would be truncated.

---

## Roadmap

> Full architecture analysis and cross-tool design docs: [`SYSTEMS_DESIGN.md`](SYSTEMS_DESIGN.md) · [`ROADMAP.md`](ROADMAP.md)

### v2.5.0 ✅
- `compileScript` — NWScript → .ncs via nwnnsscomp; returns base64
- `writeOverride` — deploy any resource file to Override; in-session index update
- `ERFService` — removes last direct-import violation from tools layer
- 9 silent exception swallows → `log.debug` throughout `tools.py`
- 1163 tests, 0 failures

### v2.7.0 — getDoor · getPlaceable · getItem · searchAll (+26 new tests)

| Change | Detail |
|--------|--------|
| **+4 MCP tools** | `getDoor`, `getPlaceable`, `getItem`, `searchAll` |
| **41 tools total** | was 30 |
| **1,1163 tests** | 0 failures (+26 since v2.6) |
| `getDoor` | UTD blueprint: tag, lock/trap props, script fields, conversation ref |
| `getPlaceable` | UTP blueprint: tag, appearance, lock/trap, inventory list, script fields |
| `getItem` | UTI blueprint: base item, cost, properties list, TLK-resolved name/description |
| `searchAll` | Unified search across 2DA + TLK + NSS + DLG in one call; scopes + limit params |

## v2.6.0 ✅ (current)
- `getArea` — rich area view: ARE properties + GIT instances (creatures/doors/placeables/waypoints/triggers with XYZ) + LYT room layout
- `tools_pkg/` refactor — 2,500-line `tools.py` split into 6 focused sub-modules; backward-compat shim keeps all imports working
- `searchResources` 2DA caching — `_2DA_CACHE` avoids re-parsing on repeated calls; invalidated on `loadInstallation`
- Canonical port registry — `ghostscripter/ipc/ports.py` is the single source of truth; `constants.py`, `ipc/server.py`, `ipc/ghostrigger_bridge.py`, `ipc/gmodular_client.py` all import from it
- 1163 tests, 0 failures (+17 new: getArea, ports registry, tools_pkg structure)

### v2.7.0 — Path Safety + MCP Config + Context-Free Descriptions (next)

| Item | Detail |
|---|---|
| Path-safety validation | `writeDLG` / `writeGFF` resref validation via `pykotor.tools.path_safety` allowlist |
| `MCP_CONFIG.md` update | Document the 30-tool list + multi-server Claude Desktop / Cursor configs |
| Context-free tool descriptions | Audit all 30 tool descriptions to remove implicit use-case language |
| `getDoor` / `getPlaceable` / `getItem` | UTD/UTP/UTI composite readers — parallel to `getNpc` / `getArea` |
| `searchAll` | Unified text search across 2DA, TLK, NSS, DLG in a single call |

### v3.0.0 — `getFaction` · gs-prefix namespace · PyKotor shim ✅

| Item | Detail |
|---|---|
| `getFaction` tool | FAC GFF composite: faction names + reputation matrix |
| Tool namespace fix | 4 tools prefixed `gs` to avoid KotorMCP collisions |
| PyKotor shim | `ShimInstallation` wraps ResourceManager behind pykotor `Installation` API |
| 1,230 tests | 0 failures |

### v3.1.0 — LIP GUI Editor · `getModule` GIT Snapshots · Qt Designer Stubs ✅

| Item | Detail |
|---|---|
| `LIPEditorWidget` | Full visual GUI: keyframe table, colour timeline, 16-shape legend, binary V1.0 I/O |
| `getModule` snapshot | `include_git` parameter adds per-area GIT instance counts |
| Qt Designer stubs | `new_project_dialog.ui` + `new_quest_dialog.ui` — dialogs try `.ui` first |
| 1,288 tests | 0 failures (+58) |

### v3.3.0 — 5 new MCP tools · `getBlueprint` · PTH/LTR/SSF I/O · 41 new tests ✅

| Item | Detail |
|---|---|
| `readPTH` / `writePTH` | PTH pathfinding GFF decode/encode; validated node-graph |
| `readLTR` | LTR Markov name-generator binary; top start/end letter probabilities |
| `writeSSF` | SSF V1.1 binary encoder; 28-slot sound set from name/index keys |
| `getBlueprint` | Universal blueprint reader for all 9 GFF blueprint types (UTC–UTW) |
| `getArea` enriched | Cameras, weather state, ARE fog/grass/shadow, GIT AreaProperties audio |
| 1,329 tests | 0 failures (+41) |

### v3.3.0 — PyKotor I/O Layer (planned)

The ROADMAP.md Phase 1 milestone: replace GhostScripter's hand-rolled binary readers with the shared `Libraries/PyKotor` format library from the monorepo.

| Item | Detail |
|---|---|
| Replace `resource_manager/` BIF/KEY reader | Use `pykotor.extract.installation.Installation` + `Capsule` |
| Replace `formats/dlg_reader.py` | Use `pykotor.resource.formats.dlg.DLG` read/write |
| Replace `formats/gff_reader.py` | Use `pykotor.resource.formats.gff` read/write |
| Replace `export/erf_writer.py` | Use `pykotor.tools.archives` ERF/RIM helpers |
| Add `pykotor` to `requirements.txt` | Make it an explicit dependency |

### v3.3.0 — GModular MCP Server + Event Bus (planned)

| Item | Detail |
|---|---|
| GModular MCP server | Expose `get_module`, `list_objects`, `get_object` tools from GModular |
| Ghostworks event bus (port 7000) | Replace 8-second IPC polling with pub/sub push events |
| GIT node-graph editor | Visual area object placement GUI |
| Remove legacy `_HANDLERS` aliases | Clean up deprecated `detectInstallations` etc. |

### Backlog (lower priority)

| Item | Notes |
|---|---|
| LIP (lip-sync) editor | Port from `HolocronToolset_old/editors/lip/`; low user demand |
| GIT node-graph UI | Visual area object placement inside GhostScripter GUI |
| Batch export pipeline | Compile → pack → override copy as a single MCP call or GUI workflow |
| Animation timeline | MDL controller data is parsed; needs a Qt timeline widget in GModular |
| Texture pipeline DDS/TGA | Asset Library shows thumbnails; full edit/export loop missing |
| NCS compile integration | `compileScript` tool exists; GUI compile button should use same code path |

---

## Building GhostScripter-K1-K2.exe

```
pip install pyinstaller pillow
build.bat
```

That's it. The script runs PyInstaller, moves `GhostScripter-K1-K2.exe` to the project root, and cleans up `dist/` and `build/`.

Place `nwnnsscomp.exe` next to the `.exe` if you want full NWScript compilation support.

---

## Contributing

Pull requests are welcome. A few things that will make them easier to merge:

- **Read the governance docs first:** [`AGENTS.md`](https://github.com/OldRepublicDevs/PyKotor/blob/master/AGENTS.md) and [`CONVENTIONS.md`](https://github.com/OldRepublicDevs/PyKotor/blob/master/CONVENTIONS.md) in the PyKotor monorepo root set the rules for all submodule tools
- **Typing convention:** use `str | None` / `dict[...]` / `list[...]` — never `typing.Optional`, `typing.Dict`, `typing.List`.  Include `from __future__ import annotations` at the top of every new file
- **Transport:** MCP server must run `stdio` by default; HTTP/SSE optional but never bind to `0.0.0.0`
- **Service boundary:** MCP tools import from `ghostscripter.core.services` only — never from internal subsystem modules
- **Tests:** run `pytest tests/ -q` to confirm 1065 still pass before opening a PR
- **Architecture:** for Ghostworks Pipeline work, read [`SYSTEMS_DESIGN.md`](SYSTEMS_DESIGN.md) — coupling/cohesion analysis, gap analysis, and priority roadmap
- Open an issue first for big structural changes

**Recently completed:**
- [x] **Monorepo integration (v2.3)** — GhostScripter promoted to primary IDE in `OldRepublicDevs/PyKotor`; KotorMCP established as canonical read layer; tool namespace policy documented
- [x] **Compliance audit (v2.3)** — all `typing.Optional/Dict/List/Tuple` replaced with built-in equivalents; `server.py` docstring corrected; `SYSTEMS_DESIGN.md §0` added
- [x] **Composite game-object tools (v2.2)** — `getResource`, `getQuest`, `getNpc`, `getScript`, `listResType`; context-free accessors that resolve KotOR format internally
- [x] **Ghostworks Pipeline documentation** — three-tool IPC diagram, port registry, ownership matrix, `SYSTEMS_DESIGN.md` with Yourdon/Constantine analysis
- [x] **MCP server** — 60 tools, 3 transport modes (stdio / HTTP / SSE), full KotOR API surface for AI agents
- [x] **v2.6 — getArea + tools_pkg refactor + port registry** — `getArea` composite tool (ARE+GIT+LYT); `tools.py` split into `tools_pkg/` sub-package; `searchResources` 2DA session cache; canonical `ipc/ports.py` registry; 1163 tests pass
- [x] **v2.5 — compileScript + writeOverride + ERFService** — `compileScript` invokes nwnnsscomp and returns .ncs as base64; `writeOverride` writes any resource directly to game Override; ERFService service wrapper removes last direct import violation; 9 silent exception swallows replaced with `log.debug`; 1163 tests pass
- [x] **Deep audit (v2.4)** — 5 runtime bugs fixed in composite tools; dead code removed (old 2da_manager, ipc/client.py); architecture coupling violations corrected; `writeTwoDA` + `writeERF` complete the write-back layer; 1163 tests pass
- [x] **Architecture refactor** — ports/services layer, `TLKFile` extracted to core, 8 Protocol interfaces, 38 architecture guard tests
- [x] **list_by_type BIF fix** — `EXT_RESTYPE` dot-key lookup now returns all game assets from `.bif` archives
- [x] **TwoDAService.get_cell() label fix** — label lookup now correctly reads `row.data['label']`
- [x] **override-only mode** — `ResourceManager.load_game()` succeeds without `chitin.key`
- [x] **ERFWriter API** — `add_resource()` + `build()` convenience methods
- [x] **compileSummary enhancements** — `int oXxx` type heuristic + ResRef length check
- [x] **DLGExporter warnings** — logs when script names will be silently truncated
- [x] **asyncio fix** — test helper uses `asyncio.run()` (eliminates Python 3.10+ deprecation warning)
- [x] **NCS decompiler integration** — auto-detects DeNCS CLI, xoreos-tools, pykotor
- [x] **Texture viewer** — TGA/TPC preview panel inside the Asset Library
- [x] **GFF VECTOR/ORIENTATION types** — full round-trip for creature/placeable blueprints

**Things I'd like to add (help appreciated):**
- [ ] **Ghostworks Event Bus** (port 7000) — replace 8-second IPC polling with push pub/sub; see `SYSTEMS_DESIGN.md §5`
- [ ] GModular MCP server — expose `get_module`, `list_objects`, `get_object` tools
- [ ] Module builder wizard — full `.mod`/`.rim` from scratch with area, creature, and waypoint placement
- [ ] Script dependency graph — visualize which scripts belong to a quest and which dialogues call them
- [ ] Batch export — export all project files in one click with a complete TSLPatcher `changes.ini`
- [ ] NCS compile integration — invoke bundled `nwnnsscomp_k1.exe`/`nwnnsscomp_k2.exe` from the GUI without needing an external copy

---

## Credits

Big thanks to the KotOR modding community — the tools and documentation that already existed made this project possible.

| Tool / Person | Why it matters here |
|---|---|
| **Fred Tetra** (KotOR Tool) | Original KotOR archive explorer — BIF/KEY extraction reference |
| **TK102** (K-GFF, DLG Editor) | GFF and dialogue format reference implementations |
| **Fair Strides** (DLG Editor) | Dialogue tree parsing and visualization |
| **Cortisol** (Holocron Toolset) | Module editing patterns, GFF format research |
| **xoreos project** | NCS decompiler, GFF tools, BIF extractor |
| **Deadly Stream** | Community documentation, format specs, modding guides |
| **Thor110, DarthParametric, AmanoJyaku** | Community knowledge, answered a lot of questions |

Full list: [CREDITS.md](CREDITS.md)

---

## License

GPL-3.0. See [LICENSE.md](LICENSE.md).

> Star Wars: Knights of the Old Republic and Knights of the Old Republic II are trademarks of Lucasfilm Ltd. This project is not affiliated with or endorsed by Lucasfilm, LucasArts, or Aspyr Media.
