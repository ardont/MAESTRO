#!/bin/bash
set -e

echo "=========================================================="
echo "Starting Auto-Init"
echo "=========================================================="

python3 /app/RLT_project/auto_init.py

echo "=========================================================="
echo "Starting Django Web Server (0.0.0.0:8000)..."
echo "=========================================================="

cd /app/RLT_project
exec python3 manage.py runserver 0.0.0.0:8000
