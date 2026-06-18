"""Oxidized Web UI for Python engine — served under /oxidized-proxy/."""

from __future__ import annotations

import html
from urllib.parse import quote, unquote

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect

from services.git_diff_html import render_git_diff_html
from services.oxidized_client import fetch_node, get_node_config, get_node_versions, get_nodes
from services.oxidized_proxy import OXIDIZED_PROXY_PREFIX

_PROXY = OXIDIZED_PROXY_PREFIX.rstrip("/")


def _is_python_engine() -> bool:
    return getattr(settings, "OXIDIZED_ENGINE", "python").lower() == "python"


def _esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def _parse_full_name(full_name: str) -> tuple[str, str]:
    full_name = unquote(full_name or "")
    if "/" in full_name:
        group, name = full_name.split("/", 1)
        return name, group
    return full_name, ""


def _node_full(name: str, group: str | None) -> str:
    if group and group not in ("", "default"):
        return f"{group}/{name}"
    return name


def _proxy(path: str) -> str:
    path = path.lstrip("/")
    return f"{_PROXY}/{path}" if path else f"{_PROXY}/nodes"


def _layout(title: str, body: str, *, breadcrumb: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_esc(title)} · Oxidized</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource/inter@5.0.18/latin-400.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@fontsource/inter@5.0.18/latin-600.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/codemirror.min.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/theme/dracula.min.css">
  <link rel="stylesheet" href="/static/oxidized-ui/style.css">
</head>
<body class="oxidized-web">
  <nav class="navbar navbar-dark enterprise-nav mb-3">
    <div class="container-fluid">
      <a class="navbar-brand" href="{_proxy('nodes')}">
        <i class="bi bi-hdd-network me-1"></i> Oxidized
      </a>
      <span class="navbar-text text-white-50 small">Python engine · Backup Tools</span>
    </div>
  </nav>
  <main class="container-fluid pb-4">
    {breadcrumb}
    {body}
  </main>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/codemirror.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.18/addon/mode/simple.min.js"></script>
  <script src="/static/js/config-editor.js"></script>
  <script src="/static/oxidized-ui/app.js"></script>
</body>
</html>"""


def _config_block(textarea_id: str, content: str, model: str = "routeros") -> str:
    safe_content = _esc(content or "")
    return f"""
<div class="config-editor-wrap card">
  <div class="card-body p-0">
    <textarea id="{textarea_id}" data-model="{_esc(model)}">{safe_content}</textarea>
  </div>
</div>"""


def render_nodes(request: HttpRequest) -> HttpResponse:
    nodes, err = get_nodes()
    if err:
        body = f'<div class="alert alert-danger">{_esc(err)}</div>'
        return HttpResponse(_layout("Nodes", body), content_type="text/html; charset=utf-8")

    rows: list[str] = []
    for node in sorted(nodes or [], key=lambda n: str(n.get("name") or "")):
        name = node.get("name") or ""
        group = node.get("group") or ""
        full_name = _node_full(name, group)
        last = node.get("last") or {}
        status = last.get("status") or node.get("status") or "never"
        last_time = last.get("end") or last.get("time") or "—"
        mtime = node.get("mtime") or "—"
        status_cls = {
            "success": "text-success",
            "fail": "text-danger",
            "no_connection": "text-warning",
        }.get(status, "text-secondary")
        rows.append(
            f"""<tr>
  <td><a href="{_proxy(f'node/show/{quote(name, safe="")}')}">{_esc(name)}</a></td>
  <td>{_esc(node.get("ip") or "—")}</td>
  <td>{_esc(node.get("model") or "—")}</td>
  <td>{_esc(group or "—")}</td>
  <td class="{status_cls}">{_esc(status)}</td>
  <td>{_esc(last_time)}</td>
  <td>{_esc(mtime)}</td>
  <td class="text-nowrap">
    <a class="btn btn-sm btn-outline-secondary" href="{_proxy(f'node/fetch/{quote(full_name, safe="")}')}" title="Fetch">
      <i class="bi bi-cloud-download"></i>
    </a>
    <a class="btn btn-sm btn-outline-secondary" href="{_proxy(f'node/version?node_full={quote(full_name, safe="")}')}" title="Versions">
      <i class="bi bi-stack"></i>
    </a>
  </td>
