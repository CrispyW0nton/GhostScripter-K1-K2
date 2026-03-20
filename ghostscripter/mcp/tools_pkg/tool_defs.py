"""MCP tool schema definitions (TOOLS list).

This module is the single source of truth for tool names, descriptions,
and input schemas served to AI clients via list_tools().
"""
from __future__ import annotations

from typing import List

import mcp.types as types


# ─── Tool schemas ─────────────────────────────────────────────────────────────

TOOLS: List[types.Tool] = [

    types.Tool(
        name="gsDetectInstallations",
        description=(
            "Detect available KotOR 1 and KotOR 2 game installations. "
            "Checks environment variables (K1_PATH, K2_PATH) and common install paths. "
            "Prefixed 'gs' to distinguish from the read-only KotorMCP tool of the same "
            "base name (see SYSTEMS_DESIGN.md §Tool Namespace Policy)."
        ),
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),

    types.Tool(
        name="gsLoadInstallation",
        description=(
            "Load (or reload) a KotOR installation into the GhostScripter resource cache. "
            "Must be called before listing or reading resources via GhostScripter write tools. "
            "Subsequent calls with the same game reuse the cached install. "
            "Prefixed 'gs' to avoid collision with KotorMCP's loadInstallation "
            "(see SYSTEMS_DESIGN.md §Tool Namespace Policy)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {
                    "type": "string",
                    "description": "Game identifier: 'K1' or 'K2' (also accepts 'kotor1', 'tsl', etc.)",
                },
                "path": {
                    "type": "string",
                    "description": "Explicit path to the game root directory (optional; overrides env vars).",
                },
            },
            "required": ["game"],
        },
    ),

    types.Tool(
        name="gsListResources",
        description=(
            "List resources in the GhostScripter-loaded KotOR installation. "
            "Filter by resource type extension (e.g. 'dlg', '2da', 'nss'), "
            "name prefix, or location (override/chitin/all). "
            "Returns resref, type, source, and byte size. "
            "Prefixed 'gs' to avoid collision with KotorMCP's listResources "
            "(see SYSTEMS_DESIGN.md §Tool Namespace Policy)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2'."},
                "resourceType": {
                    "type": "string",
                    "description": "File extension to filter by (e.g. 'dlg', '2da', 'jrl', 'nss', 'gff'). "
                                   "Omit for all types.",
                },
                "location": {
                    "type": "string",
                    "enum": ["all", "override", "chitin"],
                    "default": "all",
                    "description": "Where to search: 'all', 'override' folder only, or 'chitin' archives only.",
                },
                "query": {
                    "type": "string",
                    "description": "Case-insensitive prefix / substring filter on resource name.",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "description": "Maximum number of results (default 50, max 500).",
                },
            },
            "required": ["game"],
        },
    ),

    types.Tool(
        name="gsDescribeResource",
        description=(
            "Get a detailed structured summary of a specific KotOR resource via GhostScripter. "
            "For GFF-based files (DLG, UTC, UTP, ARE, GIT, etc.) returns a field overview. "
            "For 2DA returns column names and row count. "
            "For TLK returns entry count and language. "
            "For JRL (journal) returns category/quest summary. "
            "Prefixed 'gs' to avoid collision with KotorMCP's describeResource "
            "(see SYSTEMS_DESIGN.md §Tool Namespace Policy)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2'."},
                "resref": {"type": "string", "description": "Resource name without extension (e.g. 'appearance', 'global', 'bastila')."},
                "restype": {"type": "string", "description": "Resource type extension (e.g. '2da', 'dlg', 'jrl', 'tlk', 'utc')."},
            },
            "required": ["game", "resref", "restype"],
        },
    ),

    types.Tool(
        name="readGFF",
        description=(
            "Parse any GFF-based KotOR resource (DLG, UTC, UTP, ARE, GIT, JRL, …) "
            "and return its complete field tree as a JSON object. "
            "Lists are returned as arrays, structs as nested objects. "
            "Depth is configurable; defaults to 8."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2'."},
                "resref": {"type": "string", "description": "Resource name without extension."},
                "restype": {"type": "string", "description": "Resource type extension (e.g. 'dlg', 'utc', 'are')."},
                "maxDepth": {
                    "type": "integer",
                    "default": 8,
                    "description": "Maximum nesting depth to traverse (default 8; reduces output for deeply nested files).",
                },
            },
            "required": ["game", "resref", "restype"],
        },
    ),

    types.Tool(
        name="readDLG",
        description=(
            "Import a KotOR DLG dialogue file and return a structured JSON representation "
            "with entries (NPC lines), replies (player choices), starters, and branch trees. "
            "Each node includes: text, strref, speaker, scripts, branches, VO resref."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2'."},
                "resref": {"type": "string", "description": "DLG resource name (without .dlg extension)."},
                "includeBranches": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include branch connectivity in each node (default true).",
                },
            },
            "required": ["game", "resref"],
        },
    ),

    types.Tool(
        name="readTwoDA",
        description=(
            "Read a KotOR 2DA table and return its rows as a JSON array. "
            "Optionally filter columns and rows, and search for specific values."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2'."},
                "resref": {"type": "string", "description": "2DA resource name (e.g. 'appearance', 'classes', 'feat')."},
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column names to include (omit for all columns).",
                },
                "rowQuery": {
                    "type": "string",
                    "description": "Case-insensitive substring to filter rows by any cell value.",
                },
                "limit": {
                    "type": "integer",
                    "default": 100,
                    "description": "Max rows to return (default 100).",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "description": "Row offset for pagination.",
                },
            },
            "required": ["game", "resref"],
        },
    ),

    types.Tool(
        name="readTLK",
        description=(
            "Look up one or more string references (strrefs) in the KotOR Talk Table (dialog.tlk). "
            "Returns the text string and sound resref for each strref."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2'."},
                "strrefs": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of TLK string reference IDs to look up.",
                },
            },
            "required": ["game", "strrefs"],
        },
    ),

    types.Tool(
        name="readJournal",
        description=(
            "Read the KotOR journal (global.jrl) and return a structured overview of "
            "all quest categories, their entries (state IDs), and completion flags."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2'."},
                "categoryFilter": {
                    "type": "string",
                    "description": "Case-insensitive substring to filter category tags.",
                },
            },
            "required": ["game"],
        },
    ),

    types.Tool(
        name="searchNWScript",
        description=(
            "Search the KotOR NWScript function/constant database. "
            "Returns matching function names, signatures, parameter lists, "
            "and categories. Also supports constant lookup. "
            "Uses bundled nwscript.nss — no game installation required."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2' (default: 'K1')."},
                "query": {"type": "string", "description": "Search term (prefix match for autocomplete, or substring for broader search)."},
                "kind": {
                    "type": "string",
                    "enum": ["functions", "constants", "all"],
                    "default": "functions",
                    "description": "What to search: 'functions', 'constants', or 'all'.",
                },
                "category": {
                    "type": "string",
                    "description": "Filter results by category (e.g. 'Effects', 'Getters', 'Minigame (SWMG)').",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "description": "Maximum results (default 20).",
                },
            },
            "required": ["query"],
        },
    ),

    types.Tool(
        name="nwscriptSignature",
        description=(
            "Get the full signature and parameter details for a specific NWScript function. "
            "Returns return type, parameter names/types/defaults, and the function's docstring. "
            "Uses bundled nwscript.nss — no game installation required."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2' (default: 'K1')."},
                "functionName": {"type": "string", "description": "Exact NWScript function name (case-sensitive)."},
            },
            "required": ["functionName"],
        },
    ),

    types.Tool(
        name="writeGFF",
        description=(
            "Write a GFF binary file from a JSON field dict. "
            "The JSON must have the same structure returned by readGFF. "
            "Returns the GFF bytes as a base64-encoded string and its byte size."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "fileType": {
                    "type": "string",
                    "description": "4-char GFF file type (e.g. 'DLG ', 'UTC ', 'JRL ', 'UTP ').",
                },
                "fields": {
                    "type": "object",
                    "description": "JSON object of field_name -> value (same schema as readGFF output).",
                },
            },
            "required": ["fileType", "fields"],
        },
    ),

    types.Tool(
        name="journalOverview",
        description=(
            "Return a structured overview of all journal plot categories and entries "
            "from global.jrl.  This tool name is intentionally shared with "
            "OldRepublicDevs/KotorMCP (same schema, same semantics) so that agent "
            "configurations using either server receive identical results.  "
            "GhostScripter's implementation delegates to JournalService (part of the "
            "IDE core); KotorMCP's implementation uses pykotor directly.  "
            "When both servers are active, prefer KotorMCP for read-only workflows "
            "and GhostScripter when you also need writeDLG / writeGFF in the same "
            "session.  See SYSTEMS_DESIGN.md §Tool Namespace Policy."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2'."},
            },
            "required": ["game"],
        },
    ),

    types.Tool(
        name="writeDLG",
        description=(
            "Export a dialogue JSON (as returned by readDLG) back to a KotOR binary DLG file. "
            "Creates entries, replies, starters, scripts, and VO references. "
            "Returns the binary data as a base64-encoded string suitable for saving as a .dlg file."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {
                    "type": "string",
                    "description": "Target game: 'K1' or 'K2'. Affects which fields are written.",
                },
                "dialogue": {
                    "type": "object",
                    "description": (
                        "Dialogue structure (same schema as readDLG output). "
                        "Must contain 'entries' and 'replies' arrays, each with 'text', "
                        "'strref', optional 'script1'/'script2', 'vo_resref', etc. "
                        "Optional top-level fields: 'end_script', 'abort_script'."
                    ),
                },
            },
            "required": ["game", "dialogue"],
        },
    ),

    types.Tool(
        name="writeTwoDA",
        description=(
            "Serialise a 2DA table to a binary or text KotOR 2DA file. "
            "Accepts the rows/columns structure (as returned by readTwoDA or twoDALookup), "
            "applies optional cell edits, and returns the final 2DA as a base64-encoded string "
            "in either text (V2.0) or binary (V2.b) format."
        ),
        inputSchema={
            "type": "object",
            "required": ["resref", "columns", "rows"],
            "properties": {
                "resref": {
                    "type": "string",
                    "description": "2DA name without extension (e.g. 'appearance', 'baseitems').",
                },
                "columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column names in order (same as readTwoDA 'columns' output).",
                },
                "rows": {
                    "type": "array",
                    "description": "Array of row objects. Each object must have a 'label' key plus one key per column.",
                    "items": {"type": "object"},
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "binary"],
                    "default": "text",
                    "description": "Output format: 'text' (V2.0, human-readable) or 'binary' (V2.b, smaller).",
                },
                "edits": {
                    "type": "array",
                    "description": "Optional list of cell edits to apply before serialisation.",
                    "items": {
                        "type": "object",
                        "required": ["row", "column", "value"],
                        "properties": {
                            "row": {
                                "type": ["integer", "string"],
                                "description": "Row index (int) or row label (string).",
                            },
                            "column": {"type": "string", "description": "Column name."},
                            "value": {"type": "string", "description": "New cell value (use '****' for empty)."},
                        },
                    },
                },
            },
        },
    ),

    types.Tool(
        name="writeERF",
        description=(
            "Pack a set of KotOR resource files into a binary ERF v1.0 archive "
            "(used as .mod, .erf, or .sav files in KotOR mods). "
            "Accepts a list of file objects with resref, type, and base64-encoded data. "
            "Returns the packed archive as a base64-encoded string ready to write to disk. "
            "ERF archives are the standard distribution format for KotOR module mods."
        ),
        inputSchema={
            "type": "object",
            "required": ["files"],
            "properties": {
                "files": {
                    "type": "array",
                    "description": "Resources to pack into the archive.",
                    "items": {
                        "type": "object",
                        "required": ["resref", "type", "data_b64"],
                        "properties": {
                            "resref": {
                                "type": "string",
                                "description": "Resource name without extension, max 16 chars.",
                            },
                            "type": {
                                "type": "string",
                                "description": "File type extension without dot: nss, ncs, dlg, utc, 2da, …",
                            },
                            "data_b64": {
                                "type": "string",
                                "description": "File contents as a base64-encoded string.",
                            },
                        },
                    },
                },
                "archive_type": {
                    "type": "string",
                    "enum": ["ERF ", "MOD ", "SAV "],
                    "default": "MOD ",
                    "description": "ERF file-type header: 'ERF ' (generic), 'MOD ' (module), or 'SAV ' (save game).",
                },
            },
        },
    ),

    types.Tool(
        name="compileScript",
        description=(
            "Compile a NWScript (.nss) source string to a binary .ncs file "
            "using the bundled nwnnsscomp compiler. "
            "Returns the compiled .ncs as base64, plus any compiler output. "
            "game must be 'K1' or 'K2' because the compiler links against "
            "nwscript.nss from the correct game edition. "
            "Platform note: the bundled compiler (resources/tools/nwnnsscomp_k1/k2.exe) "
            "is a Windows PE32 binary. On Linux/macOS it is invoked via Wine if Wine is "
            "on PATH; otherwise place a native nwnnsscomp binary on PATH. "
            "A structured error listing all searched paths is returned when no "
            "compiler is found."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {
                    "type": "string",
                    "description": "Game edition: 'K1' (KotOR 1) or 'K2' (TSL).",
                },
                "source": {
                    "type": "string",
                    "description": "The full NWScript (.nss) source code to compile.",
                },
                "resref": {
                    "type": "string",
                    "description": (
                        "Resource reference name for the output file (max 16 chars, "
                        "no extension). Defaults to 'script'."
                    ),
                },
            },
            "required": ["game", "source"],
        },
    ),

    types.Tool(
        name="writeOverride",
        description=(
            "Write a single resource file (base64-encoded) into the Override folder "
            "of a loaded KotOR installation. "
            "Overwrites any existing file with the same resref+type in Override. "
            "The in-session resource index is updated so subsequent reads reflect the new file."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {
                    "type": "string",
                    "description": "Game identifier: 'K1' or 'K2'.",
                },
                "resref": {
                    "type": "string",
                    "description": "Resource reference (filename without extension, max 16 chars).",
                },
                "restype": {
                    "type": "string",
                    "description": (
                        "File extension without leading dot "
                        "(e.g. 'ncs', 'nss', 'dlg', 'utc', '2da', 'gff')."
                    ),
                },
                "data_b64": {
                    "type": "string",
                    "description": "File contents as a base64-encoded string.",
                },
            },
            "required": ["game", "resref", "restype", "data_b64"],
        },
    ),

    types.Tool(
        name="compileSummary",
        description=(
            "Parse and summarise a NWScript (.nss) source string. "
            "Extracts all declared functions with their signatures, "
            "lists #include directives and global constants, "
            "and reports any obvious syntax issues (unclosed braces, "
            "missing semicolons in declarations). Does NOT invoke nwnnsscomp — "
            "this is a lightweight static analysis tool for AI context-building."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "The full NWScript (.nss) source code text to analyse.",
                },
                "filename": {
                    "type": "string",
                    "description": "Optional filename hint for error messages (e.g. 'k_hench_ai.nss').",
                },
            },
            "required": ["source"],
        },
    ),

    types.Tool(
        name="searchResources",
        description=(
            "Full-text / value search across KotOR game resources. "
            "Searches 2DA tables for rows matching a value, "
            "TLK strings containing a phrase, or DLG dialogue text. "
            "Returns resref, scope, matching row/strref, and matched value for each hit."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2'."},
                "query": {
                    "type": "string",
                    "description": "The text or value to search for (case-insensitive substring).",
                },
                "scope": {
                    "type": "string",
                    "enum": ["2da", "tlk", "all"],
                    "default": "all",
                    "description": "Where to search: '2da' (all loaded 2DA tables), 'tlk' (Talk Table strings), or 'all'.",
                },
                "limit": {
                    "type": "integer",
                    "default": 30,
                    "description": "Maximum number of results per scope (default 30).",
                },
            },
            "required": ["game", "query"],
        },
    ),

    types.Tool(
        name="moduleOverview",
        description=(
            "Get a high-level overview of a KotOR module (.rim/.erf/.mod area). "
            "Returns the area name, lists of creatures (UTC), doors (UTD), "
            "placeables (UTP), waypoints (UTW), and triggers (UTT) found "
            "in the area's GIT instance list."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2'."},
                "moduleId": {
                    "type": "string",
                    "description": "Module/area resref (e.g. 'danm13', 'tar_m02ae', 'end_m01aa').",
                },
            },
            "required": ["game", "moduleId"],
        },
    ),

    types.Tool(
        name="twoDALookup",
        description=(
            "Look up a single cell or row in a KotOR 2DA table by row label or index. "
            "More targeted than readTwoDA — ideal for quickly resolving a specific appearance, "
            "item, or class attribute without downloading an entire table."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2'."},
                "resref": {"type": "string", "description": "2DA file name without extension (e.g. 'appearance')."},
                "row": {
                    "description": "Row identifier: integer index OR string row label.",
                },
                "column": {
                    "type": "string",
                    "description": "Optional column name. Omit to return the entire row.",
                },
            },
            "required": ["game", "resref", "row"],
        },
    ),

    types.Tool(
        name="nwscriptCategories",
        description=(
            "Enumerate all NWScript function/constant categories available in the bundled "
            "nwscript.nss database, with the count of entries per category. "
            "Pass a category name to the 'category' filter of searchNWScript to narrow results. "
            "No game installation required."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "game": {"type": "string", "description": "Game identifier: 'K1' or 'K2' (default: 'K1')."},
                "kind": {
                    "type": "string",
                    "enum": ["functions", "constants", "all"],
                    "default": "functions",
                    "description": "Which categories to list.",
                },
            },
            "required": [],
        },
    ),

    types.Tool(
        name="twoDAChangesINI",
        description=(
            "Generate a TSLPatcher-compatible changes.ini patch section "
            "describing the diff between an original and modified 2DA. "
            "Output is a ready-to-paste [2DAList] block for a TSLPatcher changes.ini file."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "original": {
                    "type": "string",
                    "description": "The original 2DA content as plain text (V2.0 format).",
                },
                "modified": {
                    "type": "string",
                    "description": "The modified 2DA content as plain text (V2.0 format).",
                },
                "twoDAName": {
                    "type": "string",
                    "description": "The 2DA file name without extension (e.g. 'appearance').",
                },
            },
            "required": ["original", "modified", "twoDAName"],
        },
    ),

    # ── Composite / high-level tools (Ghostworks Pipeline) ─────────────────

    types.Tool(
        name="getResource",
        description=(
            "Return the contents of any KotOR game resource by resref and type. "
            "Automatically parses the resource into a readable form: "
            "2DA tables become row/column JSON, DLG dialogue files become "
            "structured entry/reply trees, GFF files become field dicts, "
            "NSS scripts return source text, NCS compiled scripts are "
            "decompiled if a decompiler is available, TLK strings return text. "
            "This is the universal resource accessor — use it whenever you need "
            "to read any single game file and do not want to reason about its format."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref", "type"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "Resource reference name (no extension, max 16 chars)."},
                "type": {
                    "type": "string",
                    "description": (
                        "Resource type extension: 2da, dlg, utc, utp, uts, utt, utw, ute, utm, "
                        "are, git, jrl, nss, ncs, tpc, tga, mdl, gff, tlk, …"
                    ),
                },
                "format": {
                    "type": "string",
                    "enum": ["auto", "json", "markdown", "raw_text"],
                    "description": "Output format. 'auto' chooses the most readable form for the resource type.",
                },
            },
        },
    ),

    types.Tool(
        name="getQuest",
        description=(
            "Return a composite view of a KotOR quest: journal states, "
            "the scripts responsible for each state transition, and optionally "
            "dialogue entries that reference the quest's scripts. "
            "Combines data from global.jrl (states), dialog.tlk (resolved text), "
            "NWScript files (state logic), and DLG files (dialogue triggers)."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "questId"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "questId": {
                    "type": "string",
                    "description": "Quest plot tag as it appears in global.jrl (e.g. 'k_swg_dxn_main').",
                },
                "includeScripts": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include source/decompiled NWScript for each state transition script.",
                },
                "includeDialogues": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "Search DLG files for entries that reference this quest's scripts. "
                        "WARNING: may parse up to 50 DLG archives — adds 1-5 s on large installs. "
                        "Disable when you only need quest state/script data."
                    ),
                },
            },
        },
    ),

    types.Tool(
        name="getNpc",
        description=(
            "Return a composite view of a KotOR NPC. "
            "Reads the UTC template (stats, scripts, Conversation field), "
            "resolves the appearance row from appearance.2da, "
            "resolves the faction name from repute.2da, "
            "and summarises the opening line of any attached DLG dialogue."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {
                    "type": "string",
                    "description": "UTC resref (e.g. 'n_jedivash') or NPC tag.",
                },
                "includeDialogue": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include a summary of the NPC's dialogue file.",
                },
            },
        },
    ),

    types.Tool(
        name="getScript",
        description=(
            "Return a KotOR NWScript in readable form. "
            "Prefers .nss source when available; falls back to decompiling the .ncs binary "
            "via NCSDecomp, xoreos-tools ncsdecomp, or pykotor (tried in order). "
            "Optionally runs static analysis and returns detected issues "
            "(type mismatches, ResRef length violations, brace errors)."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {
                    "type": "string",
                    "description": "Script resref without extension (e.g. 'k_swg_dxn_01').",
                },
                "analyze": {
                    "type": "boolean",
                    "default": True,
                    "description": "Run static analysis and include issues in the result.",
                },
            },
        },
    ),

    types.Tool(
        name="listResType",
        description=(
            "Enumerate all KotOR game resources of a given type, with optional name filter. "
            "Returns resrefs, locations (override/BIF/module), and sizes. "
            "Supports pagination via offset and limit parameters."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "type"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "type": {
                    "type": "string",
                    "description": "Resource type (2da, dlg, nss, utc, utp, mdl, tpc, …)",
                },
                "pattern": {
                    "type": "string",
                    "description": "Optional substring filter on resref name.",
                },
                "offset": {"type": "integer", "default": 0},
                "limit": {"type": "integer", "default": 50, "maximum": 200},
            },
        },
    ),

    types.Tool(
        name="getArea",
        description=(
            "Return a composite view of a KotOR area by resref. "
            "Reads <resref>.are (area properties: name, tileset, ambient sound, flags), "
            "<resref>.git (game instance table: all placed creatures, doors, placeables, "
            "waypoints, triggers, stores, sounds, encounters — each with tag, resref, XYZ), "
            "and <resref>.lyt (room layout: room model names with XYZ offsets). "
            "Returns a parse_errors list for any missing or corrupt resources. "
            "Example resrefs: 'danm13' (Dantooine Enclave), 'tar_m02aa' (Taris Upper City)."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {
                    "type": "string",
                    "description": "Area resref (max 16 chars), e.g. 'danm13'.",
                },
            },
        },
    ),

    types.Tool(
        name="getDoor",
        description=(
            "Return a structured view of a KotOR door blueprint (UTD GFF) by resref. "
            "Extracts tag, generic type, animation state, lock properties "
            "(locked, key name, lock DC, open lock DC), trap properties "
            "(detectable, disarmable, type, DCs), script fields "
            "(OnOpen, OnClosed, OnLock, OnUnlock, OnClick, OnDeath, etc.), "
            "and conversation resref. "
            "listResType(type='utd') enumerates available door resrefs."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {
                    "type": "string",
                    "description": "Door blueprint resref (max 16 chars), e.g. 'door_med_01'.",
                },
            },
        },
    ),

    types.Tool(
        name="getPlaceable",
        description=(
            "Return a structured view of a KotOR placeable blueprint (UTP GFF) by resref. "
            "Extracts tag, appearance, static/useable flags, lock properties, "
            "trap properties, inventory item list, script fields "
            "(OnOpen, OnUsed, OnClosed, OnClick, OnInvDisturbed, OnDeath, etc.), "
            "and conversation resref. "
            "listResType(type='utp') enumerates available placeable resrefs."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {
                    "type": "string",
                    "description": "Placeable blueprint resref (max 16 chars), e.g. 'plc_footlocker'.",
                },
            },
        },
    ),

    types.Tool(
        name="getItem",
        description=(
            "Return a structured view of a KotOR item blueprint (UTI GFF) by resref. "
            "Extracts tag, base item type, stack size, cost, stolen/identified flags, "
            "charges, upgrade level, item properties list (PropertyName, Subtype, "
            "CostTable, CostValue, Param1), name and description text "
            "(resolved from dialog.tlk when includeTLK is true), "
            "and script fields (OnActivated, OnHeartbeat, OnUserDefined). "
            "listResType(type='uti') enumerates available item resrefs."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {
                    "type": "string",
                    "description": "Item blueprint resref (max 16 chars), e.g. 'g_w_lghtsbr01'.",
                },
                "includeTLK": {
                    "type": "boolean",
                    "description": "Resolve TLK strrefs for name and description (default true).",
                },
            },
        },
    ),

    types.Tool(
        name="searchAll",
        description=(
            "Unified case-insensitive text search across multiple resource scopes in one call. "
            "Scopes: '2da' (all 2DA table cells), 'tlk' (dialog.tlk strings), "
            "'nss' (NWScript source files, line by line), 'dlg' (dialogue node texts). "
            "Each match returns: scope, source filename, detail (row/line/strref), and matched value. "
            "Configurable scopes list and limit (max 500). Uses 2DA session cache."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "query"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "query": {
                    "type": "string",
                    "description": "Substring to search for (case-insensitive).",
                },
                "scopes": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["2da", "tlk", "nss", "dlg"]},
                    "description": "Scopes to search (default: all four).",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max total matches to return (default 100, max 500).",
                    "default": 100,
                    "maximum": 500,
                },
            },
        },
    ),

    # ── v2.8 tools ──────────────────────────────────────────────────────────

    types.Tool(
        name="getModule",
        description=(
            "Read module.ifo for a KotOR module by module_id resref. "
            "Returns module name, tag, voice-over ID, entry area resref, "
            "entry position (x/y/z) and direction (dir_x/dir_y), "
            "area list (Mod_Area_list resrefs), and all module event scripts "
            "(Mod_OnLoad, Mod_OnHeartbeat, Mod_OnClientEnter, etc.). "
            "When include_git=true also returns area_summaries: per-area "
            "GIT instance counts (creatures, doors, placeables, waypoints, "
            "triggers, stores, sounds, encounters) — useful for module maps "
            "and placement audits. Requires loadInstallation first."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "module_id"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "module_id": {
                    "type": "string",
                    "description": "Module IFO resref without extension (e.g. 'danm13'). "
                                   "Use 'module' to read the installation-root module.ifo.",
                },
                "include_git": {
                    "type": "boolean",
                    "description": "If true, include per-area GIT instance-count summaries "
                                   "in area_summaries. Increases response size. Default false.",
                    "default": False,
                },
            },
        },
    ),

    types.Tool(
        name="getEncounter",
        description=(
            "Read a KotOR encounter blueprint (UTE) by resref. "
            "Returns tag, active flag, difficulty index, faction, "
            "spawn list (creature resrefs with challenge rating and single-spawn flag), "
            "and script fields (OnEntered, OnExhausted, OnExit, OnHeartbeat, OnSpawn, OnUserDefined). "
            "Requires loadInstallation first. "
            "Use listResType(type='ute') to enumerate encounter resrefs."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "Encounter blueprint resref (max 16 chars)."},
            },
        },
    ),

    types.Tool(
        name="getTrigger",
        description=(
            "Read a KotOR trigger blueprint (UTT) by resref. "
            "Returns tag, trap type, trap one-shot flag, linked object tag, "
            "trap properties (detectable, disarmable, trap DC, disarm DC), "
            "and script fields (ScriptOnEnter, ScriptOnExit, OnTrapTriggered, OnDisarm, OnClick). "
            "Requires loadInstallation first. "
            "Use listResType(type='utt') to enumerate trigger resrefs."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "Trigger blueprint resref (max 16 chars)."},
            },
        },
    ),

    types.Tool(
        name="getWaypoint",
        description=(
            "Read a KotOR waypoint blueprint (UTW) by resref. "
            "Returns tag, localized name, position (x/y/z), orientation (dir_x/dir_y), "
            "and map note fields (has_map_note, map_note_enabled, map_note text). "
            "Requires loadInstallation first. "
            "Use listResType(type='utw') to enumerate waypoint resrefs."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "Waypoint blueprint resref (max 16 chars)."},
            },
        },
    ),

    types.Tool(
        name="getStore",
        description=(
            "Read a KotOR merchant/store blueprint (UTM) by resref. "
            "Returns tag, localized name, mark-up percentage, mark-down percentage, "
            "buy/sell capability flags, inventory list (item resrefs with infinite-stock flag), "
            "and script fields (OnOpenStore). "
            "Requires loadInstallation first. "
            "Use listResType(type='utm') to enumerate store resrefs."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "Store blueprint resref (max 16 chars)."},
            },
        },
    ),

    types.Tool(
        name="getSound",
        description=(
            "Read a KotOR ambient/placed sound object blueprint (UTS) by resref. "
            "Returns tag, active/looping/positional/continuous flags, volume, "
            "pitch variation, min/max distances, position (x/y/z), "
            "and sounds list (audio ResRef strings). "
            "Requires loadInstallation first. "
            "Use listResType(type='uts') to enumerate sound object resrefs."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "Sound object resref (max 16 chars)."},
            },
        },
    ),

    types.Tool(
        name="readSSF",
        description=(
            "Decode a KotOR Sound Set File (SSF) by resref. "
            "SSF files are 28-slot binary tables that map creature sound events "
            "(BATTLE_CRY_1-6, SELECT_1-3, ATTACK_GRUNT_1-3, PAIN_GRUNT_1-2, "
            "LOW_HEALTH, DEAD, CRITICAL_HIT, TARGET_IMMUNE, LAY_MINE, DISARM_MINE, "
            "BEGIN_STEALTH, BEGIN_SEARCH, BEGIN_UNLOCK, UNLOCK_FAILED, UNLOCK_SUCCESS, "
            "SEPARATED_FROM_PARTY, REJOINED_PARTY, POISONED) "
            "to StrRef integers in dialog.tlk. "
            "Returns slot list with index, canonical name, strref, and resolved TLK text. "
            "Requires loadInstallation first. "
            "Use listResType(type='ssf') to enumerate sound set resrefs."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {
                    "type": "string",
                    "description": "Sound set resref without extension (max 16 chars), e.g. 'p_bastila'.",
                },
                "resolve_tlk": {
                    "type": "boolean",
                    "description": "Look up each StrRef in dialog.tlk and include the text (default true).",
                },
            },
        },
    ),

    # ── v2.9 additions ────────────────────────────────────────────────────────
    types.Tool(
        name="readLIP",
        description=(
            "Decode a KotOR lip-sync animation file (LIP) by resref. "
            "LIP files are fixed-format binaries (header: 'LIP V1.0', 4-byte float "
            "duration, uint32 keyframe count) followed by 5-byte keyframe entries "
            "(float time + uint8 mouth-shape index 0-15). "
            "Mouth shapes: 0=NEUTRAL, 1=EE, 2=EH, 3=AH, 4=OH, 5=OOH, "
            "6=Y, 7=STS, 8=FV, 9=NG, 10=TH, 11=MPB, 12=TD, 13=SH, 14=L, 15=KG. "
            "Returns duration_s (total audio length), keyframe_count, and a list of "
            "keyframes each with time_s and shape_index + shape_name. "
            "Requires loadInstallation first. "
            "Use listResType(type='lip') to enumerate available lip-sync resrefs."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {
                    "type": "string",
                    "description": "LIP resref without extension (max 16 chars), e.g. 'n_bastila001'.",
                },
            },
        },
    ),
    types.Tool(
        name="writeLIP",
        description=(
            "Encode and write a KotOR lip-sync animation file (LIP V1.0) from a "
            "keyframe list. Provide the total audio duration in seconds and an ordered "
            "list of keyframes, each with 'time' (float seconds from start) and 'shape' "
            "(integer 0-15 or string name: NEUTRAL, EE, EH, AH, OH, OOH, Y, STS, FV, "
            "NG, TH, MPB, TD, SH, L, KG). "
            "Returns base64-encoded LIP binary and keyframe count. "
            "To write the result to disk use writeOverride after decoding. "
            "Keyframes must be in ascending time order; shapes outside 0-15 are rejected."
        ),
        inputSchema={
            "type": "object",
            "required": ["duration", "keyframes"],
            "properties": {
                "duration": {
                    "type": "number",
                    "description": "Total audio/animation duration in seconds (float, e.g. 3.5).",
                },
                "keyframes": {
                    "type": "array",
                    "description": "Ordered list of mouth-shape keyframes.",
                    "items": {
                        "type": "object",
                        "required": ["time", "shape"],
                        "properties": {
                            "time": {
                                "type": "number",
                                "description": "Keyframe time from start in seconds.",
                            },
                            "shape": {
                                "description": "Mouth shape as integer 0-15 or name string.",
                            },
                        },
                    },
                },
            },
        },
    ),
    types.Tool(
        name="getCreature",
        description=(
            "Return a structured view of a KotOR creature blueprint (UTC) by resref. "
            "Extracts: tag, localized name, race, subrace, gender, class/level pairs, "
            "ability scores (STR/DEX/CON/INT/WIS/CHA), base HP/max HP, AC, "
            "appearance (appearance.2da row), faction, conversation resref, "
            "equipment list (resrefs by slot), feat list, skill ranks, "
            "and all script fields (OnSpawn, OnDeath, OnPerception, OnAttacked, "
            "OnDamaged, OnEndCombatRound, OnHeartbeat, OnBlocked, OnUserDefined). "
            "Requires loadInstallation first. "
            "Use listResType(type='utc') to enumerate creature blueprint resrefs."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {
                    "type": "string",
                    "description": "Creature blueprint resref without extension (max 16 chars), e.g. 'n_bastila'.",
                },
                "include_tlk": {
                    "type": "boolean",
                    "description": "Resolve localized name from dialog.tlk (default true).",
                },
            },
        },
    ),

    types.Tool(
        name="getFaction",
        description=(
            "Return the faction definition table from a KotOR FAC file. "
            "FAC files define named factions and their mutual reputation values (0-100). "
            "Standard file is 'repute.fac'; pass a custom resref for module-specific overrides. "
            "Returns each faction's index, name, and reputation entries (target faction index + value). "
            "Requires gsLoadInstallation first."
        ),
        inputSchema={
            "type": "object",
            "required": ["game"],
            "properties": {
                "game": {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {
                    "type": "string",
                    "description": "FAC file resref without extension (default 'repute').",
                },
            },
        },
    ),

    types.Tool(
        name="readPTH",
        description=(
            "Decode a KotOR PTH (pathfinding) file for an area. "
            "PTH files are GFF-based and define the NPC pathfinding graph: "
            "a list of X/Y nodes (Path_Points) connected by directed edges "
            "(Path_Conections with Destination index). "
            "Returns point_count, connection_count, and a points list each "
            "with {x, y, connections: [int, ...]}. "
            "The resref matches the area resref (same as .are/.git/.lyt). "
            "Requires gsLoadInstallation first."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game":   {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "Area resref (e.g. 'danm13')."},
            },
        },
    ),

    types.Tool(
        name="readLTR",
        description=(
            "Decode a KotOR LTR (Letter/Name Generator) binary file. "
            "LTR files store 3rd-order Markov chain probability tables used by "
            "the character-creation name generator. "
            "Returns letter_count, file_size_bytes, and the top-5 most probable "
            "starting and ending letters with their float32 probabilities. "
            "Common resrefs: 'humanm', 'humanf', 'alien'. "
            "Requires gsLoadInstallation first."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game":   {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "LTR resref (e.g. 'humanm', 'humanf')."},
            },
        },
    ),

    types.Tool(
        name="writeSSF",
        description=(
            "Encode a KotOR SSF (Sound Set File) binary from a slot→StrRef mapping. "
            "SSF files define 28 sound-event slots for creatures "
            "(BATTLE_CRY_1..6, SELECT_1..3, ATTACK_GRUNT_1..3, PAIN_GRUNT_1..3, "
            "LOW_HP, DEAD, CRITICAL_HIT, TARGET_IMMUNE, LAY_MINE, DISARM_MINE, "
            "BEGIN_STEALTH, BEGIN_SEARCH, BEGIN_UNLOCK, SKILL_IMPEDE, POISONED). "
            "Returns base64-encoded SSF V1.1 binary. Unspecified slots default to "
            "-1 (no sound). Slot keys can be 0-27 or canonical names. "
            "Complements readSSF. Requires gsLoadInstallation first."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref", "slots"],
            "properties": {
                "game":   {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "Target SSF resref (max 16 chars)."},
                "slots": {
                    "type": "object",
                    "description": "Dict of {slot_name_or_index: strref_int}. "
                                   "E.g. {\"BATTLE_CRY_1\": 12345, \"0\": 12345}.",
                },
                "write_override": {
                    "type": "boolean",
                    "description": "If true, also write to Override folder. Default false.",
                    "default": False,
                },
            },
        },
    ),


    # ── v3.2 additions ─────────────────────────────────────────────────────────
    types.Tool(
        name="writePTH",
        description=(
            "Encode a KotOR PTH (pathfinding) path-node graph from a list of {x, y, connections} points. "
            "PTH files are GFF-based and define the NPC pathfinding graph for an area; each node has an "
            "X/Y position and a list of connected node indices (0-based directed edges). "
            "Returns base64-encoded PTH descriptor (full GFF binary pending PyKotor I/O integration). "
            "Connection indices must be valid (0..point_count-1). "
            "Use write_override=true to install via writeOverride after generation. "
            "Complements readPTH."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref", "points"],
            "properties": {
                "game":   {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "Area resref (max 16 chars), e.g. 'danm13'."},
                "points": {
                    "type": "array",
                    "description": "List of path nodes. Each: {x: float, y: float, connections: [int,...]}.",
                    "items": {"type": "object"},
                },
                "write_override": {
                    "type": "boolean",
                    "description": "If true, also install via writeOverride. Default false.",
                    "default": False,
                },
            },
        },
    ),

    types.Tool(
        name="getBlueprint",
        description=(
            "Universal KotOR blueprint reader for all GFF-based blueprint types: "
            "utc (creature), uti (item), utp (placeable), utd (door), "
            "ute (encounter), utm (merchant), uts (sound), utt (trigger), utw (waypoint). "
            "Returns tag, resref, name, description, scripts dict, plus type-specific fields "
            "(stats for utc, base_item/cost for uti, appearance/hp/locked for utp/utd, etc.). "
            "Use listResType(type='utc') etc. to enumerate available resrefs. "
            "Requires gsLoadInstallation first."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref", "type"],
            "properties": {
                "game":   {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "Blueprint resref without extension, e.g. 'n_bastila', 'g_w_lghtsbr01'."},
                "type": {
                    "type": "string",
                    "description": "Resource type: utc | uti | utp | utd | ute | utm | uts | utt | utw",
                    "enum": ["utc", "uti", "utp", "utd", "ute", "utm", "uts", "utt", "utw"],
                },
            },
        },
    ),

    # ── v3.2 new tools ────────────────────────────────────────────────────────

    types.Tool(
        name="readGUI",
        description=(
            "Read a KotOR GUI (GFF-based UI definition) file and return its control tree. "
            "GUI files define the KotOR 2D interface: panels, buttons, labels, list boxes, "
            "sliders, checkboxes, scroll bars, and progress bars. "
            "Each control has a GUIControlType (Panel=2, Label=5, Button=6, CheckBox=7, "
            "Slider=8, ScrollBar=9, Progress=10, ListBox=11), position (EXTENT.LEFT/TOP), "
            "size (WIDTH/HEIGHT), and optional text. "
            "Common resrefs: 'mainmenu16x12', 'chargen_main', 'in_game_bttns', 'inv_main'. "
            "Returns control_count and a controls list with tag, type_id, type_name, x, y, "
            "width, height, text_label. "
            "Requires gsLoadInstallation first."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "resref"],
            "properties": {
                "game":   {"type": "string", "description": "'K1' or 'K2'"},
                "resref": {"type": "string", "description": "GUI resref without extension (e.g. 'mainmenu16x12')."},
            },
        },
    ),

    types.Tool(
        name="readSave",
        description=(
            "Read a KotOR save-game folder and return a structured metadata summary. "
            "KotOR save games are folder-based: each slot contains SAVENFO.res (GFF), "
            "savegame.sav (ERF), globalvars.res, partytable.res, and per-module snapshots. "
            "SAVENFO.res stores: SaveName (localised), LastModule, AreaName, TimePlayed (secs), "
            "CheatUsed flag, and party table data. "
            "Returns: game, save_path, save_name, last_module, area_name, time_played_secs, "
            "cheat_used, party_members (stub list), global_count (stub), "
            "module_snapshots (list of snapshot module IDs). "
            "Provide 'save_path' as an absolute OS path to the save slot folder. "
            "Full party-BIC and globalvars parsing will be added in v3.3 (Phase 1 backlog). "
            "Does NOT require loadInstallation."
        ),
        inputSchema={
            "type": "object",
            "required": ["game", "save_path"],
            "properties": {
                "game":      {"type": "string", "description": "'K1' or 'K2'"},
                "save_path": {
                    "type": "string",
                    "description": "Absolute OS path to the save-game slot folder (e.g. '/saves/000000 - Taris').",
                },
            },
        },
    ),

]



