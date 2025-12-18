#!/bin/bash
#===============================================
# i3T4AN (Ethan Blair) - StreamDock
# Project:      StreamDock
# File:         First-run setup script
# Run this ONCE before `docker-compose up` on a fresh install.
#===============================================

set -e

MEDIA_ROOT="${HOME}/Documents/StreamDockMedia"

echo "StreamDock Setup"
echo "==================="

# Create directory structure
echo "Creating media directories..."
mkdir -p "${MEDIA_ROOT}/downloads"
mkdir -p "${MEDIA_ROOT}/transcoded"
mkdir -p "${MEDIA_ROOT}/database"
mkdir -p "${MEDIA_ROOT}/qbittorrent/qBittorrent/config"

# Copy default qBittorrent config (enables auth bypass)
QBIT_CONF="${MEDIA_ROOT}/qbittorrent/qBittorrent.conf"
if [ ! -f "${QBIT_CONF}" ]; then
    echo "Installing default qBittorrent config (auth disabled)..."
    cp "$(dirname "$0")/config/qBittorrent.conf" "${QBIT_CONF}"
else
    echo "qBittorrent config already exists, skipping..."
fi

# Copy .env.example if .env doesn't exist
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "Creating .env from template..."
        cp ".env.example" ".env"
        echo "Please edit .env and add your TMDB API key!"
    fi
else
    echo "env already exists, skipping..."
fi

# Auto-detect and set SERVER_IP for network access
echo "Detecting local IP address..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "")
else
    # Linux
    LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "")
fi

if [ -n "$LOCAL_IP" ]; then
    # Check if SERVER_IP already set in .env
    if ! grep -q "^SERVER_IP=" ".env" 2>/dev/null; then
        echo "SERVER_IP=${LOCAL_IP}" >> ".env"
        echo "Detected IP: ${LOCAL_IP}"
    else
        # Update existing SERVER_IP if empty
        if grep -q "^SERVER_IP=$" ".env" 2>/dev/null; then
            sed -i.bak "s/^SERVER_IP=$/SERVER_IP=${LOCAL_IP}/" ".env" && rm -f ".env.bak"
            echo "Updated IP: ${LOCAL_IP}"
        fi
    fi
else
    echo "Could not detect IP - set SERVER_IP manually in .env"
fi

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your TMDB_API_KEY"
echo "  2. Run: docker-compose up -d"
echo "  3. Open: http://localhost:8000"
echo ""
echo "Access from other devices: http://${LOCAL_IP:-localhost}:8000"
echo ""
