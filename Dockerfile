# ====================
# Stage 1: Rust Builder (PO Token server'ı build et)
# ====================
FROM rust:1.85-slim-bookworm AS rust-builder

# Gerekli bağımlılıklar (git vs. için)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Repo'yu clone et ve build
RUN git clone --single-branch --branch master \
    https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs.git . \
    && cargo build --release \
    && mkdir -p /app/po-token-server/bin \
    && cp target/release/bgutil-pot-provider /app/po-token-server/bin/ \
    && echo "✓ Rust PO Token build tamamlandı"

# ====================
# Stage 2: Runtime (Python + ffmpeg + Node vs. + derlenmiş binary)
# ====================
FROM python:3.12-slim-bookworm

# Sistem paketleri (ffmpeg, curl, git vs.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    ca-certificates \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Rust'tan derlenmiş binary'yi kopyala
COPY --from=rust-builder /app/po-token-server/bin/bgutil-pot-provider /app/po-token-server/bin/bgutil-pot-provider

# Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --upgrade yt-dlp

# Uygulama dosyaları
COPY . .

# Portlar
EXPOSE 8000

# Startup script
RUN chmod +x docker-entrypoint.sh

CMD ["/app/docker-entrypoint.sh"]
