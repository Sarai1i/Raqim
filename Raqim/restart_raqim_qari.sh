#!/usr/bin/env bash
set -euo pipefail

BACKEND_LOG="/home/ubuntu/Raqim/Backend/logs/backend_qari_prod.log"
FRONTEND_LOG="/home/ubuntu/Raqim/frontend_qari.log"

fuser -k 5000/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true

cd /home/ubuntu/Raqim/Backend
mkdir -p logs
nohup /home/ubuntu/Raqim/start_backend_qari.sh > "$BACKEND_LOG" 2>&1 &

cd /home/ubuntu/Raqim/my-app
nohup /home/ubuntu/Raqim/start_frontend_qari.sh > "$FRONTEND_LOG" 2>&1 &

echo "Raqim Qari OCR backend starting on port 5000. Log: $BACKEND_LOG"
echo "Raqim frontend starting on port 3000. Log: $FRONTEND_LOG"
