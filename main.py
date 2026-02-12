from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import StreamingResponse
import yt_dlp
import httpx
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple

app = FastAPI(title="YouTube Audio Proxy (No Bot - Stream Relay)")

# Cache: {video_id: (audio_url, expire_time)}
audio_cache: Dict[str, Tuple[str, datetime]] = {}

@app.get("/proxy-audio/{video_id}")
async def proxy_audio(video_id: str = Path(..., description="YouTube Video ID")):
    now = datetime.utcnow()
    start_time = time.time()
    print(f"Proxy istek: video_id={video_id}")

    # Cache kontrolü
    if video_id in audio_cache:
        cached_url, expire_time = audio_cache[video_id]
        if now < expire_time:
            print(f"Cache HIT ({time.time() - start_time:.2f} sn)")
            return await stream_audio(cached_url, video_id)
        else:
            print(f"Cache EXPIRED: {video_id}")
            del audio_cache[video_id]

    youtube_url = f"https://youtube.com/watch?v={video_id}"
    print(f"Extraction başladı: {youtube_url}")

    ydl_opts = {
        'format': '140/bestaudio[ext=m4a]/best[ext=m4a]/bestaudio',  # m4a öncelikli
        'quiet': True,
        'simulate': True,
        'noplaylist': True,
        'extractor_args': {'youtube': {'player_client': ['android']}},  # Android client en az bot algılıyor
        'user_agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        'referer': 'https://m.youtube.com/',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            audio_url = info.get('url') or next((f['url'] for f in info.get('formats', []) if f.get('format_id') == '140'), None)
            if not audio_url:
                raise ValueError("m4a formatı yok")

            # Cache'e ekle (TTL 1 saat)
            expire = now + timedelta(hours=1)
            audio_cache[video_id] = (audio_url, expire)

            print(f"Extraction bitti ({time.time() - start_time:.2f} sn) - Cache eklendi")
            return await stream_audio(audio_url, video_id)

    except Exception as e:
        print(f"Hata: {str(e)}")
        raise HTTPException(500, str(e))

async def stream_audio(audio_url: str, video_id: str):
    async def generate():
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("GET", audio_url) as resp:
                if resp.status_code != 200:
                    raise HTTPException(500, f"Stream hatası: {resp.status_code}")
                async for chunk in resp.aiter_bytes(chunk_size=1024*1024):
                    yield chunk

    print(f"Stream başladı: {video_id}")
    return StreamingResponse(generate(), media_type="audio/mp4")
