#===============================================================
# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Watch progress and settings API routes
#===============================================================

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import WatchProgress, Settings, Media


# Routers
router = APIRouter(prefix="/api/progress", tags=["Progress"])
settings_router = APIRouter(prefix="/api/settings", tags=["Settings"])


# Models
class ProgressResponse(BaseModel):
    """Watch progress response."""
    media_id: int
    episode_id: Optional[int]
    position: int
    duration: Optional[int]
    progress_percent: float
    completed: bool


class UpdateProgressRequest(BaseModel):
    """Request to update watch progress."""
    position: int
    duration: Optional[int] = None
    episode_id: Optional[int] = None
    completed: Optional[bool] = None


class SettingsResponse(BaseModel):
    """Settings key-value pair."""
    key: str
    value: str


class UpdateSettingsRequest(BaseModel):
    """Request to update settings."""
    settings: Dict[str, str]


# Progress Endpoints
@router.get("/{media_id}", response_model=ProgressResponse)
async def get_progress(
    media_id: int,
    episode_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get watch progress for media.
    
    - **media_id**: The media ID
    - **episode_id**: Optional episode ID for TV shows
    """
    query = select(WatchProgress).where(WatchProgress.media_id == media_id)
    
    if episode_id is not None:
        query = query.where(WatchProgress.episode_id == episode_id)
    else:
        query = query.where(WatchProgress.episode_id.is_(None))
    
    result = await db.execute(query)
    progress = result.scalars().first()
    
    if not progress:
        # Return zero progress if not found
        return ProgressResponse(
            media_id=media_id,
            episode_id=episode_id,
            position=0,
            duration=None,
            progress_percent=0.0,
            completed=False,
        )
    
    return ProgressResponse(
        media_id=progress.media_id,
        episode_id=progress.episode_id,
        position=progress.position,
        duration=progress.duration,
        progress_percent=progress.progress_percent,
        completed=progress.completed,
    )


@router.post("/{media_id}", response_model=ProgressResponse)
async def update_progress(
    media_id: int,
    request: UpdateProgressRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Update watch progress for media.
    
    - **media_id**: The media ID
    - **position**: Current playback position in seconds
    - **duration**: Optional total duration
    - **episode_id**: Optional episode ID for TV shows
    - **completed**: Optional flag to mark as watched
    """
    # Verify media exists
    media = await db.get(Media, media_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    
    # Find existing progress
    query = select(WatchProgress).where(WatchProgress.media_id == media_id)
    
    if request.episode_id is not None:
        query = query.where(WatchProgress.episode_id == request.episode_id)
    else:
        query = query.where(WatchProgress.episode_id.is_(None))
    
    result = await db.execute(query)
    progress = result.scalars().first()
    
    if progress:
        # Update existing
        progress.position = request.position
        if request.duration is not None:
            progress.duration = request.duration
        if request.completed is not None:
            progress.completed = request.completed
        # Auto-complete if near end (95%+)
        elif progress.duration and progress.position >= progress.duration * 0.95:
            progress.completed = True
    else:
        # Create new
        progress = WatchProgress(
            media_id=media_id,
            episode_id=request.episode_id,
            position=request.position,
            duration=request.duration,
            completed=request.completed or False,
        )
        db.add(progress)
    
    await db.commit()
    await db.refresh(progress)
    
    return ProgressResponse(
        media_id=progress.media_id,
        episode_id=progress.episode_id,
        position=progress.position,
        duration=progress.duration,
        progress_percent=progress.progress_percent,
        completed=progress.completed,
    )


@router.delete("/{media_id}", response_model=dict)
async def clear_progress(
    media_id: int,
    episode_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Clear watch progress for media.
    
    - **media_id**: The media ID
    - **episode_id**: Optional episode ID
    """
    query = select(WatchProgress).where(WatchProgress.media_id == media_id)
    
    if episode_id is not None:
        query = query.where(WatchProgress.episode_id == episode_id)
    
    result = await db.execute(query)
    progress_list = result.scalars().all()
    
    for p in progress_list:
        await db.delete(p)
    
    await db.commit()
    
    return {"status": "ok", "cleared": len(progress_list)}


# Settings Endpoints
@settings_router.get("", response_model=Dict[str, str])
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Get all application settings."""
    result = await db.execute(select(Settings))
    settings_list = result.scalars().all()
    
    return {s.key: s.value for s in settings_list}


@settings_router.get("/{key}", response_model=SettingsResponse)
async def get_setting(key: str, db: AsyncSession = Depends(get_db)):
    """
    Get a specific setting.
    
    - **key**: The setting key
    """
    setting = await db.get(Settings, key)
    
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    
    return SettingsResponse(key=setting.key, value=setting.value)


@settings_router.put("", response_model=Dict[str, str])
async def update_settings(
    request: UpdateSettingsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Update multiple settings.
    
    - **settings**: Dictionary of key-value pairs to update
    """
    for key, value in request.settings.items():
        setting = await db.get(Settings, key)
        
        if setting:
            setting.value = value
        else:
            setting = Settings(key=key, value=value)
            db.add(setting)
    
    await db.commit()
    
    # Return all settings
    result = await db.execute(select(Settings))
    settings_list = result.scalars().all()
    
    return {s.key: s.value for s in settings_list}


@settings_router.delete("/{key}", response_model=dict)
async def delete_setting(key: str, db: AsyncSession = Depends(get_db)):
    """
    Delete a setting.
    
    - **key**: The setting key
    """
    setting = await db.get(Settings, key)
    
    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")
    
    await db.delete(setting)
    await db.commit()
    
    return {"status": "ok", "deleted": key}
