FROM python:3.12-slim
	
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
	
COPY . /app
	
# The flag is also stored outside the web root, so players must use
# path traversal / LFI to reach it (it is baked into app.py as well).
RUN mkdir -p /opt/secrets && \
    echo "FLAG{lfi_0bs3rv4t0ry_ch4rt3d_c0m3t_7f9x}" > /opt/secrets/flag.txt && \
    chmod 644 /opt/secrets/flag.txt && \
    mkdir -p /data
	
ENV LOG_DB=/data/userlog.db
EXPOSE 5000
CMD ["python", "app.py"]