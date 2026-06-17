from pathlib import Path

from django.conf import settings


def _log_path() -> Path:
    return Path(settings.OXIDIZED_LOG_PATH)


def tail_oxidized_log(max_lines: int = 500, search: str = "") -> dict:
    path = _log_path()
    if not path.exists():
        return {
            "available": False,
            "path": str(path),
            "lines": [],
            "returned": 0,
            "error": "Файл лога не найден — проверьте volume oxidized-data",
        }

    max_lines = max(1, min(max_lines, 2000))
    chunk_size = max(65536, max_lines * 256)

    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - chunk_size))
            raw = handle.read()
    except OSError as exc:
        return {
            "available": False,
            "path": str(path),
            "lines": [],
            "returned": 0,
            "error": str(exc),
        }

    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()[-max_lines:]

    query = search.strip().lower()
    if query:
        tokens = [t for t in query.split() if t]
        lines = [
            line
            for line in lines
            if all(token in line.lower() for token in tokens)
        ]

    return {
        "available": True,
        "path": str(path),
        "lines": lines,
        "returned": len(lines),
        "truncated": size > chunk_size,
        "error": None,
    }
