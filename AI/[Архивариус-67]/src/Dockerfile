FROM python:3.13-slim

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/tmp

COPY . .

RUN useradd -ms /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

RUN uv sync --frozen --no-cache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--worker-tmp-dir", "/tmp", "app:create_app()"]
