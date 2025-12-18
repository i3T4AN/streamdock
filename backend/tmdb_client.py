#===============================================================
# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         TMDB API client for metadata and posters
#===============================================================

import os
import time
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from functools import lru_cache
import httpx
from dotenv import load_dotenv

load_dotenv()


# Configuration
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

# Rate limiting: 40 requests per 10 seconds
RATE_LIMIT_REQUESTS = 40
RATE_LIMIT_WINDOW = 10  # seconds


# Poster/Backdrop Sizes
class PosterSize:
    """Available poster sizes from TMDB."""
    SMALL = "w92"
    MEDIUM = "w185"
    LARGE = "w342"
    XLARGE = "w500"
    ORIGINAL = "original"


class BackdropSize:
    """Available backdrop sizes from TMDB."""
    SMALL = "w300"
    MEDIUM = "w780"
    LARGE = "w1280"
    ORIGINAL = "original"


# Media Result Dataclass
@dataclass
class MediaResult:
    """Structured media search result."""
    tmdb_id: int
    title: str
    media_type: str  # "movie" or "tv"
    year: Optional[int]
    poster_path: Optional[str]
    backdrop_path: Optional[str]
    overview: Optional[str]
    vote_average: float
    popularity: float
    
    def get_poster_url(self, size: str = PosterSize.LARGE) -> Optional[str]:
        """Get full poster URL."""
        return TMDBClient.get_poster_url(self.poster_path, size)
    
    def get_backdrop_url(self, size: str = BackdropSize.LARGE) -> Optional[str]:
        """Get full backdrop URL."""
        return TMDBClient.get_backdrop_url(self.backdrop_path, size)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tmdb_id": self.tmdb_id,
            "title": self.title,
            "media_type": self.media_type,
            "year": self.year,
            "poster_url": self.get_poster_url(),
            "backdrop_url": self.get_backdrop_url(),
            "overview": self.overview,
            "vote_average": self.vote_average,
            "popularity": self.popularity,
        }
    
    @classmethod
    def from_movie(cls, data: dict) -> "MediaResult":
        """Create MediaResult from movie API response."""
        release_date = data.get("release_date", "")
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
        
        return cls(
            tmdb_id=data.get("id", 0),
            title=data.get("title", "Unknown"),
            media_type="movie",
            year=year,
            poster_path=data.get("poster_path"),
            backdrop_path=data.get("backdrop_path"),
            overview=data.get("overview"),
            vote_average=data.get("vote_average", 0),
            popularity=data.get("popularity", 0),
        )
    
    @classmethod
    def from_tv(cls, data: dict) -> "MediaResult":
        """Create MediaResult from TV API response."""
        first_air = data.get("first_air_date", "")
        year = int(first_air[:4]) if first_air and len(first_air) >= 4 else None
        
        return cls(
            tmdb_id=data.get("id", 0),
            title=data.get("name", "Unknown"),
            media_type="tv",
            year=year,
            poster_path=data.get("poster_path"),
            backdrop_path=data.get("backdrop_path"),
            overview=data.get("overview"),
            vote_average=data.get("vote_average", 0),
            popularity=data.get("popularity", 0),
        )


# Rate Limiter
class RateLimiter:
    """Simple rate limiter for API requests."""
    
    def __init__(self, max_requests: int = RATE_LIMIT_REQUESTS, window: int = RATE_LIMIT_WINDOW):
        self.max_requests = max_requests
        self.window = window
        self.requests: List[float] = []
    
    async def acquire(self) -> None:
        """Wait if necessary to respect rate limits."""
        now = time.time()
        
        # Remove old requests outside the window
        self.requests = [t for t in self.requests if now - t < self.window]
        
        # If at limit, wait until oldest request expires
        if len(self.requests) >= self.max_requests:
            wait_time = self.window - (now - self.requests[0])
            if wait_time > 0:
                await asyncio.sleep(wait_time)
                self.requests = self.requests[1:]
        
        # Record this request
        self.requests.append(time.time())


