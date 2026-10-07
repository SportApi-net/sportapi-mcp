"""Compact, token-efficient views of SportAPI models for language models.

The raw Sport Line API responses are large (a detailed Prematch match can carry
200+ markets). These helpers keep what an assistant needs to answer questions
— names, IDs, times, scores, odds — and drop empty fields, icons and legacy data.

Odds are rendered as short strings, for example ``"W1 2.657 | X 2.996 | W2 3.115"``.
In the detailed ``event`` (``group``) format the API arranges selections in
columns; they are rendered row by row (``"Over 2.5 1.8 | Under 2.5 2.0; ..."``)
so that lines such as Over/Under of the same total stay next to each other.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from itertools import zip_longest
from typing import Any

from sportapi import Country, Market, Match, Outcome, Sport, Tournament, TournamentEvents

JSONDict = dict[str, Any]


def dumps(data: Any) -> str:
    """Serialise a tool result: compact JSON, Unicode kept as is."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def iso_time(timestamp: int | None) -> str | None:
    """Unix seconds -> ``2026-08-21T19:00Z`` (UTC, minute precision)."""
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _compact(data: JSONDict) -> JSONDict:
    """Drop keys whose value is ``None``, ``""``, ``[]`` or ``{}``."""
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}


# --- odds -----------------------------------------------------------------------


def format_odds(value: float) -> str:
    return f"{value:g}"


def outcome_text(outcome: Outcome, *, pointers: bool = False) -> str:
    text = outcome.name.strip() or "?"
    text += " blocked" if outcome.blocked else " " + format_odds(outcome.odds)
    if pointers and outcome.pointer:
        text += f" [{outcome.pointer}]"
    return text


def market_odds_text(market: Market, *, pointers: bool = False) -> str:
    """All selections of a market as one line, in API order."""
    if market.column_outcomes:
        rows = zip_longest(*market.column_outcomes)
        return "; ".join(
            " | ".join(outcome_text(o, pointers=pointers) for o in row if o is not None)
            for row in rows
        )
    return " | ".join(outcome_text(o, pointers=pointers) for o in market.outcomes)


def _matches_filter(market: Market, wanted: Sequence[str]) -> bool:
    name = market.name.strip().casefold()
    for term in wanted:
        term = term.strip()
        if not term:
            continue
        if term.isdigit():  # a market id (group_id), never a name fragment
            if int(term) == market.id:
                return True
        elif term.casefold() in name:
            return True
    return False


def select_markets(
    markets: Sequence[Market], wanted: Sequence[str] | None, limit: int | None
) -> tuple[list[Market], int]:
    """Filter markets by name substring or ``group_id`` and cap their number.

    Returns the selected markets (API order kept) and how many matching markets
    were left out because of ``limit``.
    """
    chosen = [m for m in markets if not wanted or _matches_filter(m, wanted)]
    if limit is not None and len(chosen) > limit:
        return chosen[:limit], len(chosen) - limit
    return chosen, 0


def odds_map(
    markets: Sequence[Market], wanted: Sequence[str] | None, limit: int | None
) -> dict[str, str]:
    """``{market name: odds line}`` for match lists (markets sharing a name are merged)."""
    result: dict[str, str] = {}
    selected, _ = select_markets(markets, wanted, limit)
    for market in selected:
        line = market_odds_text(market)
        if not line:
            continue
        name = market.name or f"group {market.id}"
        result[name] = f"{result[name]} | {line}" if name in result else line
    return result


# --- matches --------------------------------------------------------------------


def live_state(match: Match) -> JSONDict:
    """Score, period and minute of a Live match (empty values dropped)."""
    return _compact(
        {
            "score": match.score_full,
            "periods": match.score_period,
            "period": match.period_name,
            "minute": match.timer // 60 if match.timer else None,
            "extra_time": match.extra_time,
            "finished": True if match.finale else None,
        }
    )


