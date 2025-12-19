#===============================================================
# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Library management API routes
#===============================================================

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models import Media, Episode, MediaType
from library_scanner import library_scanner
from tmdb_client import tmdb_client


# Router
router = APIRouter(prefix="/api/library", tags=["Library"])


# Response Models
class EpisodeResponse(BaseModel):
    """Episode information."""
    id: int
    season: int
    episode: int
    title: Optional[str]
    file_path: str
    duration: Optional[int]
    
    class Config:
        from_attributes = True


class MediaResponse(BaseModel):
    """Media information."""
    id: int
    title: str
    tmdb_id: Optional[int]
    media_type: str
    year: Optional[int]
    poster_url: Optional[str]
    backdrop_url: Optional[str]
    overview: Optional[str]
    folder_path: str
    file_path: Optional[str]
    episode_count: Optional[int] = None
    has_originals: bool = False  # True if non-MP4 originals exist alongside transcoded MP4s
    
    class Config:
        from_attributes = True
    
    @classmethod
    def from_model(cls, m: "Media", episode_count: Optional[int] = None, has_originals: bool = False) -> "MediaResponse":
        """Create MediaResponse from Media model."""
        from models import MediaType
        return cls(
            id=m.id,
            title=m.title,
            tmdb_id=m.tmdb_id,
            media_type=m.media_type.value,
            year=m.year,
            poster_url=m.poster_url,
            backdrop_url=m.backdrop_url,
            overview=m.overview,
            folder_path=m.folder_path,
            file_path=m.file_path,
            episode_count=episode_count,
            has_originals=has_originals,
        )


class MediaDetailResponse(MediaResponse):
    """Detailed media information with episodes."""
    episodes: List[EpisodeResponse] = []


class UpdateMediaRequest(BaseModel):
    """Request to update media metadata."""
    title: Optional[str] = None
    tmdb_id: Optional[int] = None
    year: Optional[int] = None
    overview: Optional[str] = None
    poster_url: Optional[str] = None
    backdrop_url: Optional[str] = None


class ScanResponse(BaseModel):
    """Library scan result."""
    scanned: int
    imported: int
    skipped: int
    errors: int
    imported_items: List[str]
    skipped_items: List[str]


# Helper to check if media has replaceable originals
TRANSCODE_EXTENSIONS = {'.mkv', '.avi', '.wmv', '.flv', '.webm', '.mov', '.m4v', '.ts', '.m2ts'}

def check_has_originals(media: Media) -> bool:
    """
    Check if media has original non-MP4 files that can be replaced.
    Returns True only if:
    - Original files exist in /downloads/ with extensions needing transcode
    - Corresponding MP4 files exist in /transcoded/
    """
    from pathlib import Path
    
    files_to_check = []
    
    if media.media_type == MediaType.TV:
        # For TV shows, check episode file paths
        for ep in media.episodes:
            if ep.file_path:
                files_to_check.append(ep.file_path)
    else:
        # For movies, check media file path
        if media.file_path:
            files_to_check.append(media.file_path)
    
    # Check if any original (non-MP4) files exist in /downloads/
    for file_path in files_to_check:
        path = Path(file_path)
        ext = path.suffix.lower()
        
        # If file is already an MP4 in /transcoded/, check if original exists
        if ext == '.mp4' and '/transcoded/' in str(path):
            # Derive original path - look for any transcode extension in /downloads/
            filename_stem = path.stem
            for orig_ext in TRANSCODE_EXTENSIONS:
                # Check in the folder_path for original
                if media.folder_path:
                    orig_path = Path(media.folder_path) / f"{filename_stem}{orig_ext}"
                    if orig_path.exists():
                        return True
        elif ext in TRANSCODE_EXTENSIONS:
            # File path points to original - check if transcoded MP4 exists
            transcoded_path = Path('/transcoded') / f"{path.stem}.mp4"
            if transcoded_path.exists() and Path(file_path).exists():
                return True
    
    return False


