FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLCONFIGDIR=/tmp/matplotlib \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY challenge ./challenge

RUN pip install --no-cache-dir "qualtran==0.7.0"

CMD ["python", "-m", "challenge.inspect_vault"]
