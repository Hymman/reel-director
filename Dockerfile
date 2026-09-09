# syntax=docker/dockerfile:1.7

# ==========================
# Stage 1: Build Frontend
# ==========================
FROM node:22-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ==========================
# Stage 2: Shared Backend
# ==========================
FROM python:3.11-slim AS backend-base
WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app

# ==========================
# Stage 3: Deterministic Test Image
# docker compose --profile test run --rm test
# ==========================
FROM backend-base AS test
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist
COPY backend/test_*.py ./
COPY backend/tests ./tests
ENV PYTHONUNBUFFERED=1 \
    ENVIRONMENT=test \
    DEMO_MODE=true \
    USE_VERTEX_AI=false \
    MEDIA_DELIVERY_MODE=proxy
CMD ["python", "-m", "pytest", "-q"]

# ==========================
# Stage 4: Runtime Image
# ==========================
FROM backend-base AS runtime
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

ENV PYTHONUNBUFFERED=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
