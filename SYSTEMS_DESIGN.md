# Ghostworks Pipeline — Systems Design

> **Design/history document, not a retail-data authority.** Example globals,
> module IDs, payloads, and completed checkboxes illustrate intended flows. Use
> [AUDIT_REPORT.md](AUDIT_REPORT.md) for verified format behavior and provenance.

> Applied from: *Structured Design* by Edward Yourdon & Larry L. Constantine  
> The **Ghostworks Pipeline** is the "Unreal Engine of KotOR modding" — three tightly-integrated
> tools that together cover every step of the mod creation workflow.

---

## 0. Monorepo Context

GhostScripter-K1-K2 lives inside the **OldRepublicDevs/PyKotor** monorepo as a git
submodule at `Tools/GhostScripter-K1-K2`.  The monorepo also contains:

| Submodule path | Repo | Role |
|---|---|---|
| `Tools/KotorMCP` | OldRepublicDevs/KotorMCP | Canonical **read** MCP layer (built on pykotor) |
| `Tools/GhostScripter-K1-K2` | CrispyW0nton/GhostScripter-K1-K2 | IDE + **write** MCP layer |
| `Tools/GModular` | CrispyW0nton/GModular | World editor / module builder |
| `Tools/HolocronToolset` | OldRepublicDevs/HolocronToolset | Legacy GUI toolset (reference) |
| `Libraries/PyKotor` | OldRepublicDevs/PyKotor | Shared binary-format library |

### Division of responsibility between KotorMCP and GhostScripter MCP

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │  PyKotor Monorepo — MCP Layer                                          │
 │                                                                        │
 │   KotorMCP (Tools/KotorMCP)          GhostScripter MCP (this file)    │
 │   ────────────────────────────       ──────────────────────────────   │
 │   kotor_ prefix tool names           camelCase tool names              │
 │   read-only game data access         read + WRITE (writeDLG/writeGFF) │
 │   built on pykotor library           built on GhostScripter services   │
 │   stdio transport only               stdio primary; HTTP/SSE optional  │
 │   no GUI dependency                  IDE-integrated (PyQt5 GUI)        │
 │   walkmesh diagrams, refs, dlg desc  composite queries (getQuest etc.) │
 │   archive extraction                 NWScript compilation               │
 │                                      NWScript analysis & compilation   │
 │                                                                        │
 │  Shared: journalOverview (intentional), same game identifier (K1/K2)  │
 └────────────────────────────────────────────────────────────────────────┘
```

### Tool Namespace Policy

| Namespace | Prefix / style | Owner | Principle |
|---|---|---|---|
| KotorMCP read tools | `kotor_` snake_case | OldRepublicDevs/KotorMCP | pykotor-backed, read-only |
| GhostScripter tools | camelCase | CrispyW0nton/GhostScripter | IDE-integrated, read+write |
| Intentional overlaps | no prefix change | both | same schema, same semantics |

**Intentional overlaps** (present in both servers, identical schema):
- `journalOverview` — both servers expose this; KotorMCP is canonical for read-only
  workflows; GhostScripter's copy is kept for agent sessions that need write tools too.

**Naming decision record:**  When a tool name exists in KotorMCP with `kotor_` prefix,
GhostScripter should NOT duplicate it with a different name unless GhostScripter adds
meaningfully different behaviour (e.g. write-back, cross-resource
composition).  Avoid pure read-only duplicates; defer to KotorMCP + pykotor.

### Governance rules (from AGENTS.md)

- **Transport**: All MCP servers run over **stdio** by default.  HTTP/SSE is supported
  but must never bind to `0.0.0.0`; use `localhost` only.
- **Path safety**: Write tools use `pykotor.tools.path_safety` canonicalization (or an
  equivalent allowlist in GhostScripter's `core.export` module).
- **No unmanaged MCP servers**: Do not enable additional MCP servers outside the
  workspace-approved configuration.

---

## 1. The Three-Tool Pipeline

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
 │   MCP server (34 tools)    3D object placement GLTF/OBJ import       │
 │   Module packager          IPC bridges          MCP server (34 tools)│
 │   ERF/RIM/MOD packer       GhostRigger/GModular Write-back tooling    │
 │                                                                      │
 │   Port 7002 ◄─────────────────────────────────────────► Port 7001   │
 │                 IPC REST (Ghostworks event bus)                      │
 │                         Port 7003 (GModular CB)                      │
 └──────────────────────────────────────────────────────────────────────┘
```

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

---

## 2. Yourdon/Constantine Analysis

### 2.1 Current Coupling Assessment

Following Constantine's coupling hierarchy (data → stamp → control → external → common → content):

**Positive (low coupling — keep):**
- All three tools communicate over HTTP REST — maximum loose coupling between processes
- GhostScripter MCP tools communicate only through `core.services` (no internal imports)
- GhostRigger isolates pykotor in `adapters.py` (content coupling eliminated)
- GModular uses Qt signals between format library and GUI (no pathological coupling)

**Problems (high coupling — fix):**
- **Port hardcoding**: GS uses 7002, GR uses 7001, GM uses 7003 — but these are _not consistent_ across repos (GR README says 7001 is GR, GS README says 7002; GM uses different numbering). → Need canonical `GHOSTWORKS_PORTS` constants.
- **Duplicated format readers**: GFF reader exists independently in GhostScripter, GModular, AND GhostRigger. Three implementations of the same thing = logical coupling spread across a system boundary. → Should consolidate or make one canonical source.
- **State across MCP calls**: Each MCP server maintains an `_INSTALLS` dict, but these are isolated per-process. A model rendered in GhostRigger is invisible to GhostScripter. → Needs a shared state channel.
- **Tool name coupling to use-case**: `readDLG`, `compileSummary` — these names imply _what_ will be done, not _what data_ the tool accesses. This forces the AI to infer when to use each tool. → Context-free names.

### 2.2 Current Cohesion Assessment

**Strong cohesion (keep):**
- `DialogueService` — all methods serve one object type → **functional cohesion** ✓
- `TwoDAService` — all methods serve one format → **functional cohesion** ✓
- `AgDecBridge` — all methods serve one external API → **functional cohesion** ✓