# ─────────────────────────────────────────────────────────────────
# v3.3 tools
# ─────────────────────────────────────────────────────────────────
TOOLS.append(types.Tool(
    name="readNCS",
    description=(
        "Disassemble a KotOR NCS (compiled NWScript) binary. "
        "Returns file header info, instruction count, byte size, and a listing of up to 256 "
        "instructions with offset, opcode hex, qualifier hex, mnemonic, and argument bytes. "
        "Supports all NCSByteCode opcodes (CPDOWNSP, RSADDx, CONSTx, ACTION, JMP/JSR/JZ/JNZ, "
        "RETN, MOVSP, SAVEBP, RESTOREBP, STORE_STATE, DESTRUCT, and arithmetic/logic/compare ops). "
        "Requires a prior gsLoadInstallation call."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "game":   {"type": "string", "enum": ["K1", "K2"], "description": "KotOR 1 or 2"},
            "resref": {"type": "string", "maxLength": 16, "description": "Script resref without .ncs extension"},
        },
        "required": ["game", "resref"],
    },
))

TOOLS.append(types.Tool(
    name="readVIS",
    description=(
        "Read a KotOR VIS (visibility/occlusion) ASCII file. "
        "VIS files define which rooms are visible from each room, used for occlusion-culling "
        "optimization: the engine only renders rooms reachable from the current room. "
        "Returns room_count and a dict mapping each parent room to the list of visible child rooms. "
        "Format: parent room line then indented (2 spaces) child room names. "
        "Requires a prior gsLoadInstallation call."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "game":   {"type": "string", "enum": ["K1", "K2"], "description": "KotOR 1 or 2"},
            "resref": {"type": "string", "maxLength": 16, "description": "Area resref (same as VIS resref)"},
        },
        "required": ["game", "resref"],
    },
))

