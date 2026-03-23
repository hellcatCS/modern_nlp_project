#!/bin/bash
set -euo pipefail

PROJECT_DIR="/root/restaurant_bot"
IMAGE_NAME="restaurant-bot:latest"
APP_CONTAINER="restaurant-tg-bot"
DB_CONTAINER="restaurant-db"
QDRANT_CONTAINER="restaurant-qdrant"
POSTGRES_VOLUME="restaurant_postgres_data"
QDRANT_VOLUME="restaurant_qdrant_data"

cd "$PROJECT_DIR"

docker volume create "$POSTGRES_VOLUME" >/dev/null
docker volume create "$QDRANT_VOLUME" >/dev/null

if ! docker ps -a --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
  docker run -d \
    --name "$DB_CONTAINER" \
    --restart unless-stopped \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=restaurant_bot \
    -p 127.0.0.1:5433:5432 \
    -v "$POSTGRES_VOLUME:/var/lib/postgresql/data" \
    postgres:15-alpine >/dev/null
fi

if ! docker ps -a --format '{{.Names}}' | grep -qx "$QDRANT_CONTAINER"; then
  docker run -d \
    --name "$QDRANT_CONTAINER" \
    --restart unless-stopped \
    -p 127.0.0.1:6333:6333 \
    -v "$QDRANT_VOLUME:/qdrant/storage" \
    qdrant/qdrant:v1.12.1 >/dev/null
fi

docker start "$DB_CONTAINER" >/dev/null
docker start "$QDRANT_CONTAINER" >/dev/null

docker build -t "$IMAGE_NAME" .

docker rm -f "$APP_CONTAINER" >/dev/null 2>&1 || true

docker run -d \
  --name "$APP_CONTAINER" \
  --restart unless-stopped \
  --network host \
  --env-file "$PROJECT_DIR/.env" \
  -v "$PROJECT_DIR:/app" \
  -w /app \
  "$IMAGE_NAME" \
  python tg_manager/main.py >/dev/null

sleep 3
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep -E "$APP_CONTAINER|$DB_CONTAINER|$QDRANT_CONTAINER"
