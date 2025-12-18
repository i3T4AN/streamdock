#!/bin/sh
# StreamDock Webhook Wrapper
# $1 = Name (%N)
# $2 = Hash (%I)
# $3 = Save Path (%D)

# Log to stdout for docker logs
echo "🪝 Webhook wrapper executed for: $1"

# Sanitize inputs (basic quote escaping)
NAME="$1"
HASH="$2"
SAVE_PATH="$3"

# Construct JSON manually to avoid dependency on jq
JSON_DATA="{\"name\":\"$NAME\",\"hash\":\"$HASH\",\"save_path\":\"$SAVE_PATH\"}"

echo "Sending payload..."

# Use curl to send the request
/usr/bin/curl -v -X POST http://app:8000/api/webhooks/download-complete \
     -H "Content-Type: application/json" \
     -d "$JSON_DATA"
