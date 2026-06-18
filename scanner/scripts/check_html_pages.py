from pathlib import Path

from bs4 import BeautifulSoup

soup = BeautifulSoup(Path("static/index.html").read_text(encoding="utf-8"), "html.parser")
for pid in [
    "page-dashboard",
    "page-inventory",
    "page-scan",
    "page-oxidized",
    "page-oxidized-ui",
    "page-settings",
    "page-audit",
    "page-users",
]:
    el = soup.find(id=pid)
    if not el:
        print(pid, "MISSING")
        continue
    parent_pages = []
    p = el.parent
    while p and p.name:
        parent_id = p.get("id", "")
        if parent_id.startswith("page-"):
            parent_pages.append(parent_id)
        p = p.parent
    print(f"{pid}: nested under {parent_pages or 'container-fluid (ok)'}")
