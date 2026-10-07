# sportapi-mcp

An [MCP](https://modelcontextprotocol.io) server that lets AI assistants (Claude Desktop, Claude Code, Cursor, VS Code, Windsurf and other MCP clients) look up Live and Prematch matches, scores, live statistics and betting odds from [SportAPI](https://sportapi.net). It runs on demo data out of the box, without an API key.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-server-6f42c1.svg)](https://modelcontextprotocol.io)
[![CI](https://github.com/SportApi-net/sportapi-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/SportApi-net/sportapi-mcp/actions/workflows/ci.yml)

<!-- mcp-name: io.github.SportApi-net/sportapi-mcp -->

```bash
claude mcp add sportapi -- uvx sportapi-mcp
```

Then ask: *"Which football matches are live right now, and who is favoured?"*

> This MCP server is free and MIT-licensed. The SportAPI data service behind it is a commercial
> product: live data needs a personal API key ([how to get one](#get-an-api-key)). Without a key,
> every tool answers with the example responses from the SportAPI documentation, and every result
> says so.

## Features

- **11 read-only tools** covering the Sport Line API: sports, the navigation menu, countries,
  tournaments, Live and Prematch match lists, the match calendar, full match details with every
  market, team search, top matches, top championships and the key's account status.
- **Token-efficient output**: compact JSON with empty fields dropped and odds rendered as one line
  per market (`"W1 1.525 | X 5.08 | W2 6.15"`). A detailed match can carry 200+ markets, so
  `get_match` returns 15 by default and accepts a `markets` filter (`["1X2", "Total"]`).
- **Polite by design**: every request goes through a snapshot cache that enforces the
  [documented minimum update intervals](https://sportapi.net/docs/sport-line/getting-started/update-guidelines.html)
  and never sends overlapping requests for the same data. No tool polls or fans out over matches,
  however often the assistant calls it.
- **Demo mode** with no setup, clearly labelled (`"source": "demo"`) so that an assistant never
  presents a snapshot as live data.
- **Actionable errors**: an expired key, a sport outside the subscription, a finished match or a
  `game_id` from the wrong line type come back as short explanations the assistant can act on.
- **Two prompts**: a live betting overview for a sport and a market comparison (implied
  probabilities, bookmaker margin, fair odds) for one match.
- Built on the official [SportAPI Python client](https://github.com/SportApi-net/sportapi-python)
  and the official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk). stdio by
  default, Streamable HTTP optional.

## What you can ask

Example conversations in demo mode (answers abridged). The assistant picks the tools itself.

**"What's happening in live football right now?"**
→ `list_live_matches(sport_id=1)`

> *Demo data from the SportAPI documentation, not live.* 39 football matches are in play.
> Garuda Darwin 0:1 Darwin Olympic (76', NPL Northern Territory): Darwin Olympic are near-certain
> winners at 1.064. Ikonnect FA U19 0:1 Obosa U19 (33'): Obosa favoured at 1.40, the draw at 4.65.
> Caucaia U20 — Floresta EC U20 is goalless at 2', with Floresta slight favourites at 2.112.

**"Arsenal against Coventry: how are the goal lines priced?"**
→ `get_match(game_id=746146992, line_type="live", markets=["Total"])`

> Arsenal lead 3:0 at 56' (xG 1.45 vs 0.03, shots on target 4:0). Total goals: Over 3.5 at 1.23,
> Over 4.5 at 2.09 / Under 4.5 at 1.81, Over 5.5 at 4.41. The market expects a fourth goal but
> leans against a fifth.

**"When does Manchester City play next, and what are the odds?"**
→ `search_matches(text="Manchester")`, then `get_match(game_id=730321837, line_type="prematch", markets=["1X2", "Total"])`

> Manchester City — Bournemouth, Premier League, 23 Aug 2026 13:00 UTC. 1X2: City 1.525,
> draw 5.08, Bournemouth 6.15. Over 2.5 goals 1.39, under 2.5 2.72.

**"What are the biggest games this weekend?"** → `top_matches(line_type="prematch", include_odds=True)`

**"Is my SportAPI key OK, and how many requests did I make this week?"** → `account_status()` (live mode)

With a key, the same questions work for every sport in your subscription, with current data.

## Install

The server is a Python package (Python 3.10+). The easiest way to run it is with
[uv](https://docs.astral.sh/uv/getting-started/installation/): `uvx` downloads and runs it in an
isolated environment, with no install step.

```bash
uvx sportapi-mcp            # starts the stdio server; MCP clients launch it for you
```

Or install it with pip and use the `sportapi-mcp` command instead of `uvx sportapi-mcp`:

```bash
pip install sportapi-mcp
```

The `env` blocks below are optional: leave them out to start in demo mode.

### Claude Desktop

Edit `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "sportapi": {
      "command": "uvx",
      "args": ["sportapi-mcp"],
      "env": {
        "SPORTAPI_KEY": "YOUR_API_KEY",
        "SPORTAPI_BASE_URL": "https://YOUR_API_DOMAIN"
      }
    }
  }
}
```

Restart Claude Desktop; the SportAPI tools appear in the tools menu.

### Claude Code

```bash
# demo mode
claude mcp add sportapi -- uvx sportapi-mcp

# live data, available in all your projects
claude mcp add sportapi --scope user \
  -e SPORTAPI_KEY=YOUR_API_KEY -e SPORTAPI_BASE_URL=https://YOUR_API_DOMAIN \
  -- uvx sportapi-mcp
```

### Cursor

Add to `~/.cursor/mcp.json` (all projects) or `.cursor/mcp.json` (one project):

```json
{
  "mcpServers": {
    "sportapi": {
      "command": "uvx",
      "args": ["sportapi-mcp"],
      "env": {
        "SPORTAPI_KEY": "YOUR_API_KEY",
        "SPORTAPI_BASE_URL": "https://YOUR_API_DOMAIN"
      }
    }
  }
}
```

### VS Code

Add to `.vscode/mcp.json`. VS Code asks for the key once and stores it securely:

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "sportapi-key",
      "description": "SportAPI key",
      "password": true
    }
  ],
  "servers": {
    "sportapi": {
      "type": "stdio",
      "command": "uvx",
      "args": ["sportapi-mcp"],
      "env": {
        "SPORTAPI_KEY": "${input:sportapi-key}",
        "SPORTAPI_BASE_URL": "https://YOUR_API_DOMAIN"
      }
    }
  }
}
```

### Windsurf and other clients

Any MCP client that can start a stdio server works: the command is `uvx`, the argument is
`sportapi-mcp`, and the environment variables are listed [below](#configuration). For Windsurf,
put the `mcpServers` block shown for Cursor into `~/.codeium/windsurf/mcp_config.json`.

### Streamable HTTP and Docker

```bash
sportapi-mcp --transport streamable-http --port 8000      # http://127.0.0.1:8000/mcp

docker build -t sportapi-mcp .
docker run -i --rm -e SPORTAPI_KEY -e SPORTAPI_BASE_URL sportapi-mcp          # stdio
docker run --rm -p 8000:8000 sportapi-mcp --transport streamable-http --host 0.0.0.0
```

The HTTP transport has no authentication of its own: keep it on localhost or behind your own
gateway, because anyone who can reach it uses your key.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `SPORTAPI_KEY` | for live data | Your API key. The server sends it only in the `Package` HTTP header, never in URLs or tool output. |
| `SPORTAPI_BASE_URL` | for live data | Your personal API base URL, issued together with the key (`https://YOUR_API_DOMAIN`). |
| `SPORTAPI_LANGUAGE` | no | Response language code, default `en`. It must be enabled for your key; see [languages](https://sportapi.net/docs/sport-line/reference/languages.html). Demo data is English only. |

Set both `SPORTAPI_KEY` and `SPORTAPI_BASE_URL` for live data, or neither for demo mode.
`sportapi-mcp --demo` forces demo mode even when a key is configured.

A key is bound to the server IP addresses or sites approved for it
([authentication and access](https://sportapi.net/docs/sport-line/getting-started/authentication-and-access.html)).
An MCP server usually runs on your own computer, so make sure that address is allowed for the key;
`account_status` shows the IP address SportAPI sees.

## Tools

| Tool | What it answers | SportAPI method |
|---|---|---|
| `list_sports` | Which sports have Live / Prematch matches now, with counts | [`sports`](https://sportapi.net/docs/sport-line/api-reference/optional-methods/sports.html) |
| `get_menu` | Sport → country → tournament tree with IDs and counts | [`menu`](https://sportapi.net/docs/sport-line/api-reference/menu.html) |
| `list_countries` | Countries with matches in one sport | [`countries`](https://sportapi.net/docs/sport-line/api-reference/optional-methods/countries.html) |
| `list_tournaments` | Tournaments of one sport and country | [`tournaments`](https://sportapi.net/docs/sport-line/api-reference/optional-methods/tournaments.html) |
| `list_live_matches` | Live matches of a sport or tournament: score, period, minute, main odds. Without a sport: live sports plus top live matches | [`events`](https://sportapi.net/docs/sport-line/api-reference/events.html) |
| `list_prematch_matches` | Upcoming matches: the "Top 50", a tournament, the full line, or the calendar (next 2/4/6/12 hours, today … 5 days ahead) | [`events`](https://sportapi.net/docs/sport-line/api-reference/events.html), [calendar](https://sportapi.net/docs/sport-line/api-reference/events-by-period.html) |
| `get_match` | One match: score, live statistics, every market and its odds, sub-events (halves, corners, cards…) | [`event`](https://sportapi.net/docs/sport-line/api-reference/event.html) |
| `search_matches` | Find matches by team or participant name, Live and Prematch | [`search`](https://sportapi.net/docs/sport-line/api-reference/search.html) |
| `top_matches` | Up to 10 most popular matches (all sports, or one sport for Prematch) | [`topmatches`](https://sportapi.net/docs/sport-line/api-reference/optional-methods/topmatches.html), [`toplist`](https://sportapi.net/docs/sport-line/api-reference/optional-methods/toplist.html) |
| `top_championships` | Up to 12 popular championships with match counts | [`topchampionships`](https://sportapi.net/docs/sport-line/api-reference/optional-methods/topchampionships.html) |
| `account_status` | Demo or live; with a key: expiry, sports, languages, access mode, requests over 7 days | [`account`](https://sportapi.net/docs/sport-line/api-reference/optional-methods/account.html) |

Prompts: `live_betting_overview(sport)` and `compare_match_markets(match, markets)`.

How the output maps to the API data (decimal odds, blocked selections, market IDs, sub-events,
live statistics) is described in the [odds](https://sportapi.net/docs/sport-line/data-models/odds.html),
[match](https://sportapi.net/docs/sport-line/data-models/match.html) and
[live statistics](https://sportapi.net/docs/sport-line/data-models/live-statistics.html) data models.
`get_match(include_pointers=true)` adds each selection's `oc_pointer`, the code used by bet
placement systems such as the [SportAPI Coupon API](https://sportapi.net/docs/coupon/bet-placement/bet-pointer.html).

### Demo mode coverage

Demo mode serves the full English example responses from the
[SportAPI documentation](https://sportapi.net/docs/sport-line/examples/json-responses/overview.html)
(snapshots from August–October 2026):

- `list_sports`, `get_menu`, `top_matches`: Live and Prematch;
- `list_countries`, `list_live_matches`, `list_prematch_matches`: football (`sport_id` 1);
- `list_tournaments`: football, `country_id` 1;
- `get_match`: `746146992` (Live, Arsenal — Coventry City) and `730321837` (Prematch, Manchester City — Bournemouth);
- `search_matches`: "Perth" (Live) and "Manchester" (Prematch).

Anything else (other sports and matches, the calendar, esports, `top_championships`) returns a
message that lists what demo mode covers and how to get a key.

## Update intervals

Every response is a snapshot. The server reuses a snapshot until the documented minimum interval
for that method has passed, for example 7 s for the Live match list, 5 s for a Live match and
30 s for a Prematch match. Results served from the cache carry `cached_seconds`. Concurrent
calls for the same data wait for the request already in flight. See the
[data update guidelines](https://sportapi.net/docs/sport-line/getting-started/update-guidelines.html).

## Documentation

- [Quick start](https://sportapi.net/docs/sport-line/getting-started/quick-start.html)
- [API methods overview](https://sportapi.net/docs/sport-line/api-reference/overview.html)
- [Core concepts](https://sportapi.net/docs/sport-line/getting-started/core-concepts.html): Live vs Prematch, IDs
- [Error handling](https://sportapi.net/docs/sport-line/getting-started/error-handling.html)
- [Sports and sport IDs](https://sportapi.net/docs/sport-line/reference/sports.html)
- [SportAPI documentation](https://sportapi.net/docs.html)

Building your own integration instead? Use the [SportAPI Python client](https://github.com/SportApi-net/sportapi-python)
this server is built on.

## Get an API key

Live data needs a personal API key and base URL from SportAPI. Plans start from $30/month, with a
free 2-day trial.

- Telegram: [@sportapinet_bot](https://t.me/sportapinet_bot?start=github_sportapi_mcp)
- Website: [sportapi.net](https://sportapi.net)

Keep the key in your MCP client's configuration or a secret store, never in a shared chat or a
Git repository.

## Contributing

Issues and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). Run
`ruff check . && mypy && pytest` before submitting.

## License

[MIT](LICENSE) © 2026 SportAPI