**Weak cohesion (redesign):**
- `_compile_summary` in `tools.py` mixes: static analysis + token extraction + type heuristics + ResRef checking → **sequential cohesion** (should be three separate tools with functional cohesion each)
- `describeResource` tries to handle GFF + 2DA + TLK + DLG + binary → **logical cohesion** (same control flag selects entirely different behaviour)
- `readJournal` / `journalOverview` are duplicates → **coincidental cohesion** (two names for the same function)

### 2.3 Transform Analysis — Data Flow

The KotOR mod pipeline is a classic **transform-centered** design:

```
 Raw game data                Transform center               Mod output
 (chitin.key, BIF)  ──────►  GhostWorks pipeline  ──────►  Override/
                              (read → edit → write)          .mod file
                                                             TSLPatcher
```

**Afferent stream** (input branch):
```
chitin.key/BIF → ResourceManager → format readers → data models
```

**Transform center** (where the value is added):
```
data models → services (DialogueService, TwoDAService, etc.) → user edits
```

**Efferent stream** (output branch):
```
data models → format writers → Override/ → game loads mod
```

This means MCP tools should be structured around the **transforms**, not the file formats.

### 2.4 Transaction Analysis — Context Routing

The MCP server is a **transaction-centered** design: a single `handle_tool` dispatcher receives a tool name, analyzes its type, and routes it to one of many handlers. This is exactly the pattern Constantine describes for transaction analysis.

The current problem: **tool names encode the transaction type** (`readGFF`, `readDLG`, `readTwoDA`) rather than the **data object type** (`get_resource`). This creates:
- N-way duplication of similar read logic
- AI agents must know _which_ read function to call for which file type
- Adding a new format requires a new tool instead of extending an existing one

**Fix:** Single `get_resource(resref, type)` that resolves format internally.

---

## 3. Gap Analysis — What's Missing

### 3.1 Missing from GhostScripter MCP

| Gap | Impact | Priority |
|---|---|---|
| `get_resource` — unified resource accessor by resref+type | Forces AI to know file types; prevents generic queries | **Critical** |
| `get_quest` — composite quest view (JRL + scripts + DLG + 2DA) | AI can't answer "what does this quest do?" without 5 separate calls | **Critical** |
| `get_npc` — composite NPC view (UTC + appearance.2da + DLG + scripts) | Same — 4 separate calls for one entity | **High** |
| `get_area` — module area summary (ARE + GIT object inventory) | Needs GModular IPC or local RIM reader | **High** |
| `get_script` — script with decompiled NCS if available | `compileSummary` only works on .nss source, not compiled .ncs | **High** |
| `list` — unified resource listing with type/pattern filter | `listResources` exists but needs pagination and type hierarchy | **Medium** |
| `search` — cross-resource full text search | `searchResources` exists but doesn't cross JRL/TLK/DLG simultaneously | **Medium** |
| IPC: notify GModular when a script compiles | GModular file watcher exists but GS doesn't push | **Medium** |
| IPC: receive model updates from GhostRigger | Bridge polls but doesn't have a `/notify` endpoint on GS side | **Medium** |
| Discord bot context | Tools return raw JSON; no Markdown formatting mode | **Low** |

### 3.2 Missing from GModular

| Gap | Impact | Priority |
|---|---|---|
| DLG visual editor | Identified as planned — needed for full pipeline | **High** |
| NWScript compile (via GhostScripter IPC) | IPC bridge exists but compile trigger not wired | **High** |
| `get_module` MCP tool | GModular has no MCP server at all | **High** |
| Native `.wok` export (KotOR binary) | Currently exports GWOK for GhostRigger only | **Medium** |
| Animation playback | Controller data parsed, not played | **Low** |

### 3.3 Missing from GhostRigger

| Gap | Impact | Priority |
|---|---|---|
| `get_model` MCP tool | Exists as `ghostrigger_model_info` — name implies tool | **Low** (rename) |
| Supermodel texture loading | Models render untextured | **Medium** |

### 3.4 Missing from the Pipeline as a Whole

| Gap | Impact | Priority |
|---|---|---|
| **Unified event bus** (Ghostworks pub/sub) | Tools don't know when each other's state changes | **Critical** |
| **Canonical port registry** (one source of truth for 7001/7002/7003) | Port conflicts between repos | **High** |
| **Shared resource index** | Each tool re-reads chitin.key independently; no shared cache | **High** |
| **`GHOSTWORKS_BLUEPRINT.md`** as living spec | GS references it; GM references it; needs to be canonical | **High** |
| Batch export pipeline | GS has export; GM has packager; no unified "export mod as TSLPatcher package" | **Medium** |

---

## 4. Structured Design — New Tool Architecture

### 4.1 The Core Principle: Tools as Data-Object Accessors

Following Constantine's principle that **cohesive modules do one thing**: each MCP tool should return one type of **game object**, not perform one type of **file operation**.

```
❌ Current (file-operation naming — logical cohesion, context-dependent):
   readGFF, readDLG, readTwoDA, readTLK, readJournal, describeResource
   → AI must know: "is a quest in JRL? what format is UTC? what's a 2DA?"

✓ Target (data-object naming — functional cohesion, context-free):
   get_resource(resref, type)     → any game resource by name
   get_quest(quest_id)            → full quest composite (JRL + scripts + DLG)
   get_npc(tag_or_resref)         → full NPC composite (UTC + 2DA + DLG)
   get_area(module_id)            → area summary (ARE + GIT inventory)
   get_script(resref)             → script text + analysis + decompiled NCS
   list(type, pattern, limit)     → paginated resource listing
   search(query, types)           → cross-resource full-text search
```

The AI assistant in _any context_ (Discord bot, VS Code, Claude Desktop) can issue the same
calls without knowing KotOR internals. The tool resolves format internally.

### 4.2 Tool Cohesion Levels (target)

