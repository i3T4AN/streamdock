#!/bin/bash
# =======================================================================
# i3T4AN (Ethan Blair)
# Project:      StreamDock
# File:         qBittorrent first-run init script
# =======================================================================
# This script runs inside the container on every start.
# It copies the default config ONLY if one doesn't exist yet.

CONFIG_FILE="/config/qBittorrent/qBittorrent.conf"
DEFAULT_CONFIG="/defaults/qBittorrent.conf"

if [ ! -f "${CONFIG_FILE}" ]; then
    echo "[streamdock-init] First run detected, installing default qBittorrent config..."
    mkdir -p /config/qBittorrent
    cp "${DEFAULT_CONFIG}" "${CONFIG_FILE}"
    echo "[streamdock-init] Default config installed (auth bypass enabled)."
else
    echo "[streamdock-init] Existing config found, skipping..."
fi
