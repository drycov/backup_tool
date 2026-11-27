"""Nonblocking device locks shared by native backup and restore paths."""
from contextlib import contextmanager
from hashlib import sha256
from threading import Lock

from django.db import connection

_guard = Lock()
_locks = {}


class BackupBusy(RuntimeError):
    pass


@contextmanager
def backup_lock(name):
    with _guard:
        local = _locks.setdefault(name, Lock())
    if not local.acquire(blocking=False):
        raise BackupBusy("Device backup or restore already running")
    acquired = False
    key = int.from_bytes(sha256(("backup-tools:" + name).encode()).digest()[:8], "big", signed=True)
    try:
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
                acquired = bool(cursor.fetchone()[0])
            if not acquired:
                raise BackupBusy("Device backup or restore already running")
        yield
    finally:
        try:
            if acquired:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
        finally:
            local.release()