| Tool | Cohesion | Why |
|---|---|---|
| `get_resource` | **Functional** | One job: return resource bytes+text for any resref |
| `get_quest` | **Communicational** | All elements use the quest_id as shared data key |
| `get_npc` | **Communicational** | All elements use the npc tag/resref as shared key |
| `get_area` | **Communicational** | All elements describe the same game area |
| `get_script` | **Functional** | One job: return script in readable form |
| `list` | **Functional** | One job: enumerate resources matching a filter |
| `search` | **Sequential** | Search → rank → return results (pipeline) |
| `write_resource` | **Functional** | One job: persist a resource to override/ or return bytes |

### 4.3 Coupling Reduction Strategy

**Data coupling only** between MCP tools and services:
```python
# BAD (stamp coupling — passes entire ResourceManager):
result = DialogueService.load(rm, resref)  # rm has 50 methods, tool uses 1

# GOOD (data coupling — passes only the data needed):
resource_bytes = rm.read(resref + ".dlg")
result = DialogueService.from_bytes(resource_bytes)
```

**Event coupling** for IPC (replace polling with push):
```python
# BAD (current — polling every 8 seconds):
while True:
    resp = requests.get("http://localhost:7001/api/status")
    time.sleep(8)

# GOOD (event-driven — tools push events, subscribers react):
ghostworks_bus.publish("script.compiled", {"resref": "k_swg_01", "path": "/override/k_swg_01.ncs"})
ghostworks_bus.subscribe("script.compiled", lambda e: reload_module(e["resref"]))
```

### 4.4 Fan-Out and Module Hierarchy

Following Constantine's "7 ± 2 fan-out" rule, the new tool hierarchy:

```
handle_tool (dispatcher)
├── resource_tools (get_resource, list, search)
│   ├── _resolve_resource(resref, type)        ← format-agnostic lookup
│   ├── _format_for_context(data, context)     ← Markdown/JSON/plain-text
│   └── _resource_index                        ← shared index cache
│
├── composite_tools (get_quest, get_npc, get_area, get_script)
│   ├── _build_quest_composite(quest_id)
│   ├── _build_npc_composite(resref)
│   ├── _build_area_composite(module_id)
│   └── _decompile_script(resref)              ← NCS → NWScript via bridge
│
├── write_tools (write_resource, patch_2da, patch_tlk)
│   ├── _validate_resource(data, type)
│   └── _write_to_override(bytes, resref, type)
│
├── analysis_tools (analyze_script, analyze_binary, diff_2da)
│   ├── _static_analysis(source)
│   └── _binary_bridge → AgDecBridge
│
└── pipeline_tools (detect_game, load_game, module_info)
    └── _installation_cache
```

---

## 5. IPC Architecture — Unified Ghostworks Event Bus

### 5.1 Current IPC (polling model — problems)

```
GhostScripter :7002 ◄── poll ──► GhostRigger :7001
                     ◄── poll ──► GModular   :7003
```

Problems:
- 8-second latency between events (poll interval)
- Each tool independently manages connection state
- No shared event taxonomy
- Port numbers duplicated across three codebases

### 5.2 Target IPC (event-driven pub/sub)

```
                  ┌─────────────────────────────────┐
                  │  Ghostworks Event Bus  :7000     │
                  │  (lightweight HTTP pub/sub)      │
                  │                                  │
                  │  POST /publish  {topic, payload} │
                  │  GET  /subscribe?topics=...      │
                  │  GET  /events  (SSE stream)      │
                  └──────────┬──────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
  GhostScripter :7002   GModular :7003   GhostRigger :7001
   publishes:            publishes:        publishes:
   script.compiled       module.saved      model.exported
   script.opened         object.placed     rig.complete
   quest.saved           area.exported     model.updated
```

### 5.3 Canonical Ghostworks Event Taxonomy

| Topic | Publisher | Subscribers | Payload |
|---|---|---|---|
| `script.compiled` | GhostScripter | GModular (hot-reload) | `{resref, ncs_path, success, errors}` |
| `script.opened` | GhostScripter | GModular | `{resref, path}` |
| `dialogue.saved` | GhostScripter | GModular | `{resref, dlg_path}` |
| `quest.saved` | GhostScripter | — | `{quest_id, jrl_path}` |
| `module.saved` | GModular | GhostScripter | `{module_resref, git_path}` |
| `object.placed` | GModular | GhostScripter | `{tag, resref, type, position}` |
| `area.exported` | GModular | — | `{module_id, erf_path}` |
| `model.exported` | GhostRigger | GModular (hot-reload) | `{resref, mdl_path, mdx_path}` |
| `model.updated` | GhostRigger | GModular | `{resref, mdl_path}` |
| `rig.complete` | GhostRigger | GhostScripter (appearance 2DA) | `{resref, appearance_row}` |

### 5.4 Port Registry (single source of truth)

```python
# ghostworks/ports.py — imported by ALL three tools
GHOSTWORKS_PORTS = {
    "event_bus":        7000,   # Ghostworks pub/sub hub
    "ghostrigger":      7001,   # GhostRigger IPC server
    "ghostscripter":    7002,   # GhostScripter IPC server
    "gmodular":         7003,   # GModular IPC callback server
    "ghostscripter_mcp": 6400,  # GhostScripter MCP (HTTP mode)
    "ghostrigger_mcp":  7010,   # GhostRigger MCP (HTTP mode)
}
```

---

## 6. Context-Adaptive Tool Descriptions

### The Problem: Tools That Imply Context

Constantine warns against **control coupling** — passing a flag that selects completely
different behaviour. The same applies to tool descriptions: if a description says
"use this for dialogue editing" it forces the AI to interpret context before calling.

**Rule:** Tool descriptions must describe **what data the tool returns**, not **when to use it**.

### Context 1: Discord Bot

The bot asks: `"What is the quest k_swg_dxn_main?"`

With context-free tools, the flow is:
```
get_quest("k_swg_dxn_main")
→ returns: { quest_name, states, scripts[], dlg_entries[], jrl_summary }
→ bot formats as Discord markdown embed
```

The tool doesn't need to know it's a Discord bot. The tool just returns data.

### Context 2: VS Code Assistant

The user asks: `"What does the script k_swg_dxn_01.nss do?"`

```
get_script("k_swg_dxn_01")
→ returns: { source_nss, analysis: {functions, issues}, decompiled_ncs? }
→ VS Code displays in a side panel
```

