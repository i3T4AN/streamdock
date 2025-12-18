# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Torrent management API routes

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from torrent_client import qbit_client, TorrentInfo, format_bytes, format_speed, format_eta


# Router
router = APIRouter(prefix="/api/torrents", tags=["Torrents"])


# Request/Response Models
class AddMagnetRequest(BaseModel):
    """Request to add a magnet link."""
    magnet_link: str
    save_path: Optional[str] = None


class TorrentResponse(BaseModel):
    """Torrent information response."""
    hash: str
    name: str
    state: str
    progress: float
    progress_percent: float
    size: int
    size_formatted: str
    downloaded: int
    uploaded: int
    download_speed: int
    download_speed_formatted: str
    upload_speed: int
    upload_speed_formatted: str
    eta: int
    eta_formatted: str
    ratio: float
    save_path: str
    
    @classmethod
    def from_torrent_info(cls, t: TorrentInfo) -> "TorrentResponse":
        return cls(
            hash=t.hash,
            name=t.name,
            state=t.state.value,
            progress=t.progress,
            progress_percent=round(t.progress * 100, 1),
            size=t.size,
            size_formatted=format_bytes(t.size),
            downloaded=t.downloaded,
            uploaded=t.uploaded,
            download_speed=t.download_speed,
            download_speed_formatted=format_speed(t.download_speed),
            upload_speed=t.upload_speed,
            upload_speed_formatted=format_speed(t.upload_speed),
            eta=t.eta,
            eta_formatted=format_eta(t.eta),
            ratio=round(t.ratio, 2),
            save_path=t.save_path,
        )


class StatsResponse(BaseModel):
    """Transfer statistics response."""
    download_speed: int
    download_speed_formatted: str
    upload_speed: int
    upload_speed_formatted: str
    downloaded_total: int
    downloaded_total_formatted: str
    uploaded_total: int
    uploaded_total_formatted: str


# Endpoints
@router.post("", response_model=dict)
async def add_torrent(request: AddMagnetRequest):
    """
    Add a new torrent from magnet link.
    
    - **magnet_link**: The magnet URI to add
    - **save_path**: Optional custom download path
    """
    if not request.magnet_link.startswith("magnet:"):
        raise HTTPException(status_code=400, detail="Invalid magnet link")
    
    # Check disk space (minimum 5GB required for new downloads)
    from error_utils import check_disk_space
    has_space, message = check_disk_space(5 * 1024 * 1024 * 1024)  # 5 GB
    
    if not has_space:
        raise HTTPException(status_code=507, detail=f"Insufficient disk space: {message}")
    
    success = qbit_client.add_magnet(request.magnet_link, request.save_path)
    
    if success:
        return {"status": "ok", "message": "Torrent added successfully"}
    else:
        raise HTTPException(status_code=500, detail="Failed to add torrent")


@router.get("", response_model=List[TorrentResponse])
async def list_torrents(
    filter: Optional[str] = Query(None, description="Filter: all, downloading, seeding, completed, paused")
):
    """
    List all torrents.
    
    - **filter**: Optional state filter
    """
    torrents = qbit_client.get_torrents(filter_state=filter)
    return [TorrentResponse.from_torrent_info(t) for t in torrents]


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get current download/upload speeds and totals."""
    info = qbit_client.get_transfer_info()
    
    return StatsResponse(
        download_speed=info.get("download_speed", 0),
        download_speed_formatted=format_speed(info.get("download_speed", 0)),
        upload_speed=info.get("upload_speed", 0),
        upload_speed_formatted=format_speed(info.get("upload_speed", 0)),
        downloaded_total=info.get("downloaded_total", 0),
        downloaded_total_formatted=format_bytes(info.get("downloaded_total", 0)),
        uploaded_total=info.get("uploaded_total", 0),
        uploaded_total_formatted=format_bytes(info.get("uploaded_total", 0)),
    )


@router.get("/{torrent_hash}", response_model=TorrentResponse)
async def get_torrent(torrent_hash: str):
    """
    Get details for a specific torrent.
    
    - **torrent_hash**: The torrent hash
    """
    torrent = qbit_client.get_torrent(torrent_hash)
    
    if not torrent:
        raise HTTPException(status_code=404, detail="Torrent not found")
    
    return TorrentResponse.from_torrent_info(torrent)


@router.post("/{torrent_hash}/pause", response_model=dict)
async def pause_torrent(torrent_hash: str):
    """
    Pause a torrent.
    
    - **torrent_hash**: The torrent hash
    """
    success = qbit_client.pause_torrent(torrent_hash)
    
    if success:
        return {"status": "ok", "message": "Torrent paused"}
    else:
        raise HTTPException(status_code=500, detail="Failed to pause torrent")


@router.post("/{torrent_hash}/resume", response_model=dict)
async def resume_torrent(torrent_hash: str):
    """
    Resume a paused torrent.
    
    - **torrent_hash**: The torrent hash
    """
    success = qbit_client.resume_torrent(torrent_hash)
    
    if success:
        return {"status": "ok", "message": "Torrent resumed"}
    else:
        raise HTTPException(status_code=500, detail="Failed to resume torrent")


@router.delete("/{torrent_hash}", response_model=dict)
async def delete_torrent(
    torrent_hash: str,
    delete_files: bool = Query(False, description="Also delete downloaded files")
):
    """
    Remove a torrent.
    
    - **torrent_hash**: The torrent hash
    - **delete_files**: If true, also delete downloaded files
    """
    success = qbit_client.delete_torrent(torrent_hash, delete_files=delete_files)
    
    if success:
        return {"status": "ok", "message": "Torrent removed"}
    else:
        raise HTTPException(status_code=500, detail="Failed to remove torrent")