TOOLS.append(types.Tool(
    name="readIFO",
    description=(
        "Read a KotOR IFO (module info GFF) file. "
        "IFO is the master metadata file for a module, storing the entry area/position/direction, "
        "area list, module name/description, tag, expansion_id, creator_id, and all 14 Mod_On* "
        "script hooks (on_heartbeat, on_load, on_start, on_enter, on_leave, on_activate_item, "
        "on_acquire_item, on_unacquire_item, on_player_death, on_player_dying, on_player_levelup, "
        "on_player_respawn, on_player_rest, on_user_defined). "
        "Requires a prior gsLoadInstallation call with the target module loaded."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "game":   {"type": "string", "enum": ["K1", "K2"], "description": "KotOR 1 or 2"},
            "resref": {"type": "string", "maxLength": 16, "description": "Module resref (e.g. 'end_m01aa')"},
        },
        "required": ["game", "resref"],
    },
))

TOOLS.append(types.Tool(
    name="readWAV",
    description=(
        "Read KotOR audio file metadata without full decoding. "
        "KotOR audio files can be standard RIFF WAV, SFX-obfuscated (magic 0xBFBFBFBF), "
        "VO-obfuscated (VO header prefix), or plain MP3/OGG. "
        "Returns audio_format, obfuscation_type, byte_size, and for RIFF WAV also "
        "sample_rate, channels, bits_per_sample, and duration_ms. "
        "Provide either 'resref' (loads from installation) or 'data_b64' (raw base64 bytes). "
        "Requires gsLoadInstallation when using resref."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "game":     {"type": "string", "enum": ["K1", "K2"], "description": "KotOR 1 or 2"},
            "resref":   {"type": "string", "maxLength": 16, "description": "Audio resref without extension"},
            "data_b64": {"type": "string", "description": "Base64-encoded audio bytes (alternative to resref)"},
        },
        "required": ["game"],
    },
))

