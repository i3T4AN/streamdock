# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Library scanner for auto-importing downloads

import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import guessit
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import async_session_factory
from models import Media, Episode, MediaType
from tmdb_client import tmdb_client, MediaResult


# Configuration
DOWNLOADS_PATH = os.getenv("DOWNLOADS_PATH", "/downloads")
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".iso", ".mpg", ".mpeg", ".ts", ".m2ts"}


# ScanResult Dataclass
@dataclass
class ScanResult:
    """Result of scanning a folder."""
    folder_path: str
    folder_name: str
    title: str
    year: Optional[int]
    media_type: str  # "movie" or "tv"
    video_files: List[str]
    episodes: List[Dict[str, Any]]  # For TV shows
    tmdb_match: Optional[MediaResult]
    already_exists: bool = False
    error: Optional[str] = None


# Library Scanner
class LibraryScanner:
    """
    Scans download folders and imports media into the library.
    Uses parent folder names for TMDB lookup (clean names from torrents).
    """
    
    def __init__(self, downloads_path: str = DOWNLOADS_PATH):
        self.downloads_path = Path(downloads_path)
    
    # Main Scan Methods
    async def scan_completed_folder(self) -> List[ScanResult]:
        """
        Scan the completed downloads folder for new media.
        Returns list of scan results.
        """
        results = []
        
        if not self.downloads_path.exists():
            print(f"Downloads path does not exist: {self.downloads_path}")
            return results
        
        # Iterate through folders in completed downloads
        for item in self.downloads_path.iterdir():
            # Skip ignored folders/files
            if item.name.lower() in {"incomplete", "temp", ".ds_store"}:
                continue
            
            # Skip sample files/folders
            if "sample" in item.name.lower():
                continue
                
            if item.is_dir():
                result = await self._scan_folder(item)
                if result:
                    results.append(result)
            elif item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS:
                # Single video file (not in folder)
                result = await self._scan_single_file(item)
                if result:
                    results.append(result)
        
        return results
    
    async def _scan_folder(self, folder: Path) -> Optional[ScanResult]:
        """Scan a single folder for media content."""
        folder_name = folder.name
        
        # Parse folder name for title/year
        title, year = self.parse_folder_name(folder_name)
        
        # Find video files
        video_files = self.find_video_files(folder)
        if not video_files:
            return None  # No videos found
        
        # Identify media type (movie vs TV)
        media_type = self.identify_media_type(folder, video_files)
        
        # Parse episode info for TV shows
        episodes = []
        if media_type == "tv":
            episodes = self._parse_episodes(video_files)
        
        # Check if already in library
        already_exists = await self._check_exists(str(folder))
        
        # Match with TMDB
        tmdb_match = None
        if not already_exists:
            tmdb_match = await self.match_with_tmdb(title, year, media_type)
        
        return ScanResult(
            folder_path=str(folder),
            folder_name=folder_name,
            title=title,
            year=year,
            media_type=media_type,
            video_files=video_files,
            episodes=episodes,
            tmdb_match=tmdb_match,
            already_exists=already_exists,
        )
    
    async def _scan_single_file(self, file: Path) -> Optional[ScanResult]:
        """Scan a single video file (not in folder)."""
        # Use guessit for filename parsing
        info = guessit.guessit(file.name)
        title = info.get("title", file.stem)
        year = info.get("year")
        media_type = "tv" if info.get("type") == "episode" else "movie"
        
        episodes = []
        if media_type == "tv":
            season = info.get("season", 1)
            episode = info.get("episode", 1)
            episodes = [{"season": season, "episode": episode, "file": str(file)}]
        
        already_exists = await self._check_exists(str(file.parent), file.name)
        
        tmdb_match = None
        if not already_exists:
            tmdb_match = await self.match_with_tmdb(title, year, media_type)
        
        return ScanResult(
            folder_path=str(file.parent),
            folder_name=file.name,
            title=title,
            year=year,
            media_type=media_type,
            video_files=[str(file)],
            episodes=episodes,
            tmdb_match=tmdb_match,
            already_exists=already_exists,
        )
    
    # Parsing Methods
    def parse_folder_name(self, name: str) -> Tuple[str, Optional[int]]:
        """
        Extract title and year from folder name.
        Examples:
            "Breaking Bad Season 1" -> ("Breaking Bad", None)
            "The Matrix (1999)" -> ("The Matrix", 1999)
            "Inception.2010.1080p.BluRay" -> ("Inception", 2010)
        """
        # Try guessit first
        info = guessit.guessit(name)
        title = info.get("title", name)
        year = info.get("year")
        
        # Clean up title
        title = self._clean_title(title)
        
        # If guessit didn't find year, try regex
        if year is None:
            year_match = re.search(r'\b(19|20)\d{2}\b', name)
            if year_match:
                year = int(year_match.group())
        
        return title, year
    
    def _clean_title(self, title: str) -> str:
        """Clean up extracted title."""
        # Remove common release group tags
        patterns = [
            r'\b(720p|1080p|2160p|4K|HDR)\b',
            r'\b(BluRay|BRRip|WEB-DL|WEBRip|HDTV|DVDRip)\b',
            r'\b(x264|x265|HEVC|H\.?264|H\.?265)\b',
            r'\b(AAC|AC3|DTS|FLAC)\b',
            r'\[.*?\]',  # Brackets
            r'\((?!19|20)\d+\)',  # Parentheses without year
        ]
        
        for pattern in patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        
        # Clean up whitespace and dots
        title = title.replace('.', ' ').replace('_', ' ')
        title = re.sub(r'\s+', ' ', title).strip()
        
        return title
    
    def identify_media_type(self, folder: Path, video_files: List[str]) -> str:
        """
        Determine if folder contains a movie or TV show.
        Uses heuristics like:
            - Multiple video files = likely TV
            - Season/Episode patterns in filenames = TV
            - "Season" in folder name = TV
        """
        folder_name = folder.name.lower()
        
        # Check folder name for TV indicators
        tv_indicators = ["season", "s01", "s02", "s03", "complete", "series"]
        if any(ind in folder_name for ind in tv_indicators):
            return "tv"
        
        # Check number of video files
        if len(video_files) > 3:
            return "tv"  # Multiple episodes likely
        
        # Check filenames for episode patterns
        for file in video_files:
            filename = Path(file).name.lower()
            if re.search(r's\d{1,2}e\d{1,2}', filename, re.IGNORECASE):
                return "tv"
            if re.search(r'\d{1,2}x\d{1,2}', filename):
                return "tv"
        
        # Default to movie for single file
        return "movie"
    
    def find_video_files(self, folder: Path) -> List[str]:
        """Find all video files in folder (recursive)."""
        video_files = []
        
        for file in folder.rglob("*"):
            if file.is_file() and file.suffix.lower() in VIDEO_EXTENSIONS:
                # Skip sample files
                if "sample" in file.name.lower():
                    continue
                video_files.append(str(file))
        
        return sorted(video_files)
    
    def parse_episode_info(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        Extract season and episode from filename.
        Supports patterns like: S01E05, 1x05, etc.
        """
        info = guessit.guessit(filename)
        
        season = info.get("season")
        episode = info.get("episode")
        
        if episode is not None:
            # Handle episode lists (e.g., S01E01E02)
            if isinstance(episode, list):
                episode = episode[0]
            # Default to season 1 if not specified (common for anime naming like "- 01")
            if season is None:
                season = 1
            return {
                "season": int(season),
                "episode": int(episode),
                "title": info.get("episode_title"),
            }
        
        return None
    
    def _parse_episodes(self, video_files: List[str]) -> List[Dict[str, Any]]:
        """Parse episode info from list of video files."""
        episodes = []
        for file in video_files:
            filename = Path(file).name
            ep_info = self.parse_episode_info(filename)
            if ep_info:
                ep_info["file"] = file
                episodes.append(ep_info)
        
        # Sort by season then episode
        episodes.sort(key=lambda x: (x["season"], x["episode"]))
        return episodes
    
    # TMDB Matching
    def _title_similarity(self, title1: str, title2: str) -> float:
        """Calculate simple title similarity (0.0 to 1.0)."""
        t1 = title1.lower().strip()
        t2 = title2.lower().strip()
        
        # Exact match
        if t1 == t2:
            return 1.0
        
        # Check if one contains the other
        if t1 in t2 or t2 in t1:
            return 0.8
        
        # Word overlap
        words1 = set(t1.split())
        words2 = set(t2.split())
        if not words1 or not words2:
            return 0.0
        
        overlap = len(words1 & words2)
        total = len(words1 | words2)
        return overlap / total if total > 0 else 0.0
    
    async def match_with_tmdb(
        self,
        title: str,
        year: Optional[int],
        media_type: str
    ) -> Optional[MediaResult]:
        """
        Match title with TMDB. Only return if confident match.
        Will return None if no good match found - better to show nothing than wrong data.
        """
        MIN_SIMILARITY = 0.5  # Require at least 50% title similarity
        
        try:
            if media_type == "movie":
                results = await tmdb_client.search_movie(title, year)
            else:
                results = await tmdb_client.search_tv(title, year)
            
            if results:
                # Check first result for similarity
                best = results[0]
                similarity = self._title_similarity(title, best.title)
                
                if similarity >= MIN_SIMILARITY:
                    print(f"TMDB match: '{title}' -> '{best.title}' (similarity: {similarity:.2f})")
                    return best
                else:
                    print(f"TMDB no confident match for '{title}' (best: '{best.title}', similarity: {similarity:.2f})")
            
            # Don't do fallback guessing - if we can't find a good match, return None
            return None
            
        except Exception as e:
            print(f"TMDB match error for '{title}': {e}")
            return None
    
    # Database Operations
    async def _check_exists(self, folder_path: str, filename: str = None, tmdb_id: int = None) -> bool:
        """Check if media already exists in library by folder_path, file_path, or tmdb_id."""
        async with async_session_factory() as session:
            from sqlalchemy import or_
            
            conditions = [Media.folder_path == folder_path]
            
            # For single files, also check by file_path to avoid duplicates
            if filename:
                full_path = os.path.join(folder_path, filename)
                conditions.append(Media.file_path == full_path)
            
            # Also check by tmdb_id if provided (prevents same show being added twice)
            if tmdb_id:
                conditions.append(Media.tmdb_id == tmdb_id)
            
            query = select(Media).where(or_(*conditions))
            
            result = await session.execute(query)
            # Use first() instead of scalar_one_or_none() to handle multiple rows
            return result.scalars().first() is not None
    
    async def add_to_library(self, scan_result: ScanResult) -> Optional[Media]:
        """Add scanned media to the library database."""
        if scan_result.already_exists:
            return None
        
        async with async_session_factory() as session:
            try:
                # Double-check for duplicates by tmdb_id (prevents race conditions and loose file duplicates)
                if scan_result.tmdb_match:
                    tmdb_id = scan_result.tmdb_match.tmdb_id
                    existing = await session.execute(
                        select(Media).where(Media.tmdb_id == tmdb_id)
                    )
                    if existing.scalars().first():
                        print(f"Skipping duplicate (tmdb_id={tmdb_id}): {scan_result.title}")
                        return None
                
                # Create media record
                media_type = MediaType.TV if scan_result.media_type == "tv" else MediaType.MOVIE
                
                media = Media(
                    title=scan_result.tmdb_match.title if scan_result.tmdb_match else scan_result.title,
                    tmdb_id=scan_result.tmdb_match.tmdb_id if scan_result.tmdb_match else None,
                    media_type=media_type,
                    year=scan_result.year,
                    folder_path=scan_result.folder_path,
                    poster_url=scan_result.tmdb_match.get_poster_url() if scan_result.tmdb_match else None,
                    backdrop_url=scan_result.tmdb_match.get_backdrop_url() if scan_result.tmdb_match else None,
                    overview=scan_result.tmdb_match.overview if scan_result.tmdb_match else None,
                )
                
                # For movies, set file_path
                if media_type == MediaType.MOVIE and scan_result.video_files:
                    media.file_path = scan_result.video_files[0]
                
                session.add(media)
                await session.flush()  # Get the ID
                
                # For TV shows, add episodes
                if media_type == MediaType.TV:
                    for ep in scan_result.episodes:
                        episode = Episode(
                            media_id=media.id,
                            season=ep["season"],
                            episode=ep["episode"],
                            title=ep.get("title"),
                            file_path=ep["file"],
                        )
                        session.add(episode)
                
                await session.commit()
                print(f"Added to library: {media.title}")
                return media
                
            except Exception as e:
                await session.rollback()
                print(f"Failed to add to library: {e}")
                return None
    
    async def cleanup_missing(self) -> Dict[str, Any]:
        """Remove library entries where files no longer exist."""
        removed_media = []
        removed_episodes = []
        
        async with async_session_factory() as session:
            from sqlalchemy.orm import selectinload
            
            # Get all media with episodes loaded
            result = await session.execute(
                select(Media).options(selectinload(Media.episodes))
            )
            all_media = result.scalars().all()
            
            for media in all_media:
                # Check if this is a valid folder path (not just the root downloads folder)
                folder_path = Path(media.folder_path) if media.folder_path else None
                folder_exists = folder_path.exists() if folder_path else False
                file_exists = Path(media.file_path).exists() if media.file_path else False
                
                # For movies, check if file exists
                if media.media_type == MediaType.MOVIE:
                    if not file_exists:
                        removed_media.append(media.title)
                        await session.delete(media)
                        print(f"Removed missing movie: {media.title}")
                else:
                    # For TV shows, check episodes
                    episodes_list = list(media.episodes) if media.episodes else []
                    
                    # Remove episodes whose files are missing
                    for ep in episodes_list:
                        if ep.file_path and not Path(ep.file_path).exists():
                            removed_episodes.append(f"{media.title} S{ep.season}E{ep.episode}")
                            await session.delete(ep)
                            print(f"Removed missing episode: {media.title} S{ep.season}E{ep.episode}")
                    
                    # Get remaining episodes count after removal
                    await session.flush()
                    remaining_result = await session.execute(
                        select(Media).where(Media.id == media.id).options(selectinload(Media.episodes))
                    )
                    refreshed_media = remaining_result.scalar_one_or_none()
                    remaining_eps = len(refreshed_media.episodes) if refreshed_media and refreshed_media.episodes else 0
                    
                    # Remove TV show if no episodes remain or folder doesn't exist
                    if remaining_eps == 0 or (not folder_exists and media.folder_path != str(self.downloads_path)):
                        removed_media.append(media.title)
                        await session.delete(media)
                        print(f"Removed TV show with no episodes: {media.title}")
            
            await session.commit()
        
        return {
            "removed_media": removed_media,
            "removed_episodes": removed_episodes,
        }
    
    async def scan_and_import(self) -> Dict[str, Any]:
        """Scan for new media, import to library, and cleanup missing entries."""
        # First, cleanup missing entries
        cleanup_result = await self.cleanup_missing()
        
        # Then scan for new media
        results = await self.scan_completed_folder()
        
        imported = []
        skipped = []
        errors = []
        
        for result in results:
            if result.already_exists:
                skipped.append(result.folder_name)
            elif result.error:
                errors.append({"folder": result.folder_name, "error": result.error})
            else:
                media = await self.add_to_library(result)
                if media:
                    imported.append(result.folder_name)
                else:
                    errors.append({"folder": result.folder_name, "error": "Failed to add"})
        
        return {
            "scanned": len(results),
            "imported": len(imported),
            "skipped": len(skipped),
            "errors": len(errors),
            "imported_items": imported,
            "skipped_items": skipped,
            "error_items": errors,
            "removed": len(cleanup_result["removed_media"]) + len(cleanup_result["removed_episodes"]),
            "removed_items": cleanup_result["removed_media"] + cleanup_result["removed_episodes"],
        }


# Singleton Instance
library_scanner = LibraryScanner()
