"""Command line entry point: ``sportapi-mcp`` (stdio by default)."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from ._version import __version__
from .server import create_server
from .service import ENV_BASE_URL, ENV_KEY, ENV_LANGUAGE, GET_KEY_URL, SportAPIService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sportapi-mcp",
        description=(
            "MCP server for SportAPI: Live and Prematch sports odds, scores and statistics. "
            f"Configure {ENV_KEY} and {ENV_BASE_URL} for live data (optional {ENV_LANGUAGE}); "
            f"without them it serves demo data. API key: {GET_KEY_URL}"
        ),
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
        help="MCP transport (default: stdio, used by desktop and IDE clients).",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="streamable-http bind address (default 127.0.0.1)."
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="streamable-http port (default 8000)."
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Serve demo data even if an API key is configured.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    service = SportAPIService(demo=True if args.demo else None)
    if service.config_error:
        print(f"sportapi-mcp: {service.config_error}", file=sys.stderr)
    elif service.is_demo:
        print(
            f"sportapi-mcp: demo mode (no {ENV_KEY}/{ENV_BASE_URL}); tools return example data "
            f"from the SportAPI documentation. API key: {GET_KEY_URL}",
            file=sys.stderr,
        )
    server = create_server(service)
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
