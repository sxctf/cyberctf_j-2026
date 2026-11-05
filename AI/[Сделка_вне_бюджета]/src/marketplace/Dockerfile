FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.5 /uv /uvx /bin/
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev 2>/dev/null || uv sync --no-install-project --no-dev
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev
ENV PATH="/app/.venv/bin:$PATH"
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8020"]
