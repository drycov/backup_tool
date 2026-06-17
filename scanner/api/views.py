
import httpx
from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from pydantic import ValidationError

from api.helpers import (
    ApiError,
    error_response,
    get_current_user,
    json_response,
    parse_json_body,
    require_permission,
)
from core.models import User
from services import auth, scan_job
from services.audit import (
    ACTION_CREDENTIAL_CREATE,
    ACTION_CREDENTIAL_DELETE,
    ACTION_CREDENTIAL_UPDATE,
    ACTION_OXIDIZED_BACKUP_ALL,
    ACTION_OXIDIZED_FETCH,
    ACTION_SCAN_DISCOVER,
    ACTION_SCAN_RUN,
    list_audit_events,
    log_audit_user,
)
from services.compliance import compute_compliance_summary
from services.scan_history import get_scan_history, get_scan_trends
from services.inventory import (
    OXIDIZED_SOURCE_TOKEN,
    OXIDIZED_SOURCE_URL,
    add_device,
    devices_for_oxidized_source,
    load_inventory,
    mask_inventory_for_role,
    reimport_network_inventory,
    remove_device,
    save_inventory,
    add_credential_profile,
    delete_credential_profile,
    update_credential_profile,
    cleanup_discovered_devices,
    update_oxidized_credentials,
)
from services.ldap_auth import auth_methods
from services.oxidized_client import (
    build_diff_proxy_path,
    build_version_view_proxy_path,
    build_versions_proxy_path,
    check_health,
    fetch_node,
    get_node_config,
    get_node_versions,
    get_nodes,
)
from services.oxidized_proxy import (
    OXIDIZED_PROXY_PREFIX,
    embed_block_headers,
    hop_headers,
    oxidized_base_url,
    rewrite_proxy_body,
    rewrite_proxy_location,
    upstream_target,
)
from services.schemas import (
    BackupNotifyTestRequest,
    BackupSettingsUpdate,
    CredentialProfile,
    CredentialProfileCreate,
    CredentialProfileUpdate,
    Device,
    DeviceCreate,
    Inventory,
    LdapConfigUpdate,
    LdapTestRequest,
    OxidizedSettingsUpdate,
    ScanJobStatus,
    ScanLogEntry,
    ScanStartResponse,
)
from services import ldap_settings

_HOP_HEADERS = hop_headers()
_EMBED_BLOCK_HEADERS = embed_block_headers()

def _job_to_status(job: scan_job.ScanJob | None) -> ScanJobStatus:
    if not job:
        return ScanJobStatus(status="idle", phase="idle")
    return ScanJobStatus(
        job_id=job.id,
        status=job.status,
        phase=job.phase.value,
        message=job.message,
        discover=job.discover,
        progress_current=job.progress_current,
        progress_total=job.progress_total,
        progress_pct=job.progress_pct,
        started_at=job.started_at,
        finished_at=job.finished_at,
        summary=job.summary,
        error=job.error,
        logs=[
            ScanLogEntry(ts=e.ts, level=e.level, message=e.message) for e in job.logs
        ],
    )


def ui_page(request: HttpRequest) -> FileResponse:
    index_path = settings.BASE_DIR / "static" / "index.html"
    return FileResponse(index_path.open("rb"), content_type="text/html")


