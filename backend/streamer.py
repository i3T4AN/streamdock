# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Video streaming with range request support

import os
import re
import mimetypes
from pathlib import Path
from typing import Optional, Tuple, AsyncGenerator
import aiofiles
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse, FileResponse, Response


# Configuration
TRANSCODED_PATH = os.getenv("TRANSCODED_PATH", "/transcoded")
CHUNK_SIZE = 1024 * 1024  # 1MB chunks for streaming


# MIME Types
MIME_TYPES = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".m4v": "video/x-m4v",
    ".ts": "video/mp2t",
    ".m3u8": "application/vnd.apple.mpegurl",
    ".mpd": "application/dash+xml",
}


def get_mime_type(path: str) -> str:
    """Get MIME type for file path."""
    ext = Path(path).suffix.lower()
    return MIME_TYPES.get(ext, "application/octet-stream")


# Range Header Parser
def parse_range_header(range_header: str, file_size: int) -> Tuple[int, int]:
    """
    Parse HTTP Range header.
    Returns (start, end) byte positions.
    """
    if not range_header:
        return 0, file_size - 1
    
    # Format: bytes=start-end or bytes=start-
    match = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not match:
        return 0, file_size - 1
    
    start_str, end_str = match.groups()
    
    if start_str:
        start = int(start_str)
    else:
        start = 0
    
    if end_str:
        end = int(end_str)
    else:
        end = file_size - 1
    
    # Clamp values
    start = max(0, start)
    end = min(end, file_size - 1)
    
    return start, end


# Streamer Class
class Streamer:
    """
    Video file streamer with Range request support.
    Enables seeking in browser video players.
    """
    
    def __init__(self, transcoded_path: str = TRANSCODED_PATH):
        self.transcoded_path = Path(transcoded_path)
    
    # Direct File Streaming
    async def stream_file(self, file_path: str, request: Request) -> Response:
        """
        Stream a video file with Range support.
        Handles partial content requests for seeking.
        """
        path = Path(file_path)
        
        if not path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        file_size = path.stat().st_size
        mime_type = get_mime_type(file_path)
        
        # Check for Range header
        range_header = request.headers.get("range")
        
        if range_header:
            return await self._stream_with_range(path, range_header, file_size, mime_type)
        else:
            return await self._stream_full(path, file_size, mime_type)
    
    async def _stream_full(self, path: Path, file_size: int, mime_type: str) -> StreamingResponse:
        """Stream entire file."""
        async def file_generator():
            async with aiofiles.open(path, "rb") as f:
                while chunk := await f.read(CHUNK_SIZE):
                    yield chunk
        
        headers = {
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
        }
        
        return StreamingResponse(
            file_generator(),
            media_type=mime_type,
            headers=headers,
        )
    
    async def _stream_with_range(
        self,
        path: Path,
        range_header: str,
        file_size: int,
        mime_type: str
    ) -> StreamingResponse:
        """Stream partial content for seeking."""
        start, end = parse_range_header(range_header, file_size)
        content_length = end - start + 1
        
        async def range_generator():
            async with aiofiles.open(path, "rb") as f:
                await f.seek(start)
                remaining = content_length
                
                while remaining > 0:
                    chunk_size = min(CHUNK_SIZE, remaining)
                    chunk = await f.read(chunk_size)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk
        
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
            "Accept-Ranges": "bytes",
        }
        
        return StreamingResponse(
            range_generator(),
            status_code=206,  # Partial Content
            media_type=mime_type,
            headers=headers,
        )
    
    # HLS Streaming
    def get_hls_dir(self, media_id: int) -> Path:
        """Get HLS directory for media."""
        return self.transcoded_path / str(media_id) / "hls"
    
    async def get_hls_manifest(self, media_id: int) -> Response:
        """Serve HLS master.m3u8 playlist."""
        manifest_path = self.get_hls_dir(media_id) / "master.m3u8"
        
        if not manifest_path.exists():
            raise HTTPException(
                status_code=404,
                detail="HLS stream not available. Transcode may be in progress."
            )
        
        async with aiofiles.open(manifest_path, "r") as f:
            content = await f.read()
        
        return Response(
            content=content,
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-cache"},
        )
    
    async def get_hls_segment(self, media_id: int, segment: str) -> FileResponse:
        """Serve HLS .ts segment file."""
        segment_path = self.get_hls_dir(media_id) / segment
        
        if not segment_path.exists():
            raise HTTPException(status_code=404, detail="Segment not found")
        
        return FileResponse(
            path=str(segment_path),
            media_type="video/mp2t",
            headers={"Cache-Control": "max-age=31536000"},  # Cache segments
        )
    
    # Transcoded File Helpers
    def get_transcoded_path(self, media_id: int) -> Optional[Path]:
        """Get path to transcoded MP4 for media."""
        # Check for direct MP4
        mp4_path = self.transcoded_path / f"{media_id}.mp4"
        if mp4_path.exists():
            return mp4_path
        
        # Check in media subdirectory
        subdir_mp4 = self.transcoded_path / str(media_id) / "video.mp4"
        if subdir_mp4.exists():
            return subdir_mp4
        
        return None
    
    async def stream_media(self, media_id: int, request: Request) -> Response:
        """
        Stream media by ID.
        Checks for transcoded version first, falls back to original.
        """
        transcoded = self.get_transcoded_path(media_id)
        
        if transcoded:
            return await self.stream_file(str(transcoded), request)
        
        raise HTTPException(
            status_code=404,
            detail="Media not available. Transcode may be required."
        )
    
    # Utility Methods
    def is_transcode_ready(self, media_id: int) -> bool:
        """Check if transcoded version exists."""
        return self.get_transcoded_path(media_id) is not None
    
    def is_hls_ready(self, media_id: int) -> bool:
        """Check if HLS stream exists."""
        manifest = self.get_hls_dir(media_id) / "master.m3u8"
        return manifest.exists()
    
    def get_stream_info(self, media_id: int) -> dict:
        """Get streaming availability info for media."""
        return {
            "media_id": media_id,
            "mp4_ready": self.is_transcode_ready(media_id),
            "hls_ready": self.is_hls_ready(media_id),
            "mp4_path": str(self.get_transcoded_path(media_id)) if self.is_transcode_ready(media_id) else None,
        }


# Singleton Instance
streamer = Streamer()