### Context 3: Claude Desktop modding workflow

The user asks: `"I want to add a new companion NPC named Vash"`

```
get_npc("n_jedivash")         → existing NPC definition (UTC template)
get_quest("sas_vash")         → existing quest structure
list("utc", pattern="jedi*")  → find similar NPC templates
write_resource("n_vash_new", "utc", {...})  → create new UTC
```

### Context 4: Automated CI/test pipeline

```python
# No human in the loop — same tools, programmatic use
resources = list("nss", pattern="k_swg_*")
for r in resources["items"]:
    result = get_script(r["resref"])
    assert not result["analysis"]["errors"]
```

---

## 7. Composite Tool Designs

### 7.1 `get_quest(quest_id)` — Most Important Missing Tool

**Cohesion: Communicational** — all data elements share the `quest_id` key

```
Input:  quest_id = "k_swg_dxn_main"

Steps (internal, hidden from caller):
1. Read global.jrl → find quest entry → extract states + strref
2. For each state: resolve strref from dialog.tlk → human-readable text
3. Identify associated scripts (from JRL script fields)
4. For each script resref: read .nss (if exists) OR decompile .ncs
5. Search all DLG files for entries that reference quest_id in scripts
6. Look up journal category in globalcat.2da

Output (Markdown):
## Quest: The Ancient Temple (k_swg_dxn_main)
Category: Main Plot (row 42 in globalcat.2da)

### States
| State | ID | Description |
|-------|-----|-------------|
| Not Started | 0 | — |
| Active | 10 | Find the ancient temple on Dxun |
| Complete | 20 | The temple has been cleared |

### Scripts
- `k_swg_dxn_01.nss` (state 10 trigger)
  ```nwscript
  void main() { SetGlobalNumber("K_SWG_DXN_MAIN", 10); }
  ```
- `k_swg_dxn_02.nss` (completion)

### Dialogues referencing this quest
- `k_mandalore_01.dlg` — entry #4: "Have you found the temple yet?"
- `k_npc_dxn.dlg` — entry #12: (triggers quest start)
```

### 7.2 `get_resource(resref, type)` — Universal Resource Accessor

**Cohesion: Functional** — one job, format-agnostic

```
Input:  resref = "appearance", type = "2da"
        resref = "bas_p_bastila", type = "dlg"
        resref = "c_bantha", type = "mdl"
        resref = "k_swg_01", type = "nss"  OR  "ncs"

Internal dispatch:
  type=2da  → TwoDAService.to_markdown(paginated)
  type=dlg  → DialogueService.to_summary()
  type=utc  → GFFService.to_dict() + appearance.2da lookup
  type=nss  → raw source text
  type=ncs  → decompile via NCSDecomp → source text
  type=tlk  → TLKService.search()
  type=mdl  → GhostRigger IPC → model_info JSON
  unknown   → raw GFF parse → dict

Output: always Markdown or JSON, context-appropriate
```

### 7.3 `get_npc(resref_or_tag)` — NPC Composite View

**Cohesion: Communicational** — all data describes the same NPC

```
Input: "n_jedivash" or tag "n_jedivash001"

1. Read UTC (GFF) → base stats, scripts, dialogue reference
2. Look up appearance row in appearance.2da → visual description
3. Read the referenced DLG → entry count, first entry text, conditional scripts
4. Look up faction in repute.2da
5. Optionally: render model via GhostRigger IPC → thumbnail path

Output:
## NPC: Jedi Master Vash (n_jedivash)
Appearance: Jedi Human Female (row 108)
Faction: Jedi (row 3 in repute.2da)
HP: 40, Level: Jedi Consular 6

### Scripts
- OnHeartbeat: —
- OnDialog: k_swg_vash_dlg
- OnDeath: k_swg_vash_die

### Dialogue: k_swg_vash_01.dlg
14 entries, 8 replies
Opening: "So you've finally found me. I expected you sooner."
```

### 7.4 `get_script(resref)` — Script with Analysis

**Cohesion: Functional** — one job: return a script in readable form

```
Input: "k_swg_dxn_01"

1. Try to read k_swg_dxn_01.nss from override/ or BIF
2. If not found, read k_swg_dxn_01.ncs (compiled)
3. If .ncs: attempt decompile via NCSDecomp CLI / xoreos / pykotor
4. Run compileSummary static analysis on whatever source is found
5. Return structured result

Output:
## Script: k_swg_dxn_01
Source: override/k_swg_dxn_01.nss

```nwscript
void main() {
    SetGlobalNumber("K_SWG_DXN_MAIN_STATE", 10);
    AddJournalQuestEntry("k_swg_dxn_main", 10, FALSE);
}
```

### Analysis
- No issues detected
- Functions: main
- Globals set: K_SWG_DXN_MAIN_STATE, K_SWG_DXN_MAIN
```

---

## 8. What Works Well (Keep)

1. **Hexagonal architecture in GhostScripter** — ports/services/models layer is textbook Yourdon. Keep and extend.
2. **GModular's command pattern** — undo/redo via Command objects is perfect for a world editor. Keep.
3. **GhostRigger's adapter isolation** — pykotor interactions are isolated in adapter layer. Keep this pattern in GhostScripter.
4. **All three tools' test suites** — GR has 2,396, GS has 948, GM has 641 tests. This CI discipline must be maintained.
5. **MCP as the universal AI interface** — all three tools exposing MCP means any AI agent can use all three in one session.

---

## 9. What Needs Development (Priority Order)

### P1 — Implement now

1. **`get_resource(resref, type)`** in GhostScripter MCP — eliminates format knowledge requirement for AI
2. **`get_quest(quest_id)`** in GhostScripter MCP — most asked question in KotOR modding
3. **`get_npc(resref)`** in GhostScripter MCP — second most asked question
4. **`get_script(resref)`** in GhostScripter MCP — decompiled NCS + static analysis
5. **Canonical port constants** file — `ghostworks/ports.py` shared across all three tools

### P2 — Next sprint

