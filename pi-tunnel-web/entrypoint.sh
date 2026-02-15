#!/bin/sh
set -e
mkdir -p /app/data
touch /app/data/authorized_keys
exec python app.py
