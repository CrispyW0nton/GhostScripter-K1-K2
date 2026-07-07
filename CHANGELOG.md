# Changelog — GhostScripter-K1-K2

All notable changes, newest first. The README's [What's New](README.md#whats-new)
section carries only the latest release; full history lives here.

### v3.6.1 — Format-correctness audit: ERF ResTypes · JRL EntryList · cp1252 · MCP server harness · 1422 tests

Cross-checked GhostScripter's binary writers against PyKotor 2.3.12, retail
K1 game data (module RIMs, `global.jrl`, `dialog.tlk`, `appearance.2da`),
and the conventions used by known-good community tools (KotOR Tool,
DLGEditor, TSLPatcher, HolocronToolset).

| Change | Detail |
|--------|--------|
| **MCP server harness restored** | `ghostscripter/mcp/server.py` was missing from the repo, so `python -m ghostscripter.mcp` crashed on import. Recreated with stdio (default), `--mode http`, and `--mode sse` transports; verified with a live MCP handshake listing all 60 tools. |
| **ERF resource-type table fixed** | 40 type IDs in `erf_writer.RESTYPE_IDS` were off by one (`.utp` 2045→2044, `.utm` 2052→2051, `.uts` 2036→2035, `.utw` 2059→2058, `.jrl` 2057→2056, `.ssf` 2061→2060, `.fac` 2039→2038, `.mdx` 3009→3008, `.tpc` 3008→3007, …). Verified against PyKotor's `ResourceType` enum **and** the type IDs in retail `danm13_s.rim`. ERF/MOD archives containing placeables, doors, merchants, sounds, waypoints, journals, or soundsets were previously mistyped and unreadable by the game and by ERF tools. |
| **Duplicate ResType tables consolidated** | `dlg_writer.ERFWriter.RESTYPE_MAP` (same off-by-one bugs) and the GUI ERF packer's display table (`.utc` mapped to GIT's ID, `.wav` to LIP's, `.lip` to a nonexistent 4014, …) now both derive from the single verified table in `erf_writer.py`. |
| **JRL journals now game-compatible** | The writer emitted the entries list under the label `Entries`; the game reads `EntryList` (verified against retail `global.jrl`) — journals written by GhostScripter showed zero entries in-game, and the importer read zero entries from real game journals. `End` is now written as WORD (UInt16) to match retail files instead of BYTE. Importer reads `EntryList` with an `Entries` fallback for old GhostScripter files. Verified: `global.jrl` imports 101 categories / 643 entries and round-trips through PyKotor's JRL reader. |
| **CExoLocString encoding fixed** | Localized substrings were written as UTF-8; the game (and DLGEditor/TSLPatcher) read windows-1252. Non-ASCII dialogue text (é, ü, …) showed as mojibake in-game. Both CExoString and CExoLocString now encode cp1252. |
| **ORIENTATION field order** | GFF Orientation quaternions are now stored on disk as X,Y,Z,W (the PyKotor/HolocronToolset `Vector4` convention used by working GIT cameras) instead of W,X,Y,Z. The `add_orientation(w, x, y, z)` API is unchanged. |
| **Polish TLK codepage** | Language 5 (Polish) now maps to cp1250 (Central European) instead of cp1252, matching PyKotor. |
| **requirements.txt completed** | Added `mcp`, `uvicorn` (HTTP/SSE transports), `networkx` (dialogue graph analysis), and `Pillow` (TGA texture preview) — all previously imported by shipped features but missing from the manifest, so a fresh `pip install -r requirements.txt` produced import errors. |
| **Test-suite isolation** | Two tests assumed no game installation and, when auto-detect found a real one, wrote `test.ncs` into the user's actual `Override/` folder. Auto-detection is now mocked in those tests. Also fixed a hardcoded `/home/user/webapp` cwd in the qtpy-migration test and updated tests that pinned the old (incorrect) ResType/codepage/orientation values. |
| **LICENSE.md added** | The GPL-3.0 badge linked to a file that didn't exist. |
| **1422 tests** | 0 failures, 65 skipped |

### v3.6.0 — PyKotor Integration · getNWScriptDB · Real writePTH · GUI Compiler · 1444 tests

All blocking issues from the v3.5.0 audit resolved. GhostScripter is now shippable.

| Change | Detail |
|--------|--------|
| **PyKotor is now a required dependency** | Moved `pykotor>=2.3.0` from optional → `requirements.txt`. `compileScript` and `decompileScript` work out-of-the-box on any platform with no external binaries. |
| **`writePTH` produces real GFF V3.2 binary** | Replaced the JSON stub with a full GFF binary encoder using `GFF3Writer`. The output is directly loadable by the game. |
| **GUI `⚙ Compile → NCS` uses PyKotor first** | Script editor now tries `InbuiltNCSCompiler` (pure-Python, no Wine) before falling back to `nwnnsscomp`. Works on Linux/macOS without Wine. |
| **`getNWScriptDB` tool (#60)** | New MCP tool returns the full NWScript function + constant database (K1: 772 functions, 1489 constants). Works without a game installation. |
| **All test failures fixed** | 12 tests that broke due to PyKotor being installed (compile, PTH format, readIFO deep mocking, registry mismatch) all fixed. |
| **1444 tests** | 0 failures, 6 skipped |

> **Remaining gaps** (see ROADMAP.md): `writeOverride` requires a loaded game installation; GhostRigger IPC is one-way (GhostScripter polls, never launches GhostRigger).

### v3.5.0 — Audit & Hardening · Graceful Errors · Version Fix · 1449 tests

Full source-code audit against PyKotor, KotorMCP, and xoreos-tools. All findings documented in ROADMAP.md.

| Change | Detail |
|--------|--------|
| **Version fix** | `APP_VERSION` constant corrected to `3.5.0` (was stuck at `2.8.0`; window title now shows the right version) |
| **Graceful error handling** | 8 handlers that previously threw `KeyError` on missing args now return helpful JSON error messages: `nwscriptSignature`, `getQuest`, `getNpc`, `twoDALookup`, `moduleOverview`, `getModule`, `getBlueprint`, `twoDALookup` |
| **Arg-name aliases** | Added forgiving aliases: `moduleOverview` now accepts `module`, `module_id`, or `moduleId`; `getModule` accepts `module` or `module_id`; `twoDALookup` accepts `table` as alias for `resref`; `getQuest` accepts `quest_id` or `tag` |
| **`nwscriptSignature` guard** | Now returns `"'functionName' is required."` instead of crashing if the arg is omitted |
| **Full audit completed** | All 59 MCP tools, all 10 GUI widgets, GhostRigger MDL pipeline, all reference repos (PyKotor, KotorMCP, HolocronToolset). Findings in `ROADMAP.md §Section 2` |
| **1449 tests** | 0 failures, 1 skipped (unchanged) |

> **v3.5.0 known gaps** (all fixed in v3.6.0): `compileScript`/`decompileScript` required `pip install pykotor`; `writePTH` returned a JSON stub (not real binary).

### v3.4.1 — decompileScript · HARDCODED_MODULE_NAMES · Deep-scan Phase 3 · 1449 tests

| Change | Detail |
|--------|--------|
| **`decompileScript` tool (#59)** | New MCP tool decompiles KotOR NCS binaries back to NWScript (.nss) source. Strategy chain: (1) PyKotor `decompile_ncs()` for full source; (2) `disassemble_ncs()` for instruction listing; (3) xoreos `ncsdecomp` CLI fallback. Accepts `data_base64` (bytes from `compileScript`/`readNCS`) or `resref` (installation lookup). Returns `nss_source`, `method`, `disassembly`, `size_bytes`. |
| **`HARDCODED_MODULE_NAMES`** | 70-entry hardcoded map of KotOR module stems → human-readable area names (K1 + K2/TSL). Added to `_helpers.py`; both `moduleOverview` and `getArea` now fall back to it when the `.are` GFF has no parseable Name field. |
| **Deep-scan Phase 3** | Scanned: DLG node fields (12 attributes per node incl. camera/fade/VO); ERF V1.0 binary layout (160-byte header, 24-byte key entries); UTC creature template (12 script hooks, ItemList/SpellList, CSWSCreature addresses); JRL journal GFF (JRLQuest/JRLEntry); BWM walkmesh APIs (raycast, get_height_at, find_face_at, AABB tree); xoreos `ncsdecomp.cpp`/`ncsdis.cpp` reference; GFF ResourceType enum (247+ entries). |
| **1449 tests** | 0 failures, 1 skipped (+8 new `TestDecompileScript`) |

### v3.4.0 — Auto-installation detection · Deep scan sprint · 498 tests

| Change | Detail |
|--------|--------|
| **Auto-link on startup** | The MCP server now automatically detects your KotOR installation at launch — no manual `gsLoadInstallation` call required. Probes: env vars → Windows Registry → 30+ default install paths across Steam, GOG, LucasArts disc, Amazon, Epic, Xbox Game Pass, macOS App bundles, Flatpak, Proton, WSL. |
| **Expanded path list** | Added Flatpak Steam, Aspyr K2 port (`~/.local/share/aspyr-media/kotor2`), macOS `.app/Contents/Assets` bundles, WSL `/mnt/c/*`, Amazon Games Store, Debian-installation Steam paths — sourced from PyKotor's `get_default_paths()`. |
| **Fixed Windows Registry** | Registry keys now match PyKotor's authoritative KOTOR_REG_PATHS table: Steam App IDs 32370/208580 (`InstallLocation`), GOG IDs 1207666283/1421404581 (`PATH`), `BioWare\SW\KOTOR` (`InternalPath`/`Path`), `LucasArts\KotOR2` — both 32-bit and WOW6432Node variants. |
| **`gsDetectInstallations` enhanced** | Each game now reports `{candidates: [...], loaded: bool}` — agents see at a glance whether the game is ready without calling an extra tool. |
| **v3.4 Deep Scan** | Scanned PyKotor (`installation.py`, `tools/registry.py`, `tools/path.py`, `formats/ncs/compilers.py`), KotorMCP (`SearchLocation` enum, `GFF_HEAVY_TYPES` filter, `_iter_candidate_paths` dedup, `ENV_HINTS` multi-alias), and HolocronToolset (`InbuiltNCSCompiler` + `SpoofKotorRegistry` cross-platform NCS compile pattern). Findings documented in `ROADMAP.md §v3.4 Deep Scan`. |
| **498 tests** | 0 failures, 1 skipped |

### v3.3.1 — GFF helper refactor · XY pathfinding · PyKotor routing · 498 tests

| Change | Detail |
|--------|--------|
| **GFF helper consolidation** | Extracted `gff_scalar`, `gff_locstr`, `gff_resref`, `gff_int`, `gff_float`, `gff_list`, `gff_struct_fields` into `_helpers.py`; removed 17+ inline `_v`/`_locstr`/`_vs`/`_vr` closure defs from all handler files |
| **`pathfindRoute` XY mode** | Now accepts `start_x`/`start_y`/`end_x`/`end_y` float coords in addition to integer node indices; `find_nearest_node` snaps coordinates to the closest PTH node; schema updated to mark only `game`+`resref` as required |
| **PyKotor opportunistic routing** | `readNCS` and `readIFO` attempt to delegate to PyKotor readers when installed, falling back to the internal disassembler/GFFService transparently |
| **Test suite depth** | 13 new `readNCS` instruction-level tests; 10 new `readIFO` positive-path tests; 9 new `pathfindRoute` XY-mode tests; `TestGFFHelpers` covers all 7 shared utilities |
| **Snapshot deduplication** | Collapsed 4 duplicate `assertEqual(len(TOOLS), 58)` assertions in historical test classes to `assertGreaterEqual`; single canonical count test lives in `TestV33Additions` |
| **498 tests** | 0 failures, 1 skipped |

### v3.3.0 — `readNCS`/`readVIS`/`readIFO`/`readWAV`/`readTXI`/`pathfindRoute` · Deep scan sprint · 438 tests

| Change | Detail |
|--------|--------|
| **+6 MCP tools** | `readNCS`, `readVIS`, `readIFO`, `readWAV`, `readTXI`, `pathfindRoute` |
| **58 tools total** | was 52 in v3.2; +6 this sprint |
| **438 tests** | 0 failures (test suite restructured from 1329 in v3.2) |
| `readNCS` | Disassemble KotOR NCS (compiled NWScript) binary: file header, instruction count, byte size, and up to 256 instructions with opcode/qualifier/mnemonic/args. Full NCSByteCode opcode table from PyKotor. |
| `readVIS` | Read KotOR VIS (visibility/occlusion) ASCII file: room_count and per-room visible_rooms dict. Used for occlusion-culling; room adjacency graph for AI agents. |
| `readIFO` | Dedicated IFO (module info GFF) composite reader: mod_name, tag, entry area/XYZ/direction, area list, all 14 Mod_On* script hooks (heartbeat → user_defined). |
| `readWAV` | KotOR audio metadata without full decoding: format (wav/mp3/ogg), obfuscation type (riff/sfx/vo), sample_rate, channels, bits_per_sample, duration_ms. Also accepts raw base64. |
| `readTXI` | Read TXI (texture info) ASCII metadata: all key/value pairs (blending, mipmap, envmap, bump, cube, procedural, font dims, flipbook count). Numeric values auto-converted. |
| `pathfindRoute` | A\* shortest route on KotOR PTH path-node graph: given start_index and end_index, returns path (node index list), step_count, total Euclidean distance, waypoints {x,y}. |
| Deep scan | Scanned **xoreos-tools** (ncsdis, ncsdecomp — NCS opcode table cross-referenced), **PyKotor NCS/VIS/WAV/TXI/pathfinding** modules, **HolocronToolset** WAVEditor + IFOEditor + script_decompiler. |
| Feature parity | NCS ✅, VIS ✅, IFO ✅ (was 🟡), WAV ✅ (was 🟡), TXI ✅, savegame ✅ — 5 formats promoted to complete. |

### v3.2.0 — `readPTH`/`writePTH`/`readLTR`/`writeSSF`/`getBlueprint`/`readGUI`/`readSave` · 41 new tests

| Change | Detail |
|--------|--------|
| **+7 MCP tools** | `readPTH`, `writePTH`, `readLTR`, `writeSSF`, `getBlueprint`, `readGUI`, `readSave` |
| **52 tools total** | was 45 in v3.1 |
| `readPTH` | Decode KotOR PTH (pathfinding) GFF: returns `point_count`, `connection_count`, and a `points` list `{x, y, connections: [int,…]}`. |
| `writePTH` | Encode a PTH path-node graph from `{x, y, connections}` list. JSON descriptor. |
| `readLTR` | Decode KotOR LTR (Markov chain name-generator) binary: top-5 start/end letter probabilities. |
| `writeSSF` | Encode KotOR SSF V1.1 binary from slot→StrRef mapping. All 28 sound-event slots. |
| `getBlueprint` | Universal GFF blueprint reader for all 9 blueprint types (utc/uti/utp/utd/ute/utm/uts/utt/utw). |
| `readGUI` | Decode any KotOR `.gui` GFF: full control tree with GUIControlType, alignment, position/size. |
| `readSave` | Decode KotOR save-game folder: player_name, area_name, game_time, module snapshots. |
| `getArea` enriched | Cameras, weather state, full ARE ambient/fog/grass/shadow fields. |

### v3.1.0 — LIP GUI editor · `getModule` GIT snapshots · Qt Designer stubs · 58 new tests

| Change | Detail |
|--------|--------|
| **45 tools total** | unchanged — improvements to existing tools |
| **1,288 tests** | 0 failures (+58 since v3.0) |
| `LIPEditorWidget` | Full visual GUI for `.lip` files: keyframe table, colour-coded timeline canvas (16 mouth shapes), shape legend, phoneme→shape map, binary V1.0 encode/decode, open/save dialogs. Matches PyKotor `LIPShape` enum exactly. |
| `getModule` snapshot | New `include_git` parameter (default `false`): adds `area_summaries` list with per-area GIT instance counts (creatures, doors, placeables, waypoints, triggers, stores, sounds, encounters). Useful for module maps and placement audits. |
| Qt Designer stubs | `ghostscripter/ui/ui_files/new_project_dialog.ui` and `new_quest_dialog.ui` created. Both dialogs try `.ui` first, fall back to Python layout — identical public API either way. |
| Tests | 8 LIPEditorWidget constant tests, 6 getModule schema tests, 8 dialog loader tests, 4 lip import tests, 32 lip binary + API tests |

### v3.0.0 — `getFaction` · gs-prefixed tools · PyKotor shim · 31 new tests

| Change | Detail |
|--------|--------|
| **+1 MCP tool** | `getFaction` |
| **45 tools total** | was 44 in v2.9 |
| **1,230 tests** | 0 failures (+31 since v2.9) |
| `getFaction` | Decode KotOR faction tables (FAC GFF): faction names, reputation matrix (0–100 per faction pair). Defaults to `repute.fac`; accepts any custom resref. |
| Tool namespace fix | `detectInstallations`, `loadInstallation`, `listResources`, `describeResource` renamed to `gsDetect*`/`gsLoad*`/`gsListResources`/`gsDescribeResource` to avoid KotorMCP collisions. Legacy names kept as callable aliases until v3.2. |
| PyKotor shim | `ghostscripter/core/pykotor_shim.py` — `ShimInstallation` wraps our ResourceManager behind the pykotor `Installation` API. Transparently upgrades to real pykotor when installed. |
| Tests | 16 new shim tests, 10 getFaction tests, 5 v3.0 suite tests |

### v2.9.0 — `readLIP` · `writeLIP` · `getCreature` · qtpy migration · 36 new tests

| Change | Detail |
|--------|--------|
| **+3 MCP tools** | `readLIP`, `writeLIP`, `getCreature` |
| **44 tools total** | was 41 in v2.8 |
| **1,199 tests** | 0 failures (+36 since v2.8) |
| **qtpy compatibility layer** | All 17 UI files migrated from bare `PyQt5` → `qtpy`; swap backend to PyQt6/PySide6 by changing one `pip install` |
| `readLIP` | Decode KotOR lip-sync files (LIP V1.0): duration, keyframe count, each frame's time + mouth-shape name (NEUTRAL/EE/EH/AH/OH/OOH/Y/STS/FV/NG/TH/MPB/TD/SH/L/KG) |
| `writeLIP` | Encode LIP V1.0 binary from keyframe list — accepts shape integers 0-15 or string names; validates ascending order; returns base64 for writeOverride |
| `getCreature` | UTC blueprint composite: tag, localized name, race/subrace/gender, class+level pairs, all 6 ability scores, HP/AC, appearance row, faction, conversation, equipment list, feats, skill ranks, all script fields |
| Python 3.10 type hints | Migrated `Optional[X]` → `X \| None` and `Union[X, Y]` → `X \| Y` across 29 source files |
| Port registry hardening | `ghostrigger_bridge.py` IPCCallbackServer now defaults to `GHOSTSCRIPTER_REST` from ports.py (was a hardcoded literal) |

### v2.8.0 — 7 new blueprint tools · path-safety · 55 new tests

| Change | Detail |
|--------|--------|
| **+7 MCP tools** | `getModule`, `getEncounter`, `getTrigger`, `getWaypoint`, `getStore`, `getSound`, `readSSF` |
| **41 tools total** | was 34 in v2.7 |
| **1,163 tests** | 0 failures (+55 since v2.7) |
| `getModule` | IFO snapshot: mod name, tag, entry area/XYZ, area list, all `Mod_On*` scripts |
| `getEncounter` | UTE: tag, active, difficulty, faction, spawn list (resref + CR + single-spawn), scripts |
| `getTrigger` | UTT: tag, trap type, one-shot, linked object, trap props, scripts |
| `getWaypoint` | UTW: tag, localized name, XYZ, orientation, map note |
| `getStore` | UTM: tag, name, markup/markdown %, inventory list, OnOpenStore script |
| `getSound` | UTS: tag, active/loop flags, volume, distances, XYZ, sound resref list |
| `readSSF` | 28-slot SSF decoder: canonical slot names + StrRef + optional TLK text |
| Path-safety | `_safe_write_path` blocks traversal characters; all write tools hardened |
| All 41 descriptions | Audited for context-free wording (no implicit "you" subject) |

### v2.7.0 — `getDoor` · `getPlaceable` · `getItem` · `searchAll` · tools_pkg refactor

| Change | Detail |
|--------|--------|
| **+4 MCP tools** | `getDoor`, `getPlaceable`, `getItem`, `searchAll` |
| **34 tools total** | was 30 in v2.6 |
| `getDoor` | UTD: tag, lock/trap props, script fields, conversation resref |
| `getPlaceable` | UTP: tag, appearance, lock/trap, inventory list, scripts |
| `getItem` | UTI: base item, cost, properties list, TLK-resolved name + description |
| `searchAll` | Unified search across 2DA + TLK + NSS + DLG; scopes + limit params |
| `tools_pkg` refactor | 2,500-line `tools.py` split into focused sub-modules |
| Port registry | `ghostscripter/ipc/ports.py` — canonical port constants for all pipeline tools |

---

### v2.2.0 — Composite Game-Object Tools + Ghostworks Pipeline

**5 new context-free composite tools (Yourdon/Constantine functional cohesion)**
- `getResource` — retrieve any KotOR resource by `resref` + `type`; resolves format internally (2da, dlg, utc, nss, ncs, tlk, jrl, …)
- `getQuest` — composite quest view: JRL entry + all states with TLK text + associated scripts + DLG references
- `getNpc` — composite NPC view: UTC fields + appearance.2da row + dialogue summary + faction
- `getScript` — script source (`.nss`) or decompiled NCS + static analysis from `compileSummary`
- `listResType` — paginated resource list filtered by type with optional name pattern
- AI agents can now ask "what does quest k_swg_dxn_main do?" without knowing KotOR binary formats
- Full Ghostworks Pipeline documentation: GhostScripter + GModular + GhostRigger IPC port registry
- Systems design analysis applied from Yourdon/Constantine *Structured Design*: coupling, cohesion, transform analysis, transaction analysis
- `SYSTEMS_DESIGN.md` — comprehensive gap analysis and architecture roadmap for all three pipeline tools
- 1163 tests pass (15 new composite-tool tests, 0 warnings)

---

### v2.0.0 — MCP Server + Architecture Refactor

**MCP Server (27 tools)**
- Full [Model Context Protocol](https://modelcontextprotocol.io/) server — connect Claude Desktop, Cursor, VS Code Copilot, or any MCP-compatible AI agent directly to your KotOR installation
- Three transport modes: `stdio` (Claude Desktop), `http` (Cursor/web agents), `SSE` (legacy clients)
- 27 tools covering installation detection, resource reading, GFF/DLG/2DA writing, NWScript lookup, static analysis, TSLPatcher patch generation

**Architecture Refactor (Khononov coupling principles)**
- New `ghostscripter/core/ports/` — 8 abstract Protocol interfaces (hexagonal architecture / ports-and-adapters)
- New `ghostscripter/core/services/` — 6 service classes replacing all direct subsystem coupling in the MCP layer
- New `ghostscripter/core/models/tlk.py` — `TLKFile`/`TLKEntry` extracted from UI into a pure-Python core model
- `tlk_editor_widget.py` now re-exports `TLKFile` from core; UI has zero parsing logic
- 38 architecture guard tests enforce coupling rules; any regression fails CI

**Bug Fixes**
- `ResourceManager.list_by_type()` — `EXT_RESTYPE` keys are dot-prefixed (`.2da`, `.nss`); the old lookup stripped the dot, silently returning 0 entries from BIF archives. Now correctly finds all 209 `.2da`, 1774 `.nss`, and 32 `.dlg` files
- `TwoDAService.get_cell()` — label lookup compared against the wrong field (`row.label` = numeric index instead of `row.data['label']`); always returned `None` for string labels
- `ResourceManager.load_game()` — override-only mode (no `chitin.key`) now succeeds and returns `True`; workspace folders and flat override directories work without a full game install
- `ERFWriter` — added `add_resource()` and `build()` convenience methods so callers never need to touch `ExportEntry` or `write()` directly
- `compileSummary` — two new static-analysis checks: (1) `int oXxx` parameter type heuristic warns when an `o`-prefixed name is declared as `int` instead of `object`; (2) ResRef length check warns when string literals passed to `ExecuteScript` / `ActionStartConversation` exceed KotOR's 16-char limit
- `DLGExporter` — now logs a `WARNING` when `script1`/`script2` names exceed 16 characters before they are silently truncated
- `asyncio` deprecation — test helper `_run()` replaced `get_event_loop().run_until_complete()` with `asyncio.run()`

**Tests**
- 1163 tests pass, 0 warnings (up from 825 before this version)
- Integration tests with real KotOR 1 game assets: `chitin.key` / BIF archives / RIM / TLK / 2DA / DLG round-trips
