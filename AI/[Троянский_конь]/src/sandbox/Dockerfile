FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5.5 /uv /uvx /bin/

WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv

# Only need fastapi + uvicorn (no torch — pickle.load is equivalent for exploit purposes)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system fastapi uvicorn[standard] python-multipart

COPY sandbox.py ./
ENV PATH="/app/.venv/bin:$PATH"

# flag.txt is injected via docker secret / volume at runtime
CMD ["python", "sandbox.py"]
