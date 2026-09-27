FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build -- --base=/static/


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /opt/devops-tools

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        iputils-ping \
        openssh-client \
        sshpass \
        freetds-bin \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/ /opt/devops-tools/
COPY --from=frontend-build /app/frontend/dist/ /opt/devops-tools/frontend_dist/
COPY deploy/docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh \
    && mkdir -p /app/config /app/data /app/media /app/recordings /opt/devops-tools/staticfiles

# Bake static files into the image so runtime containers never need to run the
# memory-heavy collectstatic/whitenoise compression step. Settings fall back to
# safe defaults when /app/config/app.conf is absent (as it is during build).
RUN python manage.py collectstatic --noinput

EXPOSE 8001 2222

ENTRYPOINT ["/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8001", "ops_tool.asgi:application"]
