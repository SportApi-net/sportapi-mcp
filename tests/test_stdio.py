"""Start the real console entry point over stdio, like an MCP client does."""

from __future__ import annotations

import json
import os
import sys

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from sportapi_mcp.cli import build_parser

pytestmark = pytest.mark.anyio


async def test_server_lists_tools_and_answers_over_stdio() -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("SPORTAPI_")}
    params = StdioServerParameters(command=sys.executable, args=["-m", "sportapi_mcp"], env=env)
    async with Client(params) as client:
        assert client.server_info is not None and client.server_info.name == "sportapi"
        names = {t.name for t in (await client.list_tools()).tools}
        assert {"list_live_matches", "get_match", "search_matches"} <= names
        result = await client.call_tool("get_match", {"game_id": 746146992, "line_type": "live"})
        data = json.loads(result.content[0].text)  # type: ignore[union-attr]
        assert data["source"] == "demo" and data["match"] == "Arsenal — Coventry City"


def test_cli_arguments() -> None:
    args = build_parser().parse_args([])
    assert args.transport == "stdio" and not args.demo
    args = build_parser().parse_args(["--transport", "streamable-http", "--port", "9000"])
    assert args.transport == "streamable-http" and args.port == 9000
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--transport", "sse"])
