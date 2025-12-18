@echo off
REM StreamDock Windows Startup Script

echo StreamDock Launcher (Windows)
echo ============================

if not exist ".env" (
    echo .env file not found. Running setup...
    powershell -ExecutionPolicy Bypass -File .\setup.ps1
)

echo Starting StreamDock...
docker-compose up -d

echo.
echo StreamDock is running!
echo Access at: http://localhost:8000
pause
