"""Every tool, called through an in-memory MCP client, in demo mode (no credentials)."""

from __future__ import annotations

import pytest
from mcp import Client

from .conftest import call

pytestmark = pytest.mark.anyio

BOT = "https://t.me/sportapinet_bot?start=github_sportapi_mcp"

TOOLS = {
    "list_sports",
    "get_menu",
    "list_countries",
    "list_tournaments",
    "list_live_matches",
    "list_prematch_matches",
    "get_match",
    "search_matches",
    "top_matches",
    "top_championships",
    "account_status",
}


async def test_lists_tools_with_descriptions_and_read_only_hints(demo_client: Client) -> None:
    tools = (await demo_client.list_tools()).tools
    assert {t.name for t in tools} == TOOLS
    for tool in tools:
        assert tool.description and len(tool.description) > 40, tool.name
        assert tool.annotations is not None and tool.annotations.read_only_hint is True
        for prop, schema in tool.input_schema.get("properties", {}).items():
            assert schema.get("description"), f"{tool.name}.{prop} has no description"


async def test_server_instructions_mention_demo(demo_client: Client) -> None:
    assert demo_client.instructions is not None
    assert '"source": "demo"' in demo_client.instructions


async def test_list_sports_is_labelled_demo(demo_client: Client) -> None:
    data, error = await call(demo_client, "list_sports")
    assert not error
    assert data["source"] == "demo"
    assert BOT in data["notice"]
    assert {"id": 1, "name": "Football", "matches": 48} in data["sports"]


async def test_list_sports_prematch(demo_client: Client) -> None:
    data, _ = await call(demo_client, "list_sports", line_type="prematch")
    assert data["line_type"] == "prematch"
    assert data["sports"][0]["name"] == "Football"


async def test_get_menu_summary_and_sport(demo_client: Client) -> None:
    summary, _ = await call(demo_client, "get_menu", line_type="live")
    football = next(s for s in summary["sports"] if s["id"] == 1)
    assert football["countries"] > 0 and football["tournaments"] >= football["countries"]
    assert "tournaments" not in str(summary["sports"][0].get("countries"))

    detail, _ = await call(demo_client, "get_menu", line_type="live", sport_id=1)
    assert detail["sport"]["name"] == "Football"
    names = {t.get("name") for c in detail["countries"] for t in c["tournaments"]}
    assert "Sri Lanka. Super League" in names


async def test_get_menu_unknown_sport(demo_client: Client) -> None:
    text, error = await call(demo_client, "get_menu", line_type="live", sport_id=99999)
    assert error
    assert "has no Live matches" in text and "Football (1)" in text


async def test_list_countries_and_tournaments(demo_client: Client) -> None:
    countries, _ = await call(demo_client, "list_countries", sport_id=1, line_type="prematch")
    assert any(c["name"] == "England" for c in countries["countries"])
    tournaments, _ = await call(
        demo_client, "list_tournaments", sport_id=1, country_id=1, line_type="prematch"
    )
    assert tournaments["tournaments"] and all("id" in t for t in tournaments["tournaments"])


async def test_list_live_matches_overview(demo_client: Client) -> None:
    data, _ = await call(demo_client, "list_live_matches")
    assert data["sports"] and data["top_matches"]
    assert "hint" in data
    assert all("odds" not in m for m in data["top_matches"])


async def test_list_live_matches_for_sport(demo_client: Client) -> None:
    data, _ = await call(demo_client, "list_live_matches", sport_id=1, limit=5)
    assert data["matches_total"] == 39 and data["matches_shown"] == 5
    first = data["tournaments"][0]["matches"][0]
    assert first["game_id"] == 746051530
    assert first["score"] == "0:1" and first["minute"] == 33
    assert first["odds"]["1X2"] == "W2 1.4 | X 4.65 | W1 7.47"
    assert len(first["odds"]) <= 2


async def test_list_live_matches_markets_filter_and_no_odds(demo_client: Client) -> None:
    data, _ = await call(
        demo_client, "list_live_matches", sport_id=1, markets=["Total"], max_markets_per_match=5
    )
    for group in data["tournaments"]:
        for match in group["matches"]:
            assert all("Total" in name for name in match.get("odds", {}))

    bare, _ = await call(demo_client, "list_live_matches", sport_id=1, include_odds=False)
    assert all("odds" not in m for g in bare["tournaments"] for m in g["matches"])


async def test_list_prematch_matches_top(demo_client: Client) -> None:
    data, _ = await call(demo_client, "list_prematch_matches", sport_id=1, limit=50)
    assert data["selection"] == "Top 50"
    assert data["matches_total"] == data["matches_shown"] == 50
    match = data["tournaments"][0]["matches"][0]
    assert match["match"] == "Kazakhstan — Faroe Islands"
    assert match["start"] == "2026-10-06T14:00Z"
    assert "score" not in match


@pytest.mark.parametrize(
    "arguments",
    [{"within_hours": 2}, {"day": 1}],
)
async def test_calendar_is_not_in_demo(demo_client: Client, arguments: dict[str, int]) -> None:
    text, error = await call(demo_client, "list_prematch_matches", sport_id=1, **arguments)
    assert error
    assert "not available in demo mode" in text and BOT in text


