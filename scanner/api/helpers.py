import json
from functools import wraps
from typing import Any, Callable, Optional

from django.conf import settings
from django.http import HttpRequest, JsonResponse

from core.models import User
from services import auth


class ApiError(Exception):
    def __init__(self, detail: str, status: int = 400):
        self.detail = detail
        self.status = status
        super().__init__(detail)


def _serialize(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _serialize(value) for key, value in obj.items()}
    return obj


def json_response(data: Any, status: int = 200) -> JsonResponse:
    return JsonResponse(_serialize(data), status=status, safe=isinstance(data, dict))


def error_response(detail: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"detail": detail}, status=status)


def parse_json_body(request: HttpRequest) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ApiError("Неверный JSON") from exc


def token_from_request(request: HttpRequest) -> str:
    api_key = request.headers.get("X-API-Key", "").strip()
    if api_key:
        return api_key
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token.startswith("bk_"):
            return token
        return token
    cookie_token = request.COOKIES.get(settings.AUTH_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    raise ApiError("Требуется вход в систему", status=401)


def get_current_user(request: HttpRequest) -> User:
    token = token_from_request(request)
    if token.startswith("bk_"):
        from services.api_keys import authenticate_api_key

        user = authenticate_api_key(token)
        if not user:
            raise ApiError("Недействительный API key", status=401)
        return user
    try:
        payload = auth.decode_token(token)
    except ValueError as exc:
        raise ApiError(str(exc), status=401) from exc
    user = auth.get_user_by_id(int(payload.get("sub", "0")))
    if not user or not user.is_active:
        raise ApiError("Пользователь не найден или отключён", status=401)
    return user


def require_permission(permission: str) -> Callable:
    def decorator(view: Callable) -> Callable:
        @wraps(view)
        def wrapped(request: HttpRequest, *args, **kwargs):
            try:
                user = get_current_user(request)
            except ApiError as exc:
                return error_response(exc.detail, exc.status)
            if not auth.user_has_permission(user, permission):
                return error_response("Недостаточно прав", status=403)
            request.api_user = user
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


def optional_user(request: HttpRequest) -> Optional[User]:
    try:
        return get_current_user(request)
    except ApiError:
        return None
