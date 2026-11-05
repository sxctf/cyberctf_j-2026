FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic "mcp>=1.9"
COPY server.py /app/server.py
WORKDIR /app
CMD ["python", "server.py"]