TOOLS.append(types.Tool(
    name="readTXI",
    description=(
        "Read a KotOR TXI (texture info) ASCII metadata file. "
        "TXI files accompany TPC textures and control rendering parameters: "
        "blending mode, mipmap settings, filtering, envmap reference, bump map, cube map, "
        "procedural texture animation, font character dimensions, and flipbook frame count. "
        "Returns attribute_count and a dict of all key/value pairs (numeric where possible). "
        "Requires a prior gsLoadInstallation call."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "game":   {"type": "string", "enum": ["K1", "K2"], "description": "KotOR 1 or 2"},
            "resref": {"type": "string", "maxLength": 16, "description": "Texture resref (same base name as .tpc)"},
        },
        "required": ["game", "resref"],
    },
))

TOOLS.append(types.Tool(
    name="pathfindRoute",
    description=(
        "Find the A* shortest route between two points on a KotOR PTH path-node graph. "
        "Loads the PTH file for the area, builds the adjacency graph, and runs A* to find "
        "the optimal path. Endpoints can be supplied as PTH node indices (start_index / "
        "end_index) OR as world-space XY coordinates (start_x + start_y / end_x + end_y). "
        "When XY coords are given, the nearest PTH node is snapped automatically and "
        "start_nearest / end_nearest in the response confirm the snap distance. "
        "Returns path (ordered list of node indices), step_count, total_distance (Euclidean), "
        "and waypoints (list of {x, y} dicts). Requires a prior gsLoadInstallation call."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "game":        {"type": "string", "enum": ["K1", "K2"], "description": "KotOR 1 or 2"},
            "resref":      {"type": "string", "maxLength": 16, "description": "Area resref (PTH shares the area name)"},
            "start_index": {"type": "integer", "minimum": 0, "description": "Index of starting PTH node (Mode A)"},
            "end_index":   {"type": "integer", "minimum": 0, "description": "Index of destination PTH node (Mode A)"},
            "start_x":     {"type": "number", "description": "World X of start position — nearest node is snapped (Mode B)"},
            "start_y":     {"type": "number", "description": "World Y of start position (Mode B)"},
            "end_x":       {"type": "number", "description": "World X of destination (Mode B)"},
            "end_y":       {"type": "number", "description": "World Y of destination (Mode B)"},
        },
        "required": ["game", "resref"],
    },
))

