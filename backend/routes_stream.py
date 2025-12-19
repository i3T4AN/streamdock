# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Streaming API routes

from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import FileResponse, Response, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Media, Episode, MediaType
from streamer import streamer


# Router
router = APIRouter(prefix="/api/stream", tags=["Streaming"])
poster_router = APIRouter(prefix="/api/posters", tags=["Posters"])


# Streaming Endpoints
@router.get("/{media_id}")
async def stream_media(
    media_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Stream a media file with Range request support for seeking.
    
    - **media_id**: The media ID
    
    Supports HTTP Range headers for video seeking.
    """
    media = await db.get(Media, media_id)
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Determine file to stream
    if media.media_type == MediaType.MOVIE:
        file_path = media.file_path
    else:
        raise HTTPException(
            status_code=400,
            detail="Use /api/stream/{media_id}/episode/{episode_id} for TV shows"
        )
    
    if not file_path:
        raise HTTPException(status_code=404, detail="No video file available")
    
    # Check for transcoded version first
    transcoded = streamer.get_transcoded_path(media_id)
    if transcoded:
        file_path = str(transcoded)
    
    return await streamer.stream_file(file_path, request)


@router.get("/{media_id}/episode/{episode_id}")
async def stream_episode(
    media_id: int,
    episode_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Stream a specific episode.
    
    - **media_id**: The media ID
    - **episode_id**: The episode ID
    """
    from sqlalchemy import select
    from models import TranscodeJob, TranscodeStatus
    
    episode = await db.get(Episode, episode_id)
    
    if not episode or episode.media_id != media_id:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    file_path = episode.file_path
    
    # Check for completed transcode job for this episode
    result = await db.execute(
        select(TranscodeJob)
        .where(TranscodeJob.episode_id == episode_id)
        .where(TranscodeJob.status == TranscodeStatus.COMPLETE)
    )
    transcode_job = result.scalars().first()
    
    if transcode_job and transcode_job.output_path:
        transcoded_path = Path(transcode_job.output_path)
        if transcoded_path.exists():
            file_path = str(transcoded_path)
            print(f"Streaming transcoded: {file_path}")
    
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="Episode file not found")
    
    return await streamer.stream_file(file_path, request)


# HLS Endpoints
@router.get("/{media_id}/hls/master.m3u8")
async def get_hls_manifest(
    media_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get HLS master playlist for adaptive streaming.
    
    - **media_id**: The media ID
    """
    media = await db.get(Media, media_id)
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    return await streamer.get_hls_manifest(media_id)


@router.get("/{media_id}/hls/{segment}")
async def get_hls_segment(
    media_id: int,
    segment: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get HLS segment file (.ts).
    
    - **media_id**: The media ID
    - **segment**: The segment filename (e.g., segment_001.ts)
    """
    media = await db.get(Media, media_id)
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    if not segment.endswith(".ts"):
        raise HTTPException(status_code=400, detail="Invalid segment file")
    
    return await streamer.get_hls_segment(media_id, segment)


# Stream Info
@router.get("/{media_id}/info")
async def get_stream_info(
    media_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get streaming availability info for media.
    
    - **media_id**: The media ID
    """
    media = await db.get(Media, media_id)
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    info = streamer.get_stream_info(media_id)
    info["title"] = media.title
    info["media_type"] = media.media_type.value
    
    return info


# Poster Endpoints
@poster_router.get("/{media_id}")
async def get_poster(
    media_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get poster image for media.
    Redirects to TMDB URL or returns cached local copy.
    
    - **media_id**: The media ID
    """
    media = await db.get(Media, media_id)
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    if media.poster_url:
        # Redirect to TMDB poster URL
        return RedirectResponse(url=media.poster_url, status_code=302)
    
    # No poster available
    raise HTTPException(status_code=404, detail="No poster available")


@poster_router.get("/{media_id}/backdrop")
async def get_backdrop(
    media_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get backdrop image for media.
    
    - **media_id**: The media ID
    """
    media = await db.get(Media, media_id)
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    if media.backdrop_url:
        return RedirectResponse(url=media.backdrop_url, status_code=302)
    
    raise HTTPException(status_code=404, detail="No backdrop available")
