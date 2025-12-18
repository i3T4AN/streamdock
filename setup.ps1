# StreamDock Setup Script for Windows
# Replicates functionality of setup.sh

$MEDIA_ROOT = "$HOME\Documents\StreamDockMedia"

Write-Host "StreamDock Setup"
Write-Host "==================="

# Create directory structure
Write-Host "Creating media directories..."
New-Item -ItemType Directory -Force -Path "$MEDIA_ROOT\downloads" | Out-Null
New-Item -ItemType Directory -Force -Path "$MEDIA_ROOT\transcoded" | Out-Null
New-Item -ItemType Directory -Force -Path "$MEDIA_ROOT\database" | Out-Null
New-Item -ItemType Directory -Force -Path "$MEDIA_ROOT\qbittorrent\qBittorrent\config" | Out-Null

# Copy default qBittorrent config
$QBIT_CONF = "$MEDIA_ROOT\qbittorrent\qBittorrent.conf"
if (-not (Test-Path $QBIT_CONF)) {
    Write-Host "Installing default qBittorrent config (auth disabled)..."
    Copy-Item "config\qBittorrent.conf" $QBIT_CONF
} else {
    Write-Host "qBittorrent config already exists, skipping..."
}

# Copy .env.example if .env doesn't exist
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Write-Host "Creating .env from template..."
        Copy-Item ".env.example" ".env"
        Write-Host "Please edit .env and add your TMDB API key!"
    }
} else {
    Write-Host "env already exists, skipping..."
}

# Auto-detect and set SERVER_IP
Write-Host "Detecting local IP address..."
try {
    $LOCAL_IP = (Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Dhcp).IPAddress | Select-Object -First 1
} catch {
    $LOCAL_IP = ""
}

if (-not $LOCAL_IP) {
     # Fallback
     $LOCAL_IP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254*" }).IPAddress | Select-Object -First 1
}

if ($LOCAL_IP) {
    $envContent = Get-Content ".env" -Raw
    if ($envContent -notmatch "SERVER_IP=") {
        Add-Content ".env" "`nSERVER_IP=$LOCAL_IP"
        Write-Host "Detected IP: $LOCAL_IP (Added to .env)"
    } elseif ($envContent -match "SERVER_IP=\s*$") {
         # Update empty SERVER_IP
         $envContent = $envContent -replace "SERVER_IP=\s*$", "SERVER_IP=$LOCAL_IP"
         Set-Content ".env" $envContent
         Write-Host "Detected IP: $LOCAL_IP (Updated .env)"
    } else {
         Write-Host "SERVER_IP already set in .env. Detected IP: $LOCAL_IP"
    }
} else {
    Write-Host "Could not detect IP - set SERVER_IP manually in .env"
}

Write-Host ""
Write-Host "Setup complete!"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Edit .env and add your TMDB_API_KEY"
Write-Host "  2. Run: docker-compose up -d"
Write-Host "  3. Open: http://localhost:8000"
