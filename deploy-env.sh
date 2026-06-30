#!/bin/bash
set -e

ENV=${1:-prod}  # "prod" or "test"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

if [ "$ENV" = "prod" ]; then
  COMPOSE_FILE="docker-compose.prod.yml"
  ENV_FILE="backend/.env.production"
  PROJECT_NAME="sp-prod"
  PORT=80
elif [ "$ENV" = "test" ]; then
  COMPOSE_FILE="docker-compose.test.yml"
  ENV_FILE="backend/.env.test"
  PROJECT_NAME="sp-test"
  PORT=9080
else
  echo -e "${RED}Error: Invalid environment '$ENV'. Use 'prod' or 'test'${NC}"
  exit 1
fi

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}  Deploying SoulPulse - ${ENV} environment${NC}"
echo -e "${YELLOW}========================================${NC}"

# Pre-flight checks
echo -e "\n${GREEN}[1/5] Pre-flight checks...${NC}"

if [ ! -f "$ENV_FILE" ]; then
  echo -e "${RED}Error: $ENV_FILE not found!${NC}"
  echo "Create it from backend/.env.${ENV}.example"
  exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  echo -e "${RED}Error: $COMPOSE_FILE not found!${NC}"
  exit 1
fi

# Create data directories
echo -e "\n${GREEN}[2/5] Ensuring data directories exist...${NC}"
if [ "$ENV" = "prod" ]; then
  mkdir -p data/postgres data/chroma_data
else
  mkdir -p data-test/postgres data-test/chroma_data
fi

# Check frontend builds (warn but don't block)
echo -e "\n${GREEN}[3/5] Checking frontend builds...${NC}"
if [ ! -f "frontend/build/web/index.html" ]; then
  echo -e "${YELLOW}Warning: Flutter web build not found at frontend/build/web/${NC}"
  echo -e "${YELLOW}  Run: cd frontend && flutter build web --release --dart-define=API_BASE_URL=http://123.57.227.61:${PORT}${NC}"
fi

if [ ! -f "admin-frontend/dist/index.html" ]; then
  echo -e "${YELLOW}Warning: Admin frontend build not found at admin-frontend/dist/${NC}"
  echo -e "${YELLOW}  Run: cd admin-frontend && npm run build${NC}"
fi

# Build and deploy
echo -e "\n${GREEN}[4/5] Building and deploying...${NC}"
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" build
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d

# Health check
echo -e "\n${GREEN}[5/5] Waiting for services to be ready...${NC}"
sleep 10

# Show service status
echo ""
docker compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps

# Try health endpoint
echo ""
echo -e "${GREEN}Checking health endpoint...${NC}"
HEALTH_URL="http://localhost:${PORT}/health"
if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
  echo -e "${GREEN}Health check passed!${NC}"
  curl -s "$HEALTH_URL" | python3 -m json.tool 2>/dev/null || curl -s "$HEALTH_URL"
else
  echo -e "${YELLOW}Health endpoint not responding yet (may need more time to start)${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ${ENV} deployment complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Access URLs:"
echo "  Frontend: http://123.57.227.61:${PORT}"
echo "  Admin:    http://123.57.227.61:${PORT}/admin/"
echo "  API:      http://123.57.227.61:${PORT}/api/"
echo "  Health:   http://123.57.227.61:${PORT}/health"
echo ""
echo "Useful commands:"
echo "  Logs:     docker compose -f $COMPOSE_FILE -p $PROJECT_NAME logs -f"
echo "  Stop:     docker compose -f $COMPOSE_FILE -p $PROJECT_NAME down"
echo "  Restart:  docker compose -f $COMPOSE_FILE -p $PROJECT_NAME restart"
