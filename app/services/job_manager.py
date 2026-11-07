"""
Bounded background-work registry.

Limits (all configurable): concurrent crawls, concurrent batch jobs, and active jobs per user.
Tasks are held by strong reference (an un-referenced `asyncio.create_task` can be garbage
collected mid-run) and are cancelled on application shutdown.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Coroutine, Optional

from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger(__name__)


class JobLimitExceeded(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def to_http(self) -> HTTPException:
        return HTTPException(
            status_code=429,
            detail=self.message,
            headers={"Retry-After": "30"},
        )


class JobManager:
    def __init__(self):
        self._active: dict[str, int] = {}
        self._per_user: dict[str, int] = {}
        self._tasks: set[asyncio.Task] = set()

    # ---- limits -----------------------------------------------------------
    @staticmethod
    def _limit(kind: str) -> int:
        return {
            "crawl": settings.MAX_CONCURRENT_CRAWLS,
            "batch": settings.MAX_CONCURRENT_BATCH_JOBS,
        }.get(kind, 1)

    def active(self, kind: Optional[str] = None) -> int:
        if kind is None:
            return sum(self._active.values())
        return self._active.get(kind, 0)

    def ensure_capacity(self, kind: str, user_id: str) -> None:
        if self._active.get(kind, 0) >= self._limit(kind):
            raise JobLimitExceeded(
                f"Too many {kind} jobs are running (limit {self._limit(kind)}). Try again shortly."
            )
        if self._per_user.get(user_id, 0) >= settings.MAX_ACTIVE_JOBS_PER_USER:
            raise JobLimitExceeded(
                f"You already have {settings.MAX_ACTIVE_JOBS_PER_USER} active jobs. Wait for one to finish."
            )

    def _acquire(self, kind: str, user_id: str) -> None:
        self.ensure_capacity(kind, user_id)
        self._active[kind] = self._active.get(kind, 0) + 1
        self._per_user[user_id] = self._per_user.get(user_id, 0) + 1

    def _release(self, kind: str, user_id: str) -> None:
        self._active[kind] = max(0, self._active.get(kind, 0) - 1)
        self._per_user[user_id] = max(0, self._per_user.get(user_id, 0) - 1)
        if not self._per_user[user_id]:
            self._per_user.pop(user_id, None)

    # ---- running work -----------------------------------------------------
    def spawn(self, kind: str, user_id: str, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Start a background job, enforcing limits. Closes `coro` if the limit rejects it."""
        try:
            self._acquire(kind, user_id)
        except JobLimitExceeded:
            coro.close()
            raise

        async def runner():
            try:
                return await coro
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Background %s job failed", kind)

        task = asyncio.create_task(runner())
        self._tasks.add(task)

        def _finished(t: asyncio.Task) -> None:
            # Runs even when the task was cancelled before its first step, so slots never leak.
            self._tasks.discard(t)
            self._release(kind, user_id)
            coro.close()  # no-op if already finished; silences "never awaited" if cancelled early

        task.add_done_callback(_finished)
        return task

    @asynccontextmanager
    async def slot(self, kind: str, user_id: str):
        """Occupy a slot for the duration of a foreground job."""
        self._acquire(kind, user_id)
        try:
            yield
        finally:
            self._release(kind, user_id)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


job_manager = JobManager()
