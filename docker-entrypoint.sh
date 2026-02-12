#!/bin/bash
set -e

echo "======================================"
echo "YouTube Audio Proxy Başlatılıyor..."
echo "======================================"

# Versiyon bilgileri
echo "📋 Node.js: $(node --version)"
echo "📋 NPM: $(npm --version)"
echo "📋 Python: $(python --version)"

# PO Token server dosyası var mı?
PO_MAIN="/app/po-token-server/server/build/main.js"
if [ ! -f "$PO_MAIN" ]; then
    echo "❌ HATA: PO Token build dosyası bulunamadı!"
    echo "Beklenen: $PO_MAIN"
    ls -la /app/po-token-server/server/ 2>/dev/null || echo "Klasör bulunamadı"
    exit 1
fi

# PO Token server'ı arka planda başlat (portu açıkça 4416 yapıyoruz)
PO_PORT=4416
echo "🚀 PO Token server başlatılıyor... (port: $PO_PORT)"
cd /app/po-token-server/server/

# Daha fazla log için --verbose benzeri bir şey yoksa, en azından stderr+stdout yönlendir
node "$PO_MAIN" --port "$PO_PORT" > /tmp/po-token.log 2>&1 &
PO_TOKEN_PID=$!

echo "PO Token PID: $PO_TOKEN_PID"

# Server'ın dinlemeye başlamasını bekle (health endpoint yok → sadece port açık mı bakıyoruz)
echo "⏳ PO Token server'ın hazır olması bekleniyor (max 20 saniye)..."
for i in {1..20}; do
    sleep 1
    if nc -z localhost "$PO_PORT" 2>/dev/null; then
        echo "✅ PO Token server dinlemede görünüyor (port $PO_PORT açık)"
        break
    fi
    if [ $i -eq 20 ]; then
        echo "❌ PO Token server 20 saniye içinde portu açmadı!"
        echo "Son 30 satır log:"
        tail -n 30 /tmp/po-token.log
        echo ""
        echo "Tam log dosyası: /tmp/po-token.log"
        exit 1
    fi
done

# Ekstra: log'da "Started POT server" var mı diye bak (opsiyonel ama faydalı)
if grep -q "Started POT server" /tmp/po-token.log; then
    echo "✓ Log'da 'Started POT server' mesajı bulundu"
else
    echo "⚠️ Uyarı: Log'da 'Started POT server' mesajı yok – server erken kapanmış olabilir"
    tail -n 15 /tmp/po-token.log
fi

# FastAPI'yi foreground'da başlat
echo ""
echo "======================================"
echo "🚀 FastAPI (Uvicorn) başlatılıyor... (port 8000)"
echo "======================================"
cd /app

# exec ile PID 1 olur, sinyalleri doğru alır (docker/Koyeb için önemli)
exec uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