6. **`get_area(module_id)`** — needs GModular IPC or GhostScripter's own RIM reader
7. **GModular MCP server** — expose `get_module`, `list_objects`, `get_object` tools
8. **Unified event bus** (port 7000) — replace 8s polling with push events
9. **DLG editor in GModular** — last major visual editing gap
10. **NCS decompile wired to get_script** — NCSDecomp/xoreos/pykotor fallback chain

### P3 — Later

11. **Supermodel texture loading in GhostRigger** — untextured renders
12. **Batch export pipeline** — GS + GM joint TSLPatcher package generator
13. **Module dependency walker** — "what does this mod change?" cross-tool analysis
14. **Animation playback in GModular** — controller data is parsed, needs timeline

---

## 10. Implementation Checklist

### Done ✅
- [x] Add `get_resource`, `get_quest`, `get_npc`, `get_script`, `listResType` to `ghostscripter/mcp/tools.py` (v2.2)
- [x] Add canonical port constants (`ghostscripter/core/constants.py` IPC_PORT_*)
- [x] `journalOverview` intentional overlap documented (§0 Tool Namespace Policy)
- [x] Replace `typing.Optional/Dict/List/Tuple` with built-in equivalents (`str | None`, `dict[...]`, `list[...]`)  — CONVENTIONS.md §typing
- [x] Fix server.py docstring: add monorepo context, remove stale "no pykotor dependency" claim
- [x] Add SYSTEMS_DESIGN.md §0 Monorepo Context section
- [x] **v2.4 — Deep audit and cleanup**
  - [x] Remove dead files: `ghostscripter/core/2da_manager/` (old 314-line TwoDAFile) and `ghostscripter/ipc/client.py` (duplicate)
  - [x] Fix 5 runtime bugs in composite tools (`from_bytes`, `GFFService.read`, `TLKService.lookup`, `list_by_type` ResourceEntry, `listResType` JSON serialisation)
  - [x] Fix `_get_script` rstrip bug: `str.rstrip('.nss')` strips chars not suffix → use `endswith`
  - [x] Fix `getQuest(includeDialogues)` default to `False`; cap DLG scan from 500 → 50; cost documented
  - [x] Refactor `_describe_resource` and `_module_overview` to use `GFFService.parse_bytes` (no direct `GFF3Reader` import)
  - [x] Refactor `gmodular_client.py`: module-level `import requests` so `@patch` works in tests
  - [x] Add `writeTwoDA` MCP tool — serialise 2DA to text (V2.0) or binary (V2.b) with optional cell edits; returns base64
  - [x] Add `writeERF` MCP tool — pack resource files into ERF v1.0 binary (MOD/ERF/SAV); returns base64
  - [x] Extend `TwoDAService` with `to_text()`, `to_binary()`, `set_cell()`, `build_from_dicts()` so MCP layer never bypasses service layer
  - [x] 1051 tests passing, 0 failures (+88 since v2.3)
- [x] **v2.5 — Write-loop completion + observability**
  - [x] Add `compileScript` MCP tool — invoke nwnnsscomp; return .ncs binary as base64 + compiler output
  - [x] Add `writeOverride` MCP tool — write any resource to game Override folder; update in-session index
  - [x] Add `ERFService.build()` — wraps `ERFWriter` so `tools.py` never imports `erf_writer` directly
  - [x] Replace 9 bare `except Exception: pass/continue` with `log.debug("...", e)` throughout `tools.py`
  - [x] Add 14 new tests (compileScript: 6, writeOverride: 8) — 1065 passing, 0 failures

- [x] **v2.6 — getArea + tools_pkg refactor + caching + port registry**
- [x] **v2.7 — getDoor + getPlaceable + getItem + searchAll (+26 tests, 1108 total)**
  - [x] Add `getArea` composite tool — ARE properties + GIT instances + LYT rooms; graceful `parse_errors` list
  - [x] Refactor `tools.py` (2,500 lines) into `tools_pkg/` sub-package with 6 focused modules
  - [x] Add `searchResources` 2DA session cache (`_2DA_CACHE`): O(n×parse) → O(n×lookup) after first call
  - [x] Add canonical `ghostscripter/ipc/ports.py` port registry; all IPC files import from it
  - [x] Add 17 new tests (getArea: 7, ports: 4, tools_pkg: 6) — 1108 passing, 0 failures

### P1 — v2.7 (done)
- [x] **v2.7 — getDoor + getPlaceable + getItem + searchAll**
  - [x] Add `getDoor` composite tool — UTD blueprint: tag, lock/trap, script fields, conversation
  - [x] Add `getPlaceable` composite tool — UTP blueprint: tag, appearance, lock/trap, inventory, scripts
  - [x] Add `getItem` composite tool — UTI blueprint: base item, cost, properties list, TLK-resolved name/desc
  - [x] Add `searchAll` tool — unified text search across 2DA + TLK + NSS + DLG in one call
  - [x] Add 26 new tests (6 getDoor, 4 getPlaceable, 5 getItem, 9 searchAll, 2 count) — 1108 passing, 0 failures

### P1 — v2.8 (done)
- [x] **v2.8 — getModule + getEncounter + getTrigger + getWaypoint + getStore + getSound + readSSF**
  - [x] Add `getModule` composite tool — IFO snapshot: mod_name, tag, entry area, entry XYZ, area list, all Mod_On* scripts
  - [x] Add `getEncounter` composite tool — UTE blueprint: tag, active, difficulty, faction, spawn_list, scripts
  - [x] Add `getTrigger` composite tool — UTT blueprint: tag, trap type, one-shot, linked_to, trap sub-fields, scripts
  - [x] Add `getWaypoint` composite tool — UTW blueprint: tag, name, XYZ position, orientation, map note fields
  - [x] Add `getStore` composite tool — UTM blueprint: tag, name, mark-up/down, inventory list, scripts
  - [x] Add `getSound` composite tool — UTS blueprint: tag, active/loop/positional, volume, distances, XYZ, sounds list
  - [x] Add `readSSF` tool — SSF binary decoder: 28 canonical slot names (PyKotor SSFSound enum), StrRef + TLK text
  - [x] Path-safety: `_safe_write_path` audited; `writeOverride` hardened; all 41 tool schemas verified
  - [x] Add 55 new tests — 1163 passing, 0 failures

