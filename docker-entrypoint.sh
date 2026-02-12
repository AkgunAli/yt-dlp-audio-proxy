#!/bin/bash
set -e

echo "======================================"
echo "YouTube Audio Proxy Başlatılıyor..."
echo "======================================"

echo "📋 Python: $(python --version)"
# Node.js kaldırıldığı için node/npm echo'larını çıkardık

# PO Token binary kontrolü
PO_BINARY="/app/po-token-server/bin/bgutil-pot"
if [ ! -x "$PO_BINARY" ]; then
    echo "❌ HATA: PO Token binary bulunamadı veya çalıştırılamaz!"
    ls -la /app/po-token-server/bin/ || echo "Klasör boş"
    exit 1
fi

# PO Token server'ı başlat
PO_PORT=4416
echo "🚀 PO Token server başlatılıyor... (port: $PO_PORT)"
"$PO_BINARY" server --host 0.0.0.0 --port "$PO_PORT" > /tmp/po-token.log 2>&1 &
PO_TOKEN_PID=$!

echo "PO Token PID: $PO_TOKEN_PID"

# Server hazır olana kadar bekle
echo "⏳ PO Token server'ın hazır olması bekleniyor (max 45 saniye)..."
for i in {1..45}; do
    sleep 1
    if curl -s -f "http://localhost:${PO_PORT}/ping" > /dev/null 2>&1; then
        echo "✅ PO Token server aktif (/ping 200 döndü)"
        break
    fi
    if [ $i -eq 45 ]; then
        echo "❌ PO Token server 45 saniye içinde hazır olmadı!"
        echo "Son 30 satır log:"
        tail -n 30 /tmp/po-token.log
        exit 1
    fi
done

# FastAPI başlat
echo ""
echo "======================================"
echo "🚀 FastAPI başlatılıyor... (port 8000)"
echo "======================================"

exec uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
