#!/bin/bash
# Pi Tunnel uninstall script - run on Raspberry Pi
# curl -sSL {{ base_url }}/register/{{ token }}/uninstall-script | bash

set -e
TOKEN="{{ token }}"
BASE_URL="{{ base_url }}"
BASE_URL="${BASE_URL%/}"

echo "Pi Tunnel uninstall"
echo "==================="

# Check deps
if ! command -v curl &>/dev/null; then
    echo "Error: curl required. Install with: sudo apt-get install curl"
    exit 1
fi

# Stop and remove systemd service
SVC_FILE="/etc/systemd/system/ssh-reverse-tunnel.service"
if [ -f "$SVC_FILE" ]; then
    echo "Stopping tunnel service..."
    sudo systemctl stop ssh-reverse-tunnel.service 2>/dev/null || true
    sudo systemctl disable ssh-reverse-tunnel.service 2>/dev/null || true
    sudo rm -f "$SVC_FILE"
    sudo systemctl daemon-reload
    echo "Tunnel service removed."
else
    echo "Tunnel service not found (already uninstalled?)."
fi

# Unregister from server (remove public key)
KEY_FILE="$HOME/.ssh/id_ed25519"
[ ! -f "${KEY_FILE}.pub" ] && KEY_FILE="$HOME/.ssh/id_rsa"
if [ -f "${KEY_FILE}.pub" ]; then
    PUBKEY=$(cat "${KEY_FILE}.pub")
    echo "Unregistering from server..."
    RESP=$(curl -sS -X POST "${BASE_URL}/register/${TOKEN}/unregister" \
        -H "Content-Type: application/json" \
        -d "{\"public_key\": \"$(echo "$PUBKEY" | sed 's/"/\\"/g')\"}")
    if echo "$RESP" | grep -q '"ok":true'; then
        echo "Unregistered from server."
    else
        echo "Note: Server unregister returned: $RESP (Pi may already be unregistered)"
    fi
else
    echo "No SSH public key found. Skipping server unregister."
fi

# Remove server key from authorized_keys if present
SERVER_KEY=$(curl -sS "${BASE_URL}/register/${TOKEN}/server-key" 2>/dev/null || true)
if [ -n "$SERVER_KEY" ] && [ -f "$HOME/.ssh/authorized_keys" ]; then
    if grep -qF "$SERVER_KEY" "$HOME/.ssh/authorized_keys"; then
        grep -vF "$SERVER_KEY" "$HOME/.ssh/authorized_keys" > "$HOME/.ssh/authorized_keys.tmp"
        mv "$HOME/.ssh/authorized_keys.tmp" "$HOME/.ssh/authorized_keys"
        echo "Server key removed from authorized_keys."
    fi
fi

echo ""
echo "Pi Tunnel uninstalled."
