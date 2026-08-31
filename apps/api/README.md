# Travel Planner API

FastAPI modular monolith for the self-hosted travel planner.

```bash
uv sync --dev
uv run alembic upgrade head
uv run uvicorn travel_agent.main:app --reload
```

The application reads the existing root `.env` when started from the repository root. Secrets stay server-side and must never use a `VITE_` prefix.
