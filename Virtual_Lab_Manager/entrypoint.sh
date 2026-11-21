#!/usr/bin/env sh
set -e

PORT=${PORT:-8080}
echo "Starting Virtual Lab Manager on 0.0.0.0:${PORT}..."

# Start FastAPI backend on internal port 8000
cd /app/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# Wait for backend to be ready
until curl -s http://127.0.0.1:8000/api/health > /dev/null 2>&1; do
  echo "Waiting for backend API on 127.0.0.1:8000..."
  sleep 0.5
done
echo "Backend API is ready."

# Start Next.js frontend on 0.0.0.0:${PORT}
cd /app/frontend
export PORT=${PORT}
export HOSTNAME=0.0.0.0
export INTERNAL_API_URL=http://127.0.0.1:8000
exec node server.js
