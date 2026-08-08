"""Neon PostgreSQL database schema.

This module provides SQLAlchemy models for evaluation runs and trials,
optimized for Neon serverless PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class Run(Base):
    """Evaluation run record."""
    
    __tablename__ = "runs"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    suite_id: Mapped[str] = mapped_column(String, index=True)
    suite_version: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    started_at: Mapped[datetime] = mapped_column(index=True)
    finished_at: Mapped[datetime | None]
    total: Mapped[int]
    cases: Mapped[int]
    passed: Mapped[int]
    failed: Mapped[int]
    errors: Mapped[int]
    timeouts: Mapped[int]
    pass_rate: Mapped[float]
    average_score: Mapped[float]
    artifact_path: Mapped[str | None]
    summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    task_id: Mapped[str | None]
    
    __table_args__ = (
        Index("idx_runs_suite_started", "suite_id", "started_at"),
        Index("idx_runs_pass_rate", "pass_rate"),
        Index("idx_runs_status", "status"),
    )


class Trial(Base):
    """Individual trial record within a run."""
    
    __tablename__ = "trials"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    repetition_index: Mapped[int]
    suite: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, index=True)
    score: Mapped[float]
    duration_ms: Mapped[int]
    started_at: Mapped[datetime]
    record: Mapped[dict[str, Any]] = mapped_column(JSON)
    
    __table_args__ = (
        Index("idx_trials_run_status", "run_id", "status"),
        Index("idx_trials_case_status", "case_id", "status"),
    )
