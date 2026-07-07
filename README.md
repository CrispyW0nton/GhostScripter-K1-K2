# GhostScripter-K1-K2

> **Build mods for Star Wars: Knights of the Old Republic I & II — scripts, dialogue, quests, and game data — in one tool.**

[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](LICENSE.md)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-brightgreen)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-1422%20passed-brightgreen)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)]()
[![Version](https://img.shields.io/badge/version-3.6.1-orange)]()
[![Monorepo](https://img.shields.io/badge/monorepo-OldRepublicDevs%2FPyKotor-informational)](https://github.com/OldRepublicDevs/PyKotor)

If you've modded KotOR before, you know the drill: KotOR Tool to extract files, a text editor for scripts, DLGEditor for conversations, a 2DA editor for game tables, ERFEdit to pack it all up. GhostScripter puts that whole workflow in one place:

- **Write and compile NWScript** with syntax highlighting, autocomplete from `nwscript.nss`, and a built-in compiler — no Wine, no external binaries needed.
- **Build conversations visually** in a node-graph dialogue editor with full `.dlg` round-trip — open any stock or modded dialogue, edit it, save it back.
- **Scaffold quests** from templates that generate the global variables, journal states, and script stubs with correct community naming conventions.
- **Edit 2DA tables and dialog.tlk** in place, with one-click TSLPatcher `changes.ini` export.
- **Browse your game's files without extracting anything** — the Asset Library reads BIF/ERF/RIM archives directly, with texture previews.
- **Export with confidence** — straight to Override for testing, or packed into a proper ERF/MOD for distribution.

It also ships a **Model Context Protocol (MCP) server with 60 tools**, so AI assistants like Claude Desktop or Cursor can read, analyze, and write KotOR game assets alongside you. That part is entirely optional — the GUI works fine without it.

> **Latest release — v3.6.1:** all binary writers cross-checked against PyKotor and retail game
> data; fixed ERF resource-type IDs, journal (JRL) game compatibility, and dialogue text
> encoding. Full history in [CHANGELOG.md](CHANGELOG.md).

---

## Table of Contents

- [Getting Started](#getting-started)
  - [What you need](#what-you-need)
  - [Install](#install)
  - [First launch](#first-launch)
- [Tutorial: Your First Mod](#tutorial-your-first-mod)
- [The Editors](#the-editors)
- [Exporting and Distributing Your Mod](#exporting-and-distributing-your-mod)
- [Using AI Assistants (MCP Server)](#using-ai-assistants-mcp-server)
- [KotOR Modding Conventions](#kotor-modding-conventions)
- [Tips and Troubleshooting](#tips-and-troubleshooting)
- [Related Tools](#related-tools)
- [For Developers](#for-developers)
- [Roadmap](#roadmap)
- [Credits](#credits)
- [License](#license)

---

## Getting Started

### What you need

1. **A copy of KotOR 1 and/or KotOR 2 (TSL), installed.** Steam, GOG, and disc versions all work — GhostScripter just needs the game folder (the one containing `chitin.key`). Most of the tool's value comes from reading your game's actual files: TLK strings, 2DA rows, blueprints, and modules.

   > **Use an unmodded copy as your reference.** GhostScripter resolves names, dialogue text, and table rows from your game folder. If that folder already contains other mods' Override files, your lookups will reflect *their* changes instead of the vanilla game. Keep one clean install for authoring, and test mods on a separate copy if you can.

2. **Python 3.10 or newer** — unless you build the standalone Windows `.exe` (see [For Developers](#for-developers)).

### Install

```bash
git clone https://github.com/CrispyW0nton/GhostScripter-K1-K2.git
cd GhostScripter-K1-K2

python -m venv venv
source venv/bin/activate      # Linux/macOS
venv\Scripts\activate.bat     # Windows

pip install -r requirements.txt
```

### First launch

```bash
python ghostscripter/main.py
```

On startup GhostScripter looks for your game automatically — it checks environment variables, the Windows registry, and the usual Steam/GOG install paths for both games. When it finds one, the status bar shows the loaded game and the Asset Library fills with your game's resources.

If auto-detect misses your install, point it there yourself — any one of these works:

```bash
# Option A — in the GUI:
#   File → Set KotOR Game Directory… → browse to the folder containing chitin.key

# Option B — environment variable (also used by the MCP server):
export K1_PATH="/path/to/swkotor"        # Linux/macOS
set K1_PATH=C:\Games\swkotor             # Windows CMD
# K2_PATH works the same way for TSL
```

That's it. If you want to jump straight in, the tutorial below builds a small working quest from scratch. (There's also an interactive version inside the app: `Help → Quick-Start Guide`, or press `F1`.)

---

## Tutorial: Your First Mod

Let's build the classic starter mod: a quest with journal entries, a trigger script, and an NPC conversation. Nothing here requires previous KotOR modding experience, but if terms like *Override* or *2DA* are new to you, skim [KotOR Modding Conventions](#kotor-modding-conventions) first.

**The plan:** an NPC asks the player to find something. Accepting the task starts a quest in the player's journal.

### Step 1 — Create a project

Click **+ Project** in the toolbar. Give it a name (`TestQuest`), pick your target game (K1), and choose a folder. GhostScripter creates a project structure with folders for scripts, dialogues, quests, and 2DA edits, and remembers it in your recent projects.

### Step 2 — Scaffold the quest

Click **+ New Quest** in the sidebar → choose **Simple Quest (3 states)** → name it `relic`.

(Why such a short name? Generated script names follow the pattern `k_swg_<name>_<state>`, and KotOR truncates anything over 16 characters — a rule you'll meet again in this tutorial.)

The Quest Builder generates everything the quest needs, pre-named to community conventions:

- Two global variables: `K_SWG_RELIC` (Boolean) and `K_SWG_RELIC_STATE` (Number)
- Three journal states: *Not Started → Active → Complete*
- One script stub per state: `k_swg_relic_00`, `k_swg_relic_01`, `k_swg_relic_02`

Look through the **Overview**, **Variables**, **States**, and **Scripts** tabs to see what it made.

### Step 3 — Write and compile the trigger script

`Script → New Script` (or `Ctrl+N`) → name it `k_swg_relic_01`. This is the script that fires when the player accepts the quest:

```nwscript
void main() {
    SetGlobalBoolean("K_SWG_RELIC", TRUE);
    SetGlobalNumber("K_SWG_RELIC_STATE", 1);
    AddJournalQuestEntry("k_swg_relic", 10, FALSE);
}
```

A few editor features worth noticing while you type:

- `Ctrl+Space` autocompletes function names from the real `nwscript.nss`.
- The function reference sidebar shows full signatures — double-click to insert.
- The static checker catches classic mistakes: `int oPC` instead of `object oPC`, script names longer than KotOR's 16-character limit, unbalanced braces.

Click **⚙ Compile → NCS**. The built-in compiler (pure Python, via PyKotor) produces the `.ncs` binary the game runs. No setup required; if you happen to have `nwnnsscomp.exe`, it's used as a fallback automatically.

### Step 4 — Register the quest variables

Every global variable your scripts use needs a row in `globalcat.2da`. The Quest Builder's **globalcat.2da** tab already generated the rows — copy them, then:

1. `Tables → Open 2DA Manager with Game Library` and load `globalcat.2da` straight from your game files.
2. **+ Add Row** for each variable: label `K_SWG_RELIC` with type `Boolean`, and `K_SWG_RELIC_STATE` with type `Number`.
3. Save. The edited `.2da` will ship with your mod.

The quest also needs journal text: open the Journal Editor (`Strings → Journal Editor`), add a `k_swg_relic` category, and give state `10` its journal entry text ("Find the relic for the stranger.").

### Step 5 — Build the dialogue

`Dialog → New Dialogue` → name it `npc_questgiver`. In the node graph:

1. The starter tree gives you an NPC node — set its text: *"I need you to find something for me."*
2. Add a **Player node**: *"I'll do it."* and connect it as a branch of the NPC line.
3. Select the player node and, in the Inspector, set its **Script** field to `k_swg_relic_01` — accepting the line fires your quest script.
4. Add a second player branch: *"Not interested."* with no script, pointing to end-of-conversation (target `-1`).
5. Click **Validate** — it checks for broken links, empty nodes, and script names that would be silently truncated by the game.

Red nodes are NPC lines, blue nodes are player choices — the same Entry/Reply structure the game uses internally.

### Step 6 — Export to Override

`Tables → Export to Override` → confirm your game folder.

GhostScripter copies the compiled script (`.ncs`), the dialogue (`.dlg`), and your 2DA/journal edits into `<game>/Override/`. The output log lists every file it wrote. Files in Override take priority over the game's archives, so this is the standard way to test while developing.

To actually see the conversation in-game you'd attach the `.dlg` to an NPC — either by editing an existing creature's dialogue field (grab its `.utc` from the Asset Library) or by placing a new NPC with a tool like [GModular](https://github.com/CrispyW0nton/GModular). For a first pass, overriding an existing NPC's `.dlg` resref is the quickest way to hear your lines.

### Step 7 — Test it in game

Enable the cheat console (add `EnableCheats=1` under `[Game Options]` in `swkotor.ini`), start the game, and `warp` to a convenient module. Talk to your NPC: picking *"I'll do it."* should pop the quest into your journal. If it doesn't, the [troubleshooting section](#tips-and-troubleshooting) covers the usual suspects.

### Where to go from here

- Give the other two quest states scripts and journal text, and wire a completion trigger.
- Package the mod properly for other players — see [Exporting and Distributing](#exporting-and-distributing-your-mod).
- Let an AI assistant handle the boilerplate — see [Using AI Assistants](#using-ai-assistants-mcp-server).

---

## The Editors

A quick tour of each tool in the IDE. They all read from your project and your loaded game installation.

**Script Editor** — NWScript editing with full syntax highlighting, line numbers, autocomplete (`Ctrl+Space`), a searchable function-reference sidebar, and `void main()` / `StartingConditional()` templates. Compiles to `.ncs` with the built-in PyKotor compiler (cross-platform, no external tools) and decompiles existing `.ncs` binaries back to readable source.

**Dialogue Editor** — node-graph view of `.dlg` conversations. NPC lines and player replies are draggable nodes; branches carry conditional scripts; the Inspector exposes the full field set (voice-over refs, camera fields, TSL-specific extras). Round-trips any stock or modded dialogue. **Validate** catches broken branch targets, empty nodes, and over-long script names before the game silently misbehaves.

**Quest Builder** — three templates (Simple 3-state, Branching Light/Dark, NPC Companion) that generate globals, states, script stubs, and copy-ready `globalcat.2da` rows following `K_SWG_` naming conventions.

**2DA Manager** — spreadsheet editing for the game's data tables: inline cells, add/delete rows and columns, live search, and TSLPatcher-style operations (`AddRow`, `CopyRow`, `ModifyRow`, `ColumnAdd`) with one-click `changes.ini` export.

**TLK Editor** — search and edit all ~49,000 entries of `dialog.tlk`, jump by StrRef, and save byte-accurate binaries. Loads alongside the Dialogue Editor so node cards show real text for StrRef-based lines.

**Journal Editor** — browse and edit quest categories and journal entries in `.jrl` files, and save back to game-ready binary.

**ERF / MOD Packer** — drag files in, pick `ERF`/`MOD`/`SAV`, and build a correctly-typed binary archive. You can pull resources straight from your game library into the archive.

**Asset Library** — tabbed browser over your project *and* your entire game installation (BIF/ERF/RIM archives, no extraction step). Global search across all types; TGA/TPC textures render a live preview; models can be sent to GhostRigger for rigging work.

Everything is backed by a small local SQLite database (`~/.ghostscripter/`) that tracks recent projects, script revision history, and preferences.

---

## Exporting and Distributing Your Mod

| Method | When to use it | Menu |
|---|---|---|
| **Override** | Testing on your own machine while developing | `Tables → Export to Override` |
| **ERF / MOD archive** | Distributing module content, or feeding TSLPatcher | `Tables → Export to ERF` |
| **`changes.ini`** | Shipping 2DA edits that must merge with other mods | 2DA Manager → export button |

A note on 2DA files: **never ship a whole edited `appearance.2da`** or similar — it will clobber every other mod that touches the same table. Ship a TSLPatcher `changes.ini` instead so rows merge at install time. GhostScripter generates that diff for you.

---

## Using AI Assistants (MCP Server)

GhostScripter's MCP server lets AI agents work with your KotOR installation directly: look up 2DA rows, read dialogues and blueprints, compile scripts, build ERF archives, and write files to Override. It speaks the standard [Model Context Protocol](https://modelcontextprotocol.io/), so anything MCP-compatible can connect — Claude Desktop, Cursor, VS Code Copilot, and others.

Start it with:

```bash
python -m ghostscripter.mcp                       # stdio — for Claude Desktop
python -m ghostscripter.mcp --mode http --port 6400   # HTTP — for Cursor / VS Code
```

The server auto-detects your game the same way the GUI does; set `K1_PATH` / `K2_PATH` if needed.

**Claude Desktop** — add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ghostscripter": {
      "command": "python",
      "args": ["-m", "ghostscripter.mcp"],
      "cwd": "/path/to/GhostScripter-K1-K2",
      "env": { "K1_PATH": "/path/to/swkotor", "K2_PATH": "/path/to/swkotor2" }
    }
  }
}
```

**Cursor / VS Code** — start the server in HTTP mode (above), then add to `.cursor/mcp.json` or `.vscode/mcp.json`:

```json
{ "servers": { "ghostscripter": { "url": "http://localhost:6400/mcp" } } }
```

More configurations (SSE mode, combined multi-server setups) are in [MCP_CONFIG.md](ghostscripter/mcp/MCP_CONFIG.md).

### What agents can do with it

A typical exchange: *"What head model does Mira use?"* → the agent calls `twoDALookup` on `appearance.2da`. *"Write a dialogue where she refuses to help"* → `writeDLG` produces a game-ready binary. *"Put it in my Override"* → `writeOverride`. The composite tools (`getNpc`, `getQuest`, `getArea`, …) return whole game objects as structured JSON so the agent never needs to know which binary format is involved.

For the best experience, run it alongside [KotorMCP](https://github.com/OldRepublicDevs/KotorMCP) — the read-only companion server from the PyKotor monorepo; GhostScripter handles the write side.

<details>
<summary><strong>All 60 tools</strong> (click to expand)</summary>

**Installation & discovery** — `gsDetectInstallations`, `gsLoadInstallation`, `gsListResources`, `gsDescribeResource`, `searchResources`, `searchAll`, `listResType`

**Reading game formats** — `readGFF`, `readDLG`, `readTwoDA`, `readTLK`, `readJournal` (alias `journalOverview`), `readSSF`, `readLIP`, `readPTH`, `readLTR`, `readGUI`, `readSave`, `readNCS`, `readVIS`, `readIFO`, `readWAV`, `readTXI`

**Targeted lookups** — `twoDALookup`, `moduleOverview`, `nwscriptSignature`, `nwscriptCategories`, `searchNWScript`, `getNWScriptDB`, `pathfindRoute`

**Writing game formats** — `writeGFF`, `writeDLG`, `writeTwoDA`, `writeERF`, `writeSSF`, `writeLIP`, `writePTH`, `writeOverride`

**Scripts** — `compileScript` (NSS → NCS, pure Python), `decompileScript` (NCS → NSS), `compileSummary` (static analysis)

**Patching** — `twoDAChangesINI` (TSLPatcher-compatible `changes.ini` from a 2DA diff)

**Composite game objects** — `getResource`, `getQuest`, `getNpc`, `getCreature`, `getScript`, `getArea`, `getModule`, `getDoor`, `getPlaceable`, `getItem`, `getEncounter`, `getTrigger`, `getWaypoint`, `getStore`, `getSound`, `getFaction`, `getBlueprint`

Plus legacy unprefixed aliases for the four `gs*` tools. Every tool returns JSON; write tools return base64 payloads that chain into `writeERF` / `writeOverride`.

</details>

**Works without a game installation:** NWScript lookup (772 K1 / 812 K2 functions), script compile/decompile, static analysis, and all the write tools. Everything that *reads* game data needs a loaded installation.

---

## KotOR Modding Conventions

GhostScripter follows and enforces the community conventions used across Deadly Stream mods:

| Convention | Rule | Example |
|---|---|---|
| Global variable names | `K_SWG_` prefix, ALL_CAPS | `K_SWG_MYQUEST_STATE` |
| Quest IDs | `k_swg_` prefix, lowercase | `k_swg_retrieve_artifact` |
| Script names | `k_` prefix, lowercase, **≤ 16 chars** | `k_swg_retrieve_01` |
| ResRef length | Max 16 ASCII characters | `k_mir_debt_st` ✓ |
| NPC tags | Lowercase with underscores | `k_npc_questgiver` |

**Why 16 characters?** Every ResRef field in KotOR's binary formats is exactly 16 bytes. Longer names are *silently truncated* by the engine — the classic "my script never fires" bug. GhostScripter warns you in the script checker and again at dialogue export if any name would be cut off.

And remember: every global your scripts touch needs a `globalcat.2da` row, or the game ignores it. The Quest Builder generates these automatically.

---

## Tips and Troubleshooting

**GhostScripter didn't find my game.** Set the folder manually (`File → Set KotOR Game Directory…`) or export `K1_PATH`/`K2_PATH`. The folder you want is the one containing `chitin.key`.

**My script compiles but nothing happens in game.** Check the name length first — anything over 16 characters is truncated by the engine, so the dialogue is calling a script that doesn't exist. The Dialogue Editor's **Validate** button and the script checker both flag this.

**The quest doesn't appear in the journal.** `AddJournalQuestEntry` needs the quest to exist in `global.jrl` (Journal Editor) *and* its globals registered in `globalcat.2da`. Both files must be exported to Override.

**Lookups show another mod's data.** Your reference game folder has other mods installed. Point GhostScripter at a clean copy — see [What you need](#what-you-need).

**Texture previews say pykotor is missing.** TPC decoding uses the `pykotor` library: `pip install -r requirements.txt` covers it (TGA previews additionally use Pillow).

**Which files can I safely put in Override?** Any resource the game looks up by name: `.ncs`, `.dlg`, `.2da`, `.utc`/`.uti`/… blueprints, `.jrl`, textures. Module-level files (`.mod`/`.rim`/`.erf`) go in `Modules/` instead.

**Decompiled scripts look suspiciously empty.** NCS decompilation is best-effort — for complex control flow the decompiler can drop code. Treat decompiled source as a starting point, not gospel; the original DeNCS remains the community gold standard.

---

## Related Tools

GhostScripter is one of three tools in the **Ghostworks Pipeline**, and lives in the [OldRepublicDevs/PyKotor](https://github.com/OldRepublicDevs/PyKotor) monorepo at `Tools/GhostScripter-K1-K2`:

| Tool | What it covers |
|---|---|
| **GhostScripter-K1-K2** (this repo) | Scripts, dialogue, quests, 2DA/TLK/JRL, packaging, write-side MCP |
| [GModular](https://github.com/CrispyW0nton/GModular) | 3D module/world editing — areas, GIT object placement, walkmeshes |
| [GhostRigger-K1-K2](https://github.com/CrispyW0nton/GhostRigger-K1-K2) | MDL model rigging, skinning, K1↔K2 porting |
| [KotorMCP](https://github.com/OldRepublicDevs/KotorMCP) | Read-only MCP server on the shared PyKotor library — run alongside GhostScripter for agents |

When GhostRigger is running, GhostScripter connects to it automatically (ports 7001/7002) so you can send models back and forth from the Asset Library. Neither tool requires the other.

---

## For Developers

**Run the tests:**

```bash
python -m pytest tests/ -q
# 1422 passed, 65 skipped in ~25 seconds
```

**Build the Windows .exe:**

```bash
pip install pyinstaller pillow
build.bat
```

The script produces a standalone `GhostScripter-K1-K2.exe` at the repo root — no Python needed on the target machine.

**Architecture** — the GUI, the MCP server, and the IPC bridge are three entry points over one core layer, separated by a service boundary (`ghostscripter/core/services/`). Binary format I/O is pure-Python `struct` code cross-validated against PyKotor. The full design docs, layer diagrams, and coupling analysis live in [SYSTEMS_DESIGN.md](SYSTEMS_DESIGN.md).

**Contributing** — pull requests welcome:

- Read [`AGENTS.md`](https://github.com/OldRepublicDevs/PyKotor/blob/master/AGENTS.md) and [`CONVENTIONS.md`](https://github.com/OldRepublicDevs/PyKotor/blob/master/CONVENTIONS.md) in the monorepo root first.
- Use modern typing (`str | None`, `dict[...]`) with `from __future__ import annotations`; never `typing.Optional`/`Dict`/`List`.
- MCP tools import only from `ghostscripter.core.services` — never from subsystem internals. Guard tests enforce this.
- The MCP server defaults to stdio and must never bind HTTP to `0.0.0.0`.
- Run the test suite before opening a PR, and open an issue first for big structural changes.

---

## Roadmap

Highlights of what's planned — the full, current list lives in [ROADMAP.md](ROADMAP.md):

- **Ghostworks event bus** — replace IPC polling with push events between the three tools
- **Module builder wizard** — create a complete `.mod` from scratch with area, NPC, and waypoint placement
- **Batch export** — compile, pack, and generate a TSLPatcher `changes.ini` in one click
- **Script dependency graph** — visualize which scripts and dialogues belong to each quest

---

## Credits

Big thanks to the KotOR modding community — the tools and documentation that already existed made this project possible.

| Tool / Person | Why it matters here |
|---|---|
| **Fred Tetra** (KotOR Tool) | Original KotOR archive explorer — BIF/KEY extraction reference |
| **TK102** (K-GFF, DLG Editor) | GFF and dialogue format reference implementations |
| **Fair Strides** (DLG Editor) | Dialogue tree parsing and visualization |
| **Cortisol** (Holocron Toolset / PyKotor) | Module editing patterns, GFF format research, the PyKotor library |
| **xoreos project** | NCS decompiler, GFF tools, BIF extractor |
| **Deadly Stream** | Community documentation, format specs, modding guides |
| **Thor110, DarthParametric, AmanoJyaku** | Community knowledge, answered a lot of questions |

Full list: [CREDITS.md](CREDITS.md)

---

## License

GPL-3.0. See [LICENSE.md](LICENSE.md).

> Star Wars: Knights of the Old Republic and Knights of the Old Republic II are trademarks of Lucasfilm Ltd. This project is not affiliated with or endorsed by Lucasfilm, LucasArts, or Aspyr Media.
