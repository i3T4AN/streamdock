#===============================================================
# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Video transcoder using FFmpeg
#===============================================================

import os
import re
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum


TRANSCODED_PATH = os.getenv("TRANSCODED_PATH", "/transcoded")
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "ffprobe")


class QualityPreset(Enum):
    """Video quality presets."""
    LOW = "480p"
    MEDIUM = "720p"
    HIGH = "1080p"
    ULTRA = "2160p"


QUALITY_SETTINGS = {
    QualityPreset.LOW: {
        "resolution": "854x480",
        "video_bitrate": "1500k",
        "audio_bitrate": "128k",
        "crf": 28,
    },
    QualityPreset.MEDIUM: {
        "resolution": "1280x720",
        "video_bitrate": "3000k",
        "audio_bitrate": "192k",
        "crf": 24,
    },
    QualityPreset.HIGH: {
        "resolution": "1920x1080",
        "video_bitrate": "6000k",
        "audio_bitrate": "192k",
        "crf": 22,
    },
    QualityPreset.ULTRA: {
        "resolution": "3840x2160",
        "video_bitrate": "15000k",
        "audio_bitrate": "256k",
        "crf": 20,
    },
}


@dataclass
class VideoInfo:
    """Video file metadata."""
    path: str
    duration: float  # seconds
    width: int
    height: int
    video_codec: str
    audio_codec: str
    container: str
    bitrate: int  # kbps
    framerate: float
    file_size: int  # bytes
    
    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"
    
    @property
    def is_browser_compatible(self) -> bool:
        """Check if video can play in browser without transcoding."""
        compatible_video = self.video_codec.lower() in ["h264", "avc", "h.264"]
        compatible_audio = self.audio_codec.lower() in ["aac", "mp3", "opus"]
        compatible_container = self.container.lower() in ["mp4", "webm", "mov"]
        return compatible_video and compatible_audio and compatible_container
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "duration": self.duration,
            "width": self.width,
            "height": self.height,
            "resolution": self.resolution,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "container": self.container,
            "bitrate": self.bitrate,
            "framerate": self.framerate,
            "file_size": self.file_size,
            "browser_compatible": self.is_browser_compatible,
        }


