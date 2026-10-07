from __future__ import annotations

from sportapi import Market, Match

from sportapi_mcp import formatting as fmt


def outcome(name: str, rate: float, *, blocked: bool = False, pointer: str = "") -> dict:
    return {"oc_name": name, "oc_rate": rate, "oc_block": blocked, "oc_pointer": pointer}


def test_flat_market_line_and_blocked_selection() -> None:
    market = Market.from_dict(
        {
            "group_id": 1,
            "group_name": "1X2",
            "oc_list": [outcome("W1", 2.5), outcome("X", 3.1, blocked=True), outcome("W2", 2.8)],
        }
    )
    assert fmt.market_odds_text(market) == "W1 2.5 | X blocked | W2 2.8"


def test_column_market_is_rendered_row_by_row() -> None:
    market = Market.from_dict(
        {
            "group_id": 17,
            "group_name": "Total",
            "oc_list": [
                [outcome("Over 2.5", 1.8, pointer="p1"), outcome("Over 3.5", 2.9)],
                [outcome("Under 2.5", 2.0)],
            ],
        }
    )
    assert fmt.market_odds_text(market) == "Over 2.5 1.8 | Under 2.5 2; Over 3.5 2.9"
    assert fmt.market_odds_text(market, pointers=True).startswith("Over 2.5 1.8 [p1] | ")


def test_select_markets_by_name_fragment_or_id() -> None:
    markets = [
        Market.from_dict({"group_id": gid, "group_name": name, "oc_list": []})
        for gid, name in [(1, "1X2"), (17, "Total"), (99, "Asian Total"), (2, "Handicap")]
    ]
    chosen, omitted = fmt.select_markets(markets, ["total"], None)
    assert [m.id for m in chosen] == [17, 99] and omitted == 0
    chosen, _ = fmt.select_markets(markets, ["2", " "], None)
    assert [m.id for m in chosen] == [2]
    chosen, omitted = fmt.select_markets(markets, None, 1)
    assert [m.id for m in chosen] == [1] and omitted == 3


def test_odds_map_merges_markets_with_the_same_name() -> None:
    markets = [
        Market.from_dict({"group_id": 9429, "group_name": "Combo", "oc_list": [outcome("A", 2)]}),
        Market.from_dict({"group_id": 9429, "group_name": "Combo", "oc_list": [outcome("B", 3)]}),
    ]
    assert fmt.odds_map(markets, None, None) == {"Combo": "A 2 | B 3"}


def test_match_summary_drops_empty_fields() -> None:
    match = Match.from_dict(
        {
            "game_id": 5,
            "opp_1_name": "Home",
            "opp_2_name": "Away",
            "game_start": 1787338800,
            "score_full": "1:0",
            "timer": 125,
            "period_name": "",
        }
    )
    assert fmt.match_summary(match, live=True, context=False) == {
        "game_id": 5,
        "match": "Home — Away",
        "start": "2026-08-21T19:00Z",
        "score": "1:0",
        "minute": 2,
    }
    prematch = fmt.match_summary(match, live=False, context=False)
    assert "score" not in prematch and "minute" not in prematch


def test_iso_time() -> None:
    assert fmt.iso_time(0) is None
    assert fmt.iso_time(1787338800) == "2026-08-21T19:00Z"