async def test_prematch_argument_validation(demo_client: Client) -> None:
    text, error = await call(
        demo_client, "list_prematch_matches", sport_id=1, within_hours=2, day=1
    )
    assert error and "either within_hours or day" in text
    text, error = await call(demo_client, "list_prematch_matches", sport_id=1, within_hours=3)
    assert error  # only 2, 4, 6 or 12 are documented


async def test_get_match_live(demo_client: Client) -> None:
    data, _ = await call(demo_client, "get_match", game_id=746146992, line_type="live")
    assert data["match"] == "Arsenal — Coventry City"
    assert data["score"] == "3:0" and data["minute"] == 56
    assert data["stats"]["Attacks"] == "61:54"
    assert data["markets_total"] == 49
    assert len(data["markets"]) == 15 and data["markets_omitted"] == 34
    assert any(s["name"] == "Corners" for s in data["sub_events"])
    assert data["live_tracker"] is True


async def test_get_match_markets_filter_rows_and_pointers(demo_client: Client) -> None:
    data, _ = await call(
        demo_client,
        "get_match",
        game_id=746146992,
        line_type="live",
        markets=["17"],
        include_pointers=True,
        include_stats=False,
    )
    assert "stats" not in data
    (total,) = data["markets"]
    assert total["name"] == "Total"
    assert total["odds"].startswith(
        "Over 3.5 1.23 [746146992|17|9|3.5] | Under 3.5 4.25 [746146992|17|10|3.5]; Over 4 "
    )


async def test_get_match_prematch_with_many_markets(demo_client: Client) -> None:
    data, _ = await call(
        demo_client,
        "get_match",
        game_id=730321837,
        line_type="prematch",
        markets=["1X2"],
        max_markets=1,
    )
    assert data["match"] == "Manchester City — Bournemouth"
    assert data["markets_total"] == 204
    assert data["markets"] == [{"id": 1, "name": "1X2", "odds": "W1 1.525 | X 5.08 | W2 6.15"}]
    assert "score" not in data


async def test_get_match_unknown_market_lists_names(demo_client: Client) -> None:
    data, _ = await call(
        demo_client, "get_match", game_id=746146992, line_type="live", markets=["no such"]
    )
    assert data["markets"] == []
    assert "Both Teams To Score" in data["markets_hint"]


async def test_get_match_not_in_demo(demo_client: Client) -> None:
    text, error = await call(demo_client, "get_match", game_id=1, line_type="live")
    assert error and "not available in demo mode" in text


async def test_search_both_lines_in_demo(demo_client: Client) -> None:
    data, _ = await call(demo_client, "search_matches", text="Manchester")
    assert data["not_in_demo"] == ["live"]
    assert any(m["match"] == "Hull City — Manchester United" for m in data["prematch"])
    assert all("odds" not in m for m in data["prematch"])


async def test_search_live(demo_client: Client) -> None:
    data, _ = await call(demo_client, "search_matches", text="perth", line_type="live")
    first = data["live"][0]
    assert first["match"] == "Armadale — Perth RedStar" and first["score"] == "0:3"


async def test_search_unknown_text_in_demo(demo_client: Client) -> None:
    text, error = await call(demo_client, "search_matches", text="Real Madrid")
    assert error and "'Perth' (live), 'Manchester' (prematch)" in text


async def test_top_matches(demo_client: Client) -> None:
    live, _ = await call(demo_client, "top_matches")
    assert len(live["matches"]) == 10 and "odds" not in live["matches"][0]
    full, _ = await call(demo_client, "top_matches", line_type="prematch", include_odds=True)
    assert any("odds" in m for m in full["matches"])
    sport, _ = await call(demo_client, "top_matches", line_type="prematch", sport_id=1)
    assert sport["matches"][0]["match"] == "Hull City — Manchester United"


async def test_top_matches_by_sport_is_prematch_only(demo_client: Client) -> None:
    text, error = await call(demo_client, "top_matches", line_type="live", sport_id=1)
    assert error and "Prematch only" in text


async def test_top_championships_not_in_demo(demo_client: Client) -> None:
    text, error = await call(demo_client, "top_championships")
    assert error and "not available in demo mode" in text


async def test_account_status_in_demo(demo_client: Client) -> None:
    data, _ = await call(demo_client, "account_status")
    assert data["mode"] == "demo"
    assert data["get_api_key"] == BOT
    assert "SPORTAPI_KEY" in data["setup"]


async def test_prompts(demo_client: Client) -> None:
    prompts = {p.name for p in (await demo_client.list_prompts()).prompts}
    assert prompts == {"live_betting_overview", "compare_match_markets"}

    overview = await demo_client.get_prompt("live_betting_overview", {"sport": "Tennis"})
    text = overview.messages[0].content.text  # type: ignore[union-attr]
    assert "Tennis" in text and "list_live_matches" in text

    compare = await demo_client.get_prompt(
        "compare_match_markets", {"match": "Arsenal", "markets": "1X2, Total"}
    )
    text = compare.messages[0].content.text  # type: ignore[union-attr]
    assert "['1X2', 'Total']" in text and "search_matches" in text
