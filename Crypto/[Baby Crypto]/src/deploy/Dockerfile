FROM python:3.12-slim

RUN pip install --no-cache-dir cryptography aiohttp

RUN useradd -m -u 10001 ctf
WORKDIR /app

COPY server.py /app/server.py
COPY web /app/web
COPY deploy/run.sh /app/run.sh
RUN chmod +x /app/run.sh

ENV PORT=1337 \
    BACKEND_HOST=127.0.0.1 \
    BACKEND_PORT=1337 \
    WEB_HOST=0.0.0.0 \
    WEB_PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER ctf
EXPOSE 1337 8080
CMD ["/app/run.sh"]
