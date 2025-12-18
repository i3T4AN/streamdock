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
import os
import asyncio
from pathlib import Path
from job_worker import job_worker

# Compatible video codecs that browsers can play natively
COMPATIBLE_VIDEO_CODECS = {'h264', 'vp8', 'vp9', 'av1'}
# Compatible container formats (fast path - skip ffprobe)
COMPATIBLE_CONTAINERS = {'.mp4', '.mov', '.webm'}
# All video extensions we care about
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.m4v', '.wmv'}


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
    """
    Process completed download:
    1. Find video files in download location.
    2. Smart codec check - bypass H.264, queue H.265/AV1/unknown.
    3. Trigger library scan to update DB.
    """
    print(f"Processing completed download: {name} in {save_path}")
    
    # 1. Find all video files
    full_path = Path(save_path) / name if save_path and name else Path(save_path or "")
    
    video_files = []
    if full_path.is_file():
        if full_path.suffix.lower() in VIDEO_EXTENSIONS:
            video_files.append(full_path)
    elif full_path.is_dir():
        for root, _, files in os.walk(full_path):
            for f in files:
                if Path(f).suffix.lower() in VIDEO_EXTENSIONS:
                    video_files.append(Path(root) / f)
    
    print(f"Found {len(video_files)} video files in {full_path}")
    
    # 2. Evaluate and Queue (Smart Codec Check)
    for video_path in video_files:
        path_str = str(video_path)
        ext = video_path.suffix.lower()
        
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
            await job_worker.add_job(source_path=path_str)

    # 3. Update Library (Database Sync)
    print("Starting library scan to sync metadata...")
    result = await library_scanner.scan_and_import()
    print(f"Scan complete: imported {result['imported']}, skipped {result['skipped']}")
    
    if result['imported'] > 0:
        print(f"New media imported to DB: {result['imported_items']}")


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
