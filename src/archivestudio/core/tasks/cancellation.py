"""Cooperative cancellation for long-running task services."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event


class TaskCancelled(Exception):
    """Raised when the user requests that a task stop between batches."""

    def __init__(self, message: str = "Task cancelled by user") -> None:
        super().__init__(message)


@dataclass
class CancellationToken:
    """Thread-safe flag shared between the UI worker and core task code."""

    _event: Event = field(default_factory=Event)

    def cancel(self) -> None:
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise TaskCancelled()
