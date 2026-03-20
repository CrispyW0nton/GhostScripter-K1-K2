# GhostScripter-K1-K2 — Project Roadmap & Honest Audit

> **Repository**: https://github.com/CrispyW0nton/GhostScripter-K1-K2  
> **Last audited**: 2026-03-20  
> **Auditor**: Full source-code sweep — every handler, widget, parser, and reference repo

---

## TL;DR — If You Downloaded This Today (v3.6.0)

> **Hard requirement**: You need a copy of KotOR 1 and/or KotOR 2 (TSL) installed. An **unmodded (vanilla) install is strongly recommended** — GhostScripter reads your game's `dialog.tlk`, 2DA tables, and blueprint templates as its reference library. If Override files from other mods are present those values will be wrong.

A KotOR modder downloading this project on 2026-03-20 would get:

| Component | Status | Notes |
|---|---|---|
| **MCP server** (60 tools) | ✅ Launches | `python -m ghostscripter.mcp` works |
| **No-install MCP tools** | ✅ Work | 11 tools need no game path (was 10; added `getNWScriptDB`) |
| **Installation-dependent tools** | ❌ Require game path | All 49 read/query tools need env var / auto-detect |
| **Auto-detect game paths** | ⚠️ Probes 30+ paths | Works if game is at a known location |
| **compileScript** | ✅ Works | Uses `InbuiltNCSCompiler` (PyKotor, pure Python — bundled in requirements.txt) |
| **decompileScript** | ✅ Works | Uses `NCSDecompiler` (PyKotor) |
| **writePTH** | ✅ Real GFF binary | Full GFF V3.2 binary output (was JSON stub) |
| **Qt GUI** | ✅ Launches | `python -m ghostscripter` opens IDE |
| **GUI – Script editor compile** | ✅ Works | Tries PyKotor first; falls back to nwnnsscomp |
| **GUI – Dialogue editor** | ✅ Substantial | Full node graph + inspector UI |
| **GUI – 2DA manager** | ✅ Works | Read/edit/export 2DA tables |
| **GUI – Quest builder** | ✅ Partial | Templates work; deep JRL round-trip untested |
| **GUI – Asset library** | ⚠️ Browse only | Needs game path; no live 3D preview |
| **GUI – ERF packer** | ✅ Works | Pack files into MOD/ERF |
| **GUI – TLK editor** | ✅ Read-only | Can browse strings; editing not confirmed |
| **GUI – Journal editor** | ✅ Works | JRL read/write round-trip |
| **GUI – LIP editor** | ✅ Works | LIP binary read/write |
| **GUI – Log viewer** | ✅ Works | Live log display |
| **GhostRigger** | ✅ Works standalone (Tkinter) | Separate app (`ghostrigger/`); GhostScripter only *connects* to it via IPC if it's already running |
| **GhostRigger ↔ GhostScripter IPC** | ⚠️ Optional bridge | GhostScripter polls port 7001 every 8s; shows "GR: ✓/✗" in status bar; neither app launches the other |
| **GhostRigger 3D viewport** | ✅ Software-rendered | PIL-based; no GPU required |
| **Version badge vs. code** | ✅ Fixed | Both say 3.6.0 |
| **Test suite** | ✅ 1444/1450 pass | 0 failures, 6 skipped |
| **PyKotor (required dep)** | ✅ Bundled in requirements.txt | `pip install -r requirements.txt` gets everything |

---

## Section 1 — What Works Well

### 1.1 MCP Server
- **60 tools registered** and validated against a test registry.
- `python -m ghostscripter.mcp` starts cleanly in stdio mode.
- HTTP and SSE transports available (`--mode http --port 6400`, requires `uvicorn`).
- `_auto_load_installations()` probes env vars → Windows Registry (PyKotor-sourced keys) → 30+ default paths on startup, eliminating most manual `gsLoadInstallation` calls.

### 1.2 Tools That Work Without a Game Installation
These 11 tools function immediately with no KotOR installation:

