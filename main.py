from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import StreamingResponse
import yt_dlp
import httpx
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple
import os
from pathlib import Path as PathLib

app = FastAPI(title="YouTube Audio Proxy (Advanced Bot Protection)")

# Cache: {video_id: (audio_url, expire_time)}
audio_cache: Dict[str, Tuple[str, datetime]] = {}

# Cookie dosyası yolu
COOKIES_FILE = "youtube_cookies.txt"

def get_ydl_opts(use_cookies: bool = True):
    """yt-dlp seçeneklerini döndürür"""
    opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'noplaylist': True,
        'socket_timeout': 30,
        
        # En etkili extractor ayarları
        'extractor_args': {
            'youtube': {
                'player_client': ['android_music', 'android', 'web'],
                'skip': ['hls', 'dash']
            }
        },
        
        # Gerçek Android tarayıcı headers
        'http_headers': {
            'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 13) gzip',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
    }
    
    # Cookie kullanımı
    if use_cookies and os.path.exists(COOKIES_FILE):
        opts['cookiefile'] = COOKIES_FILE
        print(f"Cookie dosyası kullanılıyor: {COOKIES_FILE}")
    
    return opts

@app.get("/proxy-audio/{video_id}")
async def proxy_audio(video_id: str = Path(..., description="YouTube Video ID")):
    now = datetime.utcnow()
    start_time = time.time()
    print(f"\n[{now.strftime('%H:%M:%S')}] Proxy istek: video_id={video_id}")
    
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
    
    # Strateji 1: Cookie ile deneme
    audio_url = await extract_audio_url(youtube_url, use_cookies=True)
    
    # Strateji 2: Cookie yoksa/çalışmazsa cookie olmadan deneme
    if not audio_url:
        print("⚠ Cookie ile başarısız, cookie olmadan deneniyor...")
        audio_url = await extract_audio_url(youtube_url, use_cookies=False)
    
    if not audio_url:
        raise HTTPException(
            status_code=403,
            detail="YouTube bot koruması aktif. Lütfen cookie dosyası ekleyin."
        )
    
    # Cache'e ekle (TTL 50 dakika - YouTube URL'leri 1 saat geçerli)
    expire = now + timedelta(minutes=50)
    audio_cache[video_id] = (audio_url, expire)
    
    elapsed = time.time() - start_time
    print(f"✓ Extraction tamamlandı ({elapsed:.2f}s)")
    
    return await stream_audio(audio_url, video_id)

async def extract_audio_url(youtube_url: str, use_cookies: bool) -> str:
    """YouTube'dan audio URL'i çıkarır"""
    ydl_opts = get_ydl_opts(use_cookies)
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            
            # En iyi audio formatını bul
            audio_url = info.get('url')
            
            if not audio_url:
                # Formatlar arasında ara
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
        if "Sign in to confirm" in error_msg or "bot" in error_msg.lower():
            print(f"✗ Bot algılandı: {error_msg[:100]}")
        else:
            print(f"✗ Download hatası: {error_msg[:100]}")
    except Exception as e:
        print(f"✗ Beklenmeyen hata: {str(e)[:100]}")
    
    return None

async def stream_audio(audio_url: str, video_id: str):
    """Audio stream'i proxy eder"""
    async def generate():
        try:
            async with httpx.AsyncClient(
                timeout=60.0,
                follow_redirects=True,
                headers={
                    'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 13)',
                    'Range': 'bytes=0-',  # Range desteği
                }
            ) as client:
                async with client.stream("GET", audio_url) as resp:
                    if resp.status_code not in (200, 206):
                        raise HTTPException(500, f"Stream hatası: {resp.status_code}")
                    
                    chunk_count = 0
                    async for chunk in resp.aiter_bytes(chunk_size=512*1024):  # 512KB chunks
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
    """Health check endpoint"""
    return {
        "status": "ok",
        "cache_size": len(audio_cache),
        "cookie_file_exists": os.path.exists(COOKIES_FILE)
    }

@app.get("/cache-stats")
async def cache_stats():
    """Cache istatistikleri"""
    now = datetime.utcnow()
    active = sum(1 for _, (_, expire) in audio_cache.items() if expire > now)
    return {
        "total_cached": len(audio_cache),
        "active": active,
        "expired": len(audio_cache) - active
    }
