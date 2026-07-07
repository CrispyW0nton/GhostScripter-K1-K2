"""GhostScripter MCP server harness.

Exposes the 60 tools from ghostscripter.mcp.tools_pkg over the Model
Context Protocol.

Usage:
    python -m ghostscripter.mcp                      # stdio (Claude Desktop)
    python -m ghostscripter.mcp --mode http --port 6400  # Streamable HTTP
    python -m ghostscripter.mcp --mode sse --port 6400   # SSE (legacy clients)

Environment variables:
    K1_PATH / KOTOR_PATH   Path to KotOR 1 installation directory
    K2_PATH / TSL_PATH     Path to KotOR 2 / TSL installation directory

Public API (relied on by tests and __main__.py):
    SERVER  mcp.server.Server  — named "GhostScripterMCP"
    main    entry point         — parses args, runs the chosen transport
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from typing import List

import mcp.types as types
from mcp.server import Server

from ghostscripter.mcp.tools_pkg import TOOLS, handle_tool
from ghostscripter.mcp.tools_pkg._helpers import _auto_load_installations

log = logging.getLogger("ghostscripter.mcp.server")

SERVER = Server("GhostScripterMCP")


@SERVER.list_tools()
async def _list_tools() -> List[types.Tool]:
    return TOOLS


@SERVER.call_tool()
async def _call_tool(name: str, arguments: dict) -> List[types.TextContent]:
    return await handle_tool(name, arguments or {})


async def _run_stdio() -> None:
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await SERVER.run(
            read_stream,
            write_stream,
            SERVER.create_initialization_options(),
        )


def _run_sse(host: str, port: int) -> None:
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.responses import Response
    from starlette.routing import Mount, Route

    transport = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await SERVER.run(
                read_stream,
                write_stream,
                SERVER.create_initialization_options(),
            )
        return Response()

    app = Starlette(routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=transport.handle_post_message),
    ])
    uvicorn.run(app, host=host, port=port)


def _run_http(host: str, port: int) -> None:
    import uvicorn
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
    from starlette.applications import Starlette
    from starlette.routing import Mount

    manager = StreamableHTTPSessionManager(app=SERVER, stateless=True)

    async def handle_http(scope, receive, send):
        await manager.handle_request(scope, receive, send)

    import contextlib

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield

    app = Starlette(
        routes=[Mount("/mcp", app=handle_http)],
        lifespan=lifespan,
    )
    uvicorn.run(app, host=host, port=port)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="ghostscripter.mcp",
        description="GhostScripter MCP server — KotOR modding tools for AI agents.",
    )
    parser.add_argument("--mode", choices=["stdio", "http", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6400)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    # Auto-detect K1/K2 installations (env vars → registry → default paths)
    # so agents can call read tools without an explicit gsLoadInstallation.
    try:
        _auto_load_installations()
    except Exception:
        log.exception("installation auto-detect failed (continuing without)")

    if args.mode == "stdio":
        asyncio.run(_run_stdio())
    elif args.mode == "sse":
        _run_sse(args.host, args.port)
    else:
        _run_http(args.host, args.port)


if __name__ == "__main__":
    main()
