#!/bin/sh
set -eu

uv run --project /app/apps/api --frozen alembic -c /app/apps/api/alembic.ini upgrade head
exec uv run --project /app/apps/api --frozen uvicorn travel_agent.main:app --host 0.0.0.0 --port 8000 --workers 1
