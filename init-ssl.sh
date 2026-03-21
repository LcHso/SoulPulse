#!/bin/bash
set -e

DOMAIN=${1:?"Usage: bash init-ssl.sh YOUR_DOMAIN YOUR_EMAIL"}
EMAIL=${2:?"Usage: bash init-ssl.sh YOUR_DOMAIN YOUR_EMAIL"}

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DEPLOY_DIR"

echo "=== SoulPulse SSL Setup ==="
echo "Domain: $DOMAIN"
echo "Email:  $EMAIL"

# Ensure certbot directories exist
mkdir -p certbot/www certbot/conf

# Ensure Nginx is running (HTTP mode for ACME challenge)
docker compose -f docker-compose.prod.yml up -d nginx

echo "[1/3] Requesting SSL certificate from Let's Encrypt..."

docker run --rm \
    -v "$DEPLOY_DIR/certbot/conf:/etc/letsencrypt" \
    -v "$DEPLOY_DIR/certbot/www:/var/www/certbot" \
    certbot/certbot certonly \
    --webroot -w /var/www/certbot \
    -d "$DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email

echo "[2/3] SSL certificate obtained!"
echo "       Cert: certbot/conf/live/$DOMAIN/fullchain.pem"
echo "       Key:  certbot/conf/live/$DOMAIN/privkey.pem"

echo "[3/3] Now update nginx/conf.d/soulpulse.conf:"
echo "       1. Uncomment the HTTPS server block"
echo "       2. Replace YOUR_DOMAIN with: $DOMAIN"
echo "       3. Uncomment 'return 301' in HTTP block"
echo "       4. Remove the HTTP proxy locations"
echo "       5. Restart Nginx: docker compose -f docker-compose.prod.yml restart nginx"

echo ""
echo "=== Auto-renewal cron (add to crontab -e) ==="
echo "0 3 * * 1 cd $DEPLOY_DIR && docker run --rm -v $DEPLOY_DIR/certbot/conf:/etc/letsencrypt -v $DEPLOY_DIR/certbot/www:/var/www/certbot certbot/certbot renew && docker compose -f docker-compose.prod.yml restart nginx"
