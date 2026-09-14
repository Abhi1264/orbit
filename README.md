# Orbit

Internal product analytics and experimentation for **Threadline**, a multi-platform fashion storefront. One place for KPIs, funnels, cohorts, A/B readouts, anomaly RCA, releases, launch SOPs, and a GenAI analyst.

## Stack

- **Web:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn/ui
- **API:** Python 3.12, FastAPI
- **Data:** PostgreSQL 16 (app state), ClickHouse 25.3 (events), Redis 7 (cache + jobs)
- **Jobs:** Dramatiq + APScheduler
- **AI:** OpenAI-compatible API (optional; demo mode works without a key)

## Run

Needs Docker, [uv](https://docs.astral.sh/uv/), and [pnpm](https://pnpm.io/).

```bash
cp .env.example .env
make up          # postgres, clickhouse, redis, api, worker, web
make seed        # demo data: 30k users, ~900k events
```

Open [http://localhost:3000](http://localhost:3000). Password for every demo account is `probelens`.

| Email | Role |
|---|---|
| `priya.pm@threadline.test` | PM |
| `arjun.analyst@threadline.test` | Analyst |
| `admin@threadline.test` | Admin |
| `viewer@threadline.test` | Viewer |

API docs (dev only): [http://localhost:8000/api/docs](http://localhost:8000/api/docs).

```bash
make seed-full   # 50k users, ~5M events
make down        # stop
make clean       # stop and drop volumes
```

## Local API / web

```bash
make dev-infra   # databases only
make migrate
make api         # :8000
make worker
make web         # :3000
```

Leave `LLM_API_KEY` empty for deterministic demo answers. Set it (and optionally `LLM_BASE_URL` / `LLM_MODEL`) to use a real model.

In production set `APP_ENV=production` and a real `SECRET_KEY`. Swagger is then disabled.

## Deploy (OCI Ampere, one VM)

Always Free shape: **VM.Standard.A1.Flex, 2 OCPU, 12 GB**, Ubuntu aarch64. Demo seed only — `make seed-full` will OOM.

1. Open ingress **22, 80, 443**. Nothing else.
2. Install Docker, add a 2 GB swap file (`fallocate` / `mkswap` / `swapon`).
3. Clone this repo on the VM (build there; images are multi-arch).

```bash
cp .env.example .env
# Always set SECRET_KEY=$(openssl rand -hex 32). The VM is public.
# With a DNS name: APP_ENV=production, SITE_ADDRESS=orbit.example.com, ACME_EMAIL=you@domain
# Public IP only: leave SITE_ADDRESS empty and APP_ENV=development (Secure cookies need HTTPS)
make prod
make prod-seed    # ~30k users; takes a while on 2 OCPU
```

Caddy listens on 80/443 and reverse-proxies the UI. Postgres, ClickHouse, Redis, and the API stay on the Docker network.

```bash
make prod-logs
make prod-down
```

## Tests

```bash
make test
```

Push and PR run lint, unit tests, then build the API/web images, seed `dev` data, run API integration tests, and Playwright against the compose stack. Locally: `make up && SEED_PROFILE=dev make seed`, then `make test` and `make e2e`.

## Layout

```
apps/web     Next.js UI (proxies /api → FastAPI)
apps/api     FastAPI, worker, seed  (Python package: probelens)
infra        Dockerfiles and DB init
docs         Experimentation notes
```
