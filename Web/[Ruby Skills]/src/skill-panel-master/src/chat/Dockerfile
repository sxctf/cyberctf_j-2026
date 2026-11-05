FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd -g 1002 appuser && \
    useradd -u 1002 -g appuser -d /app -s /sbin/nologin appuser

COPY . .

RUN mkdir -p /app/tmp/uploads /app/tmp/skills /app/logs /app/data && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

CMD ["python", "app.py"]