def ui_config(request: HttpRequest) -> JsonResponse:
    engine = getattr(settings, "OXIDIZED_ENGINE", "python")
    return json_response(
        {
            "oxidized_public_url": settings.OXIDIZED_PUBLIC_URL,
            "oxidized_proxy_url": "/oxidized-proxy/nodes",
            "oxidized_engine": engine,
            "oxidized_engine_title": (
                "Python Oxidized" if engine == "python" else "Ruby Oxidized"
            ),
            "scanner_version": "1.0.0",
            "auth_required": True,
            "auth": auth_methods(),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def login_view(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json_body(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)
    user = auth.authenticate_user(body.get("username", ""), body.get("password", ""))
    if not user:
        return error_response("Неверный логин или пароль", status=401)

    token = auth.create_access_token(user.id, user.username, user.role)
    response = json_response(
        {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "permissions": auth.permissions_for_role(user.role),
            },
        }
    )
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="Lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return response


@csrf_exempt
@require_http_methods(["POST"])
def logout_view(request: HttpRequest) -> JsonResponse:
    response = json_response({"status": "ok"})
    response.delete_cookie(key=settings.AUTH_COOKIE_NAME, path="/")
    return response


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def auth_me(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    return json_response(
        {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "permissions": auth.permissions_for_role(user.role),
        }
    )


def _auth_users_list(request: HttpRequest) -> JsonResponse:
    users = [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "is_active": u.is_active,
            "auth_source": u.auth_source or "local",
        }
        for u in auth.list_users()
    ]
    return json_response(users)


@csrf_exempt
@require_permission(auth.PERMISSION_MANAGE_USERS)
def auth_users_dispatch(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return _auth_users_list(request)
    if request.method == "POST":
        body = parse_json_body(request)
        try:
            created = auth.create_user(
                body.get("username", ""),
                body.get("password", ""),
                body.get("role", "viewer"),
            )
        except ValueError as exc:
            return error_response(str(exc))
        return json_response(
            {
                "id": created.id,
                "username": created.username,
                "role": created.role,
                "is_active": created.is_active,
                "auth_source": created.auth_source or "local",
            }
        )
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_permission(auth.PERMISSION_MANAGE_USERS)
def auth_user_detail(request: HttpRequest, user_id: int) -> JsonResponse:
    if request.method == "PUT":
        body = parse_json_body(request)
        try:
            updated = auth.update_user(
                user_id,
                role=body.get("role"),
                is_active=body.get("is_active"),
                password=body.get("password"),
            )
        except ValueError as exc:
            return error_response(
                str(exc), status=404 if "не найден" in str(exc) else 400
            )
        return json_response(
            {
                "id": updated.id,
                "username": updated.username,
                "role": updated.role,
                "is_active": updated.is_active,
                "auth_source": updated.auth_source or "local",
            }
        )
    if request.method == "DELETE":
        user: User = request.api_user
        if user_id == user.id:
            return error_response("Нельзя удалить текущего пользователя")
        try:
            auth.delete_user(user_id)
        except ValueError as exc:
            return error_response(str(exc), status=404)
        return json_response({"status": "ok"})
    return error_response("Method not allowed", status=405)



@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_logs(request: HttpRequest) -> JsonResponse:
    try:
        max_lines = int(request.GET.get("lines", "500"))
    except ValueError:
        max_lines = 500
    search = request.GET.get("q", "")
    from services.oxidized_logs import tail_oxidized_log

    return json_response(tail_oxidized_log(max_lines=max_lines, search=search))


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def oxidized_models(request: HttpRequest) -> JsonResponse:
    from services.oxidized_config_loader import list_available_models

    return json_response({"models": list_available_models()})


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_health(request: HttpRequest) -> JsonResponse:
    return json_response(check_health())


def oxidized_source(request: HttpRequest) -> JsonResponse:
    if OXIDIZED_SOURCE_TOKEN:
        token = request.headers.get("X-Auth-Token", "")
        if token != OXIDIZED_SOURCE_TOKEN:
            return error_response("Invalid X-Auth-Token", status=401)
    return json_response(devices_for_oxidized_source())


@csrf_exempt
@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_proxy(request: HttpRequest, path: str = "") -> HttpResponse:
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() == "python":
        from services.oxidized_web_ui import handle_python_ui

        return handle_python_ui(request, path)

    target = upstream_target(path, request.META.get("QUERY_STRING", ""))

    forward_headers = {
        key.replace("HTTP_", "").replace("_", "-").title(): value
        for key, value in request.META.items()
        if key.startswith("HTTP_") and key.lower() not in ("http_host", "http_connection")
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            upstream = client.request(
                request.method,
                f"{oxidized_base_url()}{target}",
                headers=forward_headers,
                content=request.body,
            )
    except httpx.ConnectError:
        return error_response("Oxidized недоступен", status=503)
    except httpx.TimeoutException:
        return error_response("Таймаут Oxidized", status=504)

    content_type = upstream.headers.get("content-type", "")
    body = rewrite_proxy_body(upstream.content, content_type)

    response = HttpResponse(body, status=upstream.status_code)
    for key, value in upstream.headers.items():
        lower = key.lower()
        if lower in _HOP_HEADERS or lower in _EMBED_BLOCK_HEADERS:
            continue
        if lower == "content-length":
            continue
        if lower == "location":
            value = rewrite_proxy_location(value)
        response[key] = value
    if content_type:
        response["Content-Type"] = content_type
    return response


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_nodes(request: HttpRequest) -> JsonResponse:
    nodes, err = get_nodes()
    if err:
        return error_response(err, status=503)
    return json_response(nodes)


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_show(request: HttpRequest, name: str) -> JsonResponse:
    data, err = get_node_config(name)
    if err:
        return error_response(err, status=503)
    if data is None:
        return error_response(f"Node '{name}' not found", status=404)
    return json_response(data)


def _parse_version_epoch(raw_time) -> int:
    if raw_time is None:
        return 0
    if isinstance(raw_time, (int, float)):
        return int(raw_time)
    text = str(raw_time).strip()
    if not text:
        return 0
    from datetime import datetime

    normalized = text.replace("Z", "+00:00")
    try:
        return int(datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%d %H:%M:%S",
        "%a, %d %b %Y %H:%M:%S %z",
    ):
        try:
            return int(datetime.strptime(text, fmt).timestamp())
        except ValueError:
            continue
    return 0


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_versions(request: HttpRequest, name: str) -> JsonResponse:
    data, err = get_node_versions(name)
    if err:
        status = 404 if "не найден" in err.lower() else 503
        return error_response(err, status=status)
    versions = data.get("versions") or []
    enriched = []
    total = len(versions)
    for idx, item in enumerate(versions):
        num = total - idx
        raw_time = item.get("time")
        epoch = _parse_version_epoch(raw_time)
        enriched.append(
            {
                "oid": item.get("oid"),
                "time": raw_time,
                "epoch": epoch,
                "num": num,
                "view_url": build_version_view_proxy_path(
                    data["node"], data.get("group") or "", item.get("oid", ""), epoch, num
                ),
                "diff_url": build_diff_proxy_path(
                    data["node"], data.get("group") or "", item.get("oid", ""), epoch, num
                )
                if idx < total - 1
                else None,
            }
        )
    return json_response(
        {
            "node": data["node"],
            "group": data.get("group") or "",
            "node_full": data.get("node_full"),
            "versions_proxy_url": build_versions_proxy_path(
                data["node"], data.get("group") or ""
            ),
            "versions": enriched,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def oxidized_node_fetch(request: HttpRequest, name: str) -> JsonResponse:
    data, err = fetch_node(name)
    if err:
        return error_response(err, status=503)
    log_audit_user(request.api_user, ACTION_OXIDIZED_FETCH, target=name, request=request)
    return json_response({"status": "ok", "name": name, "result": data})


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def oxidized_backup_all(request: HttpRequest) -> JsonResponse:
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() != "python":
        return error_response("Доступно только для python engine", status=501)
    from services.oxidized_engine import get_manager

    result = get_manager().backup_all()
    log_audit_user(
        request.api_user,
        ACTION_OXIDIZED_BACKUP_ALL,
        detail=f"queued={result.get('queued', 0)}",
        request=request,
    )
    return json_response({"status": "ok", **result})


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_backups(request: HttpRequest, name: str) -> JsonResponse:
    from services.mikrotik_backup import MikrotikBackup, MikrotikBackupError

    try:
        files = MikrotikBackup().list_files(name)
    except MikrotikBackupError as exc:
        return error_response(str(exc), status=400)
    return json_response({"name": name, "backups": files})


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_backup_download(request: HttpRequest, name: str) -> HttpResponse:
    from services.mikrotik_backup import MikrotikBackup, MikrotikBackupError

    backup_type = (request.GET.get("type") or "bin").lower()
    filename = request.GET.get("file", "")
    if backup_type not in ("bin", "rsc"):
        return error_response("type must be bin or rsc", status=400)
    if not filename:
        return error_response("file required", status=400)
    try:
        path = MikrotikBackup().resolve_download(name, backup_type, filename)
    except MikrotikBackupError as exc:
        return error_response(str(exc), status=404)
    content_type = "application/octet-stream"
    if filename.endswith(".rsc"):
        content_type = "text/plain; charset=utf-8"
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name, content_type=content_type)


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_version_view(request: HttpRequest, name: str, oid: str) -> HttpResponse:
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() != "python":
        return error_response("Доступно только для python engine", status=501)
    from services.oxidized_engine import get_manager
    from services.oxidized_engine.exceptions import NodeNotFound

    try:
        text = get_manager().get_version(name, oid)
    except NodeNotFound:
        return error_response(f"Node '{name}' not found", status=404)
    if text == "version not found":
        return error_response("version not found", status=404)
    return HttpResponse(text, content_type="text/plain; charset=utf-8")


@require_permission(auth.PERMISSION_OXIDIZED_READ)
def oxidized_node_diff(request: HttpRequest, name: str) -> HttpResponse:
    if getattr(settings, "OXIDIZED_ENGINE", "python").lower() != "python":
        return error_response("Доступно только для python engine", status=501)
    from services.oxidized_engine import get_manager
    from services.oxidized_engine.exceptions import NodeNotFound
    from services.git_diff_html import render_git_diff_html

    oid = request.GET.get("oid", "")
    oid2 = request.GET.get("oid2") or None
    if not oid:
        return error_response("oid required", status=400)
    try:
        diff = get_manager().get_diff(name, oid, oid2)
    except NodeNotFound:
        return error_response(f"Node '{name}' not found", status=404)

    fmt = (request.GET.get("format") or "html").lower()
    patch = str(diff.get("patch") or "")
    if fmt == "json":
        return json_response(diff)
    if fmt == "text":
        return HttpResponse(patch, content_type="text/plain; charset=utf-8")
    html_body = render_git_diff_html(
        patch,
        title=f"Diff {name}",
        stat=diff.get("stat"),
    )
    return HttpResponse(html_body, content_type="text/html; charset=utf-8")


def health(request: HttpRequest) -> JsonResponse:
    inventory = load_inventory()
    summary, last_scan_at = scan_job.get_last_scan()
    if summary is None:
        from services.scan_history import get_last_scan_from_db

        summary, last_scan_at = get_last_scan_from_db()
    payload = {
        "status": "ok",
        "inventory_devices": len(inventory.devices),
        "networks": len(inventory.networks),
        "last_scan": last_scan_at,
    }
    if summary:
        payload["scan_online"] = summary.online
        payload["scan_offline"] = summary.offline
        payload["scan_partial"] = summary.partial
    return json_response(payload)


@csrf_exempt
def inventory_dispatch(request: HttpRequest) -> JsonResponse:
    try:
        user = get_current_user(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)

    if request.method == "GET":
        if not auth.user_has_permission(user, auth.PERMISSION_VIEW_INVENTORY):
            return error_response("Недостаточно прав", status=403)
        return json_response(mask_inventory_for_role(load_inventory(), user.role))
    if request.method == "PUT":
        if not auth.user_has_permission(user, auth.PERMISSION_EDIT_INVENTORY):
            return error_response("Недостаточно прав", status=403)
        body = parse_json_body(request)
        inventory = Inventory.model_validate(body)
        save_inventory(inventory)
        update_oxidized_credentials(inventory)
        return json_response(mask_inventory_for_role(inventory, user.role))
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_permission(auth.PERMISSION_EDIT_DEVICES)
def inventory_devices_dispatch(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    if request.method == "POST":
        body = parse_json_body(request)
        device = DeviceCreate.model_validate(body)
        inventory = add_device(Device(**device.model_dump()))
        return json_response(mask_inventory_for_role(inventory, user.role))
    return error_response("Method not allowed", status=405)



@csrf_exempt
@require_http_methods(["DELETE"])
@require_permission(auth.PERMISSION_EDIT_DEVICES)
def delete_device_view(request: HttpRequest, name: str) -> JsonResponse:
    user: User = request.api_user
    inventory = load_inventory()
    if not any(d.name == name for d in inventory.devices):
        return error_response(f"Device '{name}' not found", status=404)
    inventory = remove_device(name)
    return json_response(mask_inventory_for_role(inventory, user.role))


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_EDIT_CREDENTIALS)
def create_credential_profile_view(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    body = parse_json_body(request)
    profile = CredentialProfileCreate.model_validate(body)
    try:
        inventory = add_credential_profile(
            CredentialProfile(
                name=profile.name,
                group_name=profile.group_name,
                username=profile.username,
                password=profile.password,
            )
        )
        if profile.model:
            from services.oxidized_settings import set_group_model

            set_group_model(profile.group_name, profile.model)
            inventory = load_inventory()
    except ValueError as exc:
        return error_response(str(exc))
    update_oxidized_credentials(inventory)
    log_audit_user(
        request.api_user,
        ACTION_CREDENTIAL_CREATE,
        target=profile.name,
        detail=f"group={profile.group_name}",
        request=request,
    )
    return json_response(mask_inventory_for_role(inventory, user.role), status=201)


@csrf_exempt
@require_permission(auth.PERMISSION_EDIT_CREDENTIALS)
def credential_profile_detail_view(request: HttpRequest, name: str) -> JsonResponse:
    user: User = request.api_user
    if request.method == "PUT":
        body = parse_json_body(request)
        creds = CredentialProfileUpdate.model_validate(body)
        try:
            inventory = update_credential_profile(name, creds)
        except ValueError as exc:
            return error_response(str(exc), status=404)
        update_oxidized_credentials(inventory)
        log_audit_user(
            request.api_user,
            ACTION_CREDENTIAL_UPDATE,
            target=name,
            request=request,
        )
        return json_response(mask_inventory_for_role(inventory, user.role))
    if request.method == "DELETE":
        try:
            inventory = delete_credential_profile(name)
        except ValueError as exc:
            status = 404 if "не найден" in str(exc).lower() or "not found" in str(exc).lower() else 400
            return error_response(str(exc), status=status)
        update_oxidized_credentials(inventory)
        log_audit_user(
            request.api_user,
            ACTION_CREDENTIAL_DELETE,
            target=name,
            request=request,
        )
        return json_response(mask_inventory_for_role(inventory, user.role))
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_EDIT_INVENTORY)
def import_network_inventory_view(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    try:
        inventory = reimport_network_inventory()
    except FileNotFoundError as exc:
        return error_response(str(exc), status=404)
    update_oxidized_credentials(inventory)
    return json_response(mask_inventory_for_role(inventory, user.role))


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_RUN_SCAN)
def scan_inventory_view(request: HttpRequest) -> JsonResponse:
    discover = request.GET.get("discover", "").lower() in ("1", "true", "yes")
    job = scan_job.start_scan(discover=discover)
    log_audit_user(
        request.api_user,
        ACTION_SCAN_DISCOVER if discover else ACTION_SCAN_RUN,
        detail=f"job_id={job.id}",
        request=request,
    )
    return json_response(
        ScanStartResponse(job_id=job.id, status=job.status, discover=job.discover),
        status=202,
    )


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def scan_status_view(request: HttpRequest) -> JsonResponse:
    return json_response(_job_to_status(scan_job.get_current_job()))


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def get_latest_scan_view(request: HttpRequest) -> JsonResponse:
    summary, _ = scan_job.get_last_scan()
    if summary is None:
        from services.scan_history import get_last_scan_from_db

        summary, _ = get_last_scan_from_db()
    return json_response(summary)


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def compliance_summary_view(request: HttpRequest) -> JsonResponse:
    return json_response(compute_compliance_summary())


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def scan_history_view(request: HttpRequest) -> JsonResponse:
    try:
        limit = int(request.GET.get("limit", "50"))
    except ValueError:
        limit = 50
    try:
        days = int(request.GET.get("days", "30"))
    except ValueError:
        days = 30
    return json_response(get_scan_history(limit=limit, days=days))


@require_permission(auth.PERMISSION_VIEW_INVENTORY)
def scan_trends_view(request: HttpRequest) -> JsonResponse:
    try:
        days = int(request.GET.get("days", "30"))
    except ValueError:
        days = 30
    return json_response(get_scan_trends(days=days))


@require_permission(auth.PERMISSION_MANAGE_USERS)
def audit_events_view(request: HttpRequest) -> JsonResponse:
    try:
        limit = int(request.GET.get("limit", "100"))
    except ValueError:
        limit = 100
    try:
        offset = int(request.GET.get("offset", "0"))
    except ValueError:
        offset = 0
    action = request.GET.get("action", "").strip()
    return json_response(list_audit_events(limit=limit, offset=offset, action=action))


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def sync_oxidized_view(request: HttpRequest) -> JsonResponse:
    inventory = load_inventory()
    reload_info = update_oxidized_credentials(inventory)
    from django.conf import settings

    engine = getattr(settings, "OXIDIZED_ENGINE", "python")
    return json_response(
        {
            "status": "ok",
            "engine": engine,
            "engine_title": (
                "Python Oxidized" if engine == "python" else "Ruby Oxidized"
            ),
            "source": "inventory",
            "source_url": OXIDIZED_SOURCE_URL,
            "devices_count": len(inventory.devices),
            "enabled_count": sum(1 for d in inventory.devices if d.enabled),
            **reload_info,
        }
    )


@csrf_exempt
def oxidized_settings_dispatch(request: HttpRequest) -> JsonResponse:
    from services import oxidized_settings

    try:
        user = get_current_user(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)

    if request.method == "GET":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_READ):
            return error_response("Недостаточно прав", status=403)
        return json_response(oxidized_settings.get_oxidized_settings())
    if request.method == "PUT":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_WRITE):
            return error_response("Недостаточно прав", status=403)
        try:
            body = parse_json_body(request)
            payload = OxidizedSettingsUpdate.model_validate(body)
            saved = oxidized_settings.save_oxidized_settings(payload.model_dump())
        except ValidationError as exc:
            return error_response(str(exc))
        except ValueError as exc:
            return error_response(str(exc))
        return json_response(saved)
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_EDIT_INVENTORY)
def cleanup_discovered_devices_view(request: HttpRequest) -> JsonResponse:
    user: User = request.api_user
    deleted, inventory = cleanup_discovered_devices()
    update_oxidized_credentials(inventory)
    return json_response(
        {
            "status": "ok",
            "deleted": deleted,
            "message": f"Удалено устройств discovery: {deleted}",
            "inventory": mask_inventory_for_role(inventory, user.role),
        }
    )


@csrf_exempt
def backup_settings_dispatch(request: HttpRequest) -> JsonResponse:
    from services import backup_settings

    try:
        user = get_current_user(request)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)

    if request.method == "GET":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_READ):
            return error_response("Недостаточно прав", status=403)
        return json_response(backup_settings.get_config_public())
    if request.method == "PUT":
        if not auth.user_has_permission(user, auth.PERMISSION_OXIDIZED_WRITE):
            return error_response("Недостаточно прав", status=403)
        try:
            body = parse_json_body(request)
            payload = BackupSettingsUpdate.model_validate(body)
            saved = backup_settings.save_config(payload.model_dump())
        except ValidationError as exc:
            return error_response(str(exc))
        except ValueError as exc:
            return error_response(str(exc))
        return json_response(saved)
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def backup_settings_test_notify(request: HttpRequest) -> JsonResponse:
    from services.backup_notifications import send_test_notification

    try:
        body = parse_json_body(request)
        payload = BackupNotifyTestRequest.model_validate(body)
    except ValidationError as exc:
        return error_response(str(exc))
    kind = payload.kind.strip().lower()
    if kind not in ("error", "report"):
        return error_response("kind must be error or report", status=400)
    result = send_test_notification(kind)
    return json_response(result)


@csrf_exempt
@require_permission(auth.PERMISSION_MANAGE_USERS)
def ldap_settings_dispatch(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return json_response(ldap_settings.get_config_public())
    if request.method == "PUT":
        try:
            body = parse_json_body(request)
            payload = LdapConfigUpdate.model_validate(body)
            saved = ldap_settings.save_config(payload.model_dump())
        except ApiError as exc:
            return error_response(exc.detail, exc.status)
        except ValidationError as exc:
            return error_response(str(exc))
        except ValueError as exc:
            return error_response(str(exc))
        return json_response(saved)
    return error_response("Method not allowed", status=405)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_MANAGE_USERS)
def ldap_settings_test_view(request: HttpRequest) -> JsonResponse:
    try:
        body = parse_json_body(request)
        payload = LdapTestRequest.model_validate(body)
    except ApiError as exc:
        return error_response(exc.detail, exc.status)
    except ValidationError as exc:
        return error_response(str(exc))

    mode = payload.mode.strip().lower()
    if mode not in ("bind", "auth"):
        return error_response("mode должен быть bind или auth")

    result = ldap_settings.test_connection(
        mode=mode,
        username=payload.username,
        password=payload.password,
    )
    return json_response(result)

