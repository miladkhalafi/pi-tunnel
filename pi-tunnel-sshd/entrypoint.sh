#!/bin/sh
set -e
KEY_FILE="/home/pitunnel/.ssh/authorized_keys"
SSH_DIR="/home/pitunnel/.ssh"
HOST_KEYS_DIR="/host_keys"
# Allow empty file on cold start (no Pis registered yet); sshd will reject connections until keys are added
if [ ! -f "$KEY_FILE" ]; then
  echo "Mount authorized_keys at $KEY_FILE"
  exit 1
fi
# Persist SSH host keys so they survive container reboots (avoids "Host key verification failed" on Pi)
if [ -f "$HOST_KEYS_DIR/ssh_host_ed25519_key" ]; then
  cp -p "$HOST_KEYS_DIR"/ssh_host_* /etc/ssh/
else
  ssh-keygen -A
  cp -p /etc/ssh/ssh_host_* "$HOST_KEYS_DIR/"
fi
# OpenSSH rejects keys if .ssh or home is not owned by the user (common in Alpine/Docker)
chown -R pitunnel:pitunnel "$SSH_DIR"
chmod 700 "$SSH_DIR"
chmod 600 "$KEY_FILE"
# Re-chown periodically: web app writes authorized_keys and can change ownership to root
( while true; do sleep 30; chown pitunnel:pitunnel "$KEY_FILE" 2>/dev/null || true; done ) &
exec /usr/sbin/sshd -D -e
