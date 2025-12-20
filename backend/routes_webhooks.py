# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Webhook endpoints for external service callbacks

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from library_scanner import library_scanner


# Router
router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


# Models
class DownloadCompleteRequest(BaseModel):
    """Request from qBittorrent on download completion."""
    name: Optional[str] = None
    hash: Optional[str] = None
    category: Optional[str] = None
    save_path: Optional[str] = None


# Background Tasks
import asyncio
from pathlib import Path
from job_worker import job_worker

# Compatible video codecs that browsers can play natively
COMPATIBLE_VIDEO_CODECS = {'h264', 'vp8', 'vp9', 'av1'}
# Compatible container formats (fast path - skip ffprobe)
COMPATIBLE_CONTAINERS = {'.mp4', '.mov', '.webm'}


async def get_video_codec(filepath: str) -> str:
    """Use ffprobe to get the video codec of a file."""
    try:
        proc = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            filepath,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        codec = stdout.decode().strip().lower()
        print(f"ffprobe: {filepath} -> codec: {codec}")
        return codec
    except asyncio.TimeoutError:
        print(f"ffprobe timeout for {filepath}")
        return "unknown"
    except Exception as e:
        print(f"ffprobe error for {filepath}: {e}")
        return "unknown"


async def process_completed_download(name: str, save_path: str):
    """Scan library, then queue transcode jobs for incompatible files."""
    print(f"Processing completed download: {name} in {save_path}")
    
    # 1. Update Library FIRST (so episodes exist in DB)
    print("Starting library scan to create episodes...")
    result = await library_scanner.scan_and_import()
    print(f"Scan complete: imported {result['imported']}, skipped {result['skipped']}")
    
    if result['imported'] > 0:
        print(f"New media imported to DB: {result['imported_items']}")
    
    # 2. Query DB for episodes needing transcode (instead of using webhook path which may be stale)
    from database import async_session_factory
    from sqlalchemy import select, or_
    from models import Episode
    
    async with async_session_factory() as session:
        # Find episodes with incompatible containers
        incompatible_exts = ('.mkv', '.avi', '.wmv', '.m4v')
        ext_conditions = [Episode.file_path.ilike(f'%{ext}') for ext in incompatible_exts]
        
        result = await session.execute(
            select(Episode).where(or_(*ext_conditions))
        )
        episodes = result.scalars().all()
        
        print(f"Found {len(episodes)} episodes needing transcode check (from DB)")
        
        # 3. Check each episode and queue transcode jobs
        for episode in episodes:
            path_str = episode.file_path
            ext = Path(path_str).suffix.lower()
            
            # Verify file exists
            if not Path(path_str).exists():
                print(f"File not found (skipping): {path_str}")
                continue
            
            # Fast path: known compatible containers
            if ext in COMPATIBLE_CONTAINERS:
                print(f"Container OK (bypass): {path_str}")
                continue
            
            # Deep check: probe the actual codec
            codec = await get_video_codec(path_str)
            
            if codec in COMPATIBLE_VIDEO_CODECS:
                print(f"Codec OK [{codec}] (bypass): {path_str}")
            else:
                print(f"Incompatible codec [{codec}] (queueing): {path_str}")
                print(f"Linked to episode {episode.id}: S{episode.season}E{episode.episode}")
                await job_worker.add_job(
                    source_path=path_str,
                    episode_id=episode.id,
                    media_id=episode.media_id
                )


# Endpoints
@router.post("/download-complete")
async def download_complete(
    request: DownloadCompleteRequest,
    background_tasks: BackgroundTasks,
):
    """
    Webhook called by qBittorrent when a download completes.
    
    Configure in qBittorrent:
    - Settings > Downloads > Run external program on torrent completion
    - Command: curl -X POST http://app:8000/api/webhooks/download-complete -H "Content-Type: application/json" -d '{"name":"%N","hash":"%I","save_path":"%D"}'
    """
    print(f"Webhook received: download complete - {request.name}")
    
    # Process in background so we don't block qBittorrent
    background_tasks.add_task(process_completed_download, request.name, request.save_path)
    
    return {"status": "ok", "message": "Processing download completion"}


@router.post("/download-complete/test")
async def test_webhook():
    """Test endpoint to manually trigger library scan."""
    result = await library_scanner.scan_and_import()
    return {
        "status": "ok",
        "scanned": result["scanned"],
        "imported": result["imported"],
        "removed": result.get("removed", 0),
    }
