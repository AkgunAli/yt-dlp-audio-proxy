FROM python:3.11-slim

# Sistem paketlerini kur
RUN apt-get update && apt-get install -y \
    ffmpeg \
    nodejs \
    npm \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# yt-dlp güncelle
RUN yt-dlp -U

# PO Token server'ı kur
RUN git clone --single-branch --branch 1.2.2 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /app/po-token-server \
    && cd /app/po-token-server/server/ \
    && npm install \
    && npx tsc

# Uygulama dosyalarını kopyala
COPY . .

# Port'ları aç
EXPOSE 8000
EXPOSE 8080

# Startup script
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

CMD ["/app/docker-entrypoint.sh"]
