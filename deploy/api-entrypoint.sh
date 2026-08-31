#!/bin/sh
set -eu

/app/.venv/bin/alembic -c /app/apps/api/alembic.ini upgrade head
exec /app/.venv/bin/uvicorn travel_agent.main:app --host 0.0.0.0 --port 8000 --workers 1
