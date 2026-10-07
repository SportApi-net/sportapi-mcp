# Container image for MCP directories (e.g. Glama, Smithery) and self-hosting.
# stdio by default:   docker run -i --rm sportapi-mcp
# Live data:          docker run -i --rm -e SPORTAPI_KEY -e SPORTAPI_BASE_URL sportapi-mcp
# HTTP transport:     docker run --rm -p 8000:8000 sportapi-mcp --transport streamable-http --host 0.0.0.0
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install . && useradd --create-home --uid 10001 mcp

USER mcp
EXPOSE 8000
ENTRYPOINT ["sportapi-mcp"]
