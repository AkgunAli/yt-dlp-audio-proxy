#!/bin/bash

# PO Token server'ı başlat (arka planda)
echo "🚀 PO Token server başlatılıyor..."
cd /app/po-token-server/server/
node build/main.js &
PO_TOKEN_PID=$!

# Server'ın başlaması için bekle
sleep 5

# PO Token server kontrolü
if kill -0 $PO_TOKEN_PID 2>/dev/null; then
    echo "✓ PO Token server çalışıyor (PID: $PO_TOKEN_PID)"
else
    echo "⚠ PO Token server başlatılamadı"
fi

# FastAPI'yi başlat
echo "🚀 FastAPI başlatılıyor..."
cd /app
exec uvicorn main:app --host 0.0.0.0 --port 8000
