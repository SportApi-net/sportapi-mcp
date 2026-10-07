"""Connection to SportAPI shared by all tools: configuration, demo mode, caching
and translation of client errors into messages an assistant can act on."""

from __future__ import annotations

import os
import warnings
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, Literal, TypeVar

import httpx
from mcp.server.mcpserver.exceptions import ToolError
from sportapi import (
    LINE,
    LIVE,
    AccessRestrictedError,
    AsyncSportAPI,
    AuthenticationError,
    ConfigurationError,
    DemoDataUnavailableError,
    GameFinishedError,
    GameNotFoundError,
    HTTPStatusError,
    KeyBlockedError,
    KeyExpiredError,
    PermissionDeniedError,
    SportAPIDemoWarning,
    SportAPIError,
    TransportError,
)
from sportapi.polling import RECOMMENDED_INTERVALS

from .cache import SnapshotCache

T = TypeVar("T")

LineType = Literal["live", "prematch"]

ENV_KEY = "SPORTAPI_KEY"
ENV_BASE_URL = "SPORTAPI_BASE_URL"
ENV_LANGUAGE = "SPORTAPI_LANGUAGE"

GET_KEY_URL = "https://t.me/sportapinet_bot?start=github_sportapi_mcp"
SITE_URL = "https://sportapi.net"
DOCS_URL = "https://sportapi.net/docs/sport-line/getting-started/quick-start.html"

DEMO_NOTICE = (
    "DEMO DATA: no SPORTAPI_KEY/SPORTAPI_BASE_URL configured, so this is an example response "
    "from the SportAPI documentation (a snapshot from Aug-Oct 2026). Scores, times and odds are "
    "not current. Tell the user it is demo data. Live data needs an API key: " + GET_KEY_URL
)

DEMO_COVERAGE = (
    "Demo mode only has the example responses from the SportAPI documentation (English): "
    "list_sports and get_menu (live/prematch, sport_id=1 for details), list_countries(sport_id=1), "
    "list_tournaments(sport_id=1, country_id=1), list_live_matches(sport_id=1), "
    "list_prematch_matches(sport_id=1) without period filters, get_match(746146992, live), "
    "get_match(730321837, prematch), search_matches('Perth', live), "
    "search_matches('Manchester', prematch), "
    "top_matches (live, prematch, prematch with sport_id=1). "
    "For live data on every sport and match, get an API key: " + GET_KEY_URL
)

# Not a documented interval: `account` has none. A minute is plenty for a status check.
_ACCOUNT_TTL = 60.0


def api_line_type(line_type: str) -> str:
    """Tool vocabulary (``live``/``prematch``) -> API path segment (``live``/``line``)."""
    if line_type == "live":
        return LIVE
    if line_type in ("prematch", "line"):
        return LINE
    raise ToolError("line_type must be 'live' or 'prematch'.")


def label(line: str) -> str:
    return "Live" if line == LIVE else "Prematch"


