"""Add SSH port column to router.db lines that only have name:ip:model:group."""
import os
from pathlib import Path

port = int(os.environ.get("ROUTEROS_SSH_PORT", "44333"))
p = Path(__file__).resolve().parents[1] / "oxidized" / "router.db"
lines_out: list[str] = []
updated = 0
for line in p.read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if not s or s.startswith("#"):
        lines_out.append(line)
        continue
    if len(s.split(":")) == 4:
        lines_out.append(f"{s}:{port}")
        updated += 1
    else:
        lines_out.append(line)
p.write_text("\n".join(lines_out) + ("\n" if lines_out else ""), encoding="utf-8")
print(f"Patched {updated} lines with port {port}")
