from __future__ import annotations

import asyncio
import os
from pathlib import Path

from pydantic import BaseModel


class JsonlArtifactWriter:
    def __init__(self, path: Path, *, overwrite: bool = False) -> None:
        self.path = path
        self.overwrite = overwrite
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._initialize_sync)

    async def append(
        self, record: BaseModel, *, max_record_bytes: int | None = None
    ) -> None:
        payload = record.model_dump_json(exclude_none=True) + "\n"
        payload_bytes = len(payload.encode("utf-8"))
        if max_record_bytes is not None and payload_bytes > max_record_bytes:
            raise ValueError(
                f"Artifact record exceeds {max_record_bytes} bytes ({payload_bytes})"
            )
        async with self._lock:
            await asyncio.to_thread(self._append_sync, payload)

    def _initialize_sync(self) -> None:
        mode = "w" if self.overwrite else "x"
        with self.path.open(mode, encoding="utf-8", newline="\n"):
            pass

    def _append_sync(self, payload: str) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
