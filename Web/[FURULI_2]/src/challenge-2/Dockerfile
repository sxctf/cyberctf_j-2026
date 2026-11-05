FROM python:3.12-slim
	
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
	
COPY . /app
	
# Extra copy of the flag outside the app tree, reachable via traversal.
RUN mkdir -p /opt/depot-vault && \
	    echo "FLAG{p4th_tr4vers4l_d3p0t_v4ult_51z3_42}" > /opt/depot-vault/master.key && \
	    mkdir -p /data
	
ENV LOG_DB=/data/userlog.db
EXPOSE 5000
CMD ["python", "app.py"]

