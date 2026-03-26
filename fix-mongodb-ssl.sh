#!/bin/bash
set -e

echo "=== Fix MongoDB SSL Connection untuk Fly.io ==="
echo ""

# Load .env file
if [ ! -f .env ]; then
    echo "❌ File .env tidak ditemukan!"
    exit 1
fi

# Load environment variables from .env
export $(cat .env | grep -v '^#' | xargs)

# Tambahkan parameter SSL ke MongoDB connection string
if [[ $MONGODB_URL == *"?"* ]]; then
    # Sudah ada query parameters
    FIXED_MONGODB_URL="${MONGODB_URL}&tls=true&tlsAllowInvalidCertificates=true"
else
    # Belum ada query parameters
    FIXED_MONGODB_URL="${MONGODB_URL}?tls=true&tlsAllowInvalidCertificates=true"
fi

echo "MongoDB URL asli:"
echo "$MONGODB_URL" | sed 's/mongodb+srv:\/\/[^:]*:[^@]*@/mongodb+srv:\/\/*****:*****@/'
echo ""
echo "MongoDB URL yang sudah diperbaiki:"
echo "$FIXED_MONGODB_URL" | sed 's/mongodb+srv:\/\/[^:]*:[^@]*@/mongodb+srv:\/\/*****:*****@/'
echo ""

echo "🔄 Updating Fly.io secrets..."
/home/dzaky/.fly/bin/flyctl secrets set \
    MONGODB_URL="$FIXED_MONGODB_URL" \
    -a music-discord-bot-knqtgs

echo ""
echo "✅ MongoDB connection string berhasil diupdate!"
echo ""
echo "🚀 Bot akan restart otomatis dengan konfigurasi baru."
echo "   Tunggu 30 detik lalu cek logs dengan:"
echo "   flyctl logs -a music-discord-bot-knqtgs"
