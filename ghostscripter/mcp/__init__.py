"""GhostScripter MCP — Model Context Protocol server for KotOR modding.

Native implementation using GhostScripter's own readers/writers,
inspired by OldRepublicDevs/PyKotor KotorMCP.

Tools exposed:
  Installation & discovery
  • detectInstallations   — find K1/K2 game directories
  • loadInstallation      — cache a game installation for use
  • listResources         — browse resources by type/location
  • describeResource      — structured summary of a GFF/2DA/TLK/DLG/JRL
  • searchResources       — full-text search across 2DA tables and TLK strings

  Reading resources
  • readGFF               — parse any GFF-based file into a JSON dict
  • readDLG               — import a dialogue file as structured JSON
  • readTwoDA             — read a 2DA table with filtering and pagination
  • readTLK               — look up TLK strings by strref
  • readJournal           — overview of global.jrl quests (alias: journalOverview)

  Targeted lookups
  • twoDALookup           — look up a single row/cell in a 2DA table
  • moduleOverview        — list creatures, doors, placeables in a game area
  • nwscriptSignature     — full signature + parameters for one NWScript function
  • nwscriptCategories    — list all function/constant category names

  Writing resources
  • writeDLG              — export a dialogue JSON back to binary DLG
  • writeGFF              — write a generic GFF from a JSON dict

  Analysis & patching
  • searchNWScript        — autocomplete / search NWScript functions/constants
  • compileSummary        — static analysis of NWScript source (functions, issues)
  • twoDAChangesINI       — generate TSLPatcher changes.ini from 2DA diff

Transport modes (server.py / __main__.py):
  stdio  — pipe-based, for Claude Desktop and local MCP clients
  http   — streamable HTTP, for web-based clients
  sse    — Server-Sent Events, for legacy MCP clients

Quick start:
  python -m ghostscripter.mcp                        # stdio
  python -m ghostscripter.mcp --mode http --port 6400  # HTTP
"""
