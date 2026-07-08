#!/bin/bash
set -e

# Initial Let’s Encrypt certificate issuance for themovingtrain.org.
# Run this on the VPS before the first `docker compose -f docker-compose.prod.yml up -d`.
# Renewals are handled automatically by the `certbot` service in docker-compose.prod.yml.

DOMAIN="themovingtrain.org"
WWW_DOMAIN="www.themovingtrain.org"
EMAIL="admin@themovingtrain.org"  # Change to a real admin email address
COMPOSE_FILE="docker-compose.prod.yml"

if [ -d "/etc/letsencrypt/live/${DOMAIN}" ] || docker compose -f "$COMPOSE_FILE" run --rm certbot certificates 2>/dev/null | grep -q "$DOMAIN"; then
    echo "Certificate for ${DOMAIN} already exists. Skipping issuance."
    exit 0
fi

echo "Stopping any containers using port 80..."
docker compose -f "$COMPOSE_FILE" stop nginx certbot 2>/dev/null || true

echo "Obtaining initial certificate for ${DOMAIN} and ${WWW_DOMAIN}..."
docker compose -f "$COMPOSE_FILE" run --rm --service-ports certbot certonly \
    --standalone \
    --preferred-challenges http \
    -d "$DOMAIN" \
    -d "$WWW_DOMAIN" \
    --agree-tos \
    --no-eff-email \
    -m "$EMAIL"

echo "Certificate obtained. Starting production services..."
docker compose -f "$COMPOSE_FILE" up -d

echo "Done."
