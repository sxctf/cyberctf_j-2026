FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.5 /uv /uvx /bin/

# git is required for agent operations
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN uv pip install --system httpx fastapi uvicorn[standard] python-dotenv

COPY agent.py tools.py ./
CMD ["python", "agent.py"]
