from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import RedirectResponse
import yt_dlp
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple

app = FastAPI(title="YouTube Audio Stream Proxy (iOS Compatible - Audio Only)")

# Cache: {video_id: (audio_url, expire_time)}
audio_cache: Dict[str, Tuple[str, datetime]] = {}

@app.get("/audio/{video_id}")
async def get_audio_stream(video_id: str = Path(..., description="YouTube Video ID")):
    """
    YouTube videosundan SADECE audio stream URL'sini döndürür (m4a öncelikli).
    Video dönmez, direkt redirect eder. Cache ile hızlandırıldı (TTL: 1 saat).
    """
    start_time = time.time()
    now = datetime.utcnow()
    print(f"İstek: video_id={video_id}")

    # Cache kontrolü
    if video_id in audio_cache:
        cached_url, expire_time = audio_cache[video_id]
        if now < expire_time:
            print(f"Cache HIT ({time.time() - start_time:.2f} sn): {cached_url[:100]}...")
            return RedirectResponse(cached_url)
        else:
            print(f"Cache EXPIRED: {video_id}")
            del audio_cache[video_id]

    youtube_url = f"https://youtube.com/watch?v={video_id}"
    print(f"Extraction başladı: {youtube_url}")

    ydl_opts = {
        'format': '140/bestaudio[ext=m4a]/best[ext=m4a]/bestaudio',  # m4a öncelikli, video yok
        'quiet': True,
        'simulate': True,
        'no_warnings': True,
        'noplaylist': True,
        'extract_flat': True,
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'referer': 'https://www.youtube.com/',
        'extractor_args': {'youtube': {'player_client': ['ios', 'android']}},  # Bot koruması bypass
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)

            # Direkt URL varsa dön (audio-only olmalı)
            if 'url' in info:
                audio_url = info['url']
            else:
                # Formatlar arasından SADECE audio olanları al
                audio_formats = [
                    f for f in info.get('formats', [])
                    if f.get('acodec') != 'none' and f.get('vcodec') == 'none'  # video yok
                ]

                if audio_formats:
                    best_format = max(audio_formats, key=lambda f: f.get('abr', 0) or f.get('tbr', 0))
                    audio_url = best_format.get('url')
                else:
                    raise ValueError("Sadece audio formatı bulunamadı")

            # Cache'e ekle (TTL 1 saat)
            expire = now + timedelta(hours=1)
            audio_cache[video_id] = (audio_url, expire)

            print(f"Extraction bitti ({time.time()