# Simple Cache
class SimpleCache:
    """Simple in-memory cache with TTL."""
    
    def __init__(self, ttl: int = 3600):  # 1 hour default
        self.ttl = ttl
        self._cache: Dict[str, tuple] = {}  # key -> (value, timestamp)
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Store value in cache."""
        self._cache[key] = (value, time.time())
    
    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()


# TMDB Client
class TMDBClient:
    """
    Client for The Movie Database (TMDB) API.
    Handles movie/TV searches with rate limiting and caching.
    """
    
    def __init__(self, api_key: str = TMDB_API_KEY):
        self.api_key = api_key
        self.base_url = TMDB_BASE_URL
        self.rate_limiter = RateLimiter()
        self.cache = SimpleCache(ttl=3600)  # 1 hour cache
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def _request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make API request with rate limiting and error handling."""
        if not self.api_key:
            print("TMDB API key not configured")
            return None
        
        # Check cache first
        cache_key = f"{endpoint}:{str(params)}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached
        
        # Rate limit
        await self.rate_limiter.acquire()
        
        # Build request
        url = f"{self.base_url}{endpoint}"
        request_params = {"api_key": self.api_key}
        if params:
            request_params.update(params)
        
        try:
            client = await self._get_client()
            response = await client.get(url, params=request_params)
            
            if response.status_code == 200:
                data = response.json()
                self.cache.set(cache_key, data)
                return data
            elif response.status_code == 401:
                print("TMDB API key invalid")
                return None
            elif response.status_code == 404:
                return None
            elif response.status_code == 429:
                # Rate limited, wait and retry
                await asyncio.sleep(2)
                return await self._request(endpoint, params)
            else:
                print(f"TMDB API error: {response.status_code}")
                return None
                
        except httpx.TimeoutException:
            print("TMDB API timeout")
            return None
        except Exception as e:
            print(f"TMDB API error: {e}")
            return None
    
    # Search Methods
    async def search_movie(self, query: str, year: Optional[int] = None) -> List[MediaResult]:
        """Search for movies by title."""
        params = {"query": query}
        if year:
            params["year"] = str(year)
        
        data = await self._request("/search/movie", params)
        if not data:
            return []
        
        results = data.get("results", [])
        return [MediaResult.from_movie(r) for r in results]
    
    async def search_tv(self, query: str, year: Optional[int] = None) -> List[MediaResult]:
        """Search for TV shows by title."""
        params = {"query": query}
        if year:
            params["first_air_date_year"] = str(year)
        
        data = await self._request("/search/tv", params)
        if not data:
            return []
        
        results = data.get("results", [])
        return [MediaResult.from_tv(r) for r in results]
    
    async def search_multi(self, query: str) -> List[MediaResult]:
        """Search for both movies and TV shows."""
        params = {"query": query}
        
        data = await self._request("/search/multi", params)
        if not data:
            return []
        
        results = []
        for item in data.get("results", []):
            media_type = item.get("media_type")
            if media_type == "movie":
                results.append(MediaResult.from_movie(item))
            elif media_type == "tv":
                results.append(MediaResult.from_tv(item))
            # Skip "person" results
        
        return results
    
    # Detail Methods
    async def get_movie_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """Get full movie details by TMDB ID, including cast."""
        data = await self._request(f"/movie/{tmdb_id}", {"append_to_response": "credits"})
        if not data:
            return None
        
        release_date = data.get("release_date", "")
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None
        
        # Parse cast (top 10)
        credits = data.get("credits", {})
        cast = []
        for person in credits.get("cast", [])[:10]:
            cast.append({
                "name": person.get("name"),
                "character": person.get("character"),
                "profile_url": self.get_profile_url(person.get("profile_path")),
            })
        
        # Get director from crew
        director = None
        for person in credits.get("crew", []):
            if person.get("job") == "Director":
                director = person.get("name")
                break
        
        return {
            "tmdb_id": data.get("id"),
            "title": data.get("title"),
            "original_title": data.get("original_title"),
            "media_type": "movie",
            "year": year,
            "release_date": release_date,
            "runtime": data.get("runtime"),
            "overview": data.get("overview"),
            "tagline": data.get("tagline"),
            "poster_url": self.get_poster_url(data.get("poster_path")),
            "backdrop_url": self.get_backdrop_url(data.get("backdrop_path")),
            "vote_average": data.get("vote_average"),
            "vote_count": data.get("vote_count"),
            "genres": [g.get("name") for g in data.get("genres", [])],
            "status": data.get("status"),
            "imdb_id": data.get("imdb_id"),
            "cast": cast,
            "director": director,
        }
    
    async def get_tv_details(self, tmdb_id: int) -> Optional[Dict[str, Any]]:
        """Get full TV show details by TMDB ID, including cast."""
        data = await self._request(f"/tv/{tmdb_id}", {"append_to_response": "credits"})
        if not data:
            return None
        
        first_air = data.get("first_air_date", "")
        year = int(first_air[:4]) if first_air and len(first_air) >= 4 else None
        
        # Parse cast (top 10)
        credits = data.get("credits", {})
        cast = []
        for person in credits.get("cast", [])[:10]:
            cast.append({
                "name": person.get("name"),
                "character": person.get("character"),
                "profile_url": self.get_profile_url(person.get("profile_path")),
            })
        
        # Get creators
        creators = [c.get("name") for c in data.get("created_by", [])]
        
        return {
            "tmdb_id": data.get("id"),
            "title": data.get("name"),
            "original_title": data.get("original_name"),
            "media_type": "tv",
            "year": year,
            "first_air_date": first_air,
            "last_air_date": data.get("last_air_date"),
            "number_of_seasons": data.get("number_of_seasons"),
            "number_of_episodes": data.get("number_of_episodes"),
            "episode_runtime": data.get("episode_run_time", []),
            "overview": data.get("overview"),
            "tagline": data.get("tagline"),
            "poster_url": self.get_poster_url(data.get("poster_path")),
            "backdrop_url": self.get_backdrop_url(data.get("backdrop_path")),
            "vote_average": data.get("vote_average"),
            "vote_count": data.get("vote_count"),
            "genres": [g.get("name") for g in data.get("genres", [])],
            "status": data.get("status"),
            "networks": [n.get("name") for n in data.get("networks", [])],
            "cast": cast,
            "creators": creators,
        }
    
    # URL Helpers
    @staticmethod
    def get_poster_url(path: Optional[str], size: str = PosterSize.LARGE) -> Optional[str]:
        """Construct full poster URL from path."""
        if path:
            return f"{TMDB_IMAGE_BASE}/{size}{path}"
        return None
    
    @staticmethod
    def get_backdrop_url(path: Optional[str], size: str = BackdropSize.LARGE) -> Optional[str]:
        """Construct full backdrop URL from path."""
        if path:
            return f"{TMDB_IMAGE_BASE}/{size}{path}"
        return None
    
    @staticmethod
    def get_profile_url(path: Optional[str], size: str = "w185") -> Optional[str]:
        """Construct full profile photo URL from path."""
        if path:
            return f"{TMDB_IMAGE_BASE}/{size}{path}"
        return None


# Singleton Instance
tmdb_client = TMDBClient()
