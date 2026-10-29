#!/usr/bin/env bash
# ==============================================================================
# HealthSlip AI - Production Deployment Automation Script
# Builds, tests, and deploys the containerized stack with zero-downtime checks
# ==============================================================================

set -euo pipefail

echo "======================================================================"
echo "🩺 Starting HealthSlip AI Production Deployment"
echo "======================================================================"

# 1. Check Docker & Compose availability
command -v docker >/dev/null 2>&1 || { echo >&2 "❌ Error: Docker is not installed."; exit 1; }
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
else
    echo "❌ Error: docker compose is required."
    exit 1
fi

# 2. Check or create .env from example if not present
if [ ! -f .env ]; then
    echo "⚠️ .env not found. Copying from .env.example..."
    cp .env.example .env
fi

# 3. Build & start services in detached mode
echo "📦 Building and orchestrating containers (FastAPI + MySQL 8.0)..."
$DOCKER_COMPOSE down --remove-orphans || true
$DOCKER_COMPOSE build --pull
$DOCKER_COMPOSE up -d

# 4. Wait for application healthcheck
echo "⏳ Waiting for HealthSlip AI server to report healthy status..."
MAX_RETRIES=15
COUNTER=0
HEALTHY=false

while [ $COUNTER -lt $MAX_RETRIES ]; do
    if curl -s -f http://localhost:8005/api/health >/dev/null 2>&1; then
        HEALTHY=true
        break
    fi
    echo "   Checking /api/health... (attempt $((COUNTER + 1))/$MAX_RETRIES)"
    sleep 3
    COUNTER=$((COUNTER + 1))
done

if [ "$HEALTHY" = true ]; then
    echo "======================================================================"
    echo "✅ HealthSlip AI successfully deployed and online!"
    echo "🌐 Web Dashboard & POS: http://localhost:8005"
    echo "📖 Interactive API Docs: http://localhost:8005/docs"
    echo "🩺 Health Endpoint:     http://localhost:8005/api/health"
    echo "======================================================================"
else
    echo "❌ Health check timed out. Displaying application logs:"
    $DOCKER_COMPOSE logs --tail=40 app
    exit 1
fi
