"""Read-only integrity check against the committed Git blob."""
from hashlib import sha256
from pathlib import Path
import subprocess

from services.git_helpers import git_env


def verify_config(repo, relative_path):
    root = Path(repo).resolve()
    target = (root / relative_path).resolve()
    if not target.is_relative_to(root) or target == root or ".git" in Path(relative_path).parts:
        raise ValueError("Invalid artifact path")
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"HEAD:{relative_path}"],
        capture_output=True, timeout=15, env=git_env(root),
    )
    if result.returncode:
        return {"status": "untracked" if target.is_file() else "missing"}
    expected = sha256(result.stdout).hexdigest()
    if not target.is_file():
        return {"status": "missing", "expected_sha256": expected}
    digest = sha256()
    size = 0
    with target.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    actual = digest.hexdigest()
    return {"status": "verified" if expected == actual else "mismatch",
            "sha256": actual, "expected_sha256": expected, "size_bytes": size}