| Tool | What it does |
|---|---|
| `gsDetectInstallations` | Reports auto-detected game paths |
| `nwscriptCategories` | Lists NWScript function categories |
| `nwscriptSignature` | Returns full signature for any NWScript function |
| `compileSummary` | Static analysis of .nss source (no compiler needed) |
| `searchNWScript` | Search 772 K1 / 812 K2 NWScript functions by name |
| `getNWScriptDB` | **NEW** — full NWScript DB dump (functions + constants) |
| `compileScript` | **Now works** via InbuiltNCSCompiler (PyKotor) |
| `writeGFF` | Builds GFF binary from a JSON fields dict |
| `writeDLG` | Builds binary .dlg from entries/replies |
| `writeTwoDA` | Builds binary .2da |
| `writeSSF` | Builds binary SSF sound-set file |
| `writeLIP` | Builds binary LIP phoneme file |
| `writePTH` | **Now works** — real GFF V3.2 binary PTH output |

### 1.3 Qt GUI
- Launches cleanly on PyQt5 (also works with PyQt6/PySide6 via qtpy).
- **Script editor**: dark theme, full syntax highlighting, autocomplete (Ctrl+Space), function reference panel, template insertion, compiler output console, find/replace, go-to-line, bracket matching.
- **Dialogue editor**: full node-graph view with hierarchical layout, NPC/player node inspector (all 30+ GFF fields), dialogue properties panel, import/export .dlg binary.
- **2DA manager**: read/parse/edit 2DA tables, with game-path browsing.
- **ERF packer**: drag-and-drop file packing into MOD/ERF archives.
- **Journal editor**: JRL read/write round-trip.
- **LIP editor**: binary LIP phoneme editing.
- IPC bridge to GhostRigger over localhost socket; event-drain timer for cross-process communication.

### 1.4 GhostRigger-K1-K2 (Separate Standalone Tool — Not Launched by GhostScripter)
GhostRigger is a **completely independent application** (`ghostrigger/GhostRigger-K1-K2/main.py`). You run it separately. GhostScripter does **not** start it. What GhostScripter does is poll `http://localhost:7001` every 8 seconds and show a "GR: ✓/✗" indicator in its status bar. If GhostRigger happens to be running, they can exchange model data over localhost REST — but neither one depends on the other to function.

GhostRigger's own capabilities (all working):
- Full Tkinter GUI (no Qt required).
- **MDL binary parser**: reads KotOR binary MDL + MDX, reconstructs full node tree with meshes, skins, animations.
- **MDL ASCII parser/writer**: bidirectional ASCII MDL (MDLOps format).
- **Auto-rigger**: heuristic bone weight assignment; supports humanoid, quadruped, creature templates.
- **3D viewport**: software rasterizer (PIL-based), UV-mapped, Phong lighting, skeleton overlay, arc-ball camera.
- **OBJ import/export**: full round-trip.
- **FBX import/export**: works with pyassimp/trimesh; falls back to FBX ASCII 7.4 if unavailable.
- **TGA↔TPC conversion**, DXT1/DXT5 decompression built in.
- **GameLibrary**: scans KotOR install for models, browses by category.

### 1.5 Core Format Support (Internal, No PyKotor)
- **GFF3 reader/writer**: full binary GFF V3.2, all field types (BYTE through LIST), all resource types.
- **DLG reader/writer**: complete binary DLG round-trip including AnimList, per-node scripts, camera fields.
- **ERF reader/writer**: ERF v1.0 pack/unpack, MOD/ERF/SAV archive types.
- **TwoDA parser**: binary and ASCII 2DA read/write.
- **TLK parser**: dialog.tlk StrRef lookup.
- **LIP binary**: LIP V1.0 encode/decode.
- **SSF binary**: SSF V1.1 28-slot encode/decode.
- **NCS internal disassembler**: decodes NCS bytecode to instruction list (no PyKotor).
- **PTH reader**: reads binary PTH + A* pathfinding (readPTH, pathfindRoute).
- **LTR reader**: letter-frequency table read.
- **VIS reader**: area visibility text read.
- **TXI reader**: texture info key-value parse.
- **IFO reader**: module info GFF parse.
- **WAV reader**: RIFF WAV header decode.
- **GUI reader**: KotOR GUI binary parse.

