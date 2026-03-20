"""Entry point for `python -m ghostscripter.mcp`.

Starts the GhostScripter MCP server.

Usage:
    python -m ghostscripter.mcp                      # stdio (default, for Claude Desktop)
    python -m ghostscripter.mcp --mode http --port 6400  # HTTP transport
    python -m ghostscripter.mcp --mode sse --port 6400   # SSE transport

Environment variables:
    K1_PATH   Path to KotOR 1 installation directory
    K2_PATH   Path to KotOR 2 / TSL installation directory
"""
from ghostscripter.mcp.server import main

if __name__ == "__main__":
    main()
