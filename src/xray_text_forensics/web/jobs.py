"""Bounded in-process background jobs for expensive web analyses."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock, Semaphore
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class JobRecord(BaseModel):
    job_id: str
    kind: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobCapacityError(RuntimeError):
    pass


class JobManager:
    """Small bounded executor.

    M12 intentionally keeps jobs process-local. A durable/distributed queue belongs to
    the later cloud deployment layer.
    """

    def __init__(self, *, max_workers: int, max_pending_jobs: int) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="xray-job",
        )
        self._capacity = Semaphore(max_pending_jobs)
        self._records: dict[str, JobRecord] = {}
        self._futures: dict[str, Future[None]] = {}
        self._lock = Lock()
        self._closed = False

    def submit(
        self,
        *,
        kind: str,
        task: Callable[[], dict[str, Any]],
        metadata: dict[str, Any] | None = None,
    ) -> JobRecord:
        if self._closed:
            raise RuntimeError("Job manager is closed")
        if not self._capacity.acquire(blocking=False):
            raise JobCapacityError("Background job capacity is full")

        record = JobRecord(
            job_id=f"job_{uuid4().hex}",
            kind=kind,
            status=JobStatus.PENDING,
            created_at=datetime.now(UTC),
            metadata=metadata or {},
        )
        with self._lock:
            self._records[record.job_id] = record

        try:
            future = self._executor.submit(self._run, record.job_id, task)
        except Exception:
            self._capacity.release()
            with self._lock:
                self._records.pop(record.job_id, None)
            raise

        with self._lock:
            self._futures[record.job_id] = future
        return record.model_copy(deep=True)

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._records.get(job_id)
            return record.model_copy(deep=True) if record else None

    def shutdown(self) -> None:
        self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _run(
        self,
        job_id: str,
        task: Callable[[], dict[str, Any]],
    ) -> None:
        self._update(
            job_id,
            status=JobStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        try:
            result = task()
        except Exception as exc:
            self._update(
                job_id,
                status=JobStatus.FAILED,
                finished_at=datetime.now(UTC),
                error=f"{type(exc).__name__}: {exc}",
            )
        else:
            self._update(
                job_id,
                status=JobStatus.SUCCEEDED,
                finished_at=datetime.now(UTC),
                result=result,
            )
        finally:
            self._capacity.release()

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            current = self._records[job_id]
            self._records[job_id] = current.model_copy(update=changes)