class SportAPIService:
    """Owns the :class:`sportapi.AsyncSportAPI` client and the snapshot cache."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        lang: str | None = None,
        demo: bool | None = None,
        http_client: httpx.AsyncClient | None = None,
        cache: SnapshotCache | None = None,
    ) -> None:
        self.config_error: str | None = None
        self.cache = cache or SnapshotCache()
        lang = (lang or os.environ.get(ENV_LANGUAGE) or "en").strip() or "en"
        try:
            self.client: AsyncSportAPI | None = AsyncSportAPI(
                api_key, base_url, lang=lang, demo=demo, http_client=http_client
            )
        except ConfigurationError:
            self.client = None
            self.config_error = (
                f"SportAPI is misconfigured: live mode needs both {ENV_KEY} and {ENV_BASE_URL} "
                "(the personal base URL issued with the key, e.g. https://YOUR_API_DOMAIN). "
                f"Unset both to use demo data, or get access: {GET_KEY_URL}"
            )
        if self.client is not None and self.client.is_demo:
            self.client.lang = "en"  # demo responses exist in English only
            warnings.simplefilter("ignore", SportAPIDemoWarning)

    @property
    def is_demo(self) -> bool:
        return self.client is not None and self.client.is_demo

    @property
    def lang(self) -> str:
        return self.client.lang if self.client is not None else "en"

    async def aclose(self) -> None:
        if self.client is not None:
            await self.client.aclose()

    # -- calling the API -----------------------------------------------------------

    def api(self) -> AsyncSportAPI:
        if self.client is None:
            raise ToolError(self.config_error or "SportAPI client is not configured.")
        return self.client

    async def fetch(
        self,
        method: str,
        line: str | None,
        key: tuple[Any, ...],
        call: Callable[[AsyncSportAPI], Awaitable[T]],
        *,
        what: str,
        game_id: int | None = None,
    ) -> tuple[T, float]:
        """Run one API call through the snapshot cache and translate errors.

        ``method``/``line`` select the documented minimum interval.
        Returns ``(result, age_in_seconds)``.
        """
        api = self.api()
        if line is None:
            ttl = _ACCOUNT_TTL
        else:
            ttl = float(RECOMMENDED_INTERVALS.get(method, {}).get(line) or 30)
        try:
            return await self.cache.get((method, line, self.lang, *key), ttl, lambda: call(api))
        except SportAPIError as error:
            raise self._tool_error(error, what=what, line=line, game_id=game_id) from error
        except ValueError as error:  # parameter validation in the client
            raise ToolError(str(error)) from error

    def _tool_error(
        self, error: SportAPIError, *, what: str, line: str | None, game_id: int | None
    ) -> ToolError:
        if isinstance(error, DemoDataUnavailableError):
            return ToolError(f"{what} is not available in demo mode. {DEMO_COVERAGE}")
        if isinstance(error, GameFinishedError):
            return ToolError(
                f"Match {game_id} is no longer available under this game_id ({label(line or '')}). "
                "It may have moved to Live with a new game_id, been cancelled or ended; the API "
                "does not say which. Do not request this ID again: list current matches instead."
            )
        if isinstance(error, GameNotFoundError):
            return ToolError(
                f"No {label(line or '')} match with game_id {game_id}. Live and Prematch use "
                "different game_id values: take the ID from a current list or search result of "
                "the same line_type."
            )
        if isinstance(error, (KeyExpiredError, KeyBlockedError)):
            return ToolError(
                f"SportAPI: {error.message}. Access must be renewed or unblocked by the SportAPI "
                f"manager: {GET_KEY_URL}"
            )
        if isinstance(error, AccessRestrictedError):
            return ToolError(
                f"SportAPI: {error.message}. The key only works from the IP addresses or sites "
                "allowed for it; ask the SportAPI manager to allow this address."
            )
        if isinstance(error, AuthenticationError):
            return ToolError(
                f"SportAPI rejected the API key ({error.message}). Check {ENV_KEY} and "
                f"{ENV_BASE_URL} in the MCP server configuration."
            )
        if isinstance(error, PermissionDeniedError):
            return ToolError(
                f"SportAPI: {error.message}. The key does not include this sport, language or "
                "data; account_status shows what it includes."
            )
        if isinstance(error, TransportError) or (
            isinstance(error, HTTPStatusError) and error.retryable
        ):
            return ToolError(
                f"SportAPI is temporarily unreachable while requesting {what} ({error}). "
                "Wait a few seconds before trying again."
            )
        return ToolError(f"SportAPI error while requesting {what}: {error}")

    # -- result envelope -----------------------------------------------------------

    def envelope(
        self, age: float = 0.0, *, notice: str | None = None, **data: Any
    ) -> dict[str, Any]:
        """Common header of every tool result: where the data comes from and how fresh it is."""
        if self.is_demo:
            head: dict[str, Any] = {"source": "demo", "notice": notice or DEMO_NOTICE}
        else:
            head = {"source": "live", "as_of": _utc_now(age)}
            if age >= 1:
                head["cached_seconds"] = int(age)
        head.update(data)
        return head


def _utc_now(age: float) -> str:
    now = datetime.now(timezone.utc).timestamp() - age
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
