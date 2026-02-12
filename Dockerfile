# ====================
# Stage 1: Rust Builder
# ====================
FROM rust:1.93-slim-bookworm AS rust-builder

# Gerekli sistem paketleri – rusty_v8 için curl + python3
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    pkg-config \
    libssl-dev \
    curl \
    python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Repo'yu clone + build (binary adı bgutil-pot)
RUN git clone --single-branch --branch master \
    https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs.git . \
    && cargo build --release \
    && mkdir -p /app/po-token-server/bin \
    && cp target/release/bgutil-pot /app/po-token-server/bin/bgutil-pot \
    && echo "✓ Rust PO Token build tamamlandı"

# ====================
# Stage 2: Runtime Image
# ====================
FROM python:3.12-slim-bookworm

# Sistem bağımlılıkları (Node.js kaldırıldı)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Rust binary kopyala
COPY --from=rust-builder /app/po-token-server/bin/bgutil-pot /app/po-token-server/bin/bgutil-pot

# Python paketleri + yt-dlp + PO Token plugin
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade yt-dlp \
    && pip install --no-cache-dir "git+https://github.com/yt-dlp/yt-dlp.git@master#egg=yt-dlp"  # nightly

# Uygulama dosyaları
COPY . .
COPY cookies.txt /app/cookies.txt


# Cookies dosyası varsa kopyala (opsiyonel – age-restricted için)
# COPY cookies.txt /app/cookies.txt

EXPOSE 8000

RUN chmod +x docker-entrypoint.sh

CMD ["/app/docker-entrypoint.sh"]
