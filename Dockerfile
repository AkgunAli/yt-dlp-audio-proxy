FROM python:3.11-slim

# Sistem paketlerini kur (Node.js 18.x)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    ca-certificates \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# yt-dlp güncelle
RUN yt-dlp -U

# PO Token server'ı kur ve build et
RUN git clone --single-branch --branch 1.2.2 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /app/po-token-server \
    && cd /app/po-token-server/server/ \
    && npm install \
    && npx tsc \
    && echo "✓ PO Token build tamamlandı" \
    && test -f /app/po-token-server/server/build/main.js || (echo "✗ Build başarısız!" && exit 1)

# Uygulama dosyalarını kopyala
COPY . .

# Port'ları aç
EXPOSE 8000
EXPOSE 8080

# Startup script
RUN chmod +x /app/docker-entrypoint.sh

CMD ["/app/docker-entrypoint.sh"]
