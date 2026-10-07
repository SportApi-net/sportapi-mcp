"""Live mode with the HTTP layer mocked by respx: requests, caching and error messages."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx
from mcp import Client

from sportapi_mcp import SportAPIService, create_server
from sportapi_mcp.cache import SnapshotCache

from .conftest import call, demo_payload

pytestmark = pytest.mark.anyio

BASE = "https://api.example.com"
KEY = "test-key-0000"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def live_client(clock: FakeClock) -> AsyncIterator[Client]:
    service = SportAPIService(KEY, BASE, cache=SnapshotCache(clock=clock))
    assert not service.is_demo
    async with Client(create_server(service)) as client:
        yield client


def ok(body: Any, page: str = "/v1/events") -> httpx.Response:
    return httpx.Response(200, json={"status": 1, "page": page, "body": body})


@respx.mock
async def test_live_matches_request_and_envelope(live_client: Client) -> None:
    route = respx.get(f"{BASE}/v1/events/1/0/sub/50/live/en").mock(
        return_value=httpx.Response(
            200, json=demo_payload("events.sport-1.tournament-0.sub-50.live.en.json")
        )
    )
    data, error = await call(live_client, "list_live_matches", sport_id=1, limit=3)
    assert not error
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.headers["Package"] == KEY
    assert KEY not in str(request.url)
    assert data["source"] == "live" and "notice" not in data
    assert data["as_of"].endswith("Z")
    assert data["matches_shown"] == 3
    assert KEY not in str(data)


@respx.mock
async def test_odds_false_is_sent(live_client: Client) -> None:
    route = respx.get(f"{BASE}/v1/events/1/0/sub/50/line/en").mock(return_value=ok([]))
    data, _ = await call(live_client, "list_prematch_matches", sport_id=1, include_odds=False)
    assert route.calls[0].request.url.params["odds"] == "false"
    assert data["matches_total"] == 0 and data["tournaments"] == []


@respx.mock
async def test_repeated_calls_respect_minimum_interval(
    live_client: Client, clock: FakeClock
) -> None:
    route = respx.get(f"{BASE}/v1/event/746146992/group/live/en").mock(
        return_value=httpx.Response(
            200, json=demo_payload("event.game-746146992.group.live.en.json")
        )
    )
    await call(live_client, "get_match", game_id=746146992, line_type="live")
    clock.now += 3
    cached, _ = await call(
        live_client, "get_match", game_id=746146992, line_type="live", markets=["Total"]
    )
    assert route.call_count == 1  # Live `event`: at least 5 s between requests
    assert cached["cached_seconds"] == 3
    clock.now += 3
    fresh, _ = await call(live_client, "get_match", game_id=746146992, line_type="live")
    assert route.call_count == 2
    assert "cached_seconds" not in fresh


@respx.mock
async def test_calendar_request(live_client: Client) -> None:
    route = respx.get(f"{BASE}/v1/events/1/0/sub/50/line/4/0/en").mock(return_value=ok([]))
    data, _ = await call(live_client, "list_prematch_matches", sport_id=1, within_hours=4)
    assert route.called
    assert data["selection"] == "starting within 4 h"
    day = respx.get(f"{BASE}/v1/events/1/0/sub/50/line/0/2/en").mock(return_value=ok([]))
    data, _ = await call(live_client, "list_prematch_matches", sport_id=1, day=2)
    assert day.called and data["selection"] == "day 2 (Kyiv time)"


@respx.mock
async def test_full_line_and_esports_parameters(live_client: Client) -> None:
    route = respx.get(f"{BASE}/v1/events/1/0/sub/50/line/en").mock(return_value=ok([]))
    data, _ = await call(live_client, "list_prematch_matches", sport_id=1, full_line=True)
    assert route.calls[0].request.url.params["match"] == "all"
    assert data["selection"] == "full line"
    sports = respx.get(f"{BASE}/v1/sports/live/en").mock(return_value=ok([], "/v1/sports"))
    await call(live_client, "list_sports", esports=True)
    assert sports.calls[0].request.url.params["cybersport"] == "true"


@respx.mock
async def test_search_both_lines(live_client: Client) -> None:
    live = respx.get(f"{BASE}/v1/search/live/en/Real%20Madrid").mock(
        return_value=ok([], "/v1/search")
    )
    line = respx.get(f"{BASE}/v1/search/line/en/Real%20Madrid").mock(
        return_value=httpx.Response(200, json=demo_payload("search.query-manchester.line.en.json"))
    )
    data, _ = await call(live_client, "search_matches", text="Real Madrid")
    assert live.called and line.called
    assert data["live"] == [] and data["prematch"]


@respx.mock
async def test_top_championships(live_client: Client) -> None:
    respx.get(f"{BASE}/v1/topchampionships/line/en").mock(
        return_value=ok(
            [
                {
                    "position": 2,
                    "tournament_id": 110163,
                    "tournament_name": "Italy. Serie A",
                    "sport_id": 1,
                    "sport_name": "Football",
                    "country_id": 79,
                    "country_name": "Italy",
                    "counter": 10,
                },
                {
                    "position": 1,
                    "tournament_id": 88637,
                    "tournament_name": "England. Premier League",
                    "sport_id": 1,
                    "sport_name": "Football",
                    "country_id": 231,
                    "country_name": "England",
                    "counter": 10,
                },
            ],
            "/v1/topchampionships",
        )
    )
    data, _ = await call(live_client, "top_championships")
    assert [c["tournament"] for c in data["championships"]] == [
        "England. Premier League",
        "Italy. Serie A",
    ]


@respx.mock
async def test_account_status(live_client: Client) -> None:
    respx.get(f"{BASE}/v1/account").mock(
        return_value=ok(
            {
                "client": {"public_id": "c_1", "name": "Example Ltd"},
                "your_ip": "203.0.113.10",
                "keys": [
                    {
                        "key": "0000",
                        "current": True,
                        "type": "trial",
                        "status": "active",
                        "label": None,
                        "starts_at": None,
                        "expires_at": "2026-10-09T00:00:00Z",
                        "days_left": 2,
                        "active": True,
                        "sports": [1, 3],
                        "languages": ["en"],
                        "last_used_at": None,
                        "access_mode": "ip",
                        "allowed_ips": ["203.0.113.10"],
                        "allowed_domains": [],
                        "usage_7d": [{"date": "2026-10-06", "requests": 1200}],
                    }
                ],
            },
            "/v1/account",
        )
    )
    data, _ = await call(live_client, "account_status")
    assert data["mode"] == "live"
    key = data["current_key"]
    assert key["key_ends_with"] == "0000" and key["days_left"] == 2
    assert key["sports"] == [1, 3] and key["requests_7d"] == {"2026-10-06": 1200}
    assert data["other_keys"] == 0


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"error_code": 100, "error_message": "Invalid Package"}, "rejected the API key"),
        ({"error_code": 100, "error_message": "Package has expired"}, "renewed"),
        ({"error_code": 100, "error_message": "Access denied"}, "does not include this sport"),
        (
            {
                "error_code": 100,
                "error_message": "Access from IP 203.0.113.10 is not allowed for this Package",
            },
            "allow this address",
        ),
    ],
)
@respx.mock
async def test_api_errors_become_actionable_messages(
    live_client: Client, payload: dict[str, Any], expected: str
) -> None:
    respx.get(f"{BASE}/v1/menu/live/en").mock(return_value=httpx.Response(200, json=payload))
    text, error = await call(live_client, "get_menu")
    assert error
    assert expected in text
    assert KEY not in text


@respx.mock
async def test_game_finished(live_client: Client) -> None:
    respx.get(f"{BASE}/v1/event/42/group/line/en").mock(
        return_value=ok({"message": "Game id finished"}, "/v1/event")
    )
    text, error = await call(live_client, "get_match", game_id=42, line_type="prematch")
    assert error
    assert "no longer available" in text and "Do not request this ID again" in text


@respx.mock
async def test_game_not_found(live_client: Client) -> None:
    respx.get(f"{BASE}/v1/event/42/group/live/en").mock(
        return_value=ok({"message": "Game not found"}, "/v1/event")
    )
    text, error = await call(live_client, "get_match", game_id=42, line_type="live")
    assert error and "different game_id values" in text


@respx.mock
async def test_network_error_is_temporary(live_client: Client) -> None:
    respx.get(f"{BASE}/v1/sports/live/en").mock(side_effect=httpx.ConnectError("boom"))
    text, error = await call(live_client, "list_sports")
    assert error and "temporarily unreachable" in text


@respx.mock
async def test_errors_are_not_cached(live_client: Client) -> None:
    route = respx.get(f"{BASE}/v1/sports/live/en").mock(
        side_effect=[httpx.ConnectError("boom"), ok([{"id": 1, "name": "Football", "counter": 3}])]
    )
    _, error = await call(live_client, "list_sports")
    assert error
    data, error = await call(live_client, "list_sports")
    assert not error and data["sports"] == [{"id": 1, "name": "Football", "matches": 3}]
    assert route.call_count == 2


async def test_half_configured_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPORTAPI_KEY", KEY)
    service = SportAPIService()
    assert service.config_error and "SPORTAPI_BASE_URL" in service.config_error
    async with Client(create_server(service)) as client:
        text, error = await call(client, "list_sports")
        assert error and "misconfigured" in text and KEY not in text
        text, error = await call(client, "account_status")
        assert error and "misconfigured" in text


async def test_language_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPORTAPI_LANGUAGE", "de")
    with respx.mock:
        route = respx.get(f"{BASE}/v1/sports/live/de").mock(return_value=ok([], "/v1/sports"))
        async with Client(create_server(SportAPIService(KEY, BASE))) as client:
            await call(client, "list_sports")
        assert route.called


async def test_demo_mode_ignores_language(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPORTAPI_LANGUAGE", "de")
    async with Client(create_server(SportAPIService())) as client:
        data, error = await call(client, "list_sports")
        assert not error and data["source"] == "demo"