### P1 — v2.9 (done)
- [x] **v2.9 — readLIP + writeLIP + getCreature + qtpy migration + Python 3.10 type hints**
  - [x] Add `readLIP` tool — LIP V1.0 binary decoder: duration, keyframe_count, each frame's time_s + shape_index + shape_name
  - [x] Add `writeLIP` tool — LIP V1.0 encoder from keyframe list; accepts shape int 0-15 or string name; validates ascending order
  - [x] Add `getCreature` composite tool — UTC blueprint: tag, name, race/subrace/gender, class+level pairs, 6 ability scores,
        HP, AC, appearance row, faction, conversation, equipment list, feat list, skill ranks, all script fields
  - [x] qtpy compatibility layer — 17 UI files migrated from bare PyQt5 → qtpy; PyQt6/PySide6 ready without code changes
  - [x] Python 3.10 type hints — `Optional[X]` → `X | None`, `Union[X,Y]` → `X | Y` across 29 source files
  - [x] Port registry hardening — `IPCCallbackServer` default port reads from `GHOSTSCRIPTER_REST` constant
  - [x] Add 36 new tests — 1199 passing, 0 failures

### P2 — v3.0 (done)
- [x] **v3.0 — getFaction + gs-prefixed tools + PyKotor shim**
  - [x] Add `getFaction` composite tool — FAC GFF: faction names, mutual reputation table (0–100 per pair)
  - [x] Tool namespace fix — 4 tools renamed with `gs` prefix (`gsDetectInstallations`, `gsLoadInstallation`,
        `gsListResources`, `gsDescribeResource`) to avoid KotorMCP collisions; `journalOverview` intentionally
        shared (same schema per SYSTEMS_DESIGN §Tool Namespace Policy)
  - [x] PyKotor shim — `ghostscripter/core/pykotor_shim.py`: `ShimInstallation` wraps ResourceManager behind
        pykotor `Installation` API; transparently delegates to real pykotor when installed
  - [x] Add 31 new tests — 1230 passing, 0 failures (16 shim, 10 getFaction, 5 v3.0 suite)

### P3 — v3.1 (done)
- [x] **v3.1 — LIP GUI editor + getModule GIT snapshots + Qt Designer stubs**
  - [x] `LIPEditorWidget` — `ghostscripter/ui/widgets/lip_editor_widget.py`:
        keyframe table, colour-coded timeline canvas (16 LIPShape colours), shape legend,
        phoneme→shape map (matches PyKotor `LIPShape.from_phoneme`), binary V1.0 encode/decode,
        open/save dialogs. Fully headless-testable (no Qt instantiation needed for unit tests).
  - [x] `getModule` extended — `include_git` bool parameter (default false); adds `area_summaries`
        with per-area GIT instance counts (creatures, doors, placeables, waypoints, triggers, stores,
        sounds, encounters). `inputSchema` updated with `include_git` property + default.
  - [x] Qt Designer stubs — `ghostscripter/ui/ui_files/new_project_dialog.ui` +
        `new_quest_dialog.ui`. Both dialogs: try `qtpy.uic.loadUi(ui_file)` first; fall back to
        Python hand-built layout. Identical public `get_data()` API either way.
  - [x] Add 58 new tests — 1288 passing, 0 failures
        (8 LIPEditorWidget constants, 32 lip binary/API tests, 6 getModule schema, 8 dialog loader,
        4 lip import assertions)

### P3.5 — v3.2 (done)
- [x] **v3.2 — PTH/LTR/SSF I/O tools + getBlueprint + getArea enrichment + 41 new tests**
  - [x] Fixed 3 duplicate tool registrations (readPTH/readLTR/writeSSF appended twice in prior sprint)
  - [x] `readGUI` — decode KotOR GUI GFF (GFFContent.GUI): returns control tree with types, positions,
        borders, text, and scripts. Uses `GUIControlType` / `GUIAlignment` from PyKotor `gui.py` generic.
  - [x] `readSave` — decode KotOR save-game folder: reads SAVENFO.res (save info GFF) + module IFO;
        returns area_name, player_name, game_time, credits, current_module. Path must be absolute.
  - [x] `readPTH` — decode PTH (path-node GFF): `point_count`, `connection_count`, `points` list
  - [x] `writePTH` — encode PTH path-node graph from `{x, y, connections}` list with bounds validation
  - [x] `readLTR` — decode LTR Markov name-generator binary: top-5 start/end letter probabilities
  - [x] `writeSSF` — encode SSF V1.1 binary from slot→StrRef mapping (28 slots by name or 0-27 index)
  - [x] `getBlueprint` — universal GFF blueprint reader for all 9 types (utc/uti/utp/utd/ute/utm/uts/utt/utw);
        common fields (tag, name, description, scripts) + type-specific fields validated against PyKotor generics
  - [x] `getArea` enriched — cameras, weather state (UseTemplates/CurrentWeather/WeatherStarted),
        full ARE ambient/fog/grass/shadow/stealth fields, GIT `AreaProperties` audio overrides
  - [x] Reference scans completed:
        - KotorMCP (5 tools: detectInstallations/loadInstallation/listResources/describeResource/journalOverview)
          all covered by gs* equivalents; `_summarize_gff` pattern documented for Phase 1 integration
        - HolocronToolset editors (19 files: are/git/pth/utc/uti/utp/utd/ute/utm/uts/utt/utw/ltr/ssf/dlg/fac/ifo/jrl)
          — field names verified against PyKotor generics for getBlueprint implementation
        - xoreos-tools and KotOR.js cross-referenced for LTR/LIP/SSF binary format verification
  - [x] Tool count: 52 canonical tools, 56 _HANDLERS (4 legacy aliases)
  - [x] Add 41 new tests — 1329 passing, 0 failures

