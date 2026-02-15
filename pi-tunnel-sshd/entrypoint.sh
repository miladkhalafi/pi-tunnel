#!/bin/sh
set -e
KEY_FILE="/home/pitunnel/.ssh/authorized_keys"
# Allow empty file on cold start (no Pis registered yet); sshd will reject connections until keys are added
if [ ! -f "$KEY_FILE" ]; then
  echo "Mount authorized_keys at $KEY_FILE (e.g. -v /path/to/authorized_keys:$KEY_FILE)"
  exit 1
fi
# Generate SSH host keys (required for sshd to start)
# Always run - keys may be missing in some image builds or environments
ssh-keygen -A
chown pitunnel:pitunnel "$KEY_FILE" && chmod 600 "$KEY_FILE"
exec /usr/sbin/sshd -D -e
