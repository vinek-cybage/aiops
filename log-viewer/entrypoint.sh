#!/bin/sh
set -e

# The API imports llm.py from the worker directory — expose it via PYTHONPATH
export PYTHONPATH="/app/worker:${PYTHONPATH}"

# Start the background log-processing worker
cd /app/worker
python -u service.py &
WORKER_PID=$!

# Start the FastAPI server (serves API + React static files)
cd /app/api
uvicorn main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait for both; exit when either dies
wait $WORKER_PID
wait $API_PID
