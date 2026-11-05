FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y iputils-ping

COPY . .

RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 5001

CMD ["python", "app.py"]
