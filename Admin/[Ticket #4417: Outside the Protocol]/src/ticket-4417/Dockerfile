FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    CONFIG_FILE=/app/config.env

# docker CLI (только клиент) — gateway спавнит sim-контейнеры через хостовый docker.sock
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app

COPY requirements.txt ./
# RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 7777

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["sim"]