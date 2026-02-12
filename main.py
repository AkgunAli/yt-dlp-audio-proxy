from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import StreamingResponse
import yt_dlp
import httpx
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import asyncio
import traceback

app = FastAPI(title="YouTube Audio Proxy (PO Token)")

# Cache: {video_id: (audio_url, expire_time)}
audio_cache: Dict[str, Tuple[str, datetime]] = {}

po_token_available = False
PO_SERVER_URL = "http://localhost:4416"

async def check_po_token_server(max_retries=5):
    global po_token_available
    for attempt in range(1, max_retries + 1):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.head(f"{PO_SERVER_URL}/", timeout=5.0)
                po_token_available = 200 <= response.status_code < 500
                if po_token_available:
                    print(f"✓ PO Token server aktif ({PO_SERVER_URL})")
                    return True
                else:
                    print(f"⚠ PO server yanıt: {response.status_code}")
        except Exception as e:
            print(f"⚠ PO Token server ulaşılamıyor (deneme {attempt}): {e}")
        
        if attempt < max_retries:
            await asyncio.sleep(4)
    
    po_token_available = False
    return False

@app.on_event("startup")
async def startup_event():
    print("🔍 PO Token server kontrol ediliyor...")
    await asyncio.sleep(12)  # Daha güvenli bekleme
    await check_po_token_server()

def get_ydl_opts():
    opts = {
        'format': 'best[ext=mp4]/bestaudio/best',
        'verbose': True,
        'no_warnings': False,
        'simulate': True,
        'noplaylist': True,
        'socket_timeout': 30,

        'cookiefile': '/app/cookies.txt',

        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android', 'ios'],
            },
            'youtubepot-bgutilhttp': {
                'base_url': PO_SERVER_URL,
            },
        },

        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.youtube.com/',
            'Sec-Fetch-Dest': 'document'
        },
    }
    return opts

@app.get("/proxy-audio/{video_id}")
async def proxy_audio(video_id: str = Path(...)):
    now = datetime.utcnow()
    start_time = time.time()
    print(f"\n[{now.strftime('%H:%M:%S')}] İstek: {video_id}")
    
    if video_id in audio_cache:
        cached_url, expire_time = audio_cache[video_id]
        if now < expire_time:
            print(f"✓ Cache HIT ({time.time() - start_time:.2f}s)")
            return await stream_audio(cached_url, video_id)
        else:
            print("⚠ Cache EXPIRED")
            del audio_cache[video_id]
    
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"
    audio_url = await extract_audio_url(youtube_url)
    
    if not audio_url:
        await check_po_token_server()
        detail = {
            "error": "Bot koruması aşılamadı",
            "video_id": video_id,
            "po_token_server": "active" if po_token_available else "inactive",
            "message": "Video kısıtlamalı olabilir, age-restricted olabilir veya extraction başarısız"
        }
        raise HTTPException(status_code=403, detail=detail)
    
    expire = now + timedelta(minutes=20)  # Kısa tuttuk, URL'ler çabuk expire oluyor
    audio_cache[video_id] = (audio_url, expire)
    
    print(f"✓ Extraction OK ({time.time() - start_time:.2f}s)")
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
    
    except yt_dlp.utils.DownloadError as e:
        if "DRM protected" in str(e):
            print(f"DRM korumalı video tespit edildi: {youtube_url}")
        else:
            print(f"yt-dlp DownloadError: {str(e)}")
        traceback.print_exc()
        return None
    
    except Exception as e:
        print(f"✗ Extraction hatası: {str(e)}")
        traceback.print_exc()
        return None
    
    return None
async def stream_audio(audio_url: str, video_id: str):
    async def generate():
        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                async with client.stream("GET", audio_url) as resp:
                    if resp.status_code not in (200, 206):
                        raise Exception(f"Stream status: {resp.status_code}")
                    async for chunk in resp.aiter_bytes(chunk_size=512*1024):
                        yield chunk
        except Exception as e:
            print(f"✗ Stream hatası: {e}")
            raise
    
    return StreamingResponse(
        generate(),
        media_type="audio/mp4",
        headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=1200"}
    )

# Health ve diğer endpoint'ler aynı kalabilir...
