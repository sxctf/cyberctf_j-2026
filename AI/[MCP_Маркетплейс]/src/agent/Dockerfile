FROM python:3.12-slim
RUN pip install --no-cache-dir httpx fastapi uvicorn[standard] pydantic "mcp>=1.9"
COPY agent.py /app/agent.py
WORKDIR /app
CMD ["python", "agent.py"]
