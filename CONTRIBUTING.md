# Contributing

Thanks for helping improve the SportAPI MCP server.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Checks

Run these before opening a pull request (CI runs the same):

```bash
ruff check .
ruff format --check .
mypy
pytest
```

Tests never touch the network: they call every tool through an in-memory MCP client in demo mode,
mock live-mode HTTP with [respx](https://lundberg.github.io/respx/), and start the real
`sportapi-mcp` process over stdio once.

To try the server interactively, use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector sportapi-mcp
```

## Guidelines

- Follow the [SportAPI documentation](https://sportapi.net/docs.html). Do not add endpoints,
  fields or parameters that are not documented there; open an issue instead.
- Keep tool output compact: every token returned is a token the assistant has to read.
- Respect the [update guidelines](https://sportapi.net/docs/sport-line/getting-started/update-guidelines.html):
  no tool may poll or fan out requests in a loop.
- Add tests for new behaviour and update `CHANGELOG.md`.
- **Never commit API keys**, base URLs of real accounts or `.env` files, and do not paste them
  into issues. Use placeholders such as `https://YOUR_API_DOMAIN`.

Questions about the API itself or access: [@sportapinet_bot](https://t.me/sportapinet_bot?start=github_sportapi_mcp).
