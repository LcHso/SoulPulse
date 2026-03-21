#!/bin/bash
set -e

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DEPLOY_DIR"

echo "=== SoulPulse Deployment ==="
echo "Directory: $DEPLOY_DIR"

# Check .env.production exists
if [ ! -f backend/.env.production ]; then
    echo "[WARN] backend/.env.production not found!"
    echo "       Copy from .env.example and fill in real keys:"
    echo "       cp backend/.env.example backend/.env.production"
    exit 1
fi

# Create data directory for persistent volumes
mkdir -p data

# Touch SQLite DB file if it doesn't exist (Docker bind mount needs it)
if [ ! -f data/soulpulse.db ]; then
    touch data/soulpulse.db
    echo "[INFO] Created empty data/soulpulse.db"
fi

# Create chroma_data directory
mkdir -p data/chroma_data

# Create certbot directories
mkdir -p certbot/www certbot/conf

# Check if Flutter web build exists
if [ ! -f frontend/build/web/index.html ]; then
    echo "[WARN] Flutter web build not found at frontend/build/web/"
    echo "       Build it first with:"
    echo "       cd frontend && flutter build web --release --dart-define=API_BASE_URL=http://YOUR_SERVER_IP"
    echo ""
    echo "       Or set SKIP_FRONTEND=1 to deploy backend only."
    if [ "$SKIP_FRONTEND" != "1" ]; then
        exit 1
    fi
fi

echo "[1/3] Building Docker images..."
docker compose -f docker-compose.prod.yml build

echo "[2/3] Starting services..."
docker compose -f docker-compose.prod.yml up -d

echo "[3/3] Waiting for services to start..."
sleep 5

docker compose -f docker-compose.prod.yml ps

echo ""
echo "=== Deployment Complete ==="
echo ""
SERVER_IP=$(hostname -I | awk '{print $1}')
echo "Frontend: http://${SERVER_IP}/"
echo "API:      http://${SERVER_IP}/api/"
echo "Health:   http://${SERVER_IP}/health"
echo ""

# Check if SSL certs exist
if [ ! -d certbot/conf/live ]; then
    echo "[NOTE] SSL not configured yet. Run: bash init-ssl.sh YOUR_DOMAIN YOUR_EMAIL"
fi
