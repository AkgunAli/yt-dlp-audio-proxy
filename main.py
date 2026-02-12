from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import StreamingResponse
import yt_dlp
import httpx
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import subprocess
import os

app = FastAPI(title="YouTube Audio Proxy (PO Token)")

# Cache: {video_id: (audio_url, expire_time)}
audio_cache: Dict[str, Tuple[str, datetime]] = {}

def check_po_token_provider():
    """PO Token provider kurulu mu kontrol et"""
    try:
        result = subprocess.run(
            ['yt-dlp', '-v', '--print', 'filename', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stderr
        
        if 'PO Token Providers: bgutil' in output:
            print("✓ PO Token provider aktif")
            return True
        else:
            print("⚠ PO Token provider bulunamadı")
            return False
    except Exception as e:
        print(f"⚠ PO Token kontrol hatası: {e}")
        return False

def get_ydl_opts_with_po_token():
    """PO Token ile yt-dlp seçenekleri"""
    opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'noplaylist': True,
        'socket_timeout': 30,
        
        # İyileştirilmiş extractor ayarları
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web'],
                'skip': ['hls', 'dash']
            }
        },
        
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }
    
    return opts

def get_ydl_opts_fallback():
    """Fallback seçenekler"""
    return {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'age_limit': None,  # Yaş kontrolünü devre dışı bırak
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_embedded'],  # En az kısıtlamalı client
                'skip': ['hls', 'dash']
            }
        },
    }

@app.get("/proxy-audio/{video_id}")
async def proxy_audio(video_id: str = Path(..., description="YouTube Video ID")):
    """
    YouTube audio proxy - PO Token ile bot korumasını aşar
    """
    now = datetime.utcnow()
    start_time = time.time()
    print(f"\n[{now.strftime('%H:%M:%S')}] İstek: video_id={video_id}")
    
    # Cache kontrolü
    if video_id in audio_cache:
        cached_url, expire_time = audio_cache[video_id]
        if now < expire_time:
            elapsed = time.time() - start_time
            print(f"✓ Cache HIT ({elapsed:.2f}s)")
            return await stream_audio(cached_url, video_id)
        else:
            print(f"⚠ Cache EXPIRED")
            del audio_cache[video_id]
    
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    
    # Strateji 1: PO Token ile dene (en güçlü)
    print("→ Strateji 1: PO Token ile deneniyor...")
    audio_url = await extract_audio_url(youtube_url, get_ydl_opts_with_po_token())
    
    # Strateji 2: TV Embedded client (fallback)
    if not audio_url:
        print("→ Strateji 2: TV Embedded client deneniyor...")
        audio_url = await extract_audio_url(youtube_url, get_ydl_opts_fallback())
    
    if not audio_url:
        # Detaylı hata mesajı
        has_po_token = check_po_token_provider()
        
        error_detail = {
            "error": "Bot koruması aşılamadı",
            "video_id": video_id,
            "po_token_installed": has_po_token
        }
        
        if not has_po_token:
            error_detail["solution"] = "PO Token provider kurun: pip install bgutil-ytdlp-pot-provider"
            error_detail["instructions"] = [
                "1. pip install bgutil-ytdlp-pot-provider",
                "2. Docker ile PO Token server başlatın: docker run -d -p 8080:8080 brainicism/bgutil-ytdlp-pot-provider",
                "3. Sunucuyu restart edin"
            ]
        else:
            error_detail["message"] = "Video yaş kısıtlamalı veya bölge kısıtlamalı olabilir"
        
        raise HTTPException(status_code=403, detail=error_detail)
    
    # Cache'e ekle
    expire = now + timedelta(minutes=50)
    audio_cache[video_id] = (audio_url, expire)
    
    elapsed = time.time() - start_time
    print(f"✓ Extraction tamamlandı ({elapsed:.2f}s)")
    
    return await stream_audio(audio_url, video_id)

async def extract_audio_url(youtube_url: str, ydl_opts: dict) -> Optional[str]:
    """YouTube'dan audio URL'i çıkarır"""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            
            audio_url = info.get('url')
            
            if not audio_url:
                formats = info.get('formats', [])
                for fmt in formats:
                    if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                        audio_url = fmt.get('url')
                        break
            
            if audio_url:
                print(f"✓ Audio URL bulundu")
                return audio_url
            
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        # Sessizce devam et
        pass
    except Exception as e:
        pass
    
    return None

async def stream_audio(audio_url: str, video_id: str):
    """Audio stream'i proxy eder"""
    async def generate():
        try:
            async with httpx.AsyncClient(
                timeout=60.0,
                follow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
                    'Range': 'bytes=0-',
                }
            ) as client:
                async with client.stream("GET", audio_url) as resp:
                    if resp.status_code not in (200, 206):
                        raise HTTPException(500, f"Stream hatası: {resp.status_code}")
                    
                    chunk_count = 0
                    async for chunk in resp.aiter_bytes(chunk_size=512*1024):
                        chunk_count += 1
                        yield chunk
                    
                    print(f"✓ Stream tamamlandı: {video_id} ({chunk_count} chunks)")
        except Exception as e:
            print(f"✗ Stream hatası: {str(e)}")
            raise
    
    print(f"→ Stream başlatılıyor: {video_id}")
    return StreamingResponse(
        generate(),
        media_type="audio/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600"
        }
    )

@app.get("/health")
async def health():
    """Health check + PO Token durumu"""
    has_po_token = check_po_token_provider()
    
    return {
        "status": "ok",
        "cache_size": len(audio_cache),
        "po_token_provider": "installed" if has_po_token else "missing",
        "recommendation": "Install PO Token for best results" if not has_po_token else "All good!"
    }

@app.get("/setup-instructions")
async def setup_instructions():
    """PO Token kurulum talimatları"""
    return {
        "title": "PO Token Kurulumu",
        "why": "YouTube'un bot korumasını aşmak için gerekli",
        "steps": [
            {
                "step": 1,
                "title": "Plugin Kurulumu",
                "command": "pip install bgutil-ytdlp-pot-provider"
            },
            {
                "step": 2,
                "title": "Docker ile PO Token Server (Kolay Yöntem)",
                "commands": [
                    "docker run -d --name po-token-server -p 8080:8080 brainicism/bgutil-ytdlp-pot-provider",
                    "# Server otomatik başlar, restart gerek yok"
                ]
            },
            {
                "step": 3,
                "title": "Manuel Kurulum (Docker yoksa)",
                "commands": [
                    "git clone --single-branch --branch 1.2.2 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git",
                    "cd bgutil-ytdlp-pot-provider/server/",
                    "npm install",
                    "npx tsc",
                    "node build/main.js &"
                ]
            },
            {
                "step": 4,
                "title": "Test",
                "command": "curl http://localhost:8000/health"
            }
        ],
        "note": "PO Token server arka planda çalışmalı. Docker ile en kolay."
    }

@app.post("/clear-cache")
async def clear_cache():
    """Cache temizle"""
    size = len(audio_cache)
    audio_cache.clear()
    return {"success": True, "cleared": size}
