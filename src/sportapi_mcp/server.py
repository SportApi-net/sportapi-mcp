"""The SportAPI MCP server: tools and prompts over the Sport Line API."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from sportapi import LINE, LIVE, AsyncSportAPI, Match

from . import formatting as fmt
from ._version import __version__
from .service import GET_KEY_URL, SITE_URL, LineType, SportAPIService, api_line_type, label

INSTRUCTIONS = """\
SportAPI tools return sports data from the SportAPI Sport Line API: Live (in-play) and \
Prematch (upcoming) matches, scores, live statistics and betting odds.

How to navigate:
- IDs (sport_id, tournament_id, game_id) must come from a current tool result; never guess them. \
Football is sport_id 1.
- list_sports / get_menu -> list_live_matches or list_prematch_matches -> get_match for full odds.
- Live and Prematch are separate: the same fixture has a different game_id in each. \
Call get_match with the line_type the game_id came from.
- Every result is a snapshot. Repeated calls within the documented minimum interval return the \
cached snapshot, so do not call a tool in a loop to "watch" a match.

If a result has "source": "demo", it is example data from the SportAPI documentation, not live: \
say so to the user. Odds are information, not betting advice.
"""

_F = TypeVar("_F", bound=Callable[..., Any])

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True, idempotent_hint=True)

LineParam = Annotated[
    LineType,
    Field(description="'live' = matches in progress, 'prematch' = matches not started yet."),
]
SportParam = Annotated[
    int, Field(ge=0, description="sport_id from list_sports or get_menu (1 = Football).")
]
MarketsParam = Annotated[
    list[str] | None,
    Field(
        description=(
            "Only show these markets: case-insensitive name fragments (e.g. 'Total', '1X2', "
            "'Handicap') or numeric market ids (group_id). Omit for the default markets."
        )
    ),
]
EsportsParam = Annotated[
    bool, Field(description="Esports instead of traditional sports (SportAPI cybersport mode).")
]
OddsParam = Annotated[
    bool, Field(description="Include the main odds. False makes the response much smaller.")
]
MaxMarketsParam = Annotated[
    int, Field(ge=0, le=20, description="Maximum markets shown per match (API order).")
]
LimitParam = Annotated[int, Field(ge=1, le=200, description="Maximum matches to return.")]


def create_server(service: SportAPIService | None = None) -> MCPServer[Any]:
    """Build the MCP server. ``service`` is injectable for tests."""
    svc = service or SportAPIService()

    @asynccontextmanager
    async def lifespan(_: MCPServer[Any]) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await svc.aclose()

    mcp: MCPServer[Any] = MCPServer(
        "sportapi",
        title="SportAPI",
        description="Live and Prematch sports odds, scores and statistics from SportAPI.",
        instructions=INSTRUCTIONS,
        website_url=SITE_URL,
        version=__version__,
        lifespan=lifespan,
        log_level="WARNING",
    )

    def tool(fn: _F) -> _F:
        """Register a read-only tool; the docstring (dedented) is its description."""
        return mcp.tool(
            description=inspect.cleandoc(fn.__doc__ or ""),
            annotations=READ_ONLY,
            structured_output=False,
        )(fn)

    def prompt(title: str) -> Callable[[_F], _F]:
        def register(fn: _F) -> _F:
            return mcp.prompt(title=title, description=inspect.cleandoc(fn.__doc__ or ""))(fn)

        return register

    # -- navigation --------------------------------------------------------------------

    @tool
    async def list_sports(line_type: LineParam = "live", esports: EsportsParam = False) -> str:
        """List the sports that have Live or Prematch matches right now, with match counts.

        Start here to get a sport_id. Sports without matches are not listed.
        """
        line = api_line_type(line_type)
        sports, age = await svc.fetch(
            "sports",
            line,
            ("sports", esports),
            lambda api: api.sports(line, cybersport=esports),
            what=f"{label(line)} sports",
        )
        return fmt.dumps(
            svc.envelope(
                age,
                line_type=line_type,
                sports=[fmt.sport_row(s) for s in sports],
            )
        )

    @tool
    async def get_menu(
        line_type: LineParam = "live",
        sport_id: Annotated[
            int | None,
            Field(
                ge=0,
                description="Show the countries and tournaments of this sport. Omit for a summary.",
            ),
        ] = None,
        esports: EsportsParam = False,
    ) -> str:
        """Navigation tree sport -> country -> tournament for Live or Prematch.

        Without sport_id: every sport with its number of matches, countries and tournaments.
        With sport_id: that sport's countries and tournaments (ids and match counts), to pick a
        tournament_id for list_live_matches / list_prematch_matches.
        """
        line = api_line_type(line_type)
        menu, age = await svc.fetch(
            "menu",
            line,
            ("menu", esports),
            lambda api: api.menu(line, cybersport=esports),
            what=f"the {label(line)} menu",
        )
        if sport_id is None:
            rows = [
                fmt.sport_row(s)
                | {
                    "countries": len(s.countries),
                    "tournaments": sum(len(c.tournaments) for c in s.countries),
                }
                for s in menu
            ]
            return fmt.dumps(svc.envelope(age, line_type=line_type, sports=rows))
        sport = next((s for s in menu if s.id == sport_id), None)
        if sport is None:
            available = ", ".join(f"{s.name} ({s.id})" for s in menu)
            raise ToolError(
                f"Sport {sport_id} has no {label(line)} matches right now. "
                f"Sports with matches: {available or 'none'}."
            )
        return fmt.dumps(
            svc.envelope(
                age,
                line_type=line_type,
                sport=fmt.sport_row(sport),
                countries=[fmt.country_row(c, tournaments=True) for c in sport.countries],
            )
        )

    @tool
    async def list_countries(sport_id: SportParam, line_type: LineParam = "live") -> str:
        """List the countries (regions) that have matches in one sport, with match counts."""
        line = api_line_type(line_type)
        countries, age = await svc.fetch(
            "countries",
            line,
            ("countries", sport_id),
            lambda api: api.countries(sport_id, line),
            what=f"{label(line)} countries of sport {sport_id}",
        )
        return fmt.dumps(
            svc.envelope(
                age,
                line_type=line_type,
                sport_id=sport_id,
                countries=[fmt.country_row(c, tournaments=False) for c in countries],
            )
        )

    @tool
    async def list_tournaments(
        sport_id: SportParam,
        country_id: Annotated[int, Field(ge=0, description="country id from list_countries.")],
        line_type: LineParam = "live",
        esports: EsportsParam = False,
    ) -> str:
        """List the tournaments of one sport and country that have matches, with match counts."""
        line = api_line_type(line_type)
        tournaments, age = await svc.fetch(
            "tournaments",
            line,
            ("tournaments", sport_id, country_id, esports),
            lambda api: api.tournaments(sport_id, country_id, line, cybersport=esports),
            what=f"{label(line)} tournaments of sport {sport_id}, country {country_id}",
        )
        return fmt.dumps(
            svc.envelope(
                age,
                line_type=line_type,
                sport_id=sport_id,
                country_id=country_id,
                tournaments=[fmt.tournament_row(t) for t in tournaments],
            )
        )

    # -- matches -------------------------------------------------------------------------

    @tool
    async def list_live_matches(
        sport_id: Annotated[
            int | None,
            Field(
                ge=0,
                description=(
                    "sport_id (1 = Football). Omit for an overview: live sports with counts "
                    "plus the top live matches."
                ),
            ),
        ] = None,
        tournament_id: Annotated[
            int, Field(ge=0, description="Only this tournament (from get_menu); 0 = all.")
        ] = 0,
        markets: MarketsParam = None,
        max_markets_per_match: MaxMarketsParam = 2,
        include_odds: OddsParam = True,
        limit: LimitParam = 25,
        esports: EsportsParam = False,
    ) -> str:
        """Live (in-play) matches with score, period, minute and main odds, grouped by tournament.

        Use get_match with a game_id from here (line_type 'live') for all markets and live stats.
        """
        if sport_id is None:
            sports, age1 = await svc.fetch(
                "sports",
                LIVE,
                ("sports", esports),
                lambda api: api.sports(LIVE, cybersport=esports),
                what="Live sports",
            )
            top, age2 = await svc.fetch(
                "topmatches",
                LIVE,
                ("topmatches", False),
                lambda api: api.topmatches(LIVE),
                what="top Live matches",
            )
            return fmt.dumps(
                svc.envelope(
                    max(age1, age2),
                    line_type="live",
                    sports=[fmt.sport_row(s) for s in sports],
                    top_matches=[fmt.match_summary(m, live=True, odds=False) for m in top],
                    hint="Pass sport_id to list every live match of a sport with odds.",
                )
            )
        groups, age = await svc.fetch(
            "events",
            LIVE,
            ("events", sport_id, tournament_id, esports, include_odds),
            lambda api: api.events(
                sport_id,
                LIVE,
                tournament_id=tournament_id,
                cybersport=esports,
                odds=include_odds,
            ),
            what=f"Live matches of sport {sport_id}",
        )
        items, shown, total = fmt.tournament_groups(
            groups,
            live=True,
            limit=limit,
            odds=include_odds,
            markets=markets,
            max_markets=max_markets_per_match,
        )
        return fmt.dumps(
            svc.envelope(
                age,
                line_type="live",
                sport_id=sport_id,
                matches_total=total,
                matches_shown=shown,
                tournaments=items,
            )
        )

    @tool
    async def list_prematch_matches(
        sport_id: SportParam,
        tournament_id: Annotated[
            int,
            Field(ge=0, description="Only this tournament (from get_menu); 0 = whole sport."),
        ] = 0,
        within_hours: Annotated[
            Literal[2, 4, 6, 12] | None,
            Field(description="Only matches starting within the next 2, 4, 6 or 12 hours."),
        ] = None,
        day: Annotated[
            int | None,
            Field(
                ge=0,
                le=5,
                description=(
                    "Only matches on one day: 0 = today, 1 = tomorrow ... 5. Days follow Kyiv "
                    "time (Europe/Kyiv)."
                ),
            ),
        ] = None,
        full_line: Annotated[
            bool,
            Field(
                description=(
                    "With tournament_id 0: the sport's whole line instead of the 'Top' "
                    "selection of 50 matches."
                )
            ),
        ] = False,
        markets: MarketsParam = None,
        max_markets_per_match: MaxMarketsParam = 2,
        include_odds: OddsParam = True,
        limit: LimitParam = 25,
        esports: EsportsParam = False,
    ) -> str:
        """Upcoming (Prematch) matches with start time and main odds, grouped by tournament.

        For a whole sport (tournament_id 0) SportAPI returns its 'Top' selection of 50 matches
        (top leagues first, then by start time). Use within_hours or day for a schedule.
        Use get_match with a game_id from here (line_type 'prematch') for all markets.
        """
        if within_hours is not None and day is not None:
            raise ToolError("Use either within_hours or day, not both.")
        calendar = within_hours is not None or day is not None
        if calendar and (esports or full_line):
            raise ToolError("within_hours/day cannot be combined with esports or full_line.")
        if full_line and tournament_id:
            raise ToolError("full_line only applies to a whole sport (tournament_id 0).")
        if calendar:
            hours, days = within_hours or 0, day or 0
            groups, age = await svc.fetch(
                "events_by_period",
                LINE,
                ("calendar", sport_id, tournament_id, hours, days, include_odds),
                lambda api: api.events_by_period(
                    sport_id,
                    tournament_id=tournament_id,
                    hours=hours,
                    days=days,
                    odds=include_odds,
                ),
                what="the Prematch match calendar",
            )
            selection = (
                f"starting within {within_hours} h" if within_hours else f"day {day} (Kyiv time)"
            )
        else:
            groups, age = await svc.fetch(
                "events",
                LINE,
                ("events", sport_id, tournament_id, esports, full_line, include_odds),
                lambda api: api.events(
                    sport_id,
                    LINE,
                    tournament_id=tournament_id,
                    cybersport=esports,
                    full_line=full_line,
                    odds=include_odds,
                ),
                what=f"Prematch matches of sport {sport_id}",
            )
            if tournament_id:
                selection = "tournament"
            elif full_line or esports:
                selection = "full line"
            else:
                selection = "Top 50"
        items, shown, total = fmt.tournament_groups(
            groups,
            live=False,
            limit=limit,
            odds=include_odds,
            markets=markets,
            max_markets=max_markets_per_match,
        )
        return fmt.dumps(
            svc.envelope(
                age,
                line_type="prematch",
                sport_id=sport_id,
                selection=selection,
                matches_total=total,
                matches_shown=shown,
                tournaments=items,
            )
        )

    @tool
    async def get_match(
        game_id: Annotated[
            int, Field(ge=0, description="game_id from a match list, search or sub_events.")
        ],
        line_type: Annotated[
            LineType,
            Field(description="The line type the game_id came from ('live' or 'prematch')."),
        ],
        markets: MarketsParam = None,
        max_markets: Annotated[
            int, Field(ge=1, le=300, description="Maximum markets to return (API order).")
        ] = 15,
        include_stats: Annotated[
            bool, Field(description="Include live statistics (attacks, shots, xG...).")
        ] = True,
        include_pointers: Annotated[
            bool,
            Field(
                description=(
                    "Append each selection's oc_pointer code (needed only for bet placement "
                    "systems)."
                )
            ),
        ] = False,
    ) -> str:
        """Full details of one match: score, live statistics, all betting markets and odds,
        and its sub-events (halves, corners, cards...).

        A match can have hundreds of markets: filter with `markets` (e.g. ["1X2", "Total"]).
        Odds are decimal; 'blocked' means the selection is suspended. Sub-events have their
        own game_id: call get_match again with it and the same line_type.
        """
        line = api_line_type(line_type)
        match, age = await svc.fetch(
            "event",
            line,
            ("event", game_id),
            lambda api: api.event(game_id, line),
            what=f"{label(line)} match {game_id}",
            game_id=game_id,
        )
        details = fmt.match_details(
            match,
            live=line == LIVE,
            markets=markets,
            max_markets=max_markets,
            stats=include_stats,
            pointers=include_pointers,
        )
        return fmt.dumps(svc.envelope(age, line_type=line_type, **details))

    @tool
    async def search_matches(
        text: Annotated[
            str,
            Field(
                min_length=2,
                max_length=100,
                description="Full or partial team / participant name, e.g. 'Manchester'.",
            ),
        ],
        line_type: Annotated[
            Literal["live", "prematch", "both"],
            Field(description="Where to search; 'both' searches Live and Prematch."),
        ] = "both",
        limit: Annotated[int, Field(ge=1, le=50, description="Maximum results per line.")] = 15,
    ) -> str:
        """Find matches by team or participant name. Returns game_id, teams, tournament, start
        time and (Live) score; use get_match for odds."""
        wanted = ["live", "prematch"] if line_type == "both" else [line_type]
        results: dict[str, Any] = {}
        missing: list[str] = []
        oldest = 0.0

        def searcher(line: str) -> Callable[[AsyncSportAPI], Awaitable[list[Match]]]:
            return lambda api: api.search(text, line)

        for kind in wanted:
            line = api_line_type(kind)
            try:
                found, age = await svc.fetch(
                    "search",
                    line,
                    ("search", text.strip()),
                    searcher(line),
                    what=f"{label(line)} search for {text!r}",
                )
            except ToolError:
                if svc.is_demo and line_type == "both":
                    missing.append(kind)
                    continue
                raise
            oldest = max(oldest, age)
            results[kind] = [
                fmt.match_summary(m, live=line == LIVE, odds=False) for m in found[:limit]
            ]
        if missing and not results:
            raise ToolError(
                f"Search for {text!r} is not available in demo mode. "
                "Demo searches: 'Perth' (live), 'Manchester' (prematch). "
                f"Live search across all teams needs an API key: {GET_KEY_URL}"
            )
        data: dict[str, Any] = {"query": text, **results}
        if missing:
            data["not_in_demo"] = missing
        if all(not v for v in results.values()):
            data["hint"] = "No matches found. Try a shorter part of the team name."
        return fmt.dumps(svc.envelope(oldest, **data))

    # -- curated selections ------------------------------------------------------------------

    @tool
    async def top_matches(
        line_type: LineParam = "live",
        sport_id: Annotated[
            int | None,
            Field(ge=0, description="Prematch only: top matches of this sport instead of all."),
        ] = None,
        include_odds: Annotated[
            bool, Field(description="Include a short list of main odds per match.")
        ] = False,
        max_markets_per_match: MaxMarketsParam = 2,
    ) -> str:
        """SportAPI's selection of up to 10 most popular matches right now (all sports, or one
        sport for Prematch). A quick answer to 'what are the big games?'."""
        line = api_line_type(line_type)
        if sport_id is not None:
            if line == LIVE:
                raise ToolError(
                    "Per-sport top matches exist for Prematch only. For Live use "
                    "list_live_matches(sport_id) or top_matches without sport_id."
                )
            matches, age = await svc.fetch(
                "toplist",
                LINE,
                ("toplist", sport_id, include_odds),
                lambda api: api.toplist(sport_id, full=include_odds),
                what=f"top Prematch matches of sport {sport_id}",
            )
        else:
            matches, age = await svc.fetch(
                "topmatches",
                line,
                ("topmatches", include_odds),
                lambda api: api.topmatches(line, full=include_odds),
                what=f"top {label(line)} matches",
            )
        return fmt.dumps(
            svc.envelope(
                age,
                line_type=line_type,
                matches=[
                    fmt.match_summary(
                        m,
                        live=line == LIVE,
                        odds=include_odds,
                        max_markets=max_markets_per_match,
                    )
                    for m in matches
                ],
            )
        )

    @tool
    async def top_championships(line_type: LineParam = "prematch") -> str:
        """Up to 12 popular championships (tournaments) with their match counts, without
        esports. Use list_live_matches / list_prematch_matches with the tournament_id."""
        line = api_line_type(line_type)
        items, age = await svc.fetch(
            "topchampionships",
            line,
            ("topchampionships",),
            lambda api: api.topchampionships(line),
            what=f"top {label(line)} championships",
        )
        return fmt.dumps(
            svc.envelope(
                age,
                line_type=line_type,
                championships=[
                    {
                        "tournament": c.tournament_name,
                        "tournament_id": c.tournament_id,
                        "sport": c.sport_name,
                        "sport_id": c.sport_id,
                        "country": c.country_name,
                        "matches": c.counter,
                    }
                    for c in sorted(items, key=lambda c: c.position)
                ],
            )
        )

    # -- account -------------------------------------------------------------------------------

    @tool
    async def account_status() -> str:
        """Show whether the server uses live data or demo data and, with an API key, the key's
        status: expiry, sports, languages, access restrictions and requests over 7 days."""
        if svc.config_error:
            raise ToolError(svc.config_error)
        if svc.is_demo:
            return fmt.dumps(
                svc.envelope(
                    notice=(
                        "The server runs in demo mode: tools return example responses from the "
                        "SportAPI documentation, not live data."
                    ),
                    mode="demo",
                    language="en",
                    setup=(
                        "Set SPORTAPI_KEY and SPORTAPI_BASE_URL (both issued by the SportAPI "
                        "manager) in the MCP server's env and restart it."
                    ),
                    get_api_key=GET_KEY_URL,
                    pricing="Plans from $30/month, free 2-day trial.",
                    website=SITE_URL,
                )
            )
        account, age = await svc.fetch(
            "account", None, ("account",), lambda api: api.account(), what="account status"
        )
        current = account.current_key
        key_info: dict[str, Any] | None = None
        if current is not None:
            key_info = {
                "key_ends_with": current.key,
                "status": current.status,
                "active": current.active,
                "type": current.type,
                "label": current.label,
                "starts_at": current.starts_at,
                "expires_at": current.expires_at,
                "days_left": current.days_left,
                "sports": current.sports,
                "languages": current.languages,
                "access_mode": current.access_mode,
                "last_used_at": current.last_used_at,
                "requests_7d": {u.date: u.requests for u in current.usage_7d},
            }
            key_info = {k: v for k, v in key_info.items() if v not in (None, "", [], {})}
        return fmt.dumps(
            svc.envelope(
                age,
                mode="live",
                language=svc.lang,
                client=account.client_name or None,
                your_ip=account.your_ip or None,
                current_key=key_info,
                other_keys=max(len(account.keys) - (1 if current else 0), 0),
            )
        )

    # -- prompts ---------------------------------------------------------------------------------

    @prompt("Live betting overview")
    def live_betting_overview(sport: str = "Football") -> str:
        """Overview of the live matches of one sport: scores, favourites by the odds and the
        most interesting games."""
        return f"""Give me a live betting overview for {sport} using the SportAPI tools.

