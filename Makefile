.PHONY: install migrate dev-api dev-web test lint build check docs-check

install:
	uv sync --project apps/api --dev
	npm ci

migrate:
	uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head

dev-api:
	uv run --project apps/api uvicorn travel_agent.main:app --reload --host 0.0.0.0 --port 8000

dev-web:
	npm run web:dev

test:
	uv run --project apps/api pytest
	npm run web:test

lint:
	uv run --project apps/api ruff check apps/api/src apps/api/tests
	uv run --project apps/api ruff format --check apps/api/src apps/api/tests
	uv run --project apps/api mypy
	cd apps/api && .venv/bin/lint-imports
	npm run web:lint

build:
	uv build --project apps/api
	npm run web:build

docs-check:
	scripts/validate_design_docs.sh

check: docs-check lint test build
