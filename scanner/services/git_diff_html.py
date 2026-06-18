from __future__ import annotations

import html
from typing import Any


def _line_class(line: str) -> str:
    if line.startswith(("+++ ", "--- ")):
        return "diff-file"
    if line.startswith("@@"):
        return "diff-hunk"
    if line.startswith("+"):
        return "diff-add"
    if line.startswith("-"):
        return "diff-del"
    if line.startswith(("diff --git", "index ", "new file mode", "deleted file mode")):
        return "diff-meta"
    if line.startswith(("commit ", "Author:", "Date:", "    ")) and not line.startswith("    update "):
        return "diff-header"
    return "diff-ctx"


def render_side_by_side_html(
    old_text: str,
    new_text: str,
    *,
    title: str = "",
) -> str:
    import difflib

    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    table = difflib.HtmlDiff(wrapcolumn=72).make_table(
        old_lines,
        new_lines,
        fromdesc="Было",
        todesc="Стало",
        context=True,
        numlines=3,
    )
    page_title = html.escape(title or "Side-by-side diff")
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{page_title}</title>
  <style>
    body {{ margin: 0; background: #0d1117; color: #c9d1d9; font: 13px/1.45 Consolas, monospace; }}
    table.diff {{ width: 100%; border-collapse: collapse; }}
    .diff_header {{ background: #161b22; color: #8b949e; }}
    .diff_next {{ background: #21262d; }}
    .diff_add {{ background: rgba(46, 160, 67, 0.15); }}
    .diff_chg {{ background: rgba(210, 168, 255, 0.12); }}
    .diff_sub {{ background: rgba(248, 81, 73, 0.15); }}
    td {{ vertical-align: top; white-space: pre-wrap; word-break: break-word; }}
  </style>
</head>
<body>{table}</body>
</html>"""


def render_git_diff_html(
    patch: str,
    *,
    title: str = "",
    stat: list[Any] | None = None,
) -> str:
    """Render unified git patch as a standalone HTML page (Oxidized-style)."""
    lines_html: list[str] = []
    for line in patch.splitlines():
        cls = _line_class(line)
        lines_html.append(f'<span class="{cls}">{html.escape(line)}</span>\n')

    stat_html = ""
    if stat and len(stat) >= 3:
        added = stat[1]
        removed = stat[2]
        stat_html = (
            f'<div class="diff-stat">{added} insertions(+), {removed} deletions(-)</div>'
        )

    page_title = html.escape(title or "Git diff")
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{page_title}</title>
  <style>
    body {{ margin: 0; background: #0d1117; color: #c9d1d9; }}
    .diff-stat {{
      padding: 8px 14px;
      background: #161b22;
      border-bottom: 1px solid #30363d;
      color: #8b949e;
      font: 12px/1.4 Consolas, "Courier New", monospace;
    }}
    pre {{
      margin: 0;
      padding: 12px 14px;
      font: 13px/1.45 Consolas, "Courier New", monospace;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .diff-add {{ color: #3fb950; background: rgba(46, 160, 67, 0.12); display: block; }}
    .diff-del {{ color: #f85149; background: rgba(248, 81, 73, 0.12); display: block; }}
    .diff-hunk {{ color: #d2a8ff; display: block; }}
    .diff-file {{ color: #79c0ff; font-weight: 600; display: block; }}
    .diff-meta {{ color: #8b949e; display: block; }}
    .diff-header {{ color: #8b949e; display: block; }}
    .diff-ctx {{ display: block; }}
  </style>
</head>
<body>
{stat_html}
<pre>{"".join(lines_html)}</pre>
</body>
</html>"""