1. Call list_sports with line_type "live" and find the sport_id of {sport}. If it has no live
   matches, say so and list the sports that do.
2. Call list_live_matches with that sport_id and max_markets_per_match 2.
3. Summarise: how many matches are live; per tournament, a compact table with match, score,
   period/minute and the main odds. Point out close games, late stages and clear favourites or
   surprises according to the odds (low odds = favourite).
4. Pick at most two interesting matches and call get_match for each (line_type "live",
   markets ["1X2", "Total"]) to add key live statistics.

Call each tool once: results are snapshots, not a stream. If a result has "source": "demo",
say clearly that it is demo data from the SportAPI documentation, not live data. Odds are
information, not betting advice."""

    @prompt("Compare odds markets for a match")
    def compare_match_markets(match: str, markets: str = "1X2, Total, Handicap") -> str:
        """Find a match and compare its betting markets: implied probabilities, bookmaker
        margin and fair odds."""
        wanted = [m.strip() for m in markets.split(",") if m.strip()]
        return f"""Compare the betting markets of the match "{match}" using the SportAPI tools.

1. Find it with search_matches (line_type "both"). If several matches fit, pick the most
   relevant one and say which; if none, say so and stop.
2. Call get_match with its game_id, the line_type it was found in and markets {wanted}.
3. For each market, make a table of selections with decimal odds and implied probability
   (1 / odds). Ignore blocked selections. Where the selections are complementary — W1/X/W2,
   Over/Under of the same line, the two sides of the same handicap — compute the bookmaker
   margin (sum of implied probabilities - 1) and the fair odds without margin.
4. Conclude which lines have the lowest margin and what the odds say about the expected
   result.

If a result has "source": "demo", say clearly that it is demo data from the SportAPI
documentation, not live data. Odds are information, not betting advice."""

    return mcp