def match_summary(
    match: Match,
    *,
    live: bool,
    context: bool = True,
    odds: bool = True,
    markets: Sequence[str] | None = None,
    max_markets: int | None = 3,
) -> JSONDict:
    """One match as a small dict. ``context`` adds sport and tournament names."""
    data: JSONDict = {
        "game_id": match.game_id,
        "match": match.name,
        "start": iso_time(match.game_start),
    }
    if context:
        data["sport"] = match.sport_name
        data["sport_id"] = match.sport_id
        data["tournament"] = match.tournament_name
        data["tournament_id"] = match.tournament_id
    if match.game_dop_name:
        data["note"] = match.game_dop_name
    if live:
        data.update(live_state(match))
    if odds and match.markets:
        data["odds"] = odds_map(match.markets, markets, max_markets)
    return _compact(data)


def tournament_groups(
    groups: Iterable[TournamentEvents],
    *,
    live: bool,
    limit: int,
    odds: bool,
    markets: Sequence[str] | None,
    max_markets: int | None,
) -> tuple[list[JSONDict], int, int]:
    """Matches grouped by tournament, capped at ``limit`` matches.

    Returns ``(groups, shown, total)``.
    """
    result: list[JSONDict] = []
    shown = total = 0
    for group in groups:
        total += len(group.matches)
        room = limit - shown
        if room <= 0:
            continue
        items = [
            match_summary(
                m, live=live, context=False, odds=odds, markets=markets, max_markets=max_markets
            )
            for m in group.matches[:room]
        ]
        if items:
            shown += len(items)
            result.append(
                {
                    "tournament": group.tournament_name,
                    "tournament_id": group.tournament_id,
                    "matches": items,
                }
            )
    return result, shown, total


def match_details(
    match: Match,
    *,
    live: bool,
    markets: Sequence[str] | None,
    max_markets: int,
    stats: bool,
    pointers: bool,
) -> JSONDict:
    """Detailed view of one ``event`` response."""
    data: JSONDict = {
        "game_id": match.game_id,
        "match": match.name,
        "sport": match.sport_name,
        "sport_id": match.sport_id,
        "country": match.country_name,
        "tournament": match.tournament_name,
        "tournament_id": match.tournament_id,
        "start": iso_time(match.game_start),
    }
    if match.game_dop_name:
        data["note"] = match.game_dop_name
    if match.is_sub_game:
        data["main_game_id"] = match.game_mid
    if live:
        data.update(live_state(match))
    if stats and match.stats:
        data["stats"] = {s.name or str(s.id): f"{s.opp1}:{s.opp2}" for s in match.stats}
    if match.event_plan:
        data["participants"] = [
            f"{p.opp_1_name} — {p.opp_2_name}" for p in match.event_plan if p.opp_1_name
        ]
    selected, omitted = select_markets(match.markets, markets, max_markets)
    data["markets_total"] = len(match.markets)
    data["markets"] = [
        {"id": m.id, "name": m.name, "odds": market_odds_text(m, pointers=pointers)}
        for m in selected
    ]
    if omitted:
        data["markets_omitted"] = omitted
    if markets and not selected:
        data["markets_hint"] = "No market matched the filter. Available market names: " + ", ".join(
            dict.fromkeys(m.name for m in match.markets)
        )
    if match.sub_games:
        data["sub_events"] = [
            _compact({"game_id": s.game_id, "name": s.name}) for s in match.sub_games
        ]
    if match.has_tracker:
        data["live_tracker"] = True
    if match.has_video:
        data["video"] = True
    return _compact(data) | {"markets": data["markets"]}


# --- navigation -------------------------------------------------------------------


def sport_row(sport: Sport) -> JSONDict:
    return {"id": sport.id, "name": sport.name, "matches": sport.counter}


def tournament_row(tournament: Tournament) -> JSONDict:
    return _compact({"id": tournament.id, "name": tournament.name, "matches": tournament.counter})


def country_row(country: Country, *, tournaments: bool) -> JSONDict:
    row: JSONDict = {"id": country.id, "name": country.name, "matches": country.counter}
    if tournaments:
        row["tournaments"] = [tournament_row(t) for t in country.tournaments]
    return row
