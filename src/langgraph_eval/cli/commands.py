"""CQRS command handlers for write operations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


class TriggerRunCommand:
    """Command to trigger a new evaluation run."""
    
    def __init__(self, config: dict[str, Any], run_id: str | None = None) -> None:
        self.config = config
        self.run_id = run_id or f"run-{uuid4()}"
    
    async def execute(self) -> dict[str, Any]:
        """Execute the command and return job info."""
        return {
            "job_id": self.run_id,
            "status": "queued",
            "config": self.config,
        }


class CreateDatasetCommand:
    """Command to create or replace a dataset."""
    
    def __init__(self, name: str, cases: list[dict[str, Any]]) -> None:
        self.name = name
        self.cases = cases
    
    async def execute(self) -> dict[str, Any]:
        """Execute the command to create dataset."""
        import json
        
        datasets_dir = Path("datasets")
        datasets_dir.mkdir(exist_ok=True)
        
        dataset_path = datasets_dir / f"{self.name}.jsonl"
        with open(dataset_path, "w") as f:
            for case in self.cases:
                f.write(json.dumps(case) + "\n")
        
        return {
            "name": self.name,
            "path": str(dataset_path),
            "case_count": len(self.cases),
            "created_at": datetime.now(UTC).isoformat(),
        }
