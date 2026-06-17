import re
from typing import Optional

import httpx
from django.conf import settings
from django.http import FileResponse, HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

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
    update_oxidized_credentials,
)
from services.ldap_auth import auth_methods
from services.oxidized_client import check_health, fetch_node, get_node_config, get_nodes
from services.schemas import (
    CredentialProfile,
    CredentialProfileCreate,
    CredentialProfileUpdate,
    Device,
    DeviceCreate,
    Inventory,
    ScanJobStatus,
    ScanLogEntry,
    ScanStartResponse,
)

_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)
_EMBED_BLOCK_HEADERS = frozenset(
    {
        "x-frame-options",
        "content-security-policy",
        "content-security-policy-report-only",
    }
)
OXIDIZED_PROXY_PREFIX = "/oxidized-proxy"
_ROOT_ATTR_RE = re.compile(
    r"(?P<attr>href|src|action)\s*=\s*(?P<q>['\"])/(?P<rest>[^'\"]*)"
)
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)/")


def _rewrite_proxy_location(location: str) -> str:
    location = location.strip()
    for base in (settings.OXIDIZED_URL, settings.OXIDIZED_PUBLIC_URL):
        if location.startswith(base):
            suffix = location[len(base) :] or "/"
            if not suffix.startswith("/"):
                suffix = f"/{suffix}"
            return f"{OXIDIZED_PROXY_PREFIX}{suffix}"
    if location.startswith("/") and not location.startswith(OXIDIZED_PROXY_PREFIX):
        return f"{OXIDIZED_PROXY_PREFIX}{location}"
    return location


def _rewrite_proxy_body(content: bytes, content_type: str) -> bytes:
    if not content:
        return content
    ct = (content_type or "").lower()
    if not any(token in ct for token in ("html", "css", "javascript", "json")):
        return content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content
    text = text.replace(f"{settings.OXIDIZED_URL}/", f"{OXIDIZED_PROXY_PREFIX}/")
    text = text.replace(
        f"{settings.OXIDIZED_PUBLIC_URL}/", f"{OXIDIZED_PROXY_PREFIX}/"
    )
    if "html" in ct or "javascript" in ct:
        text = _ROOT_ATTR_RE.sub(
            lambda m: (
                f"{m.group('attr')}={m.group('q')}"
                f"{OXIDIZED_PROXY_PREFIX}/{m.group('rest')}"
            ),
            text,
        )
    if "css" in ct:
        text = _CSS_URL_RE.sub(f"url(\\1{OXIDIZED_PROXY_PREFIX}/", text)
    return text.encode("utf-8")


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
    return json_response(
        {
            "oxidized_public_url": settings.OXIDIZED_PUBLIC_URL,
            "oxidized_proxy_url": "/oxidized-proxy/nodes",
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
    target = f"/{path}" if path else "/"
    if request.META.get("QUERY_STRING"):
        target = f"{target}?{request.META['QUERY_STRING']}"

    forward_headers = {
        key.replace("HTTP_", "").replace("_", "-").title(): value
        for key, value in request.META.items()
        if key.startswith("HTTP_") and key.lower() not in ("http_host", "http_connection")
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            upstream = client.request(
                request.method,
                f"{settings.OXIDIZED_URL}{target}",
                headers=forward_headers,
                content=request.body,
            )
    except httpx.ConnectError:
        return error_response("Oxidized недоступен", status=503)
    except httpx.TimeoutException:
        return error_response("Таймаут Oxidized", status=504)

    content_type = upstream.headers.get("content-type", "")
    body = _rewrite_proxy_body(upstream.content, content_type)

    response = HttpResponse(body, status=upstream.status_code)
    for key, value in upstream.headers.items():
        lower = key.lower()
        if lower in _HOP_HEADERS or lower in _EMBED_BLOCK_HEADERS:
            continue
        if lower == "content-length":
            continue
        if lower == "location":
            value = _rewrite_proxy_location(value)
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


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def oxidized_node_fetch(request: HttpRequest, name: str) -> JsonResponse:
    data, err = fetch_node(name)
    if err:
        return error_response(err, status=503)
    return json_response({"status": "ok", "name": name, "result": data})


def health(request: HttpRequest) -> JsonResponse:
    inventory = load_inventory()
    summary, last_scan_at = scan_job.get_last_scan()
    return json_response(
        {
            "status": "ok",
            "inventory_devices": len(inventory.devices),
            "networks": len(inventory.networks),
            "last_scan": last_scan_at,
        }
    )


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
            CredentialProfile(**profile.model_dump())
        )
    except ValueError as exc:
        return error_response(str(exc))
    update_oxidized_credentials(inventory)
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
        return json_response(mask_inventory_for_role(inventory, user.role))
    if request.method == "DELETE":
        try:
            inventory = delete_credential_profile(name)
        except ValueError as exc:
            status = 404 if "не найден" in str(exc).lower() or "not found" in str(exc).lower() else 400
            return error_response(str(exc), status=status)
        update_oxidized_credentials(inventory)
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
    return json_response(summary)


@csrf_exempt
@require_http_methods(["POST"])
@require_permission(auth.PERMISSION_OXIDIZED_WRITE)
def sync_oxidized_view(request: HttpRequest) -> JsonResponse:
    inventory = load_inventory()
    update_oxidized_credentials(inventory)
    return json_response(
        {
            "status": "ok",
            "source": "http",
            "source_url": OXIDIZED_SOURCE_URL,
            "devices_count": len(inventory.devices),
            "enabled_count": sum(1 for d in inventory.devices if d.enabled),
        }
    )
