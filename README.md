# Orbit

Internal product analytics and experimentation for **Threadline**, a multi-platform fashion storefront. KPIs, funnels, cohorts, A/B readouts, anomaly root-cause analysis, releases, launch SOPs and an AI analyst, all on one event store.

- **Web:** Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn/ui
- **API:** Python 3.12, FastAPI, Dramatiq + APScheduler for jobs
- **Data:** PostgreSQL 16 (app state), ClickHouse 25.3 (events), Redis 7 (cache, queue)
- **Optional:** any OpenAI-compatible LLM, Amplitude, Metabase

## Quick start

Needs Docker, [uv](https://docs.astral.sh/uv/) and [pnpm](https://pnpm.io/).

```bash
cp .env.example .env
make up      # postgres, clickhouse, redis, api, worker, web
make seed    # demo data: 30k users, ~900k events
```

Open [http://localhost:3000](http://localhost:3000). Every demo account's password is `probelens`.

| Email | Role |
|---|---|
| `priya.pm@threadline.test` | PM |
| `arjun.analyst@threadline.test` | Analyst |
| `admin@threadline.test` | Admin |
| `viewer@threadline.test` | Viewer |

API docs are at [http://localhost:8000/api/docs](http://localhost:8000/api/docs) outside production. `make seed-full` loads 50k users and ~5M events. `make down` stops the stack and `make clean` also drops its volumes.

## Local development

```bash
make dev-infra   # databases only
make migrate
make api         # :8000, reloads on change
make worker
make web         # :3000
```

The AI analyst gives deterministic answers until `LLM_API_KEY` is set; `LLM_BASE_URL` and `LLM_MODEL` point it at any OpenAI-compatible endpoint. After changing API schemas, `make openapi` regenerates the web client's types.

## Experiments

- **Lifecycle.** Draft → running → completed or stopped. Decision rules (minimum effect, sample and duration) are set before the start; once running, the design is frozen and the API rejects changes to it.
- **Assignment.** Seeded experiments take each user's variant from their first exposure event. Experiments created in the UI assign users retroactively by hashing `"{key}:{user_id}"` into 10,000 buckets, so they can be read against historical data. The Python and ClickHouse implementations are tested against each other.
- **Statistics.** The user is the unit of analysis. Ratio metrics use per-user sums with delta-method variance, and variants are compared with two-sided z-tests and 95% intervals. A sample ratio mismatch check (chi-square, p < 0.001) runs first, power comes from the control's variance, and segment cuts are labelled exploratory.
- **Recommendation.** `experiments/decision.py` turns a readout into ship, iterate, stop or continue, and lists every check it ran. A guardrail that is not significantly worse but whose interval still allows a 10% regression counts as inconclusive, not safe. Recording a decision adds it to the decision log by default, and every experiment has a Markdown memo built from the same readout.

## Amplitude (optional)

ClickHouse stays Orbit's event store; Amplitude can receive a copy of every storefront event. The storefront is the seeded simulator, so events go out server-side through Amplitude's Python SDK and the key never reaches a browser.

Set `AMPLITUDE_API_KEY` in `.env` (plus `AMPLITUDE_SERVER_ZONE=EU` for EU projects), run `make up`, then send events either way:

- `make seed` sends them as it loads. To seed without sending: `docker compose run --rm seed python -m probelens.seed --no-amplitude`.
- `make amplitude-backfill` sends what ClickHouse already holds. `ARGS='--days 7'` limits the range; `ARGS='--dry-run'` prints counts and a sample event without sending.

The demo seed is about 900k events, so check your Amplitude plan first. How sending behaves:

- ClickHouse commits each batch first, and only committed events go to Amplitude.
- A rejected key means nothing is sent. If Amplitude stops responding or rejects two batches in a row, sending stops. Either way the seed finishes with all data in ClickHouse.
- Every event has a deterministic `insert_id`, so Amplitude drops re-sent events from a backfill or reseed. Future-dated events wait for a later backfill.
- Event names and properties come from `apps/api/probelens/tracking/taxonomy.py`, and `tests/test_tracking.py` checks the simulator against it. No names, emails, addresses or credentials are sent.

Settings → Integrations shows whether Amplitude accepted the key and what the last export sent, delivered or failed. Development builds add a debugger listing the latest events with Amplitude's response to each.

## Metabase (optional)

Stakeholder dashboards on Orbit's own metric definitions. In `.env`:

```bash
METABASE_URL=http://localhost:3001
METABASE_SITE_URL=http://localhost:3001
METABASE_ADMIN_EMAIL=you@example.com
METABASE_ADMIN_PASSWORD=
MB_ENCRYPTION_SECRET_KEY=   # openssl rand -hex 32, before the first run
```

`make bi` starts Metabase on port 3001 and provisions it: read-only `orbit_bi` logins with a fresh password each run, the BI views, and six dashboards (Product overview, Conversion funnel, Retention, Returns, Acquisition, Experiments). Every card is run before it reports success. Run `make up` afterwards so the API sees `METABASE_URL`; `make bi-setup` re-provisions in place and keeps dashboard URLs.

- Dashboard numbers equal Orbit's for the same dates and filters; `tests/test_bi.py` compares them with Orbit's query engine.
- `orbit_bi` reads ClickHouse under a small `bi_analytics` profile (2 threads, 600 MB, 60 s per query) so dashboards can't starve Orbit, and sees only the `bi` schema in Postgres.
- Experiment readouts are snapshots written by the seed and by the worker, at boot and daily at 00:30.
- Orbit doesn't depend on Metabase; when it is down, Settings → Integrations says so.

## Deploy (OCI Ampere, one VM)

Always Free shape: **VM.Standard.A1.Flex, 2 OCPU, 12 GB**, Ubuntu aarch64. Use the demo seed; `make seed-full` runs out of memory.

1. Open ingress **22, 80, 443** and nothing else.
2. Install Docker and add a 2 GB swap file (`fallocate`, `mkswap`, `swapon`).
3. Clone this repo on the VM and build there; the images are multi-arch.

```bash
cp .env.example .env
# Always set SECRET_KEY=$(openssl rand -hex 32). The VM is public.
# With a DNS name: APP_ENV=production, SITE_ADDRESS=orbit.example.com, ACME_EMAIL=you@domain
# Public IP only: leave SITE_ADDRESS empty and APP_ENV=development (Secure cookies need HTTPS)
make prod
make prod-seed    # ~30k users; takes a while on 2 OCPU
```

Caddy serves the UI on 80/443. Postgres, ClickHouse, Redis and the API stay on the Docker network. `make prod-logs` tails the services and `make prod-down` stops them.

`make prod-bi` adds Metabase (about 1.3 GB of memory), bound to `127.0.0.1:3001`. Reach it with `ssh -L 3001:localhost:3001 <vm>` and `METABASE_SITE_URL=http://localhost:3001`.

## Tests

```bash
make lint
make test   # API and web unit tests
make e2e    # Playwright, against a running stack
```

API integration tests run when the stack is reachable and skip otherwise; `ORBIT_INTEGRATION=1` makes them fail instead. To run everything locally: `make up && SEED_PROFILE=dev make seed`, then `make test` and `make e2e`. CI does the same for pull requests and pushes to `main`.

## Layout

```
apps/web     Next.js UI (proxies /api to FastAPI)
apps/api     FastAPI app, worker and seed (Python package: probelens)
infra        Dockerfiles, Caddy, database config and init
tests/e2e    Playwright smoke tests
```
