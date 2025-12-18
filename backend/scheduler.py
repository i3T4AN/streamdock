# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Background scheduler for periodic tasks

import asyncio
from datetime import datetime, timedelta
from typing import Optional
import os

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session_factory
from models import TranscodeJob, TranscodeStatus
from library_scanner import library_scanner


# Scheduler Configuration
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "30"))
CLEANUP_INTERVAL_MINUTES = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "60"))
STALE_JOB_HOURS = int(os.getenv("STALE_JOB_HOURS", "24"))


# Background Tasks
class BackgroundScheduler:
    """Manages periodic background tasks."""
    
    def __init__(self):
        self.running = False
        self.scan_task: Optional[asyncio.Task] = None
        self.cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start all background tasks."""
        if self.running:
            return
        
        self.running = True
        print(f"Starting background scheduler...")
        print(f"   - Library scan every {SCAN_INTERVAL_MINUTES} minutes")
        print(f"   - Cleanup every {CLEANUP_INTERVAL_MINUTES} minutes")
        
        self.scan_task = asyncio.create_task(self._scan_loop())
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def stop(self):
        """Stop all background tasks."""
        self.running = False
        
        if self.scan_task:
            self.scan_task.cancel()
            try:
                await self.scan_task
            except asyncio.CancelledError:
                pass
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        print("Background scheduler stopped")
    
    async def _scan_loop(self):
        """Periodic library scan loop."""
        # Wait before first scan to let system stabilize
        await asyncio.sleep(60)
        
        while self.running:
            try:
                print(f"Running scheduled library scan...")
                result = await library_scanner.scan_and_import()
                print(f"Scan complete: imported={result['imported']}, removed={result.get('removed', 0)}")
            except Exception as e:
                print(f"Scheduled scan failed: {e}")
            
            # Wait for next interval
            await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)
    
    async def _cleanup_loop(self):
        """Periodic cleanup loop."""
        # Wait before first cleanup
        await asyncio.sleep(120)
        
        while self.running:
            try:
                await self._cleanup_stale_jobs()
            except Exception as e:
                print(f"Cleanup failed: {e}")
            
            # Wait for next interval
            await asyncio.sleep(CLEANUP_INTERVAL_MINUTES * 60)
    
    async def _cleanup_stale_jobs(self):
        """Clean up stale/stuck transcode jobs."""
        async with async_session_factory() as session:
            stale_cutoff = datetime.utcnow() - timedelta(hours=STALE_JOB_HOURS)
            
            # Find jobs that have been processing for too long
            result = await session.execute(
                select(TranscodeJob).where(
                    and_(
                        TranscodeJob.status == TranscodeStatus.PROCESSING,
                        TranscodeJob.created_at < stale_cutoff
                    )
                )
            )
            stale_jobs = result.scalars().all()
            
            for job in stale_jobs:
                job.status = TranscodeStatus.FAILED
                job.error_message = "Job timed out (stale)"
                print(f"Marked stale job as failed: {job.id}")
            
            # Find and remove old completed/failed jobs (older than 7 days)
            old_cutoff = datetime.utcnow() - timedelta(days=7)
            result = await session.execute(
                select(TranscodeJob).where(
                    and_(
                        TranscodeJob.status.in_([TranscodeStatus.COMPLETE, TranscodeStatus.FAILED]),
                        TranscodeJob.created_at < old_cutoff
                    )
                )
            )
            old_jobs = result.scalars().all()
            
            for job in old_jobs:
                await session.delete(job)
                print(f"Removed old job: {job.id}")
            
            if stale_jobs or old_jobs:
                await session.commit()
                print(f"Cleanup: {len(stale_jobs)} stale, {len(old_jobs)} old jobs processed")


# Singleton Instance
scheduler = BackgroundScheduler()