TOOLS.append(types.Tool(
    name="decompileScript",
    description=(
        "Decompile a KotOR NCS binary back to NWScript (.nss) source code. "
        "Input can be supplied as base64-encoded NCS bytes (data_base64) "
        "or as a resref to look up from a loaded installation. "
        "Uses PyKotor's native decompiler (decompile_ncs) first — cross-platform, "
        "no external tools needed. Falls back to disassembly (disassemble_ncs) "
        "if full decompilation fails, then tries the xoreos ncsdecomp CLI. "
        "Returns: nss_source (full source or disassembly), method (which strategy "
        "succeeded), disassembly (low-level instruction listing when available), "
        "game, resref, and size_bytes."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "game": {
                "type": "string",
                "enum": ["K1", "K2"],
                "description": "Game edition: 'K1' (KotOR 1) or 'K2' (TSL).",
            },
            "resref": {
                "type": "string",
                "maxLength": 16,
                "description": (
                    "Resource reference of the NCS file to decompile "
                    "(looked up from a loaded installation). "
                    "Either resref or data_base64 must be provided."
                ),
            },
            "data_base64": {
                "type": "string",
                "description": (
                    "Raw NCS binary data encoded as base64. "
                    "Use this to decompile bytes returned by compileScript or readNCS. "
                    "Either data_base64 or resref must be provided."
                ),
            },
        },
        "required": ["game"],
    },
))

TOOLS.append(types.Tool(
    name="getNWScriptDB",
    description=(
        "Return the complete NWScript function and constant database for KotOR 1 or 2. "
        "Enumerates all built-in functions (with return types and parameter lists) "
        "and all constants available in the game. "
        "No game installation required — uses the bundled nwscript.nss database."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "game": {
                "type": "string",
                "enum": ["K1", "K2"],
                "description": "Game version: K1 (Knights of the Old Republic) or K2 (The Sith Lords). Default K1.",
            },
        },
        "required": [],
    },
))
