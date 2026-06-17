from services.oxidized_logging import engine_title, is_python_engine, oxidized_log_path


def tail_oxidized_log(max_lines: int = 500, search: str = "") -> dict:
    path = oxidized_log_path()
    engine = "python" if is_python_engine() else "external"

    if not path.exists():
        hint = (
            "запустите scanner и дождитесь первого цикла worker"
            if is_python_engine()
            else "запустите контейнер oxidized (profile external)"
        )
        return {
            "available": False,
            "path": str(path),
            "engine": engine,
            "engine_title": engine_title(),
            "lines": [],
            "returned": 0,
            "error": f"Файл лога не найден ({engine_title()}): {path}. {hint}",
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
            "engine": engine,
            "engine_title": engine_title(),
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
        "engine": engine,
        "engine_title": engine_title(),
        "lines": lines,
        "returned": len(lines),
        "truncated": size > chunk_size,
        "error": None,
    }
