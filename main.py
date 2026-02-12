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
PO_SERVER_URL = "http://localhost:4416"  # Default bgutil portu – gerekirse .env'den çek

async def check_po_token_server(max_retries=3):
    """PO Token server çalışıyor mu kontrol et (retry ile)"""
    global po_token_available
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient() as client:
                # Sadece bağlantı testi – /health yok, root / bile yeterli olabilir
                response = await client.head(f"{PO_SERVER_URL}/", timeout=3.0)
                po_token_available = 200 <= response.status_code < 500
                if po_token_available:
                    print(f"✓ PO Token server aktif ({PO_SERVER_URL})")
                    return True
                else:
                    print(f"⚠ PO server yanıt kodu: {response.status_code}")
        except Exception as e:
            print(f"⚠ PO Token server ulaşılamıyor (deneme {attempt}/{max_retries}): {e}")
        
        if attempt < max_retries:
            await asyncio.sleep(3)  # Retry arası bekle
    
    po_token_available = False
    return False

@app.on_event("startup")
async def startup_event():
    """Başlangıçta PO Token kontrolü + retry"""
    print("🔍 PO Token server kontrol ediliyor...")
    await asyncio.sleep(5)  # Server'ın başlaması için biraz daha uzun bekle
    await check_po_token_server()

def get_ydl_opts():
    """yt-dlp seçenekleri – PO Token provider'ı otomatik kullanacak şekilde"""
    opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'noplaylist': True,
        'socket_timeout': 30,
        
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'tv_embedded'],
                'skip': ['hls', 'dash'],
                # PO Token provider'ı belirt (plugin yüklüyse otomatik alır, ama emin olmak için)
                # 'pot_provider': f'{PO_SERVER_URL}'  # Eğer plugin destekliyorsa ekle
            }
        },
        
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        },
    }
    return opts

@app.get("/proxy-audio/{video_id}")
async def proxy_audio(video_id: str = Path(..., description="YouTube Video ID")):
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
        await check_po_token_server()
        detail = {
            "error": "Bot koruması aşılamadı",
            "video_id": video_id,
            "po_token_server": "active" if po_token_available else "inactive",
        }
        if not po_token_available:
            detail["message"] = "PO Token server çalışmıyor – logları kontrol edin (port 4416 açık mı?)"
        else:
            detail["message"] = "Video kısıtlamalı olabilir veya extraction başarısız"
        
        raise HTTPException(status_code=403, detail=detail)
    
    # Cache'e ekle (expire'ı kısalttım – YouTube URL'leri çabuk geçersizleşir)
    expire = now + timedelta(minutes=30)
    audio_cache[video_id] = (audio_url, expire)
    
    elapsed = time.time() - start_time
    print(f"✓ Extraction tamamlandı ({elapsed:.2f}s)")
    
    return await stream_audio(audio_url, video_id)

async def extract_audio_url(youtube_url: str) -> Optional[str]:
    try:
        with yt_dlp.YoutubeDL(get_ydl_opts()) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            
            audio_url = info.get('url')
            if audio_url:
                print(f"✓ Direkt audio URL bulundu")
                return audio_url
            
            # Alternatif: formats içinden audio-only bul
            formats = info.get('formats', [])
            for fmt in formats:
                if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none':
                    audio_url = fmt.get('url')
                    if audio_url:
                        print(f"✓ Audio-only format bulundu")
                        return audio_url
            
    except Exception as e:
        print(f"✗ Extraction hatası: {str(e)[:300]} ...")
    
    return None

async def stream_audio(audio_url: str, video_id: str):
    async def generate():
        try:
            async with httpx.AsyncClient(
                timeout=90.0,  # Stream uzun sürebilir
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
            "Cache-Control": "public, max-age=1800"
        }
    )

@app.get("/health")
async def health():
    await check_po_token_server()
    return {
        "status": "ok",
        "cache_size": len(audio_cache),
        "po_token_server": "active ✓" if po_token_available else "inactive ✗ (port 4416 kontrol et)",
        "timestamp": datetime.utcnow().isoformat(),
        "recommendation": "PO server loglarını incele" if not po_token_available else "Sistem çalışıyor"
    }

@app.get("/po-token-status")
async def po_token_status():
    await check_po_token_server()
    status = {
        "server_running": po_token_available,
        "server_url": PO_SERVER_URL
    }
    if po_token_available:
        try:
            async with httpx.AsyncClient() as client:
                # Sadece bağlantı testi
                resp = await client.head(PO_SERVER_URL, timeout=3.0)
                status["reachable"] = resp.status_code < 500
        except Exception as e:
            status["error"] = str(e)
    return status

@app.get("/cache-stats")
async def cache_stats():
    now = datetime.utcnow()
    active = sum(1 for _, (_, expire) in audio_cache.items() if expire > now)
    return {
        "total_cached": len(audio_cache),
        "active": active,
        "expired": len(audio_cache) - active
    }

@app.post("/clear-cache")
async def clear_cache():
    size = len(audio_cache)
    audio_cache.clear()
    print(f"✓ Cache temizlendi: {size} item")
    return {"success": True, "cleared_items": size}
