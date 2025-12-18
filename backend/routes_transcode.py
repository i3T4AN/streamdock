#===============================================================
# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Transcoding API routes
#===============================================================

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import TranscodeJob, TranscodeStatus, Media
from job_worker import job_worker
from transcoder import transcoder


# Router
router = APIRouter(prefix="/api/transcode", tags=["Transcoding"])


# Models
class JobResponse(BaseModel):
    """Transcode job information."""
    id: int
    media_id: Optional[int]
    episode_id: Optional[int]
    source_path: str
    output_path: Optional[str]
    status: str
    progress: int
    error_message: Optional[str]
    created_at: str
    completed_at: Optional[str]
    
    class Config:
        from_attributes = True


class CreateJobRequest(BaseModel):
    """Request to create a new transcode job."""
    media_id: Optional[int] = None
    episode_id: Optional[int] = None
    source_path: str
    output_path: Optional[str] = None


class QueueStatusResponse(BaseModel):
    """Queue status information."""
    running: bool
    current_job_id: Optional[int]
    pending: int
    processing: int
    complete: int
    failed: int


# Endpoints
@router.get("/jobs", response_model=List[JobResponse])
async def list_jobs(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List all transcode jobs.
    
    - **status**: Optional filter by status (pending, processing, complete, failed)
    """
    query = select(TranscodeJob).order_by(TranscodeJob.created_at.desc())
    
    if status:
        try:
            status_enum = TranscodeStatus(status)
            query = query.where(TranscodeJob.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return [
        JobResponse(
            id=job.id,
            media_id=job.media_id,
            episode_id=job.episode_id,
            source_path=job.source_path,
            output_path=job.output_path,
            status=job.status.value,
            progress=job.progress,
            error_message=job.error_message,
            created_at=job.created_at.isoformat() if job.created_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
        )
        for job in jobs
    ]


@router.get("/jobs/status", response_model=QueueStatusResponse)
async def get_queue_status():
    """Get current queue status."""
    status = await job_worker.get_queue_status()
    return QueueStatusResponse(**status)


@router.delete("/jobs/finished", response_model=dict)
async def clear_finished_jobs():
    """
    Clear all completed and failed jobs from the queue.
    """
    count = await job_worker.clear_finished_jobs()
    return {"status": "ok", "cleared": count}


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get status of a specific transcode job.
    
    - **job_id**: The job ID
    """
    job = await db.get(TranscodeJob, job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobResponse(
        id=job.id,
        media_id=job.media_id,
        episode_id=job.episode_id,
        source_path=job.source_path,
        output_path=job.output_path,
        status=job.status.value,
        progress=job.progress,
        error_message=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.post("/jobs", response_model=JobResponse)
async def create_job(request: CreateJobRequest):
    """
    Queue a new transcode job.
    
    - **source_path**: Path to source video file
    - **output_path**: Optional custom output path
    - **media_id**: Optional media ID to associate
    - **episode_id**: Optional episode ID to associate
    """
    # Validate source exists
    from pathlib import Path
    if not Path(request.source_path).exists():
        raise HTTPException(status_code=400, detail="Source file not found")
    
    job = await job_worker.add_job(
        source_path=request.source_path,
        output_path=request.output_path,
        media_id=request.media_id,
        episode_id=request.episode_id,
    )
    
    return JobResponse(
        id=job.id,
        media_id=job.media_id,
        episode_id=job.episode_id,
        source_path=job.source_path,
        output_path=job.output_path,
        status=job.status.value,
        progress=job.progress,
        error_message=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.delete("/jobs/{job_id}", response_model=dict)
async def cancel_job(job_id: int):
    """
    Cancel a pending transcode job.
    
    - **job_id**: The job ID
    
    Note: Only pending jobs can be cancelled.
    """
    success = await job_worker.cancel_job(job_id)
    
    if success:
        return {"status": "ok", "message": "Job cancelled"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Job not found or cannot be cancelled (not pending)"
        )


@router.post("/jobs/{job_id}/retry", response_model=dict)
async def retry_job(job_id: int):
    """
    Retry a failed transcode job.
    
    - **job_id**: The job ID
    """
    success = await job_worker.retry_failed_job(job_id)
    
    if success:
        return {"status": "ok", "message": "Job queued for retry"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Job not found or not in failed state"
        )


@router.post("/jobs/{job_id}/restart", response_model=dict)
async def restart_job(job_id: int):
    """
    Restart a processing or failed job.
    Kills the current process if running and requeues the job.
    
    - **job_id**: The job ID
    """
    success = await job_worker.restart_job(job_id)
    
    if success:
        return {"status": "ok", "message": "Job restarted"}
    else:
        raise HTTPException(
            status_code=400,
            detail="Job not found or cannot be restarted (not processing/failed)"
        )

