"""Build-scoped runtime controls shared by artifact workers."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from slideflow.utilities.logging import get_logger

logger = get_logger(__name__)


class RuntimeConfig(BaseModel):
    """Runtime controls with identical semantics across artifact types."""

    model_config = ConfigDict(extra="forbid")

    query_threads: StrictInt = Field(
        default=10,
        ge=1,
        description="Process-wide maximum number of active warehouse queries.",
    )


class QueryConcurrencyController:
    """Bound active warehouse executions within one build invocation."""

    def __init__(self, limit: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("query_threads must be a positive integer")
        self.limit = limit
        self._semaphore = threading.BoundedSemaphore(limit)

    @contextmanager
    def permit(self, backend: str) -> Iterator[None]:
        wait_started = time.monotonic()
        self._semaphore.acquire()
        wait_duration = time.monotonic() - wait_started
        if wait_duration >= 0.01:
            logger.info(
                "Warehouse query permit acquired: backend=%s limit=%d wait_seconds=%.3f",
                backend,
                self.limit,
                wait_duration,
            )
        try:
            yield
        finally:
            self._semaphore.release()


@dataclass(frozen=True)
class BuildRuntimeContext:
    """Resolved build controls shared by every artifact and worker."""

    query_controller: QueryConcurrencyController

    @classmethod
    def from_query_threads(cls, query_threads: int) -> "BuildRuntimeContext":
        return cls(query_controller=QueryConcurrencyController(query_threads))

    @property
    def query_threads(self) -> int:
        return self.query_controller.limit
