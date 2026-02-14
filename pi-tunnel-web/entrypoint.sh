#!/bin/sh
set -e
mkdir -p /app/data
touch /app/data/authorized_keys
exec python -m flask run --host=0.0.0.0 --port=8080