---

## Section 2 — What Is Broken or Incomplete (v3.6.0 status)

### 2.1 ✅ RESOLVED: Version Number Mismatch
`APP_VERSION` now correctly reads `3.6.0`. Window title and badge agree.

### 2.2 ✅ RESOLVED: compileScript / decompileScript Require PyKotor
PyKotor is now in `requirements.txt`. Both tools work out-of-the-box via `InbuiltNCSCompiler` and `NCSDecompiler`.

### 2.3 ✅ RESOLVED: writePTH Returns JSON, Not Binary
`writePTH` now uses `GFF3Writer` to produce real GFF V3.2 binary. The output is directly game-loadable.

### 2.4 Still Open: writeOverride Requires Live Installation
`writeOverride` (the tool that actually deploys mods) needs a loaded game installation to resolve the Override folder path. Without it you get "No K1 installation found." This means the core deployment workflow is blocked for users who haven't configured game paths. **Workaround**: set `K1_PATH`/`K2_PATH` env var, then call `gsLoadInstallation` first.

### 2.5 ✅ RESOLVED: Inconsistent Error Messages
All 8 handlers that previously threw `KeyError` on missing args now return graceful JSON errors. Argument aliases added (`questId`/`quest_id`, `table`/`resref`, `module`/`module_id`, etc.).

### 2.6 Still Open: readSave Is Incomplete
`readSave` requires `save_path` (a filesystem path the AI agent would need to know). There is no `save_index` or auto-scan of save folders. PyKotor has `SaveFolderEntry` tracking — we have not integrated it.

### 2.7 ✅ RESOLVED: getNWScriptDB Is Not Registered
The tool `getNWScriptDB` is referenced in tests and comments but is **not in the TOOLS list**. AI agents cannot call it.

### 2.8 Low: writeLIP Schema/Test Mismatch
`writeLIP` schema requires `duration` + `keyframes`. Our own internal tests previously called it with `phonemes` instead of `keyframes`, indicating the field name is not intuitive and was wrong at least once.

### 2.9 Low: No BWM Walkmesh Reader
`readBWM` / `readWOK` are not implemented as MCP tools. PyKotor has a complete `BWM` class with AABB tree, raycast, height queries, and adjacency computation. This is needed for area walkability analysis.

### 2.10 Low: No UTC/UTI/UTP Inspector
`getCreature`, `getNpc`, and `getBlueprint` return raw GFF field dumps. There is no structured inspector that resolves appearance.2da rows, race/class names, inventory items, etc. PyKotor's `UTC` class has all these parsed fields.

### 2.11 Low: GUI Has No Live NWScript Compilation
The script editor calls the bundled `nwnnsscomp.exe` on Windows. On Linux/macOS it either needs Wine or does nothing. There is no fallback to `InbuiltNCSCompiler` in the GUI layer.

### 2.12 Low: No Area Object Placement Editor
`getArea` returns a complete area dump but there is no GUI panel for placing/editing GIT instances (creatures, placeables, waypoints, triggers). This is a large gap vs. KotorTool and HolocronToolset.

---

## Section 3 — Reference Repos Scanned

All the following were scanned during our three-phase deep scan:

| Repo | Key files examined | Learnings applied |
|---|---|---|
| **PyKotor** | `installation.py`, `tools/registry.py`, `tools/path.py`, `formats/ncs/compilers.py`, `formats/ncs/decompiler.py`, `resource/generics/*.py`, `formats/gff/io_gff.py`, `formats/erf/erf_data.py`, `formats/bwm/bwm_data.py` | Auto-detect paths, registry keys, InbuiltNCSCompiler, HARDCODED_MODULE_NAMES, CaseAwarePath |
| **KotorMCP** | `server.py`, `SearchLocation` enum, `GFF_HEAVY_TYPES`, `_iter_candidate_paths`, `ENV_HINTS` | SearchLocation pattern, dedup candidate paths |
| **HolocronToolset** | `script_decompiler.py`, `SpoofKotorRegistry`, `IFOEditor`, `WAVEditor` | Decompiler strategy chain |
| **xoreos-tools** | `src/aurora/ncsdecomp.*`, `src/aurora/gff3file.cpp`, `src/aurora/gff3writer.cpp` | Xoreos fallback for decompile |