### P3.6 — v3.3 (done)
- [x] **v3.3 — Deep scan sprint: NCS/VIS/IFO/WAV/TXI/pathfinding + 438 tests total**
  - [x] `readNCS` — NCS (compiled NWScript) bytecode disassembler: validates header ("NCS V1.0"),
        returns instruction_count, byte_size, and up to 256 instructions with opcode/qualifier/mnemonic/args_hex.
        Full NCSByteCode opcode table (CPDOWNSP, RSADDx, CONSTx, ACTION, JMP/JSR/JZ/JNZ, RETN, MOVSP,
        SAVEBP, RESTOREBP, STORE_STATE, DESTRUCT, arithmetic/logic/compare ops) from PyKotor ncs_data.py.
  - [x] `readVIS` — VIS (visibility/occlusion) ASCII file reader: room_count and per-room visible_rooms list.
        Matches PyKotor `vis_data.py` format (parent room + indented children). Used for area occlusion graph.
  - [x] `readIFO` — Dedicated IFO (module info GFF) composite: mod_name, tag, entry_area/XYZ/direction,
        area_list, expansion_id, creator_id, and all 14 Mod_On* script hooks verified against PyKotor `ifo.py`.
  - [x] `readWAV` — KotOR audio metadata without full decoding: detects standard RIFF WAV, SFX-obfuscated
        (0xBFBFBFBF magic), VO-obfuscated (8-byte VO header), MP3 (0xfffb sync), OGG (OggS magic).
        Returns format, obfuscation_type, byte_size, and for RIFF WAV: sample_rate/channels/bits/duration_ms.
        Accepts `data_b64` param for offline analysis without installation.
  - [x] `readTXI` — TXI ASCII texture-info reader: parses all key/value pairs (blending, mipmap, envmap,
        bump, cube, procedural, numx/numy font dims, downsizemin, compressiontype) from PyKotor txi_data.py.
        Numeric values auto-converted from string to int/float.
  - [x] `pathfindRoute` — A* shortest path on KotOR PTH adjacency graph: loads PTH via GFFService,
        builds vertex list and adjacency dict, runs heapq-based A* with Euclidean heuristic.
        Returns path (node index list), step_count, total_distance, waypoints [{x,y}].
        Matches PyKotor `common/pathfinding.py` Pathfinder algorithm (PathfindingVertex/A* pattern).
  - [x] Deep reference scans:
        - **xoreos-tools** (ncsdis.cpp + ncsdecomp.cpp): NCS disassembly opcode table cross-referenced
        - **PyKotor NCS** (ncs_data.py, io_ncs.py, decompiler.py, ncs_types.py): NCSByteCode enum full table
        - **PyKotor VIS** (vis_data.py, io_vis.py): room visibility ASCII format documented
        - **PyKotor WAV** (wav_data.py, io_wav.py, wav_obfuscation.py): WAVType, SFX/VO/RIFF magic bytes
        - **PyKotor TXI** (txi_data.py): all texture attribute keys
        - **PyKotor pathfinding** (common/pathfinding.py): A* algorithm with PathfindingVertex
        - **HolocronToolset** WAVEditor, IFOEditor, script_decompiler.py, script_utils.py
  - [x] Tool count: 58 canonical tools, 62 _HANDLERS (4 legacy aliases)
  - [x] 438 tests passing, 0 failures

### P3.7 — v3.3.1 (done)
- [x] **v3.3.1 — GFF helper refactor + XY pathfinding + PyKotor routing + 498 tests**
  - [x] **GFF helper consolidation** — `gff_scalar`, `gff_locstr`, `gff_resref`, `gff_int`,
        `gff_float`, `gff_list`, `gff_struct_fields` extracted into `_helpers.py`; 17+ inline
        closure defs (`_v`, `_locstr`, `_vs`, `_vr`, `_lstr`, `_rs`, `_iv`, `_fv`) removed
        from `handlers_composite.py` and `handlers_read.py`. All call sites updated to use the
        shared module-level utilities directly.
  - [x] **`pathfindRoute` XY mode** — `start_x`/`start_y`/`end_x`/`end_y` float inputs in
        addition to integer node indices; `_find_nearest_node(points, x, y)` helper snaps to
        closest PTH vertex via Euclidean distance; inputSchema updated so only `game`+`resref`
        are required (four new optional params documented).
  - [x] **PyKotor opportunistic routing** — `readNCS` tries `pykotor.resource.formats.ncs`
        `read_ncs()` first; `readIFO` tries `pykotor.resource.generics.ifo.construct_ifo()`;
        both return `pykotor_used: True` flag on success and fall back to internal readers when
        PyKotor absent. `TestPyKotorGracefulFallback` covers both paths.
  - [x] **Test depth increase** — 60 new tests covering:
        - 13 `readNCS` instruction-level (RETN, JMP, CONSTx int/str/float/obj, ACTION,
          CPDOWNSP, DESTRUCT, SAVEBP+RESTOREBP sequence, unknown opcode UNK_XX, parse_errors field)
        - 10 `readIFO` positive-path (mod_name, entry_area, coords, scripts filter,
          area_list, expansion_id+is_save, value-wrapper form, result-keys, missing resref/install)
        - 9 `pathfindRoute` XY-mode (snap start/end, both XY, index-mode regression,
          partial-XY error, snap_distance field, schema required/optional checks)
        - 28 `TestGFFHelpers` (gff_scalar plain/wrapped/default/nested; gff_locstr all
          sub-keys, empty, no-TLK-without-rm; gff_resref, gff_int, gff_float, gff_list,
          gff_struct_fields)
  - [x] **Snapshot deduplication** — 4 duplicate `assertEqual(len(TOOLS), 58)` in
        `TestGhostworksPipelineTools`, `TestToolsPkgPackage`, `TestV32Additions`,
        `TestV32NewTools` demoted to `assertGreaterEqual`; single canonical assertion in
        `TestV33Additions.test_total_tool_count_is_58` is the source of truth.
  - [x] 498 tests passing, 1 skipped, 0 failures

