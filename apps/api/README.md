# Travel Planner API

FastAPI modular monolith for the self-hosted travel planner.

Implemented vertical slices:

- Slice 0: composition root, health checks, SQLite WAL and Unit of Work;
- Slice 1: secure setup, Argon2id login, encrypted identity/family fields, sessions,
  CSRF, family ownership and append-only access audit events.

```bash
uv sync --dev
uv run alembic upgrade head
uv run uvicorn travel_agent.main:app --reload
```

The application reads the existing root `.env` when started from the repository root. Secrets stay server-side and must never use a `VITE_` prefix.
