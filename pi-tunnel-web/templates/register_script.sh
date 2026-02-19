#!/bin/bash
# Pi Tunnel registration script - run on Raspberry Pi
# curl -sSL {{ base_url }}/register/{{ token }}/script | bash

set -e
TOKEN="{{ token }}"
BASE_URL="{{ base_url }}"
BASE_URL="${BASE_URL%/}"
SERVER_HOST="{{ server_host }}"
SERVER_SSH_PORT="{{ server_ssh_port }}"

echo "Pi Tunnel registration"
echo "======================"

# Check deps
for cmd in ssh-keygen curl; do
  if ! command -v $cmd &>/dev/null; then
    echo "Error: $cmd required. Install with: sudo apt-get install openssh-client curl"
    exit 1
  fi
done

# Generate key if missing
KEY_FILE="$HOME/.ssh/id_ed25519"
if [ ! -f "$KEY_FILE" ]; then
  echo "Generating SSH key..."
  mkdir -p "$HOME/.ssh"
  chmod 700 "$HOME/.ssh"
  ssh-keygen -t ed25519 -N '' -f "$KEY_FILE"
fi

PUBKEY=$(cat "${KEY_FILE}.pub")
echo "Sending public key to server..."

RESP=$(curl -sS -X POST "${BASE_URL}/register/${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"public_key\": \"$(echo "$PUBKEY" | sed 's/"/\\"/g')\"}")

if echo "$RESP" | grep -q '"ok":true'; then
  echo "Public key registered."
else
  echo "Registration failed: $RESP"
  exit 1
fi

# Fetch server public key and add to authorized_keys
echo "Fetching server public key..."
SERVER_KEY=$(curl -sS "${BASE_URL}/register/${TOKEN}/server-key")
if [ -z "$SERVER_KEY" ]; then
  echo "Warning: Server public key not configured. You must add it manually to ~/.ssh/authorized_keys"
  echo "Get it from the web UI Settings."
else
  mkdir -p "$HOME/.ssh"
  touch "$HOME/.ssh/authorized_keys"
  chmod 600 "$HOME/.ssh/authorized_keys"
  if ! grep -qF "$SERVER_KEY" "$HOME/.ssh/authorized_keys"; then
    echo "$SERVER_KEY" >> "$HOME/.ssh/authorized_keys"
    echo "Server public key added to authorized_keys."
  fi
fi

# Get port from response
PORT=$(echo "$RESP" | grep -oE '"port"[[:space:]]*:[[:space:]]*[0-9]+' | grep -oE '[0-9]+' | head -1)
[ -z "$PORT" ] && PORT=10022

# Server host: use auto-detected domain or prompt only when interactive
if [ -z "$SERVER_HOST" ]; then
  if [ -t 0 ]; then
    read -p "Server domain or hostname: " SERVER_HOST
  fi
  [ -z "$SERVER_HOST" ] && { echo "Server domain required. Set WEB_URL or SERVER_URL in server .env or run interactively."; exit 1; }
fi
# SSH port: use injected value or prompt only when interactive
if [ -z "$SERVER_SSH_PORT" ]; then
  if [ -t 0 ]; then
    read -p "SSH port on server [2222]: " SSH_PORT
  fi
  SSH_PORT=${SSH_PORT:-2222}
else
  SSH_PORT="$SERVER_SSH_PORT"
fi

# Install autossh if needed
if ! command -v autossh &>/dev/null; then
  echo "Installing autossh..."
  sudo apt-get update && sudo apt-get install -y autossh
fi

# Remove stale host key (auto-resolve "REMOTE HOST IDENTIFICATION HAS CHANGED")
# When server/container is rebuilt, host keys change; removing old entry lets the new key be accepted
ssh-keygen -f "$HOME/.ssh/known_hosts" -R "[${SERVER_HOST}]:${SSH_PORT}" 2>/dev/null || true

# Create systemd service
# ExecStartPre removes stale known_hosts entry so host key changes (e.g. after container rebuild) auto-resolve
# StrictHostKeyChecking=accept-new adds new keys without prompt; combined with pre-removal, reconnects succeed
SVC_FILE="/etc/systemd/system/ssh-reverse-tunnel.service"
sudo tee "$SVC_FILE" << EOF
[Unit]
Description=Reverse SSH tunnel to server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
ExecStartPre=-/usr/bin/ssh-keygen -f $HOME/.ssh/known_hosts -R '[${SERVER_HOST}]:${SSH_PORT}' 2>/dev/null || true
ExecStart=/usr/bin/autossh -M 0 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new -N -R ${PORT}:localhost:22 -p ${SSH_PORT} pitunnel@${SERVER_HOST}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ssh-reverse-tunnel.service
sudo systemctl start ssh-reverse-tunnel.service
echo "Tunnel service started. Check: systemctl status ssh-reverse-tunnel.service"
echo "From server, connect with: ssh -p ${PORT} \$(whoami)@localhost"
