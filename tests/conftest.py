import os

import pytest

# Set environment variables before any imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

# Configure celery for eager execution in tests
try:
    from glyph.evaluation.tasks import celery_app
    celery_app.conf.update(task_always_eager=True)
except ImportError:
    pass

@pytest.fixture(autouse=True)
async def setup_database():
    try:
        from glyph.db.session import init_db
        await init_db()
    except ImportError:
        pass
