#!/bin/bash
set -e

echo "=== Setting Secrets untuk Fly.io Apps ==="

# Load .env file
if [ ! -f .env ]; then
    echo "❌ File .env tidak ditemukan!"
    exit 1
fi

# Load environment variables from .env
export $(cat .env | grep -v '^#' | xargs)

echo ""
echo "1️⃣ Setting secrets untuk Lavalink..."
/home/dzaky/.fly/bin/flyctl secrets set \
    LAVALINK_SERVER_PASSWORD="${LAVALINK_PASSWORD}" \
    -a music-discord-bot-lavalink

echo ""
echo "2️⃣ Setting secrets untuk Discord Bot..."
/home/dzaky/.fly/bin/flyctl secrets set \
    TOKEN="${TOKEN}" \
    CLIENT_ID="${CLIENT_ID}" \
    MONGODB_URL="${MONGODB_URL}" \
    LAVALINK_HOST="music-discord-bot-lavalink.fly.dev" \
    LAVALINK_PASSWORD="${LAVALINK_PASSWORD}" \
    -a music-discord-bot-knqtgs

echo ""
echo "✅ Secrets berhasil di-set!"
