.PHONY: help up down logs seed seed-full migrate api web worker test test-api test-web e2e lint typecheck format openapi clean

help:
	@echo "make up          start postgres, clickhouse, redis, api, worker, web"
	@echo "make seed        load the demo dataset (fast, deterministic)"
	@echo "make seed-full   load the full dataset (50k users, ~5M events)"
	@echo "make dev-infra   start only databases (for running api/web locally)"
	@echo "make api         run FastAPI locally with reload"
	@echo "make worker      run the background worker locally"
	@echo "make web         run Next.js dev server"
	@echo "make test        run backend + frontend unit tests"
	@echo "make e2e         run Playwright end-to-end tests against a running stack"
	@echo "make lint        ruff + eslint"
	@echo "make typecheck   mypy-free strict tsc + pyright-free ruff checks"
	@echo "make openapi     regenerate TypeScript API types from the FastAPI schema"

up:
	docker compose up -d --build

down:
	docker compose down

clean:
	docker compose down -v

logs:
	docker compose logs -f api worker web

dev-infra:
	docker compose up -d postgres clickhouse redis

seed:
	docker compose run --rm seed

seed-full:
	SEED_PROFILE=full docker compose run --rm seed

migrate:
	cd apps/api && uv run alembic upgrade head

api:
	cd apps/api && uv run uvicorn probelens.main:app --reload --port 8000

worker:
	cd apps/api && uv run python -m probelens.worker

web:
	cd apps/web && pnpm dev

test: test-api test-web

test-api:
	cd apps/api && uv run pytest -q

test-web:
	cd apps/web && pnpm test

e2e:
	cd tests/e2e && pnpm test

lint:
	cd apps/api && uv run ruff check . && uv run ruff format --check .
	cd apps/web && pnpm lint

format:
	cd apps/api && uv run ruff format . && uv run ruff check --fix .
	cd apps/web && pnpm format

typecheck:
	cd apps/web && pnpm typecheck

openapi:
	cd apps/api && uv run python -m probelens.openapi > ../web/openapi.json
	cd apps/web && pnpm openapi
