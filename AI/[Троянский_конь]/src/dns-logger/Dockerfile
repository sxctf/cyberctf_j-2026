FROM python:3.12-slim
RUN pip install --no-cache-dir dnslib fastapi uvicorn[standard]
COPY dns_logger.py /app/dns_logger.py
WORKDIR /app
# Port 53 UDP for DNS, port 8053 HTTP API
EXPOSE 53/udp 8053
CMD ["python", "dns_logger.py"]
