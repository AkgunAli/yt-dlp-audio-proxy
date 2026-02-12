from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import StreamingResponse
import yt_dlp
import httpx
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import asyncio

app = FastAPI(title="YouTube Audio Proxy (PO Token)")

# Cache: {video_id: (audio_url, expire_time)}
audio_cache: Dict[str, Tuple[str, datetime]] = {}

# PO Token server durumu
po_token_available = False

async def check_po_token_server():
    """PO Token server çalışıyor mu kontrol et"""
    global po_token_available
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8080/health", timeout=2.0)
            po_token_available = response.status_code == 200
            if po_token_available:
                print("✓ PO Token server aktif")
            return po_token_available
    except Exception as e:
        po_token_available = False
        print(f"⚠ PO Token server ulaşılamıyor: {e}")
        return False

@app.on_event("startup")
async def startup_event():
    """Başlangıçta PO Token kontrolü"""
    print("🔍 PO Token server kontrol ediliyor...")
    await asyncio.sleep(2)  # Server'ın başlaması için bekle
    await check_po_token_server()

def get_ydl_opts():
    """yt-dlp seçenekleri"""
    return {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'noplaylist': True,
        'socket_timeout': 30,
        
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'tv_embedded'],
                'skip': ['hls', 'dash']
            }
        },
        
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }

@app.get("/proxy-audio/{video_id}")
async def proxy_audio(video_id: str = Path(..., description="YouTube Video ID")):
    """
    YouTube audio proxy - PO Token ile bot korumasını aşar
    
    Kullanım:
    curl http://localhost:8000/proxy-audio/dQw4w9WgXcQ
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
    
    # Audio URL'i çıkar
    audio_url = await extract_audio_url(youtube_url)
    
    if not audio_url:
        # PO Token durumunu kontrol et
        await check_po_token_server()
        
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Bot koruması aşılamadı",
                "video_id": video_id,
                "po_token_server": "active" if po_token_available else "inactive",
                "message": "PO Token server çalışmıyor, konteyner loglarını kontrol edin" if not po_token_available else "Video kısıtlamalı olabilir"
            }
        )
    
    # Cache'e ekle
    expire = now + timedelta(minutes=50)
    audio_cache[video_id] = (audio_url, expire)
    
    elapsed = time.time() - start_time
    print(f"✓ Extraction tamamlandı ({elapsed:.2f}s)")
    
    return await stream_audio(audio_url, video_id)

async def extract_audio_url(youtube_url: str) -> Optional[str]:
    """YouTube'dan audio URL'i çıkarır"""
    try:
        with yt_dlp.YoutubeDL(get_ydl_opts()) as ydl:
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
            
    except Exception as e:
        print(f"✗ Extraction hatası: {str(e)[:200]}")
    
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
    await check_po_token_server()
    
    return {
        "status": "ok",
        "cache_size": len(audio_cache),
        "po_token_server": "active ✓" if po_token_available else "inactive ✗",
        "recommendation": "Konteyner loglarını kontrol edin" if not po_token_available else "All systems operational"
    }

@app.get("/po-token-status")
async def po_token_status():
    """PO Token server detaylı durum"""
    await check_po_token_server()
    
    status = {
        "server_running": po_token_available,
        "server_url": "http://localhost:8080"
    }
    
    if po_token_available:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8080/health", timeout=2.0)
                status["server_response"] = response.json() if response.status_code == 200 else "error"
        except Exception as e:
            status["error"] = str(e)
    
    return status

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

@app.post("/clear-cache")
async def clear_cache():
    """Tüm cache'i temizler"""
    size = len(audio_cache)
    audio_cache.clear()
    print(f"✓ Cache temizlendi: {size} item")
    return {
        "success": True,
        "cleared_items": size
    }
