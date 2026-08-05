# Web API

## Web API & Background Workers

The harness includes an optional web layer for running evaluations as a service.

### Start the API server

```powershell
uv sync --extra web
glyph serve --host 127.0.0.1 --port 8000
```

The FastAPI server provides REST endpoints under `/api/`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/runs` | GET | List evaluation runs (filterable by suite) |
| `/api/runs/{run_id}` | GET | Get run details |
| `/api/runs` | POST | Trigger a new evaluation run |
| `/api/graders` | GET | List available grader types |
| `/api/datasets` | GET | List available datasets |

The server uses Neon PostgreSQL for persistent storage. Set `DATABASE_URL` to your connection string:

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://user:pass@your-neon-host/dbname"
glyph serve
```

### Start a Celery worker

```powershell
glyph worker --concurrency 2 --loglevel info
```

Requires a running Redis instance as the task broker.

### Scaffold a new project

```powershell
glyph init my-evaluation
```

Creates a project directory with `datasets/`, `examples/`, `prompts/`, `artifacts/`, a sample dataset, and `.gitignore`.