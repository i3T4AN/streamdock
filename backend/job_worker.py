#===============================================================
# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Job worker for processing transcoding jobs
#===============================================================

import os
import asyncio
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session_factory
from models import TranscodeJob, TranscodeStatus, Media, Episode, Settings
from transcoder import transcoder, QualityPreset


# Map setting values to QualityPreset
QUALITY_MAP = {
    "480p": QualityPreset.LOW,
    "720p": QualityPreset.MEDIUM,
    "1080p": QualityPreset.HIGH,
    "2160p": QualityPreset.ULTRA,
}


async def get_quality_preset() -> QualityPreset:
    """Read default_quality from settings and return corresponding preset."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Settings).where(Settings.key == "default_quality")
        )
        setting = result.scalars().first()
        if setting and setting.value in QUALITY_MAP:
            return QUALITY_MAP[setting.value]
    return QualityPreset.HIGH  # Default fallback


POLL_INTERVAL = int(os.getenv("JOB_POLL_INTERVAL", "5"))
MAX_RETRIES = int(os.getenv("JOB_MAX_RETRIES", "3"))
CONCURRENT_JOBS = int(os.getenv("JOB_CONCURRENT", "1"))


class JobWorker:
    """Background worker that processes transcoding jobs from the database."""
    
    def __init__(self):
        self._running = False
        self._current_job: Optional[TranscodeJob] = None
        self._current_process: Optional[asyncio.subprocess.Process] = None
        self._semaphore = asyncio.Semaphore(CONCURRENT_JOBS)
    
    async def start(self):
        """Start the job worker loop."""
        self._running = True
        print(f"Job worker started (poll interval: {POLL_INTERVAL}s, max concurrent: {CONCURRENT_JOBS})")
        
        while self._running:
            try:
                await self._process_pending_jobs()
            except Exception as e:
                print(f"Job worker error: {e}")
            
            await asyncio.sleep(POLL_INTERVAL)
    
    async def stop(self):
        """Stop the job worker loop."""
        self._running = False
        print("Job worker stopped")
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def current_job(self) -> Optional[TranscodeJob]:
        return self._current_job
    
    async def _process_pending_jobs(self):
        """Process all pending jobs (respecting concurrency limit)."""
        async with async_session_factory() as session:
            query = (
                select(TranscodeJob)
                .where(TranscodeJob.status == TranscodeStatus.PENDING)
                .order_by(TranscodeJob.created_at)
                .limit(CONCURRENT_JOBS)
            )
            result = await session.execute(query)
            jobs = result.scalars().all()
            
            if not jobs:
                return
            
            tasks = [self._process_job(job.id) for job in jobs]
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _process_job(self, job_id: int):
        """Process a single transcoding job."""
        async with self._semaphore:
            async with async_session_factory() as session:
                job = await session.get(TranscodeJob, job_id)
                if not job or job.status != TranscodeStatus.PENDING:
                    return
                
                self._current_job = job
                
                if job.source_path.lower().endswith(('.mp4', '.mov', '.webm')):
                    print(f"FORCE SUCCESS: Extension compatible {job.source_path}")
                    await self._update_job_status(
                        session, job, TranscodeStatus.COMPLETE,
                        progress=100, output_path=job.source_path,
                        error_message="Direct play compatible (force skipped)"
                    )
                    self._current_job = None
                    return

                try:
                    await self._update_job_status(
                        session, job, TranscodeStatus.PROCESSING, progress=0
                    )
                    
                    print(f"Processing job {job.id}: {job.source_path}")
                    
                    video_info = await transcoder.get_video_info(job.source_path)
                    if not video_info:
                        raise Exception("Failed to read video file")
                    
                    class ProgressTracker:
                        def __init__(self):
                            self.last_update = -1

                    tracker = ProgressTracker()

                    async def update_progress(progress: float):
                        progress_pct = int(progress * 100)
                        
                        if progress_pct >= tracker.last_update + 5 or progress_pct == 100:
                            tracker.last_update = progress_pct
                            async with async_session_factory() as sess:
                                await sess.execute(
                                    update(TranscodeJob)
                                    .where(TranscodeJob.id == job_id)
                                    .values(progress=progress_pct)
                                )
                                await sess.commit()
                    
                    def sync_progress(p):
                        asyncio.create_task(update_progress(p))
                    
                    # Get quality setting
                    quality_preset = await get_quality_preset()
                    
                    output_path = await transcoder.transcode_to_mp4(
                        source=job.source_path,
                        output=job.output_path,
                        quality=quality_preset,
                        progress_callback=sync_progress
                    )
                    
                    if output_path:
                        await self._update_job_status(
                            session, job, TranscodeStatus.COMPLETE,
                            progress=100, output_path=output_path
                        )
                        print(f"Job {job.id} completed: {output_path}")
                    else:
                        raise Exception("Transcode returned no output")
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"Job {job.id} failed: {error_msg}")
                    
                    retry_count = self._get_retry_count(job)
                    
                    if retry_count < MAX_RETRIES:
                        await self._update_job_status(
                            session, job, TranscodeStatus.PENDING,
                            error_message=f"Retry {retry_count + 1}/{MAX_RETRIES}: {error_msg}"
                        )
                        print(f"Job {job.id} queued for retry ({retry_count + 1}/{MAX_RETRIES})")
                    else:
                        await self._update_job_status(
                            session, job, TranscodeStatus.FAILED,
                            error_message=f"Max retries exceeded: {error_msg}"
                        )
                
                finally:
                    self._current_job = None
    
    async def _update_job_status(
        self,
        session: AsyncSession,
        job: TranscodeJob,
        status: TranscodeStatus,
        progress: Optional[int] = None,
        output_path: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """Update job status in database."""
        job.status = status
        
        if progress is not None:
            job.progress = progress
        
        if output_path is not None:
            job.output_path = output_path
        
        if error_message is not None:
            job.error_message = error_message
        
        if status == TranscodeStatus.COMPLETE:
            job.completed_at = datetime.utcnow()
            
            # Update episode/media file_path to point to the transcoded MP4
            # This ensures the path persists even if transcode jobs are cleared
            if output_path:
                if job.episode_id:
                    episode = await session.get(Episode, job.episode_id)
                    if episode:
                        episode.file_path = output_path
                        print(f"Updated episode {job.episode_id} file_path to: {output_path}")
                elif job.media_id:
                    media = await session.get(Media, job.media_id)
                    if media:
                        media.file_path = output_path
                        print(f"Updated media {job.media_id} file_path to: {output_path}")
        
        await session.commit()
    
    def _get_retry_count(self, job: TranscodeJob) -> int:
        """Extract retry count from error message."""
        if not job.error_message:
            return 0
        
        import re
        match = re.search(r"Retry (\d+)/", job.error_message)
        return int(match.group(1)) if match else 0
    
    async def add_job(
        self,
        source_path: str,
        output_path: Optional[str] = None,
        media_id: Optional[int] = None,
        episode_id: Optional[int] = None,
    ) -> TranscodeJob:
        """Add a new transcoding job to the queue."""
        async with async_session_factory() as session:
            job = TranscodeJob(
                source_path=source_path,
                output_path=output_path or transcoder.get_output_path(source_path),
                media_id=media_id,
                episode_id=episode_id,
                status=TranscodeStatus.PENDING,
                progress=0,
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)
            
            print(f"Job {job.id} added: {source_path}")
            return job
    
    async def get_job(self, job_id: int) -> Optional[TranscodeJob]:
        """Get job by ID."""
        async with async_session_factory() as session:
            return await session.get(TranscodeJob, job_id)
    
    async def get_pending_jobs(self) -> List[TranscodeJob]:
        """Get all pending jobs."""
        async with async_session_factory() as session:
            query = (
                select(TranscodeJob)
                .where(TranscodeJob.status == TranscodeStatus.PENDING)
                .order_by(TranscodeJob.created_at)
            )
            result = await session.execute(query)
            return list(result.scalars().all())
    
    async def get_queue_status(self) -> dict:
        """Get current queue status."""
        async with async_session_factory() as session:
            counts = {}
            for status in TranscodeStatus:
                query = select(TranscodeJob).where(TranscodeJob.status == status)
                result = await session.execute(query)
                counts[status.value] = len(result.scalars().all())
            
            return {
                "running": self._running,
                "current_job_id": self._current_job.id if self._current_job else None,
                "pending": counts.get("pending", 0),
                "processing": counts.get("processing", 0),
                "complete": counts.get("complete", 0),
                "failed": counts.get("failed", 0),
            }
    
    async def cancel_job(self, job_id: int) -> bool:
        """Cancel a pending or processing job."""
        from pathlib import Path
        
        async with async_session_factory() as session:
            job = await session.get(TranscodeJob, job_id)
            if not job:
                return False
            
            if job.status not in [TranscodeStatus.PENDING, TranscodeStatus.PROCESSING]:
                return False
            
            # If processing, kill the FFmpeg process
            if job.status == TranscodeStatus.PROCESSING:
                if transcoder.current_process:
                    try:
                        transcoder.current_process.terminate()
                        await transcoder.current_process.wait()
                    except Exception as e:
                        print(f"Error terminating process: {e}")
                    transcoder.current_process = None
                self._current_job = None
                
                # Delete incomplete output file
                if job.output_path:
                    output = Path(job.output_path)
                    if output.exists():
                        try:
                            output.unlink()
                            print(f"Deleted incomplete file: {output}")
                        except Exception as e:
                            print(f"Error deleting file: {e}")
            
            await session.delete(job)
            await session.commit()
            print(f"Job {job_id} cancelled")
            return True
    
    async def retry_failed_job(self, job_id: int) -> bool:
        """Retry a failed job."""
        async with async_session_factory() as session:
            job = await session.get(TranscodeJob, job_id)
            if job and job.status == TranscodeStatus.FAILED:
                job.status = TranscodeStatus.PENDING
                job.progress = 0
                job.error_message = None
                await session.commit()
                print(f"Job {job_id} queued for retry")
                return True
            return False
    
    async def clear_finished_jobs(self) -> int:
        """Clear completed and failed jobs."""
        async with async_session_factory() as session:
            from sqlalchemy import or_
            query = select(TranscodeJob).where(
                or_(
                    TranscodeJob.status == TranscodeStatus.COMPLETE,
                    TranscodeJob.status == TranscodeStatus.FAILED
                )
            )
            result = await session.execute(query)
            jobs = result.scalars().all()
            count = len(jobs)
            for job in jobs:
                await session.delete(job)
            await session.commit()
            print(f"Cleared {count} finished jobs")
            return count
    
    async def restart_job(self, job_id: int) -> bool:
        """Restart a processing or failed job."""
        from pathlib import Path
        
        async with async_session_factory() as session:
            job = await session.get(TranscodeJob, job_id)
            if not job or job.status not in [TranscodeStatus.PROCESSING, TranscodeStatus.FAILED]:
                return False
            
            # If processing, kill the process first
            if job.status == TranscodeStatus.PROCESSING:
                if transcoder.current_process:
                    try:
                        transcoder.current_process.terminate()
                        await transcoder.current_process.wait()
                    except Exception as e:
                        print(f"Error terminating process: {e}")
                    transcoder.current_process = None
            
            # Delete incomplete output file if exists
            if job.output_path:
                output = Path(job.output_path)
                if output.exists():
                    try:
                        output.unlink()
                        print(f"Deleted incomplete file: {output}")
                    except Exception as e:
                        print(f"Error deleting file: {e}")
            
            # Reset to pending
            job.status = TranscodeStatus.PENDING
            job.progress = 0
            job.error_message = None
            job.completed_at = None
            await session.commit()
            print(f"Job {job_id} restarted")
            return True


job_worker = JobWorker()


async def start_job_worker():
    """Start job worker in background task."""
    asyncio.create_task(job_worker.start())