### P3.8 — v3.4.0 (done)
- [x] **v3.4.0 — Auto-installation detection + deep scan sprint + 498 tests**
  - [x] **Auto-link on MCP startup** — `_auto_load_installations()` now wired into
        `server.py:main()` before any transport starts; the MCP server auto-discovers and
        loads game installations on every launch without any user action required.
        Priority: (1) `K1_PATH`/`K2_PATH`/`KOTOR_PATH`/`TSL_PATH` env vars,
        (2) Windows Registry (Steam App IDs, GOG, BioWare/LucasArts disc),
        (3) 30+ exhaustive default path list.
  - [x] **Expanded `_DEFAULT_PATHS`** — added Flatpak Steam, Aspyr K2 Linux port
        (`~/.local/share/aspyr-media/kotor2`), macOS `.app/Contents/Assets` bundle paths
        (Aspyr verified), WSL `/mnt/c/*`, Amazon Games Store, Debian Steam installation —
        sourced directly from PyKotor's `tools/path.py:get_default_paths()` function.
  - [x] **Fixed Windows Registry keys** — previous `LucasArts\Star Wars Knights...` paths
        were incorrect.  Replaced with authoritative KOTOR_REG_PATHS from PyKotor's
        `tools/registry.py`: Steam `Uninstall\Steam App 32370/208580` (`InstallLocation`),
        GOG `GOG.com\Games\1207666283/1421404581` (`PATH`), `BioWare\SW\KOTOR` +
        `LucasArts\KotOR2` (`InternalPath`/`Path`) — both 32-bit and WOW6432Node variants
        for full 64-bit Windows compatibility.
  - [x] **`gsDetectInstallations` response enhanced** — each game entry now includes a
        `loaded: bool` field so AI agents know whether a game is ready for tool calls
        without inspecting `_INSTALLS` separately.  Test suite updated accordingly.
  - [x] **Deep scan — PyKotor** — `installation.py` (`SearchLocation` enum, 14 search
        locations, `HARDCODED_MODULE_NAMES` 30-entry module→description dict, `SaveFolderEntry`);
        `tools/path.py` (`CaseAwarePath` case-insensitive resolution, `get_default_paths()`);
        `tools/registry.py` (`KOTOR_REG_PATHS`, `SpoofKotorRegistry` context manager for
        compiler registry spoofing); `resource/formats/ncs/compilers.py`
        (`InbuiltNCSCompiler` — cross-platform Python-native NCS compilation without Wine).
  - [x] **Deep scan — KotorMCP** — `_iter_candidate_paths` dedup pattern (lower-cased `seen`
        set); `ENV_HINTS` multi-alias env var lookup; `GFF_HEAVY_TYPES` filter for large GFFs;
        `SearchLocation` string API matching KotorMCP's `location` parameter convention.
  - [x] **Deep scan — HolocronToolset** — `script_decompiler.py` `ht_decompile_script()`:
        `ExternalNCSCompiler` + `SpoofKotorRegistry` pattern; identified `InbuiltNCSCompiler`
        as the cross-platform replacement that eliminates Wine requirement for `compileScript`.
  - [x] **Action items logged** — 8 v3.4 findings documented in `ROADMAP.md §v3.4 Deep Scan`
        with specific API call patterns for adoption.
  - [x] 498 tests passing, 1 skipped, 0 failures

### P3.9 — v3.4.1 (done)
- [x] **`decompileScript` MCP tool** — NCS → NSS using PyKotor `decompile_ncs` / `disassemble_ncs`
      chain; xoreos `ncsdecomp` CLI as final fallback. Tool #59. Input: `data_base64` or `resref`.
- [x] **`compileScript` cross-platform fix** — `InbuiltNCSCompiler` tried first (no Wine); nwnnsscomp
      fallback kept for environments without PyKotor.
- [x] **`HARDCODED_MODULE_NAMES`** — 70-entry dict in `_helpers.py`; `moduleOverview` + `getArea`
      fall back to it when `.are` GFF has no parseable `Name` field.
- [x] **Deep-scan Phase 3** — DLG node/link fields, ERF V1.0 binary layout, UTC creature template
      (12 script hooks), JRL journal (JRLQuest/JRLEntry), BWM walkmesh APIs (raycast/AABB tree),
      xoreos NCS disassembler reference, GFF ResourceType enum (247+ entries).
- [x] 1449 tests passing, 1 skipped, 0 failures (+8 TestDecompileScript)

### P4 — Next sprint (v3.5)
- [ ] Replace `resource_manager/` BIF/KEY reader with `pykotor.extract.installation.Installation`
- [ ] Replace `formats/dlg_reader.py` with `pykotor.resource.formats.dlg.DLG`
- [ ] Replace `formats/gff_reader.py` with `pykotor.resource.formats.gff`
- [ ] Replace `export/erf_writer.py` with `pykotor.tools.archives`
- [ ] Add `pykotor` to `requirements.txt` as explicit dependency
- [ ] Remove legacy tool name aliases (`detectInstallations` etc.) from `_HANDLERS`
- [ ] `writePTH` — upgrade from JSON descriptor to proper GFF V3.2 binary (requires Phase 1)
- [x] `decompileScript` — **DONE in v3.4.1**
- [x] `compileScript` cross-platform fix — **DONE in v3.4.0**
- [x] `moduleOverview`/`getArea` HARDCODED_MODULE_NAMES — **DONE in v3.4.1**
- [ ] `_auto_load_installations` — adopt dedup pattern (lower-cased `seen` set)
- [ ] `_auto_load_installations` — extend K2 env var check to `TSL_PATH`, `KOTOR2_PATH`
- [ ] `gsListResources` — expose `SearchLocation` string (override/modules/chitin/etc.)
- [ ] `getBlueprint` — `GFF_HEAVY_TYPES` filter: metadata-only by default, full GFF on demand

### P5 — Later (v3.5+)
- [ ] GModular MCP server (expose world-editor tools via MCP)
- [ ] Event bus publisher (`ghostworks/event_bus.py`) — pub/sub over port 7000
- [ ] GIT node-graph UI for area object placement (Phase 4)
- [ ] Dedicated UTC/UTI/UTP inspector panel (Phase 4)
- [ ] Texture pipeline integration (DDS/TGA preview in asset library)
- [ ] Batch export pipeline (compile → pack → override copy as single MCP call)
- [ ] Document `GHOSTWORKS_EVENT_BUS.md` pub/sub protocol
- [ ] BWM walkmesh reader MCP tool (mesh faces, vertices, walkable materials)

