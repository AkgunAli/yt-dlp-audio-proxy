from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import RedirectResponse
import yt_dlp
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple

app = FastAPI(title="YouTube Audio Stream Proxy (iOS Compatible)")

# Cache: {video_id: (audio_url, expire_time)}
audio_cache: Dict[str, Tuple[str, datetime]] = {}

@app.get("/audio/{video_id}")
async def get_audio_stream(video_id: str = Path(..., description="YouTube Video ID")):
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
        'format': '140/bestaudio[ext=m4a]/best[ext=m4a]/bestaudio',  # m4a öncelikli
        'quiet': True,
        'simulate': True,
        'no_warnings': True,
        'noplaylist': True,
        'extract_flat': True,
        'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'referer': 'https://www.youtube.com/',
        'extractor_args': {'youtube': {'player_client': ['ios', 'android']}},  # Bot bypass
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)

            audio_url = info.get('url') or next((f['url'] for f in info.get('formats', []) if f.get('format_id') == '140'), None)
            if not audio_url:
                raise ValueError("Audio formatı bulunamadı")

            expire = now + timedelta(hours=1)
            audio_cache[video_id] = (audio_url, expire)

            print(f"Extraction bitti ({time.time() - start_time:.2f} sn) - Cache eklendi")
            return RedirectResponse(audio_url)

    except yt_dlp.utils.DownloadError as e:
        print(f"yt-dlp hatası: {str(e)}")
        raise HTTPException(status_code=400, detail=f"YouTube hatası: {str(e)}")
    except Exception as e:
        print(f"Beklenmedik hata: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Sunucu hatası: {str(e)}")
