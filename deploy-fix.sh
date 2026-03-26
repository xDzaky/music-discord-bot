#!/bin/bash

# Script untuk deploy Discord bot ke Fly.io
# Pastikan sudah login: flyctl auth login

echo "=== Deployment Script untuk Discord Bot ke Fly.io ==="
echo ""

# Check if flyctl is available
if ! command -v flyctl &> /dev/null; then
    echo "❌ flyctl tidak ditemukan. Install dengan:"
    echo "curl -L https://fly.io/install.sh | sh"
    exit 1
fi

# Check if logged in
if ! flyctl auth whoami &> /dev/null; then
    echo "❌ Belum login ke Fly.io. Jalankan:"
    echo "flyctl auth login"
    exit 1
fi

echo "✅ flyctl ditemukan dan sudah login"
echo ""

# Read .env file
if [ ! -f .env ]; then
    echo "❌ File .env tidak ditemukan!"
    exit 1
fi

source .env

echo "📝 Mengecek secrets yang diperlukan..."
echo ""

# Set secrets untuk Lavalink
echo "1️⃣ Setting secrets untuk Lavalink..."
cd lavalink
flyctl secrets set LAVALINK_SERVER_PASSWORD="${LAVALINK_PASSWORD}" -a music-discord-bot-lavalink

echo ""
echo "2️⃣ Deploy Lavalink..."
flyctl deploy -c fly.lavalink.toml

echo ""
echo "⏳ Menunggu Lavalink siap (30 detik)..."
sleep 30

cd ..

# Set secrets untuk Discord bot
echo ""
echo "3️⃣ Setting secrets untuk Discord Bot..."
flyctl secrets set \
  TOKEN="${TOKEN}" \
  CLIENT_ID="${CLIENT_ID}" \
  MONGODB_URL="${MONGODB_URL}" \
  LAVALINK_HOST="music-discord-bot-lavalink.fly.dev" \
  LAVALINK_PASSWORD="${LAVALINK_PASSWORD}" \
  -a music-discord-bot-knqtgs

echo ""
echo "4️⃣ Deploy Discord Bot..."
flyctl deploy -c fly.bot.toml

echo ""
echo "✅ Deployment selesai!"
echo ""
echo "Cek status dengan:"
echo "  flyctl status -a music-discord-bot-knqtgs"
echo "  flyctl status -a music-discord-bot-lavalink"
echo ""
echo "Cek logs dengan:"
echo "  flyctl logs -a music-discord-bot-knqtgs"
echo "  flyctl logs -a music-discord-bot-lavalink"
