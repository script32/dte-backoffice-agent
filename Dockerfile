FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY data ./data
RUN useradd --create-home agente && mkdir -p /app/.data && chown agente /app/.data
USER agente

ENV PATH="/app/.venv/bin:$PATH" DTE_AGENT_CONFIG=/app/config.yaml
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/salud')"
CMD ["dte-agent", "api", "--host", "0.0.0.0", "--port", "8000"]
