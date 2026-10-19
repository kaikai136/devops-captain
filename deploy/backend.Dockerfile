FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/devops-tools
WORKDIR /opt/devops-tools
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl iputils-ping openssh-client sshpass freetds-bin && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend/ ./
COPY deploy/backend-entrypoint.sh /usr/local/bin/devops-entrypoint
RUN chmod +x /usr/local/bin/devops-entrypoint && mkdir -p /data/config /data/data /data/media /data/recordings /data/static
EXPOSE 8000
ENTRYPOINT ["devops-entrypoint"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "ops_tool.asgi:application"]
