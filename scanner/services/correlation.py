"""Correlation ID для трассировки scan/backup job в логах."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value or "")


@contextmanager
def correlation_context(correlation_id: str | None = None):
    cid = correlation_id or new_correlation_id()
    token = _correlation_id.set(cid)
    try:
        yield cid
    finally:
        _correlation_id.reset(token)
