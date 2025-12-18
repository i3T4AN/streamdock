#!/bin/bash
# StreamDock Linux/macOS Startup Script

echo "StreamDock Launcher"
echo "==================="

if [ ! -f ".env" ]; then
    echo ".env file not found. Running setup..."
    chmod +x setup.sh
    ./setup.sh
fi

echo "Starting StreamDock..."
docker-compose up -d

echo ""
echo "StreamDock is running!"
echo "Access at: http://localhost:8000"
