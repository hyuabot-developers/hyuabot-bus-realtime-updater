# hyuabot-bus-realtime-updater

A recurring job that fetches real-time bus arrival information and keeps the HYUabot database up to date. Runs every minute as a Kubernetes CronJob.

## Overview

On each run the job:

1. Deletes all existing records from `bus_realtime` (stale data).
2. Calls the public bus API for each tracked stop.
3. Inserts fresh arrival predictions into `bus_realtime`.

## Architecture

```
src/
├── main.py           # Entry point; deletes stale data, fetches and inserts arrivals
├── models.py         # SQLAlchemy ORM models (BusRealtime)
└── utils/
    └── database.py   # PostgreSQL engine factory
```

## Requirements

- Python ≥ 3.12
- PostgreSQL

## Environment Variables

| Variable            | Description              |
|---------------------|--------------------------|
| `POSTGRES_ID`       | PostgreSQL username      |
| `POSTGRES_PASSWORD` | PostgreSQL password      |
| `POSTGRES_HOST`     | PostgreSQL host          |
| `POSTGRES_PORT`     | PostgreSQL port          |
| `POSTGRES_DB`       | PostgreSQL database name |

## Running Locally

```bash
pip install -e .

export POSTGRES_ID=postgres
export POSTGRES_PASSWORD=password
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=hyuabot

cd src && python main.py
```

## Docker

The container exits after a single run — schedule it externally (Kubernetes CronJob every minute).

```bash
docker build -t hyuabot-bus-realtime-updater .

docker run --rm \
  -e POSTGRES_ID=postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_HOST=host.docker.internal \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_DB=hyuabot \
  hyuabot-bus-realtime-updater
```

## Development

```bash
pip install -e .[lint]       # flake8
pip install -e .[typecheck]  # mypy
pip install -e .[test]       # pytest
```

```bash
python -m flake8 src/ tests/
python -m mypy src/ tests/
python -m pytest -v
```

Tests run against a PostgreSQL instance at `localhost:25432`.

## CI/CD

| Workflow | Trigger | Jobs |
|---|---|---|
| `code-check.yml` | Push to any branch except `main` | lint, typecheck, test |
| `deploy.yml` | PR merged to `main` (or manual dispatch) | Docker build → push to `localhost:5000` |

CI runners: self-hosted X64 Linux (code checks) · ARM64 Linux (Docker build).

## License

GPLv3