# Endpoints
@router.get("", response_model=List[MediaResponse])
async def list_library(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List all media in the library.
    
    - **limit**: Max items to return (default 50, max 100)
    - **offset**: Pagination offset
    """
    
    query = (
        select(Media)
        .options(selectinload(Media.episodes))  # Eagerly load episodes
        .order_by(Media.title)
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    media_list = result.scalars().all()
    
    return [MediaResponse.from_model(m, len(m.episodes) if m.media_type == MediaType.TV else None, check_has_originals(m)) for m in media_list]


@router.get("/movies", response_model=List[MediaResponse])
async def list_movies(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
):
    """List movies only."""
    query = (
        select(Media)
        .where(Media.media_type == MediaType.MOVIE)
        .order_by(Media.title)
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    media_list = result.scalars().all()
    
    return [MediaResponse.from_model(m) for m in media_list]


@router.get("/shows", response_model=List[MediaResponse])
async def list_shows(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
):
    """List TV shows only."""
    
    query = (
        select(Media)
        .where(Media.media_type == MediaType.TV)
        .options(selectinload(Media.episodes))
        .order_by(Media.title)
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    media_list = result.scalars().all()
    
    return [MediaResponse.from_model(m, len(m.episodes)) for m in media_list]


@router.post("/scan", response_model=ScanResponse)
async def scan_library():
    """
    Trigger a manual library scan.
    Scans completed downloads folder and imports new media.
    """
    result = await library_scanner.scan_and_import()
    
    return ScanResponse(
        scanned=result["scanned"],
        imported=result["imported"],
        skipped=result["skipped"],
        errors=result["errors"],
        imported_items=result["imported_items"],
        skipped_items=result["skipped_items"],
    )


@router.get("/{media_id}", response_model=MediaDetailResponse)
async def get_media(media_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get detailed information for a specific media item.
    
    - **media_id**: The media ID
    """
    
    # Eagerly load episodes to avoid async lazy loading issue
    query = select(Media).where(Media.id == media_id).options(selectinload(Media.episodes))
    result = await db.execute(query)
    media = result.scalars().first()
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    episodes = []
    if media.media_type == MediaType.TV:
        episodes = [
            EpisodeResponse(
                id=ep.id,
                season=ep.season,
                episode=ep.episode,
                title=ep.title,
                file_path=ep.file_path,
                duration=ep.duration,
            )
            for ep in sorted(media.episodes, key=lambda e: (e.season, e.episode))
        ]
    
    return MediaDetailResponse(
        id=media.id,
        title=media.title,
        tmdb_id=media.tmdb_id,
        media_type=media.media_type.value,
        year=media.year,
        poster_url=media.poster_url,
        backdrop_url=media.backdrop_url,
        overview=media.overview,
        folder_path=media.folder_path,
        file_path=media.file_path,
        episode_count=len(episodes),
        episodes=episodes,
    )


@router.get("/{media_id}/details")
async def get_media_full_details(media_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get full details for a media item, including TMDB cast/crew data.
    Used for the Netflix-style detail view.
    
    - **media_id**: The media ID
    """
    
    # Get media from database
    query = select(Media).where(Media.id == media_id).options(selectinload(Media.episodes))
    result = await db.execute(query)
    media = result.scalars().first()
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Base response from database
    response = {
        "id": media.id,
        "title": media.title,
        "tmdb_id": media.tmdb_id,
        "media_type": media.media_type.value,
        "year": media.year,
        "poster_url": media.poster_url,
        "backdrop_url": media.backdrop_url,
        "overview": media.overview,
        "folder_path": media.folder_path,
        "file_path": media.file_path,
        "genres": [],
        "cast": [],
        "director": None,
        "creators": [],
        "runtime": None,
        "tagline": None,
        "vote_average": None,
    }
    
    # Get episodes for TV shows
    if media.media_type == MediaType.TV:
        response["episodes"] = [
            {
                "id": ep.id,
                "season": ep.season,
                "episode": ep.episode,
                "title": ep.title,
                "file_path": ep.file_path,
            }
            for ep in sorted(media.episodes, key=lambda e: (e.season, e.episode))
        ]
    
    # Fetch full details from TMDB if we have an ID
    if media.tmdb_id:
        try:
            if media.media_type == MediaType.MOVIE:
                tmdb_data = await tmdb_client.get_movie_details(media.tmdb_id)
            else:
                tmdb_data = await tmdb_client.get_tv_details(media.tmdb_id)
            
            if tmdb_data:
                response["genres"] = tmdb_data.get("genres", [])
                response["cast"] = tmdb_data.get("cast", [])
                response["director"] = tmdb_data.get("director")
                response["creators"] = tmdb_data.get("creators", [])
                response["runtime"] = tmdb_data.get("runtime") or (
                    tmdb_data.get("episode_runtime", [None])[0] if tmdb_data.get("episode_runtime") else None
                )
                response["tagline"] = tmdb_data.get("tagline")
                response["vote_average"] = tmdb_data.get("vote_average")
                response["number_of_seasons"] = tmdb_data.get("number_of_seasons")
                response["networks"] = tmdb_data.get("networks", [])
        except Exception as e:
            print(f"Failed to fetch TMDB details: {e}")
    
    return response


@router.get("/{media_id}/episodes", response_model=List[EpisodeResponse])
async def get_episodes(media_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get episodes for a TV show.
    
    - **media_id**: The media ID
    """
    
    query = select(Media).where(Media.id == media_id).options(selectinload(Media.episodes))
    result = await db.execute(query)
    media = result.scalars().first()
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    if media.media_type != MediaType.TV:
        raise HTTPException(status_code=400, detail="Not a TV show")
    
    return [
        EpisodeResponse(
            id=ep.id,
            season=ep.season,
            episode=ep.episode,
            title=ep.title,
            file_path=ep.file_path,
            duration=ep.duration,
        )
        for ep in sorted(media.episodes, key=lambda e: (e.season, e.episode))
    ]


@router.put("/{media_id}", response_model=MediaResponse)
async def update_media(
    media_id: int,
    request: UpdateMediaRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Update media metadata manually.
    
    - **media_id**: The media ID
    """
    media = await db.get(Media, media_id)
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Update fields if provided
    if request.title is not None:
        media.title = request.title
    if request.tmdb_id is not None:
        media.tmdb_id = request.tmdb_id
    if request.year is not None:
        media.year = request.year
    if request.overview is not None:
        media.overview = request.overview
    if request.poster_url is not None:
        media.poster_url = request.poster_url
    if request.backdrop_url is not None:
        media.backdrop_url = request.backdrop_url
    
    await db.commit()
    await db.refresh(media)
    
    return MediaResponse.from_model(media)


@router.delete("/{media_id}", response_model=dict)
async def delete_media(
    media_id: int,
    delete_files: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """
    Remove media from library.
    
    - **media_id**: The media ID
    - **delete_files**: If true, also delete files from disk
    """
    import shutil
    from pathlib import Path
    
    media = await db.get(Media, media_id)
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    title = media.title
    folder_path = media.folder_path
    file_path = media.file_path
    
    # Delete from database
    await db.delete(media)
    await db.commit()
    
    # Delete files if requested
    files_deleted = False
    if delete_files:
        try:
            if folder_path and Path(folder_path).exists():
                # Don't delete root downloads folder
                if folder_path != "/downloads":
                    shutil.rmtree(folder_path)
                    files_deleted = True
            elif file_path and Path(file_path).exists():
                Path(file_path).unlink()
                files_deleted = True
        except Exception as e:
            print(f"Failed to delete files: {e}")
    
    return {
        "status": "ok", 
        "message": f"Removed '{title}' from library",
        "files_deleted": files_deleted,
    }


@router.post("/{media_id}/replace-originals", response_model=dict)
async def replace_originals(
    media_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete original non-MP4 files after transcoding is complete.
    Only works when transcoded MP4s exist for all files.
    
    - **media_id**: The media ID
    """
    from pathlib import Path
    
    query = select(Media).where(Media.id == media_id).options(selectinload(Media.episodes))
    result = await db.execute(query)
    media = result.scalars().first()
    
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    deleted_count = 0
    deleted_files = []
    errors = []
    
    # Collect all file paths to check
    if media.media_type == MediaType.TV:
        file_paths = [(ep.file_path, ep) for ep in media.episodes if ep.file_path]
    else:
        file_paths = [(media.file_path, media)] if media.file_path else []
    
    for file_path, record in file_paths:
        path = Path(file_path)
        ext = path.suffix.lower()
        
        # Case 1: DB points to MP4 in /transcoded/ - find and delete original in /downloads/
        if ext == '.mp4' and '/transcoded/' in str(path):
            filename_stem = path.stem
            for orig_ext in TRANSCODE_EXTENSIONS:
                if media.folder_path:
                    orig_path = Path(media.folder_path) / f"{filename_stem}{orig_ext}"
                    if orig_path.exists():
                        try:
                            orig_path.unlink()
                            deleted_files.append(str(orig_path))
                            deleted_count += 1
                            print(f"Deleted original: {orig_path}")
                        except Exception as e:
                            errors.append(f"Failed to delete {orig_path}: {e}")
        
        # Case 2: DB still points to original - check if MP4 exists, then delete original
        elif ext in TRANSCODE_EXTENSIONS:
            transcoded_path = Path('/transcoded') / f"{path.stem}.mp4"
            if transcoded_path.exists():
                try:
                    # Delete the original
                    if path.exists():
                        path.unlink()
                        deleted_files.append(str(path))
                        deleted_count += 1
                        print(f"Deleted original: {path}")
                    
                    # Update DB to point to the MP4
                    record.file_path = str(transcoded_path)
                    print(f"Updated file_path to: {transcoded_path}")
                except Exception as e:
                    errors.append(f"Failed to delete {path}: {e}")
    
    await db.commit()
    
    if deleted_count == 0:
        raise HTTPException(status_code=400, detail="No original files found to replace")
    
    return {
        "status": "ok",
        "deleted_count": deleted_count,
        "deleted_files": deleted_files,
        "errors": errors,
    }
