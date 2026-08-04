# Local observability

This stack uses only self-hosted open-source components: OpenTelemetry Collector, Prometheus, Grafana Tempo, and Grafana OSS. The software has no usage fee. Local compute, disk, networking, and any infrastructure used to host it are not free by definition.

Docker Desktop is free for personal use, education, non-commercial open source, and qualifying small businesses under Docker's current terms. Larger organizations should verify Docker Desktop licensing or use a compatible alternative such as Podman Desktop. The Compose file itself is not tied to a paid service.

## Start

Install Docker Desktop or a compatible Compose runtime, then create the ignored local environment file and set a real password:

```powershell
Copy-Item observability/.env.example observability/.env
notepad observability/.env
docker compose --env-file observability/.env -f observability/docker-compose.yml up -d
```

All host ports bind to `127.0.0.1`:

- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`
- Tempo API: `http://localhost:3200`
- OTLP/gRPC: `localhost:4317`
- OTLP/HTTP: `localhost:4318`

The `LangGraph Evaluation RED` dashboard and Prometheus/Tempo datasources are provisioned automatically.

## Send evaluation telemetry

Install the OTLP extra and enable the CLI bootstrap:

```powershell
uv sync --extra otel
$env:LANGGRAPH_EVAL_OTEL_ENABLED = "true"
$env:OTEL_SERVICE_NAME = "personal-evaluation-harness"
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4317"
$env:OTEL_RESOURCE_ENVIRONMENT = "local"
uv run glyph run --factory examples.simple_graph:create_evaluation --dataset datasets/example.jsonl --output artifacts/observed-run.jsonl
```

The CLI shuts down both providers in a `finally` block, flushing metrics and spans before the short-lived process exits. When `LANGGRAPH_EVAL_OTEL_ENABLED` is absent or false, no SDK providers or network exporters are created.

Verify ingestion in Prometheus with `evaluation_trials_total`, then open the Grafana dashboard. Traces are available through the provisioned Tempo datasource. Prometheus alert rules cover sustained system error ratio, target p95 latency, export failures, and collector availability. Tune the example 5% and 30-second thresholds after establishing a suite-specific baseline.

## Stop and delete data

Stop containers while preserving local metrics, traces, and dashboards:

```powershell
docker compose --env-file observability/.env -f observability/docker-compose.yml down
```

Delete the named volumes as well:

```powershell
docker compose --env-file observability/.env -f observability/docker-compose.yml down --volumes
```

This local stack has no authentication beyond the Grafana login and no TLS between containers. Keep the localhost bindings for personal use. Add a reverse proxy, TLS, authentication, backups, retention policy, and access controls before exposing it to another machine.