</tr>"""
        )

    body = f"""
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4 class="mb-0">nodes /</h4>
  <a class="btn btn-primary btn-sm" href="{_proxy('nodes')}"><i class="bi bi-arrow-clockwise me-1"></i>Refresh</a>
</div>
<div class="table-responsive">
  <table class="table table-sm table-striped table-hover">
    <thead>
      <tr>
        <th>Name</th><th>IP</th><th>Model</th><th>Group</th>
        <th>Last Status</th><th>Last Update</th><th>Last Changed</th><th>Actions</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows) if rows else '<tr><td colspan="8" class="text-muted text-center">No nodes</td></tr>'}
    </tbody>
  </table>
</div>"""
    return HttpResponse(_layout("Nodes", body), content_type="text/html; charset=utf-8")


def render_show(request: HttpRequest, name: str) -> HttpResponse:
    data, err = get_node_config(name)
    if err:
        body = f'<div class="alert alert-danger">{_esc(err)}</div>'
        return HttpResponse(_layout(name, body), content_type="text/html; charset=utf-8")
    if data is None:
        body = '<div class="alert alert-warning">Node not found</div>'
        return HttpResponse(_layout(name, body), status=404, content_type="text/html; charset=utf-8")

    content = data if isinstance(data, str) else str(data)
    node_row = next((n for n in (get_nodes()[0] or []) if n.get("name") == name), {})
    group = node_row.get("group") or ""
    full_name = _node_full(name, group)
    model = node_row.get("model") or "routeros"

    breadcrumb = f"""
<nav aria-label="breadcrumb">
  <ol class="breadcrumb">
    <li class="breadcrumb-item"><a href="{_proxy('nodes')}">nodes</a></li>
    <li class="breadcrumb-item active">{_esc(name)}</li>
  </ol>
</nav>"""
    body = f"""
<div class="d-flex justify-content-between align-items-center mb-2">
  <h4 class="mb-0">{_esc(name)}</h4>
  <div>
    <a class="btn btn-sm btn-outline-primary" href="{_proxy(f'node/version?node_full={quote(full_name, safe="")}')}">
      <i class="bi bi-stack me-1"></i>Versions
    </a>
    <a class="btn btn-sm btn-primary" href="{_proxy(f'node/fetch/{quote(full_name, safe="")}')}">
      <i class="bi bi-cloud-download me-1"></i>Fetch
    </a>
  </div>
</div>
{_config_block("ox-config-view", content, model)}"""
    return HttpResponse(_layout(name, body, breadcrumb=breadcrumb), content_type="text/html; charset=utf-8")


def render_versions(request: HttpRequest) -> HttpResponse:
    node_full = request.GET.get("node_full", "")
    if node_full:
        name, group = _parse_full_name(node_full)
    else:
        name = request.GET.get("node", "")
        group = request.GET.get("group", "")

    data, err = get_node_versions(name)
    if err:
        body = f'<div class="alert alert-danger">{_esc(err)}</div>'
        return HttpResponse(_layout("Versions", body), content_type="text/html; charset=utf-8")

    versions = data.get("versions") or []
    full_name = _node_full(name, group or data.get("group"))
    rows: list[str] = []
    total = len(versions)
    for idx, item in enumerate(versions):
        oid = item.get("oid") or ""
        num = total - idx
        view_url = _proxy(
            "node/version/view?"
            + f"node={quote(name, safe='')}&group={quote(group or data.get('group') or '', safe='')}"
            + f"&oid={quote(oid, safe='')}&num={num}"
        )
        diff_btn = '<span class="text-muted">—</span>'
        if idx < total - 1:
            diff_url = _proxy(
                "node/version/diffs?"
                + f"node={quote(name, safe='')}&group={quote(group or data.get('group') or '', safe='')}"
                + f"&oid={quote(oid, safe='')}&num={num}"
            )
            diff_btn = f'<a class="btn btn-sm btn-outline-primary" href="{diff_url}"><i class="bi bi-file-diff"></i></a>'

        rows.append(
            f"""<tr>
  <td>{num}</td>
  <td>{_esc(item.get("date") or item.get("time") or "—")}</td>
  <td><code class="small">{_esc(str(oid)[:12])}</code></td>
  <td class="text-end text-nowrap">
    <a class="btn btn-sm btn-outline-secondary" href="{view_url}"><i class="bi bi-eye"></i></a>
    {diff_btn}
  </td>