class Transcoder:
    """FFmpeg-based video transcoder (CPU-only for Docker compatibility)."""
    
    def __init__(self, output_path: str = TRANSCODED_PATH):
        self.output_path = Path(output_path)
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.current_process: Optional[asyncio.subprocess.Process] = None
    
    async def get_video_info(self, path: str) -> Optional[VideoInfo]:
        """Get video metadata using ffprobe."""
        try:
            cmd = [
                FFPROBE_PATH,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                path
            ]
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            
            if proc.returncode != 0:
                return None
            
            data = json.loads(stdout.decode())
            
            video_stream = None
            audio_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video" and not video_stream:
                    video_stream = stream
                elif stream.get("codec_type") == "audio" and not audio_stream:
                    audio_stream = stream
            
            if not video_stream:
                return None
            
            format_info = data.get("format", {})
            
            fps_str = video_stream.get("r_frame_rate", "0/1")
            if "/" in fps_str:
                num, den = map(int, fps_str.split("/"))
                framerate = num / den if den else 0
            else:
                framerate = float(fps_str)
            
            return VideoInfo(
                path=path,
                duration=float(format_info.get("duration", 0)),
                width=video_stream.get("width", 0),
                height=video_stream.get("height", 0),
                video_codec=video_stream.get("codec_name", "unknown"),
                audio_codec=audio_stream.get("codec_name", "unknown") if audio_stream else "none",
                container=format_info.get("format_name", "unknown").split(",")[0],
                bitrate=int(format_info.get("bit_rate", 0)) // 1000,
                framerate=framerate,
                file_size=int(format_info.get("size", 0)),
            )
            
        except Exception as e:
            print(f"ffprobe error: {e}")
            return None
    
    def needs_transcoding(self, info: VideoInfo) -> bool:
        """Check if video needs transcoding for browser playback."""
        path_str = str(info.path).lower()
        if path_str.endswith(('.mp4', '.mov', '.webm')):
            print(f"Extension compatible: {info.path}")
            return False
            
        print(f"Needs transcoding: {info.path}")
        return True
    

    async def transcode_to_mp4(
        self,
        source: str,
        output: Optional[str] = None,
        quality: QualityPreset = QualityPreset.HIGH,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> Optional[str]:
        """Transcode video to browser-compatible MP4."""
        info = await self.get_video_info(source)
        if not info:
            return None
        
        if output is None:
            source_path = Path(source)
            output = str(self.output_path / f"{source_path.stem}.mp4")
        
        cmd = self._build_transcode_cmd(source, output, quality)
        
        print(f"Transcoding: {Path(source).name} -> {Path(output).name}")
        
        success = await self._run_ffmpeg(cmd, info.duration, progress_callback)
        
        if success and Path(output).exists():
            print(f"Transcode complete: {output}")
            return output
        else:
            print(f"Transcode failed: {source}")
            return None
    
    def _build_transcode_cmd(
        self,
        source: str,
        output: str,
        quality: QualityPreset
    ) -> list:
        """Build FFmpeg transcode command (CPU-only with libx264)."""
        settings = QUALITY_SETTINGS[quality]
        
        cmd = [FFMPEG_PATH, "-y", "-hide_banner"]
        cmd.extend(["-i", source])
        
        # CPU encoding with libx264 (ultrafast preset for speed)
        cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", str(settings["crf"])])
        
        # Scale to target resolution while maintaining aspect ratio
        width, height = settings["resolution"].split("x")
        cmd.extend(["-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"])
        
        # AAC audio
        cmd.extend(["-c:a", "aac", "-b:a", settings["audio_bitrate"]])
        
        # Fast start for web streaming
        cmd.extend(["-movflags", "+faststart"])
        
        # Progress output to stdout
        cmd.extend(["-progress", "pipe:1", "-nostdin"])
        
        cmd.append(output)
        return cmd
    
    async def _run_ffmpeg(
        self,
        cmd: list,
        duration: float,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> bool:
        """Run FFmpeg command with progress tracking."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL
            )
            self.current_process = proc
            
            progress_pattern = re.compile(r"out_time=(\d{2}):(\d{2}):(\d{2})\.(\d+)")
            
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                
                line_str = line.decode()
                
                match = progress_pattern.search(line_str)
                if match and duration > 0:
                    hours, mins, secs = map(int, match.groups()[:3])
                    micro_str = match.group(4)
                    seconds = hours * 3600 + mins * 60 + secs + float(f"0.{micro_str}")
                    
                    progress = min(seconds / duration, 1.0)
                    
                    if progress_callback:
                        progress_callback(progress)
                elif match:
                     print(f"Progress match but invalid duration: {duration}")
            
            await proc.wait()
            return proc.returncode == 0
            
        except Exception as e:
            print(f"FFmpeg error: {e}")
            return False
    
    async def create_hls_stream(
        self,
        source: str,
        output_dir: Optional[str] = None,
        quality: QualityPreset = QualityPreset.HIGH,
        segment_duration: int = 6,
    ) -> Optional[str]:
        """Create HLS stream with segments."""
        info = await self.get_video_info(source)
        if not info:
            return None
        
        if output_dir is None:
            source_path = Path(source)
            output_dir = str(self.output_path / source_path.stem / "hls")
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        settings = QUALITY_SETTINGS[quality]
        playlist_path = str(Path(output_dir) / "master.m3u8")
        segment_pattern = str(Path(output_dir) / "segment_%03d.ts")
        
        cmd = [
            FFMPEG_PATH, "-y", "-hide_banner",
            "-i", source,
            "-c:v", "libx264", "-preset", "fast", "-crf", str(settings["crf"]),
            "-c:a", "aac", "-b:a", settings["audio_bitrate"],
            "-f", "hls",
            "-hls_time", str(segment_duration),
            "-hls_list_size", "0",
            "-hls_segment_filename", segment_pattern,
            playlist_path
        ]
        
        print(f"Creating HLS stream: {Path(source).name}")
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        _, stderr = await proc.communicate()
        
        if proc.returncode == 0 and Path(playlist_path).exists():
            print(f"HLS stream created: {playlist_path}")
            return playlist_path
        else:
            print(f"HLS creation failed: {stderr.decode()[:200]}")
            return None
    
    def get_output_path(self, source: str, suffix: str = ".mp4") -> str:
        """Generate output path for transcoded file."""
        source_path = Path(source)
        return str(self.output_path / f"{source_path.stem}{suffix}")
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format duration as HH:MM:SS."""
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{mins:02d}:{secs:02d}"


transcoder = Transcoder()
