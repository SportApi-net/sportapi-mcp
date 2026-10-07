# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-07

### Added

- MCP server `sportapi-mcp` (stdio by default, `--transport streamable-http` optional) built on the
  official [SportAPI Python client](https://github.com/SportApi-net/sportapi-python) and the
  official MCP Python SDK.
- Tools: `list_sports`, `get_menu`, `list_countries`, `list_tournaments`, `list_live_matches`,
  `list_prematch_matches` (with the "Top 50" selection, full line and the match calendar),
  `get_match`, `search_matches`, `top_matches`, `top_championships`, `account_status`.
- Compact, token-efficient JSON output: odds as one line per market, empty fields dropped,
  `markets` filter and per-match / per-response limits.
- Snapshot cache that enforces the documented minimum update intervals and never sends
  overlapping requests for the same data.
- Demo mode on the example responses from the SportAPI documentation, clearly labelled in every
  result.
- Prompts: `live_betting_overview`, `compare_match_markets`.
- `Dockerfile`, `smithery.yaml` and `server.json` (MCP Registry) for MCP directories.

[0.1.0]: https://github.com/SportApi-net/sportapi-mcp/releases/tag/v0.1.0