</tr>"""
        )

    breadcrumb = f"""
<nav aria-label="breadcrumb">
  <ol class="breadcrumb">
    <li class="breadcrumb-item"><a href="{_proxy('nodes')}">nodes</a></li>
    <li class="breadcrumb-item"><a href="{_proxy(f'node/show/{quote(name, safe="")}')}">{_esc(name)}</a></li>
    <li class="breadcrumb-item active">versions</li>
  </ol>
</nav>"""
    body = f"""
<h4 class="mb-3">versions / {_esc(full_name)}</h4>
<div class="table-responsive">
  <table class="table table-sm table-striped">
    <thead><tr><th>#</th><th>Date</th><th>OID</th><th class="text-end">Actions</th></tr></thead>
    <tbody>
      {''.join(rows) if rows else '<tr><td colspan="4" class="text-muted text-center">No versions</td></tr>'}
    </tbody>
  </table>
</div>"""
    return HttpResponse(_layout("Versions", body, breadcrumb=breadcrumb), content_type="text/html; charset=utf-8")


def render_version_view(request: HttpRequest) -> HttpResponse:
    name = request.GET.get("node", "")
    oid = request.GET.get("oid", "")
    if not name or not oid:
        return HttpResponse("node and oid required", status=400)

    from services.oxidized_engine import get_manager
    from services.oxidized_engine.exceptions import NodeNotFound

    try:
        text = get_manager().get_version(name, oid)
    except NodeNotFound:
        return HttpResponse("node not found", status=404)
    if text == "version not found":
        return HttpResponse("version not found", status=404)

    num = request.GET.get("num", "")
    breadcrumb = f"""
<nav aria-label="breadcrumb">
  <ol class="breadcrumb">
    <li class="breadcrumb-item"><a href="{_proxy('nodes')}">nodes</a></li>
    <li class="breadcrumb-item"><a href="{_proxy(f'node/show/{quote(name, safe="")}')}">{_esc(name)}</a></li>
    <li class="breadcrumb-item active">version {_esc(num)}</li>
  </ol>
</nav>"""
    body = f"""
<h4 class="mb-2">version / {_esc(name)} #{_esc(num)}</h4>
<p class="text-muted small mb-2"><code>{_esc(oid)}</code></p>
{_config_block("ox-version-view", text)}"""
    return HttpResponse(_layout(f"Version {num}", body, breadcrumb=breadcrumb), content_type="text/html; charset=utf-8")


def render_version_diffs(request: HttpRequest) -> HttpResponse:
    name = request.GET.get("node", "")
    oid = request.GET.get("oid", "")
    oid2 = request.GET.get("oid2") or None
    if not name or not oid:
        return HttpResponse("node and oid required", status=400)

    from services.oxidized_engine import get_manager
    from services.oxidized_engine.exceptions import NodeNotFound

    try:
        diff = get_manager().get_diff(name, oid, oid2)
    except NodeNotFound:
        return HttpResponse("node not found", status=404)

    patch = str(diff.get("patch") or "")
    html_body = render_git_diff_html(patch, title=f"Diff {name}", stat=diff.get("stat"))
    return HttpResponse(html_body, content_type="text/html; charset=utf-8")


def render_fetch(request: HttpRequest, full_name: str) -> HttpResponse:
    name, _group = _parse_full_name(full_name)
    fetch_node(name)
    return HttpResponseRedirect(_proxy(f"node/show/{quote(name, safe='')}"))


def handle_python_ui(request: HttpRequest, path: str) -> HttpResponse:
    if not _is_python_engine():
        return HttpResponse("Python UI only", status=501)

    clean = (path or "").strip("/")

    if clean in ("", "nodes"):
        return render_nodes(request)
    if clean.startswith("node/show/"):
        name = unquote(clean.split("/", 2)[2])
        return render_show(request, name)
    if clean == "node/version":
        return render_versions(request)
    if clean == "node/version/view":
        return render_version_view(request)
    if clean == "node/version/diffs":
        return render_version_diffs(request)
    if clean.startswith("node/fetch/") or clean.startswith("node/next/"):
        full_name = unquote(clean.split("/", 2)[2])
        return render_fetch(request, full_name)

    return HttpResponseRedirect(_proxy("nodes"))
