#!/bin/bash
set -e

echo "======================================"
echo "YouTube Audio Proxy Başlatılıyor..."
echo "======================================"

echo "📋 Node.js: $(node --version)"
echo "📋 NPM: $(npm --version)"
echo "📋 Python: $(python --version)"

# PO Token binary kontrolü
PO_BINARY="/app/po-token-server/bin/bgutil-pot-provider"
if [ ! -x "$PO_BINARY" ]; then
    echo "❌ HATA: PO Token binary bulunamadı veya çalıştırılamaz!"
    ls -la /app/po-token-server/bin/ || echo "Klasör boş"
    exit 1
fi

# PO Token server'ı başlat (Rust versiyonu: server subcommand)
PO_PORT=4416
echo "🚀 PO Token server başlatılıyor... (Rust binary, port: $PO_PORT)"
"$PO_BINARY" server --port "$PO_PORT" > /tmp/po-token.log 2>&1 &
PO_TOKEN_PID=$!

echo "PO Token PID: $PO_TOKEN_PID"

# Port açılana kadar bekle (Rust'ta /ping endpoint'i var!)
echo "⏳ PO Token server'ın hazır olması bekleniyor (max 30 saniye)..."
for i in {1..30}; do
    sleep 1
    if curl -s -f "http://localhost:${PO_PORT}/ping" > /dev/null 2>&1; then
        echo "✅ PO Token server aktif (/ping endpoint 200 döndü)"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ PO Token server 30 saniye içinde hazır olmadı!"
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
