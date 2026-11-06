# The MCP server image. Build from the repository root.
FROM ghcr.io/astral-sh/uv:0.12.23 AS uv

FROM python:3.12.15-slim-trixie AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY phase-1-core/api/pyproject.toml phase-1-core/api/pyproject.toml
COPY phase-1-core/safety/pyproject.toml phase-1-core/safety/pyproject.toml
COPY phase-1-core/llm-gateway/pyproject.toml phase-1-core/llm-gateway/pyproject.toml
COPY phase-1-core/mcp-server/pyproject.toml phase-1-core/mcp-server/pyproject.toml
COPY phase-2-agentic/orchestrator/pyproject.toml phase-2-agentic/orchestrator/pyproject.toml
RUN uv sync --frozen --no-dev --package platform-v2-mcp-server --no-install-project
COPY phase-1-core/mcp-server/src phase-1-core/mcp-server/src
RUN uv sync --frozen --no-dev --package platform-v2-mcp-server --no-editable

FROM python:3.12.15-slim-trixie
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
USER 10001
EXPOSE 8001
ENV OTEL_SDK_DISABLED=true
CMD ["opentelemetry-instrument", "uvicorn", "mcp_server.main:app", "--host", "0.0.0.0", "--port", "8001", "--no-server-header"]
