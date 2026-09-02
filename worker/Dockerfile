# Runs the MCP server over streamable-http, for a Cloudflare Container fronted
# by the Worker in worker/. Local/Claude Desktop use stays on stdio via `uv tool
# run mcp-ynab` — this image is only for the remote deployment.
FROM python:3.13-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src
COPY README.md ./

RUN uv sync --frozen --no-dev

ENV CACHE_DB_PATH=/tmp/ynab-mcp-cache.db
EXPOSE 8080

CMD ["uv", "run", "uvicorn", "src.server.http:app", "--host", "0.0.0.0", "--port", "8080"]
