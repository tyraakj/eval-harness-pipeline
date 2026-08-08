"""Tests for FastAPI server module."""

from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient

    from glyph.api.main import app
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available. Install with: uv sync --extra web")
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint."""
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available. Install with: uv sync --extra web")
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_list_runs(client):
    """Test list runs endpoint."""
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available. Install with: uv sync --extra web")
    response = client.get("/api/runs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_list_datasets(client):
    """Test list datasets endpoint."""
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available. Install with: uv sync --extra web")
    response = client.get("/api/datasets")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "datasets" in data


def test_list_graders(client):
    """Test list graders endpoint."""
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available. Install with: uv sync --extra web")
    response = client.get("/api/graders")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    # Should have at least some graders
    assert len(data) > 0


def test_trigger_run(client):
    """Test trigger run endpoint."""
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available. Install with: uv sync --extra web")
    request_data = {
        "config": {
            "suite_id": "test",
            "total_cases": 10,
            "repetitions": 1,
        },
        "run_id": "test-run-123",
    }
    response = client.post("/api/runs", json=request_data)
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert "status" in data


def test_get_run_detail_not_found(client):
    """Test get run detail with non-existent run."""
    if not FASTAPI_AVAILABLE:
        pytest.skip("FastAPI not available. Install with: uv sync --extra web")
    response = client.get("/api/runs/nonexistent")
    assert response.status_code == 404
