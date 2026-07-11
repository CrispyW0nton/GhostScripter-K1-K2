# GhostScripter MCP — Configuration Guide

The GhostScripter MCP server exposes KotOR modding tools to AI agents (Claude, Cursor,
VS Code Copilot, etc.) via the Model Context Protocol.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start — stdio (Claude Desktop)](#quick-start--stdio-claude-desktop)
3. [Quick Start — HTTP (Cursor / VS Code)](#quick-start--http-cursor--vs-code--web-agents)
4. [Quick Start — SSE (Legacy Clients)](#quick-start--sse-legacy-mcp-clients)
5. [Environment Variables](#environment-variables)
6. [Available Tools (60 total)](#available-tools-60-total)
7. [AgentDecompile Integration](#agentdecompile-integration--binary-analysis)
8. [Combined Multi-Server Config](#combined-multi-server-config)
9. [Example Workflow](#example-workflow)
10. [Common Steam Paths](#common-steam-paths)

---

## Prerequisites

```bash
# Core MCP dependencies (already in requirements.txt)
pip install mcp uvicorn

# Optional: httpx for AgentDecompile bridge tools (binary*)
pip install httpx
```

---

## Quick Start — stdio (Claude Desktop)

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

---

## Quick Start — HTTP (Cursor / VS Code / Web Agents)

```bash
# Start the server on port 6400
cd /path/to/GhostScripter-K1-K2
K1_PATH=/path/to/swkotor K2_PATH=/path/to/swkotor2 \
    python -m ghostscripter.mcp --mode http --port 6400
```

Add to `.cursor/mcp.json` (Cursor) or `.vscode/mcp.json` (VS Code):

```json
{
  "servers": {
    "ghostscripter": {
      "url": "http://localhost:6400/mcp"
    }
  }
}
```

---

## Quick Start — SSE (Legacy MCP Clients)

```bash
python -m ghostscripter.mcp --mode sse --port 6400
```

Connect via `http://localhost:6400/mcp`.

---

## Environment Variables

### GhostScripter

| Variable      | Description                                      | Example                       |
|--------------|--------------------------------------------------|-------------------------------|
| `K1_PATH`    | Path to KotOR 1 installation root               | `/home/user/.steam/swkotor`   |
| `K2_PATH`    | Path to KotOR 2 / TSL installation root         | `/home/user/.steam/swkotor2`  |
| `KOTOR_PATH` | Alias for `K1_PATH`                             | Same as K1_PATH               |
| `TSL_PATH`   | Alias for `K2_PATH`                             | Same as K2_PATH               |

### AgentDecompile Bridge

| Variable        | Description                                                    | Default                      |
|----------------|----------------------------------------------------------------|------------------------------|
| `AGDEC_URL`    | Base URL of the AgentDecompile/Ghidra server                  | `http://localhost:8080`      |
| `AGDEC_TIMEOUT`| Per-request timeout in seconds for binary analysis calls       | `60`                         |
| `AGDEC_SESSION`| Optional MCP session ID to reuse across calls                  | *(auto-negotiated)*          |

---

## Available Tools (60 total)

> The list below covers the core tools; see the README's
> [All 60 Tools](../../README.md#all-60-tools) table for the complete set.

### Installation & Discovery
| Tool | Description |
|------|-------------|
| `detectInstallations` | Find K1/K2 game directories automatically |
| `loadInstallation` | Cache a game installation for the session |
| `listResources` | Browse resources by type, location, or name |
| `describeResource` | Structured summary of any GFF/2DA/TLK/JRL resource |
| `searchResources` | Full-text search across 2DA tables and TLK strings |

### Reading Resources
| Tool | Description |
|------|-------------|
| `readGFF` | Parse GFF into a typed, lossless JSON tree (all field types retained) |
| `readDLG` | Import a dialogue file as structured JSON |
| `readTwoDA` | Read a 2DA table with filtering and pagination |
| `readTLK` | Look up TLK strings by strref ID |
| `readJournal` / `journalOverview` | Overview of global.jrl quests |

### Targeted Lookups
| Tool | Description |
|------|-------------|
| `twoDALookup` | Look up a single row or cell in a 2DA table |
| `moduleOverview` | List creatures, doors, and placeables in a game area |
| `nwscriptSignature` | Full signature + parameters for one NWScript function |
| `nwscriptCategories` | List all function/constant category names with counts |

### Writing Resources
| Tool | Description |
|------|-------------|
| `writeDLG` | Export a dialogue JSON back to binary DLG |
| `writeGFF` | Losslessly write a typed `readGFF` document; untyped inference requires explicit lossy opt-in |

### Analysis & Patching
| Tool | Description |
|------|-------------|
| `searchNWScript` | Autocomplete / search NWScript functions and constants |
| `compileSummary` | Static analysis of NWScript source (functions, issues) |
| `twoDAChangesINI` | Generate TSLPatcher changes.ini from a 2DA diff |

### Binary Analysis — AgentDecompile Bridge *(requires AGDEC_URL)*
| Tool | Description |
|------|-------------|
| `agdecStatus` | Check AgentDecompile server health and list its tools |
| `binaryAnalyze` | Get metadata for a KotOR binary (arch, function count) |
| `binaryDecompile` | Decompile any engine function to C-like pseudocode |
| `binarySearchSymbols` | Search symbol names inside the binary |
| `binaryListFunctions` | Paginated list of all functions in the binary |
| `binaryGetReferences` | Find callers / callees of a function or address |
| `binaryListStrings` | Extract printable strings from the binary |

---

## AgentDecompile Integration — Binary Analysis

GhostScripter integrates with [AgentDecompile](https://github.com/bolabaden/agentdecompile)
to bring Ghidra-powered reverse engineering directly into the KotOR modding workflow.

### What it enables

When you have a KotOR engine binary (`swkotor.exe`, `swkotor2.exe`) loaded in Ghidra via
AgentDecompile, GhostScripter's `binary*` tools allow an AI agent to:

- **Understand engine internals** — decompile NWScript opcode handlers, GFF parser routines,
  ResRef resolvers, and combat AI to understand exactly how the engine behaves.
- **Verify mod safety** — cross-reference function addresses to confirm a patch won't break
  unrelated systems.
- **Discover hardcoded constants** — extract magic numbers, resource type codes, and internal
  flag values that are not documented anywhere.
- **Trace data flow** — follow how a `.dlg` file is loaded from disk all the way to the
  conversation UI, identifying the right hook points for custom dialogue scripting.

### Architecture

```
AI Agent (Claude / Cursor)
     │
     ▼
GhostScripter MCP  (port 6400)          ← KotOR data tools
  │  binary* tools forward via HTTP
     ▼
AgentDecompile MCP  (port 8080)         ← Ghidra binary analysis
     ▼
swkotor.exe / swkotor2.exe
```

### Starting AgentDecompile

**Option A — Docker (recommended, no Ghidra install needed):**

```bash
# Import your KotOR binary into a local binaries folder first
mkdir -p ./binaries
cp "/path/to/swkotor/swkotor.exe" ./binaries/

# Start the AgentDecompile server
docker run --rm \
  --add-host host.docker.internal:host-gateway \
  -v "$(pwd)/binaries:/binaries" \
  -p 8080:8080 \
  docker.io/bolabaden/agentdecompile-mcp:latest

# Verify it's running
curl http://localhost:8080/
```

**Option B — Local install:**

```bash
pip install git+https://github.com/bolabaden/agentdecompile
# Start with a local Ghidra project
GHIDRA_INSTALL_DIR=/path/to/ghidra \
AGENT_DECOMPILE_PROJECT_PATH=./ghidra_projects \
  agentdecompile-server -t streamable-http --port 8080
```

### Connecting GhostScripter to AgentDecompile

Set the `AGDEC_URL` environment variable before starting GhostScripter:

```bash
# stdio (Claude Desktop)
AGDEC_URL=http://localhost:8080 python -m ghostscripter.mcp

# HTTP
AGDEC_URL=http://localhost:8080 \
K1_PATH=/path/to/swkotor \
  python -m ghostscripter.mcp --mode http --port 6400
```

### Verifying the connection

```
agdecStatus()
# → { "reachable": true, "tool_count": 37, "tools": ["decompile-function", ...] }
```

### Typical KotOR binary analysis workflow

```python
# 1. Verify AgentDecompile is up
agdecStatus()

# 2. Get metadata on the binary
binaryAnalyze(programPath="/K1/swkotor.exe")
# → { "name": "swkotor.exe", "language": "x86:LE:32:default",
#     "functionCount": 24591, "compiler": "windows" }

# 3. Find all functions related to NWScript execution
binaryListFunctions(programPath="/K1/swkotor.exe", nameFilter="Script")

# 4. Decompile the VM execute function
binaryDecompile(programPath="/K1/swkotor.exe", functionIdentifier="CScriptVM::Execute")

# 5. Find every caller of the GFF loader
binaryGetReferences(programPath="/K1/swkotor.exe", target="LoadGFF", direction="to")

# 6. Extract hardcoded resource type strings
binaryListStrings(programPath="/K1/swkotor.exe", filter="UTC", minLength=3, limit=20)

# 7. Search for ResRef-handling symbols
binarySearchSymbols(programPath="/K1/swkotor.exe", query="ResRef")
```

---

## Combined Multi-Server Config

To run both GhostScripter and AgentDecompile together in Claude Desktop, add both to
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ghostscripter": {
      "command": "python",
      "args": ["-m", "ghostscripter.mcp"],
      "cwd": "/path/to/GhostScripter-K1-K2",
      "env": {
        "K1_PATH": "/path/to/swkotor",
        "K2_PATH": "/path/to/swkotor2",
        "AGDEC_URL": "http://localhost:8080"
      }
    },
    "agdec-proxy": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/bolabaden/agentdecompile",
        "agentdecompile-proxy",
        "--backend-url", "http://localhost:8080",
        "--transport", "stdio"
      ]
    }
  }
}
```

> **Note:** The `agdec-proxy` entry gives Claude direct access to all 37 AgentDecompile
> tools *in addition to* the 7 bridged `binary*` tools in GhostScripter.  The bridge tools
> are convenient when you only want a single server; the direct proxy gives the full tool
> surface.  Use whichever fits your workflow.

For VS Code / Cursor (`.vscode/mcp.json`):

```json
{
  "servers": {
    "ghostscripter": {
      "url": "http://localhost:6400/mcp"
    },
    "agdec-proxy": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/bolabaden/agentdecompile",
        "agentdecompile-proxy",
        "--backend-url", "http://localhost:8080",
        "--transport", "stdio"
      ]
    }
  }
}
```

---

## Example Workflow

```python
# ── KotOR 1 mod workflow with binary analysis ────────────────────────────────

# 1. Load the K1 installation
loadInstallation(game="K1")

# 2. List all dialogue files starting with "bas_"
listResources(game="K1", resourceType="dlg", query="bas_")

# 3. Read a dialogue file
readDLG(game="K1", resref="bas_p_bastila")

# 4. Look up appearance row 4
twoDALookup(game="K1", resref="appearance", row=4, column="label")

# 5. Search TLK for "Bastila"
searchResources(game="K1", query="Bastila", scope="tlk", limit=10)

# 6. Get all NWScript Effects functions
searchNWScript(game="K1", query="", category="Effects", kind="functions", limit=30)

# 7. Analyse a script for issues
compileSummary(source="void main() { GiveItem(\"g_i_mask02\", GetFirstPC()); }")

# 8. Generate a TSLPatcher patch for a modified 2DA
twoDAChangesINI(original=orig_text, modified=new_text, twoDAName="appearance")

# ── Binary analysis (requires AgentDecompile) ────────────────────────────────

# 9. Verify Ghidra backend is running
agdecStatus()

# 10. Understand how GFF files are parsed
binaryDecompile(
    programPath="/K1/swkotor.exe",
    functionIdentifier="CExoFile::Read",
    limit=150,
)

# 11. Find every function that touches ResRef resolution
binarySearchSymbols(programPath="/K1/swkotor.exe", query="ResRef")
```

---

## Common Steam Paths

**Linux:**
- KotOR 1: `~/.local/share/Steam/steamapps/common/swkotor`
- KotOR 2: `~/.local/share/Steam/steamapps/common/Knights of the Old Republic II`

**macOS:**
- KotOR 1: `~/Library/Application Support/Steam/steamapps/common/swkotor`
- KotOR 2: `~/Library/Application Support/Steam/steamapps/common/Knights of the Old Republic II`

**Windows:**
- KotOR 1: `C:\Program Files (x86)\Steam\steamapps\common\swkotor`
- KotOR 2: `C:\Program Files (x86)\Steam\steamapps\common\Knights of the Old Republic II`
