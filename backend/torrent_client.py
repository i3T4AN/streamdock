#===============================================================
#  i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         qBittorrent API client wrapper
#===============================================================

import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum
import qbittorrentapi
from dotenv import load_dotenv

load_dotenv()


# Configuration
QBIT_HOST = os.getenv("QBIT_HOST", "localhost")
QBIT_PORT = int(os.getenv("QBIT_PORT", "8080"))
QBIT_USERNAME = os.getenv("QBIT_USERNAME", "admin")
QBIT_PASSWORD = os.getenv("QBIT_PASSWORD", "adminadmin")


# Torrent State Enum
class TorrentState(Enum):
    """Simplified torrent states."""
    DOWNLOADING = "downloading"
    SEEDING = "seeding"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    QUEUED = "queued"
    CHECKING = "checking"
    UNKNOWN = "unknown"


# Torrent Info Dataclass
@dataclass
class TorrentInfo:
    """Structured torrent information."""
    hash: str
    name: str
    state: TorrentState
    progress: float  # 0.0 to 1.0
    size: int  # bytes
    downloaded: int  # bytes
    uploaded: int  # bytes
    download_speed: int  # bytes/sec
    upload_speed: int  # bytes/sec
    eta: int  # seconds, -1 if unknown
    ratio: float
    save_path: str
    added_on: int  # timestamp
    completion_on: int  # timestamp, 0 if not complete
    
    @classmethod
    def from_qbit(cls, torrent: dict) -> "TorrentInfo":
        """Create TorrentInfo from qBittorrent API response."""
        state_map = {
            "downloading": TorrentState.DOWNLOADING,
            "stalledDL": TorrentState.DOWNLOADING,
            "uploading": TorrentState.SEEDING,
            "stalledUP": TorrentState.SEEDING,
            "pausedDL": TorrentState.PAUSED,
            "pausedUP": TorrentState.PAUSED,
            "queuedDL": TorrentState.QUEUED,
            "queuedUP": TorrentState.QUEUED,
            "checkingDL": TorrentState.CHECKING,
            "checkingUP": TorrentState.CHECKING,
            "checkingResumeData": TorrentState.CHECKING,
            "error": TorrentState.ERROR,
            "missingFiles": TorrentState.ERROR,
        }
        
        raw_state = torrent.get("state", "unknown")
        state = state_map.get(raw_state, TorrentState.UNKNOWN)
        
        # Mark as completed if progress is 100%
        if torrent.get("progress", 0) >= 1.0 and state != TorrentState.ERROR:
            state = TorrentState.COMPLETED
        
        return cls(
            hash=torrent.get("hash", ""),
            name=torrent.get("name", "Unknown"),
            state=state,
            progress=torrent.get("progress", 0),
            size=torrent.get("size", 0),
            downloaded=torrent.get("downloaded", 0),
            uploaded=torrent.get("uploaded", 0),
            download_speed=torrent.get("dlspeed", 0),
            upload_speed=torrent.get("upspeed", 0),
            eta=torrent.get("eta", -1),
            ratio=torrent.get("ratio", 0),
            save_path=torrent.get("save_path", ""),
            added_on=torrent.get("added_on", 0),
            completion_on=torrent.get("completion_on", 0),
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hash": self.hash,
            "name": self.name,
            "state": self.state.value,
            "progress": self.progress,
            "progress_percent": round(self.progress * 100, 1),
            "size": self.size,
            "downloaded": self.downloaded,
            "uploaded": self.uploaded,
            "download_speed": self.download_speed,
            "upload_speed": self.upload_speed,
            "eta": self.eta,
            "ratio": round(self.ratio, 2),
            "save_path": self.save_path,
            "added_on": self.added_on,
            "completion_on": self.completion_on,
        }


