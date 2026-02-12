#!/bin/bash
set -e

echo "======================================"
echo "YouTube Audio Proxy Başlatılıyor..."
echo "======================================"

# Node.js kontrolü
echo "📋 Node.js: $(node --version)"
echo "📋 NPM: $(npm --version)"

# PO Token server dosya kontrolü
if [ ! -f /app/po-token-server/server/build/main.js ]; then
    echo "❌ HATA: PO Token build dosyası bulunamadı!"
    echo "Beklenen: /app/po-token-server/server/build/main.js"
    ls -la /app/po-token-server/server/ || echo "Klasör bulunamadı"
    exit 1
fi

# PO Token server'ı başlat (arka planda)
echo "🚀 PO Token server başlatılıyor..."
cd /app/po-token-server/server/
node build/main.js > /tmp/po-token.log 2>&1 &
PO_TOKEN_PID=$!

# Server'ın başlaması için bekle
echo "⏳ PO Token server'ın hazır olması bekleniyor..."
for i in {1..10}; do
    sleep 1
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo "✅ PO Token server çalışıyor (PID: $PO_TOKEN_PID)"
        break
    fi
    if [ $i -eq 10 ]; then
        echo "❌ PO Token server başlatılamadı!"
        echo "Son 20 satır log:"
        tail -n 20 /tmp/po-token.log
        exit 1
    fi
done

# FastAPI'yi başlat
echo "🚀 FastAPI başlatılıyor..."
echo "======================================"
cd /app
exec uvicorn main:app --host 0.0.0.0 --port 8000