### 3.1 Features Found in PyKotor Not Yet in Our Program

| PyKotor Feature | Our Status | Priority |
|---|---|---|
| `InbuiltNCSCompiler` — Python-native NCS compile | Partially wired; broken without `pip install pykotor` | 🔴 High |
| `NCSDecompiler` — Python-native NCS decompile | Partially wired; broken without `pip install pykotor` | 🔴 High |
| `CaseAwarePath` — case-insensitive path resolution | Not integrated; case bugs on Linux/macOS | 🟡 Medium |
| `SaveFolderEntry` — save-game scanning | Not integrated; readSave requires raw path | 🟡 Medium |
| `BWM` — walkmesh AABB tree, raycast, height | Not exposed as MCP tool | 🟡 Medium |
| `UTC/UTI/UTP/UTD/UTS` structured parsing | GFF field dump only; no semantic resolving | 🟡 Medium |
| `GFF I/O` as main reader — delegate to PyKotor | Still using internal reader | 🟢 Low |
| `ERF/RIM/BIF/KEY` reader delegation | Still using internal reader | 🟢 Low |
| `LYT` room layout reader | readLYT not implemented as MCP tool | 🟢 Low |
| `MDL` binary reader (`formats/mdl/`) | GhostRigger has own parser; not MCP-exposed | 🟢 Low |
| `TPC` texture reader/exporter | Not MCP-exposed | 🟢 Low |

---

## Section 4 — Version History

