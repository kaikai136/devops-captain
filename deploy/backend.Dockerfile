FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    APP_CONFIG_FILE=/etc/devops-tools/app.conf \
    REDIS_CONFIG_FILE=/etc/devops-tools/redis.conf
WORKDIR /app/backend
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates iputils-ping openssh-client sshpass freetds-bin \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend/ ./
COPY deploy/backend-entrypoint.sh /usr/local/bin/backend-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/backend-entrypoint \
    && chmod +x /usr/local/bin/backend-entrypoint \
    && mkdir -p /data /app/backend/staticfiles
EXPOSE 8000
ENTRYPOINT ["backend-entrypoint"]
CMD ["backend"]
