#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Load .env from the project root
if [ -f "../.env" ]; then
    set -a
    source "../.env"
    set +a
fi

export DATABASE_URL=postgresql://aiops:aiops@localhost:3111/aiops
export FRONTEND_DIR=../web

exec .venv/Scripts/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
