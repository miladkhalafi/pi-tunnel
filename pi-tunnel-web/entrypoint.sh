#!/bin/sh
set -e
mkdir -p /app/data /app/data/.ssh
touch /app/data/authorized_keys
exec python app.py
