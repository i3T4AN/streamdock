#===============================================================
# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         Main application entry point (FastAPI)
#===============================================================

import os
import asyncio
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

# Database imports
from database import init_db, close_db, engine
import models  # Import models to register them with SQLAlchemy

# Load environment variables
load_dotenv()


# Lifespan Events (startup/shutdown)
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    from scheduler import scheduler
    from job_worker import job_worker
    
    # Startup
    print("Starting StreamDock...")
    await init_db()
    print("Database tables created")
    await scheduler.start()
    asyncio.create_task(job_worker.start())
    yield
    # Shutdown
    print("Shutting down StreamDock...")
    await scheduler.stop()
    await job_worker.stop()
    await close_db()


# Create FastAPI app
app = FastAPI(
    title="StreamDock",
    description="Self-hosted media streaming platform",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend static files
app.mount("/css", StaticFiles(directory="/app/frontend/css"), name="css")
app.mount("/js", StaticFiles(directory="/app/frontend/js"), name="js")
app.mount("/images", StaticFiles(directory="/app/frontend/images"), name="images")


# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and return a clean error response."""
    error_id = f"ERR-{id(exc)}"
    print(f"Unhandled exception [{error_id}]: {type(exc).__name__}: {exc}")
    print(traceback.format_exc())
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "error_id": error_id,
            "type": type(exc).__name__,
            "message": str(exc) if os.getenv("DEBUG") else "An unexpected error occurred",
        }
    )


# Health Check Endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for Docker."""
    return {"status": "healthy", "service": "streamdock"}


# Root - Serve Frontend
@app.get("/")
async def root():
    """Serve the main frontend application."""
    return FileResponse("/app/frontend/index.html")


@app.get("/downloads.html")
async def downloads_page():
    """Serve the downloads page."""
    return FileResponse("/app/frontend/downloads.html")


@app.get("/settings.html")
async def settings_page():
    """Serve the settings page."""
    return FileResponse("/app/frontend/settings.html")


@app.get("/favicon.ico")
async def favicon():
    """Serve the favicon."""
    return FileResponse("/app/frontend/favicon.ico")


# API Status
@app.get("/api/status")
async def api_status():
    """API status check with database connection test."""
    import socket
    from sqlalchemy import text
    from torrent_client import qbit_client
    
    db_status = "connected"
    qbit_status = "disconnected"
    
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    try:
        if qbit_client.is_connected():
            qbit_status = "connected"
    except Exception:
        pass
    
    # Get server IP for network access
    # Use environment variable if set, otherwise try to detect
    server_ip = os.getenv("SERVER_IP", "")
    if not server_ip:
        try:
            # Get all network interfaces
            hostname = socket.gethostname()
            # Try to get the external-facing IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            try:
                # Connect to an external address to determine which interface is used
                s.connect(("8.8.8.8", 80))
                server_ip = s.getsockname()[0]
            except Exception:
                # Fallback to hostname resolution
                server_ip = socket.gethostbyname(hostname)
            finally:
                s.close()
        except Exception:
            server_ip = "localhost"
    
    return {
        "status": "ok",
        "version": "0.1.0",
        "server_ip": server_ip,
        "services": {
            "database": db_status,
            "qbittorrent": qbit_status,
            "tmdb": "configured"
        }
    }


# Register API Routers
from routes_torrents import router as torrents_router
from routes_library import router as library_router
from routes_stream import router as stream_router, poster_router
from routes_transcode import router as transcode_router
from routes_progress import router as progress_router, settings_router
from routes_webhooks import router as webhooks_router

app.include_router(torrents_router)
app.include_router(library_router)
app.include_router(stream_router)
app.include_router(poster_router)
app.include_router(transcode_router)
app.include_router(progress_router)
app.include_router(settings_router)
app.include_router(webhooks_router)
