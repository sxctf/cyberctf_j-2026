FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn[standard] httpx "sqlalchemy[asyncio]" aiosqlite greenlet "mcp>=1.9"
COPY orchestrator.py /app/orchestrator.py
WORKDIR /app
CMD ["uvicorn", "orchestrator:app", "--host", "0.0.0.0", "--port", "8014"]
