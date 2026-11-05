FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.5 /uv /uvx /bin/
WORKDIR /app
RUN uv pip install --system fastapi uvicorn[standard] "sqlalchemy[asyncio]" aiosqlite python-dotenv greenlet
COPY webhook.py ./
CMD ["uvicorn", "webhook:app", "--host", "0.0.0.0", "--port", "8000"]
