FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic httpx python-multipart
COPY server.py /app/server.py
WORKDIR /app
ENV PAYMENT_DATA_DIR=/data
CMD ["python", "server.py"]