### v3.4.1 (2026-03-19) — Deep Scan Phase 3 + decompileScript
- ✅ `decompileScript` tool (#59): three-strategy chain (PyKotor decompile → PyKotor disassemble → Xoreos CLI)
- ✅ `HARDCODED_MODULE_NAMES` dict: 70 entries from PyKotor + K2 entries
- ✅ `moduleOverview` + `getArea` use `HARDCODED_MODULE_NAMES` as fallback
- ✅ Deep-scan Phase 3 documented: DLG (12 node fields), ERF (160-byte header), UTC (script hooks), JRL (quest/entry), BWM (AABB/raycast), Xoreos decompiler
- ✅ Test suite: **1449 passed, 1 skipped, 0 failures**

### v3.4.0 (2026-03-05) — Auto-Install Detection
- ✅ `_auto_load_installations()` called from server startup
- ✅ Expanded `_DEFAULT_PATHS` to 30+ locations (Flatpak, Aspyr, WSL, Amazon, macOS)
- ✅ Corrected Windows Registry keys from PyKotor's `KOTOR_REG_PATHS`
- ✅ `gsDetectInstallations` returns `loaded: bool` flag
- ✅ Deep scan Phase 1-2: PyKotor, KotorMCP, HolocronToolset

### v3.3.x — Core MCP Expansion
- ✅ `readNCS`, `readVIS`, `readIFO`, `readWAV`, `readTXI`, `pathfindRoute`
- ✅ PyKotor opportunistic routing (readNCS/readIFO delegate to PyKotor when installed)
- ✅ GFF helper consolidation; XY pathfinding mode

### v3.2 — Composite Tools + Phase 5
- ✅ `getArea`, `getModule`, `getCreature`, `getNpc`, `getQuest`, `getScript`
- ✅ `getEncounter`, `getTrigger`, `getWaypoint`, `getStore`, `getSound`
- ✅ `getBlueprint`, `readGUI`, `readSave`, `readNCS`, `readVIS`

---

## Section 5 — Prioritised Roadmap

### 🔴 P0 — Fix Now (Blocking Modders)

#### P0.1 — Fix APP_VERSION constant
**File**: `ghostscripter/core/constants.py`  
**Problem**: `APP_VERSION = "2.8.0"` — window title shows wrong version.  
**Fix**: Update to `"3.4.1"`.  
**Effort**: 5 minutes.

#### P0.2 — Add PyKotor to requirements.txt as a required dependency
**Problem**: `compileScript` and `decompileScript` silently degrade without it. The README lists it as optional, but both core features are broken without it.  
**Options**:
1. Make it required: `pykotor>=1.8.0` in requirements.txt.
2. Bundle the minimal NCS compiler/decompiler source inline (no external dep).
3. Ship a pre-compiled `nwnnsscomp` for each platform in `resources/`.  
**Recommended**: Option 1 + test on a fresh virtualenv.  
**Effort**: 1 hour (including CI test).

#### P0.3 — Add safe `args.get()` guards to all handlers
**Problem**: 8+ tools throw `KeyError` on missing/wrong argument names.  
**Files**: `handlers_query.py`, `handlers_composite.py`, `handlers_read.py`  
**Fix Pattern**:
```python
# BEFORE (crashes)
quest_id = args["questId"]

# AFTER (graceful)
quest_id = args.get("questId") or args.get("quest_id")
if not quest_id:
    return _err("getQuest: 'questId' is required.")
```
**Tools to fix**: `getQuest`, `getNpc`, `twoDALookup`, `moduleOverview`, `getModule`, `getBlueprint`, `readSave`, `nwscriptSignature`.  
**Effort**: 2 hours.

---

### 🟠 P1 — High Priority (Core Functionality)

#### P1.1 — Fix writePTH to emit real GFF binary
**Problem**: `writePTH` returns `"format": "PTH-JSON"` — the game cannot load it.  
**Solution**: Implement PTH GFF3 binary encoding using our existing `GFF3Writer` class.  
A PTH file is a standard GFF with a struct array of `{X: float, Y: float}` and a `Connections` list for each point. Our `GFF3Writer` supports all needed types.  
**Effort**: 4 hours.

#### P1.2 — Register getNWScriptDB as an MCP Tool
**Problem**: `getNWScriptDB` is referenced in tests but is not in `TOOLS`.  
**Fix**: Add tool definition to `tool_defs.py` and handler mapping to `__init__.py`.  
**Effort**: 1 hour.

#### P1.3 — Standardise Arg Names Across All Tool Schemas
**Current inconsistencies**:
- `moduleOverview` uses `moduleId` but callers expect `module`
- `getModule` uses `module_id` (snake_case) while all others use camelCase
- `getBlueprint` uses `type` (Python keyword collision) — rename to `restype`
- `readSave` uses `save_path` — add `save_index` alternative
- Some tools use `data_b64`, others use `data_base64`

**Decision needed**: Pick one convention (recommend camelCase for all, snake_case for internal Python only) and apply it consistently.  
**Effort**: 3 hours + test updates.

#### P1.4 — Make NWScript Compilation Work Cross-Platform
**Current state**: On Linux without Wine, `compileScript` fails.  
**Approach**:
1. `pip install pykotor` brings in `InbuiltNCSCompiler` — no Wine, no external binary.
2. If PyKotor is not installed, include bundled `nwnnsscomp` binaries for Linux/macOS ARM64.
3. GUI script editor should use the same strategy chain as the MCP tool.  
**Effort**: 8 hours.

#### P1.5 — writeOverride Without Live Installation
**Problem**: `writeOverride` requires knowing the game's Override path, which requires the installation to be loaded. Modders building files in a CI environment or for distribution cannot use it without a game copy present.  
**Solution**: Add an `output_dir` optional parameter that accepts a filesystem path. If no installation is loaded AND `output_dir` is provided, write there instead.  
**Effort**: 3 hours.

---

### 🟡 P2 — Medium Priority (Polish & Completeness)

#### P2.1 — Integrate CaseAwarePath for All File Lookups
**Problem**: On Linux/macOS, `chitin.key` ≠ `CHITIN.KEY`. File lookups silently fail.  
**Source**: PyKotor `tools/path.py` → `CaseAwarePath` class.  
**Effort**: 4 hours.

#### P2.2 — Structured UTC/UTI/UTP Inspector (getNpc / getBlueprint)
**Problem**: These tools return raw GFF field dumps with opaque integer IDs.  
**Solution**: Resolve appearance.2da rows, race/class names, item base types, and ability score labels in the response — same approach as `_get_npc` already partially does for `appearance_id`.  
**Effort**: 8 hours per resource type (UTC/UTI/UTP are highest priority).

#### P2.3 — readSave Auto-Scan
**Problem**: `readSave` requires a raw filesystem path. Modders don't know where save files are.  
**Solution**: Implement save-folder scanning (PyKotor `SaveFolderEntry` pattern). Return a list of saves with indices when `save_path` is omitted.  
**Effort**: 6 hours.

#### P2.4 — readBWM / readWOK MCP Tool
**Problem**: No walkmesh reader in the MCP server.  
**Solution**: Expose PyKotor's `BWM` class (or our own implementation) via MCP. Return walkable/unwalkable faces, AABB bounding box, vertex list, raycast results.  
**Effort**: 6 hours.

#### P2.5 — GUI: Cross-Platform Script Compilation
**Problem**: GUI script editor uses `nwnnsscomp.exe` + Wine fallback. No PyKotor path.  
**Solution**: Add `InbuiltNCSCompiler` fallback to `ScriptEditorWidget._compile()`.  
**Effort**: 3 hours.

#### P2.6 — GUI: Area Object Placement Panel
**Problem**: `getArea` returns all GIT objects but there's no GUI to view/edit them.  
**Solution**: Add a `GITEditorWidget` that shows creatures, placeables, waypoints, etc. on a 2D overhead map (room layout from LYT). Basic move/add/delete.  
**Effort**: 40+ hours (large feature).

#### P2.7 — Add readLYT MCP Tool
**Problem**: Room layout data is key to area composition, but `readLYT` is not an MCP tool.  
**Solution**: Parse `.lyt` ASCII format (already done inside `getArea`) and expose it directly.  
**Effort**: 3 hours.

---

### 🟢 P3 — Future / Nice-to-Have

#### P3.1 — Replace Internal GFF/DLG/ERF Readers with PyKotor I/O
**Current state**: We have our own `dlg_reader.py`, `gff_reader`, `erf_writer`. They work but are a maintenance burden.  
**Benefit**: PyKotor is battle-tested against hundreds of game files, including edge cases.  
**Risk**: API differences; need adapter layer.  
**Effort**: 20+ hours; recommend doing incrementally (GFF first).

#### P3.2 — GModular MCP Server / Event Bus (Port 7000)
**Status**: Architecturally designed, not built.  
**What it is**: A separate `ghostworks/event_bus.py` pub/sub server. GhostScripter publishes events (script_compiled, dlg_saved, area_changed); GhostRigger and GModular subscribe.  
**Effort**: 30+ hours.

#### P3.3 — TPC Texture Viewer (MCP + GUI)
**Problem**: TPC files are used for all KotOR textures but can't be inspected via MCP.  
**Solution**: Expose PyKotor's TPC reader + DXT decompressor via `readTPC` MCP tool.  
**Effort**: 6 hours.

#### P3.4 — MDL Binary Reader MCP Tool
**Problem**: GhostRigger has a fine MDL parser but it's not accessible via MCP.  
**Solution**: Expose as `readMDL` — return node list, mesh summary, animation list.  
**Effort**: 8 hours.

#### P3.5 — Batch Export Pipeline
**Problem**: Modders need to compile 20 scripts, pack them into a MOD, and deploy.  
**Solution**: `batchCompile` + `batchPack` MCP tools; a GUI pipeline wizard.  
**Effort**: 12 hours.

#### P3.6 — TSLPatcher / HoloPatcher Integration
**Problem**: KotOR mods are typically distributed as TSLPatcher self-installers.  
**Solution**: `exportTSLPatcher` MCP tool that generates `changes.ini` from a diff of 2DA/GFF files.  
**Effort**: 20+ hours.

#### P3.7 — K2/TSL Specific Features
Several K2 DLG fields (TSL emotion, facial animations, `NumReplies`) and UTC fields (Influence, Party member scripts) are not fully modelled. K2 has different appearance.2da columns.

---

## Section 6 — Test Coverage Snapshot

| Test file | Tests | Focus |
|---|---|---|
| `test_mcp_tools.py` | ~1300 | MCP tool registry, schema validation, handler responses |
| `test_dlg_roundtrip.py` | ~30 | DLG binary encode/decode |
| `test_gff_roundtrip.py` | ~25 | GFF binary encode/decode |
| `test_gff_writer.py` | ~20 | GFF3 field types |
| `test_kotor_formats.py` | ~20 | ERF, TwoDA, LIP, SSF, PTH |
| `test_compiler.py` | ~15 | NWScript compile/summary |
| `test_journal_editor.py` | ~10 | JRL parse/edit |
| `test_2da_editor.py` | ~10 | 2DA edit/export |
| Other test files | ~20 | IPC, bug fixes, parser robustness |

**Total**: 1449 passed, 1 skipped (TestGetFaction.test_valid_fac_parsed — needs game file).

**Coverage gap**: No tests exercise the Qt GUI widgets (dialogue editor, script editor, etc.). No tests exercise GhostRigger's MDL parser or viewport against real MDL files.

---

## Section 7 — What a Modder Should Do Today

### Using the MCP server with an AI agent (e.g. Claude, Cursor)

1. Install: `pip install -r requirements.txt`
2. Optionally: `pip install pykotor` (enables compile/decompile)
3. Set your game path: `export K1_PATH=/path/to/KOTOR1` (or let auto-detect find it)
4. Run: `python -m ghostscripter.mcp`
5. Connect your AI agent in stdio mode

**Works out of the box**: NWScript lookup, GFF/DLG/2DA/SSF/LIP write, compileSummary  
**Needs game path**: readGFF, readDLG, getArea, getCreature, twoDALookup (and all other read tools)  
**Needs PyKotor**: compileScript, decompileScript  

### Using the Qt GUI

1. `pip install -r requirements.txt`
2. `python -m ghostscripter`
3. Set game directory via File → Set Game Directory
4. Open/create a project

**Works fully**: Script editor, dialogue editor, 2DA manager, ERF packer  
**Partially works**: Asset library (needs game dir), TLK editor (read-only confirmed)  
**Not yet in GUI**: Area object placement, NPC inspector with resolved stats

---

## Section 8 — Sprint Planning

### Sprint 1 (v3.5) — "Make It Just Work" — ~2 weeks
- [ ] P0.1 Fix APP_VERSION to 3.4.1
- [ ] P0.2 Add pykotor to requirements.txt (or bundle compiler)
- [ ] P0.3 Add safe `args.get()` guards to all 8 broken handlers
- [ ] P1.1 Fix writePTH to emit real GFF binary
- [ ] P1.2 Register getNWScriptDB as MCP tool
- [ ] P1.3 Standardise arg names (pick camelCase, deprecate snake_case aliases)
- [ ] P2.5 Add InbuiltNCSCompiler fallback in GUI script editor

### Sprint 2 (v3.6) — "Deployment & Discovery" — ~3 weeks
- [ ] P1.4 Cross-platform NWScript compilation (Linux/macOS native)
- [ ] P1.5 writeOverride with output_dir fallback
- [ ] P2.1 CaseAwarePath integration
- [ ] P2.3 readSave auto-scan
- [ ] P2.4 readBWM MCP tool
- [ ] P2.7 readLYT MCP tool

### Sprint 3 (v4.0) — "Inspector & Placement" — ~6 weeks
- [ ] P2.2 UTC/UTI/UTP structured inspector
- [ ] P2.6 GITEditorWidget (area object placement GUI)
- [ ] P3.1 Replace internal GFF reader with PyKotor I/O
- [ ] P3.3 readTPC MCP tool
- [ ] P3.4 readMDL MCP tool

### Sprint 4 (v4.5) — "Pipeline & Distribution" — ~6 weeks
- [ ] P3.2 GModular event bus on port 7000
- [ ] P3.5 Batch export pipeline (batchCompile, batchPack)
- [ ] P3.6 TSLPatcher/HoloPatcher export
- [ ] P3.7 K2/TSL specific field coverage

---

## Appendix A — All 59 MCP Tools: Current Status

| # | Tool | Needs Install | Works Without PyKotor | Notes |
|---|---|---|---|---|
| 1 | gsDetectInstallations | No | ✅ | Returns empty list if not found |
| 2 | gsLoadInstallation | Yes | ✅ | Manual path override |
| 3 | gsListResources | Yes | ✅ | |
| 4 | gsDescribeResource | Yes | ✅ | |
| 5 | readGFF | Yes | ✅ | Internal reader |
| 6 | readDLG | Yes | ✅ | Internal reader |
| 7 | readTwoDA | Yes | ✅ | |
| 8 | readTLK | Yes | ✅ | |
| 9 | readJournal | Yes | ✅ | |
| 10 | searchNWScript | No | ✅ | Bundled DB |
| 11 | nwscriptSignature | No | ✅ | ⚠️ KeyError if arg missing |
| 12 | writeGFF | No | ✅ | |
| 13 | journalOverview | Yes | ✅ | |
| 14 | writeDLG | No | ✅ | |
| 15 | writeTwoDA | No | ✅ | |
| 16 | writeERF | No | ✅ | |
| 17 | compileScript | No | ❌ | Needs PyKotor or Wine+exe |
| 18 | writeOverride | Yes | ✅ | Needs loaded installation |
| 19 | compileSummary | No | ✅ | Static analysis only |
| 20 | searchResources | Yes | ✅ | |
| 21 | moduleOverview | Yes | ✅ | ⚠️ KeyError on wrong arg name |
| 22 | twoDALookup | Yes | ✅ | ⚠️ KeyError on wrong arg name |
| 23 | nwscriptCategories | No | ✅ | |
| 24 | twoDAChangesINI | No | ✅ | |
| 25 | getResource | Yes | ✅ | |
| 26 | getQuest | Yes | ✅ | ⚠️ KeyError on wrong arg name |
| 27 | getNpc | Yes | ✅ | ⚠️ KeyError on wrong arg name |
| 28 | getScript | Yes | ✅ | |
| 29 | listResType | Yes | ✅ | |
| 30 | getArea | Yes | ✅ | |
| 31 | getDoor | Yes | ✅ | |
| 32 | getPlaceable | Yes | ✅ | |
| 33 | getItem | Yes | ✅ | |
| 34 | searchAll | Yes | ✅ | |
| 35 | getModule | Yes | ✅ | ⚠️ `module_id` vs `module` |
| 36 | getEncounter | Yes | ✅ | |
| 37 | getTrigger | Yes | ✅ | |
| 38 | getWaypoint | Yes | ✅ | |
| 39 | getStore | Yes | ✅ | |
| 40 | getSound | Yes | ✅ | |
| 41 | readSSF | Yes | ✅ | |
| 42 | readLIP | Yes | ✅ | |
| 43 | writeLIP | No | ✅ | Requires `keyframes` not `phonemes` |
| 44 | getCreature | Yes | ✅ | |
| 45 | getFaction | Yes | ✅ | |
| 46 | readPTH | Yes | ✅ | |
| 47 | readLTR | Yes | ✅ | |
| 48 | writeSSF | No | ✅ | |
| 49 | writePTH | No | ⚠️ | Returns JSON stub, not binary |
| 50 | getBlueprint | Yes | ✅ | ⚠️ `type` vs `restype` confusion |
| 51 | readGUI | Yes | ✅ | |
| 52 | readSave | No | ✅ | Requires raw `save_path` |
| 53 | readNCS | Yes | ✅ | PyKotor optional upgrade |
| 54 | readVIS | Yes | ✅ | |
| 55 | readIFO | Yes | ✅ | PyKotor optional upgrade |
| 56 | readWAV | Yes | ✅ | |
| 57 | readTXI | Yes | ✅ | |
| 58 | pathfindRoute | Yes | ✅ | |
| 59 | decompileScript | No | ❌ | Needs PyKotor or Xoreos CLI |

**Missing from TOOLS**: `getNWScriptDB` (handler exists, not registered)

---

*Roadmap written after full source audit of: GhostScripter-K1-K2, GhostRigger-K1-K2, PyKotor reference, KotorMCP reference, HolocronToolset reference.*  
*Next review: after Sprint 1 (v3.5) completion.*