# QBitClient Class
class QBitClient:
    """
    Wrapper for qBittorrent Web API.
    Provides simplified interface for torrent management.
    """
    
    def __init__(
        self,
        host: str = QBIT_HOST,
        port: int = QBIT_PORT,
        username: str = QBIT_USERNAME,
        password: str = QBIT_PASSWORD,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._client: Optional[qbittorrentapi.Client] = None
        self._connected = False
    
    # Connection Management
    def connect(self) -> bool:
        """
        Establish connection to qBittorrent.
        Returns True if successful, False otherwise.
        """
        try:
            self._client = qbittorrentapi.Client(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
            )
            self._client.auth_log_in()
            self._connected = True
            print(f"Connected to qBittorrent at {self.host}:{self.port}")
            return True
        except qbittorrentapi.LoginFailed as e:
            print(f"qBittorrent login failed: {e}")
            self._connected = False
            return False
        except Exception as e:
            print(f"qBittorrent connection error: {e}")
            self._connected = False
            return False
    
    def disconnect(self) -> None:
        """Disconnect from qBittorrent."""
        if self._client:
            try:
                self._client.auth_log_out()
            except Exception:
                pass
        self._connected = False
        self._client = None
    
    def is_connected(self) -> bool:
        """Check if currently connected, attempt connection if not."""
        if not self._connected or not self._client:
            # Try to connect if not already connected
            self.connect()
        
        if not self._connected or not self._client:
            return False
        
        try:
            # Quick check by getting app version
            self._client.app_version()
            return True
        except Exception:
            self._connected = False
            return False
    
    def _ensure_connected(self) -> None:
        """Ensure connection is active, reconnect if needed."""
        if not self.is_connected():
            if not self.connect():
                raise ConnectionError("Failed to connect to qBittorrent")
    
    # Torrent Management
    def add_magnet(self, magnet_link: str, save_path: Optional[str] = None) -> bool:
        """
        Add a torrent from magnet link.
        Returns True if successful.
        """
        self._ensure_connected()
        try:
            kwargs = {"urls": magnet_link}
            if save_path:
                kwargs["save_path"] = save_path
            self._client.torrents_add(**kwargs)
            return True
        except Exception as e:
            print(f"Failed to add magnet: {e}")
            return False
    
    def get_torrents(self, filter_state: Optional[str] = None) -> List[TorrentInfo]:
        """
        Get list of all torrents.
        Optional filter: 'all', 'downloading', 'seeding', 'completed', 'paused', 'active'
        """
        self._ensure_connected()
        try:
            kwargs = {}
            if filter_state and filter_state != "all":
                kwargs["filter"] = filter_state
            torrents = self._client.torrents_info(**kwargs)
            return [TorrentInfo.from_qbit(t) for t in torrents]
        except Exception as e:
            print(f"Failed to get torrents: {e}")
            return []
    
    def get_torrent(self, torrent_hash: str) -> Optional[TorrentInfo]:
        """Get specific torrent by hash."""
        self._ensure_connected()
        try:
            torrents = self._client.torrents_info(torrent_hashes=torrent_hash)
            if torrents:
                return TorrentInfo.from_qbit(torrents[0])
            return None
        except Exception as e:
            print(f"Failed to get torrent {torrent_hash}: {e}")
            return None
    
    def pause_torrent(self, torrent_hash: str) -> bool:
        """Pause a torrent."""
        self._ensure_connected()
        try:
            self._client.torrents_pause(torrent_hashes=torrent_hash)
            return True
        except Exception as e:
            print(f"Failed to pause torrent: {e}")
            return False
    
    def resume_torrent(self, torrent_hash: str) -> bool:
        """Resume a paused torrent."""
        self._ensure_connected()
        try:
            self._client.torrents_resume(torrent_hashes=torrent_hash)
            return True
        except Exception as e:
            print(f"Failed to resume torrent: {e}")
            return False
    
    def delete_torrent(self, torrent_hash: str, delete_files: bool = False) -> bool:
        """
        Delete a torrent.
        If delete_files is True, also delete downloaded files.
        """
        self._ensure_connected()
        try:
            self._client.torrents_delete(
                torrent_hashes=torrent_hash,
                delete_files=delete_files
            )
            return True
        except Exception as e:
            print(f"Failed to delete torrent: {e}")
            return False
    
    # Speed & Stats
    def get_download_speed(self) -> int:
        """Get current global download speed in bytes/sec."""
        self._ensure_connected()
        try:
            info = self._client.transfer_info()
            return info.get("dl_info_speed", 0)
        except Exception:
            return 0
    
    def get_upload_speed(self) -> int:
        """Get current global upload speed in bytes/sec."""
        self._ensure_connected()
        try:
            info = self._client.transfer_info()
            return info.get("up_info_speed", 0)
        except Exception:
            return 0
    
    def get_transfer_info(self) -> Dict[str, Any]:
        """Get full transfer statistics."""
        self._ensure_connected()
        try:
            info = self._client.transfer_info()
            return {
                "download_speed": info.get("dl_info_speed", 0),
                "upload_speed": info.get("up_info_speed", 0),
                "downloaded_total": info.get("dl_info_data", 0),
                "uploaded_total": info.get("up_info_data", 0),
                "connection_status": info.get("connection_status", "unknown"),
            }
        except Exception as e:
            print(f"Failed to get transfer info: {e}")
            return {}
    
    # Utility Methods
    def get_version(self) -> str:
        """Get qBittorrent version."""
        self._ensure_connected()
        try:
            return self._client.app_version()
        except Exception:
            return "unknown"
    
    def get_completed_torrents(self) -> List[TorrentInfo]:
        """Get list of completed torrents."""
        return [t for t in self.get_torrents() if t.state == TorrentState.COMPLETED]
    
    def get_active_torrents(self) -> List[TorrentInfo]:
        """Get list of actively downloading/seeding torrents."""
        return self.get_torrents(filter_state="active")


# Singleton Instance
qbit_client = QBitClient()


# Helper Functions
def format_bytes(size: int) -> str:
    """Format bytes to human readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def format_speed(speed: int) -> str:
    """Format speed (bytes/sec) to human readable string."""
    return f"{format_bytes(speed)}/s"


def format_eta(seconds: int) -> str:
    """Format ETA seconds to human readable string."""
    if seconds < 0 or seconds == 8640000:  # qBit uses 8640000 for infinity
        return "∞"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m"
