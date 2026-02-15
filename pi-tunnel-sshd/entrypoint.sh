#!/bin/sh
set -e
KEY_FILE="/home/pitunnel/.ssh/authorized_keys"
# Allow empty file on cold start (no Pis registered yet); sshd will reject connections until keys are added
if [ ! -f "$KEY_FILE" ]; then
  echo "Mount authorized_keys at $KEY_FILE (e.g. -v /path/to/authorized_keys:$KEY_FILE)"
  exit 1
fi
# Generate SSH host keys if missing (required for sshd to start)
if [ ! -f /etc/ssh/ssh_host_ed25519_key ]; then
  ssh-keygen -A
fi
chown pitunnel:pitunnel "$KEY_FILE" && chmod 600 "$KEY_FILE"
exec /usr/sbin/sshd -D -e
