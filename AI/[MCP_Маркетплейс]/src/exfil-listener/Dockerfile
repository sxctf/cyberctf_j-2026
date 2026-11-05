FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi uvicorn[standard]
COPY listener.py /app/listener.py
WORKDIR /app
CMD ["python", "listener.py"]
