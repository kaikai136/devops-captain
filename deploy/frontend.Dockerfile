FROM node:22-alpine AS frontend-build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS django-static-build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    APP_CONFIG_FILE=/tmp/static-build/app.conf \
    DJANGO_STATIC_ROOT=/app/backend/staticfiles \
    DJANGO_DEBUG=0 \
    DJANGO_SECRET_KEY=static-build-only-secret-key
WORKDIR /app/backend
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY backend/ ./
RUN python manage.py collectstatic --noinput

FROM nginx:1.27-alpine
COPY --from=frontend-build /src/dist /usr/share/nginx/html
COPY --from=django-static-build /app/backend/staticfiles /srv/devops-static
EXPOSE 80
