#!/bin/sh
set -e
KEY_FILE="/home/pitunnel/.ssh/authorized_keys"
SSH_DIR="/home/pitunnel/.ssh"
# Allow empty file on cold start (no Pis registered yet); sshd will reject connections until keys are added
if [ ! -f "$KEY_FILE" ]; then
  echo "Mount authorized_keys at $KEY_FILE (e.g. -v /path/to/authorized_keys:$KEY_FILE)"
  exit 1
fi
# Generate SSH host keys (required for sshd to start)
# Always run - keys may be missing in some image builds or environments
ssh-keygen -A
# OpenSSH rejects keys if .ssh or home is not owned by the user (common in Alpine/Docker)
chown -R pitunnel:pitunnel "$SSH_DIR"
chmod 700 "$SSH_DIR"
chmod 600 "$KEY_FILE"
exec /usr/sbin/sshd -D -e
