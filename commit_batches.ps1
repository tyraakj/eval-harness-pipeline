git add src/glyph/specialized_workers/artifact.py src/glyph/specialized_workers/base.py src/glyph/specialized_workers/infra/celery_config.py src/glyph/specialized_workers/evaluation/tasks.py
git commit -m "fix(workers): Fix artifact hashing and celery task configurations"

git add src/glyph/specialized_workers/orchestrator.py src/glyph/specialized_workers/aggregator.py src/glyph/specialized_workers/evaluation/runner.py src/glyph/specialized_workers/worker_dataset_service.py
git commit -m "fix(workers): Resolve orchestrator enum usage and trial record metric extraction"

git add src/glyph/db/orm_models.py src/glyph/services/run_service.py
git commit -m "fix(db): Update ORM models and run service layers for evaluation fixes"

git add tests/test_specialized_workers.py tests/test_ai_decision_gates.py tests/test_zero_token_replay.py
git commit -m "test: Fix specialized worker tests, zero token generation schema, and remove hardcoded success outputs"

git add .kiro/specs/glyph-full-repair/spec.md
git commit -m "docs(spec): Update spec.md for Part 3 completion"
