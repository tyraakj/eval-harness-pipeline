from __future__ import annotations

from pathlib import Path

import pytest

from langgraph_eval.utils.datasets import load_jsonl


def test_dataset_rejects_duplicate_ids(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    line = '{"id":"same","input":{},"expected":{}}\n'
    path.write_text(line + line, encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate case ID"):
        load_jsonl(path)
