FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TRITON_DB_PATH=/data/triton_challenge.sqlite3

WORKDIR /challenge

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN useradd --create-home --uid 10001 ctf \
    && mkdir -p /data \
    && chown -R ctf:ctf /challenge /data

USER ctf

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

