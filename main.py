from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import StreamingResponse
import yt_dlp
import httpx
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import random

app = FastAPI(title="YouTube Audio Proxy (No Cookie)")

# Cache: {video_id: (audio_url, expire_time)}
audio_cache: Dict[str, Tuple[str, datetime]] = {}

# User-Agent rotasyonu
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
]

def get_random_user_agent():
    """Rastgele user agent döndür"""
    return random.choice(USER_AGENTS)

def get_ydl_opts_strategy_1():
    """Strateji 1: iOS client"""
    return {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'extractor_args': {
            'youtube': {
                'player_client': ['ios'],
                'skip': ['hls', 'dash']
            }
        },
        'http_headers': {
            'User-Agent': 'com.google.ios.youtube/19.09.3 (iPhone14,3; U; CPU iOS 15_6 like Mac OS X)',
            'X-YouTube-Client-Name': '5',
            'X-YouTube-Client-Version': '19.09.3',
        }
    }

def get_ydl_opts_strategy_2():
    """Strateji 2: Android Music client"""
    return {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'extractor_args': {
            'youtube': {
                'player_client': ['android_music'],
                'skip': ['hls', 'dash']
            }
        },
        'http_headers': {
            'User-Agent': 'com.google.android.apps.youtube.music/6.42.52 (Linux; U; Android 13)',
        }
    }

def get_ydl_opts_strategy_3():
    """Strateji 3: TV client"""
    return {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_embedded'],
                'skip': ['hls', 'dash']
            }
        },
    }

def get_ydl_opts_strategy_4():
    """Strateji 4: Web + Random User Agent"""
    return {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'http_headers': {
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    }

def get_ydl_opts_strategy_5():
    """Strateji 5: Android embedded"""
    return {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'extractor_args': {
            'youtube': {
                'player_client': ['android_embedded'],
                'skip': ['hls', 'dash']
            }
        },
    }

# Tüm stratejiler
STRATEGIES = [
    ("iOS Client", get_ydl_opts_strategy_1),
    ("Android Music", get_ydl_opts_strategy_2),
    ("TV Embedded", get_ydl_opts_strategy_3),
    ("Web + Random UA", get_ydl_opts_strategy_4),
    ("Android Embedded", get_ydl_opts_strategy_5),
]

@app.get("/proxy-audio/{video_id}")
async def proxy_audio(video_id: str = Path(..., description="YouTube Video ID")):
    """
    YouTube audio proxy endpoint - Çoklu strateji ile bot korumasını aşar
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
    
    # Tüm stratejileri sırayla dene
    for strategy_name, strategy_func in STRATEGIES:
        print(f"→ Deneniyor: {strategy_name}")
        audio_url = await extract_audio_url(youtube_url, strategy_func())
        
        if audio_url:
            print(f"✓ BAŞARILI: {strategy_name}")
            
            # Cache'e ekle
            expire = now + timedelta(minutes=50)
            audio_cache[video_id] = (audio_url, expire)
            
            elapsed = time.time() - start_time
            print(f"✓ Extraction tamamlandı ({elapsed:.2f}s)")
            
            return await stream_audio(audio_url, video_id)
        
        # Stratejiler arası kısa bekleme
        await asyncio.sleep(0.5)
    
    # Hiçbir strateji çalışmadı
    raise HTTPException(
        status_code=403,
        detail={
            "error": "Tüm stratejiler başarısız oldu",
            "tried_strategies": len(STRATEGIES),
            "message": "YouTube bu video için tüm client'ları engelliyor. Video yaş kısıtlamalı veya bölge kısıtlamalı olabilir."
        }
    )

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
                return audio_url
            
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        # Sessizce geç, başka strateji denenecek
        pass
    except Exception as e:
        # Sessizce geç
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
                    'User-Agent': get_random_user_agent(),
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
    """Health check endpoint"""
    return {
        "status": "ok",
        "cache_size": len(audio_cache),
        "available_strategies": len(STRATEGIES)
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

@app.post("/clear-cache")
async def clear_cache():
    """Tüm cache'i temizler"""
    size = len(audio_cache)
    audio_cache.clear()
    return {"success": True, "cleared": size}

# asyncio import ekle
import asyncio
