from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from importlib import resources
from typing import Any

import pytest
from mcp import Client

from sportapi_mcp import SportAPIService, create_server


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _no_credentials(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests never pick up real credentials from the environment."""
    for name in ("SPORTAPI_KEY", "SPORTAPI_BASE_URL", "SPORTAPI_LANGUAGE"):
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.fixture
async def demo_client() -> AsyncIterator[Client]:
    async with Client(create_server(SportAPIService())) as client:
        yield client


def demo_payload(filename: str) -> Any:
    """A documentation example response bundled with the sportapi client."""
    text = (resources.files("sportapi") / "_demo_data" / filename).read_text(encoding="utf-8")
    return json.loads(text)


async def call(client: Client, name: str, **arguments: Any) -> tuple[Any, bool]:
    """Call a tool; return (parsed JSON or error text, is_error)."""
    result = await client.call_tool(name, arguments)
    text = result.content[0].text  # type: ignore[union-attr]
    if result.is_error:
        return text, True
    return json.loads(text), False
