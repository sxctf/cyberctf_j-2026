FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic httpx playwright==1.49.0

COPY agent.py /app/agent.py

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

CMD ["python", "agent.py"]
