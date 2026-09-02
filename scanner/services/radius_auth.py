"""RADIUS SSO authentication and role mapping."""

import logging
from typing import Optional

from services.radius_settings import RadiusConfigData, get_config, radius_configured

logger = logging.getLogger(__name__)


def _role_attribute_values(reply, attr_name: str) -> list[str]:
    """Извлечь все значения атрибута из Access-Accept."""
    try:
        values = reply[attr_name]
    except Exception:
        values = None
    if not values:
        return []
    out: list[str] = []
    for attr in values:
        raw = getattr(attr, "value", attr)
        if isinstance(raw, bytes):
            try:
                out.append(raw.decode("utf-8", "replace").strip())
            except Exception:
                out.append(str(raw).strip())
        else:
            out.append(str(raw).strip())
    return [v for v in out if v]


def _map_role(cfg: RadiusConfigData, attr_values: list[str]) -> tuple[str, str | None]:
    admin = [v.strip() for v in cfg.admin_values.split(",") if v.strip()]
    operator = [v.strip() for v in cfg.operator_values.split(",") if v.strip()]

    matched: str | None = None
    for value in attr_values:
        for needle in admin:
            if value == needle or value.lower() == needle.lower():
                return "admin", value
        for needle in operator:
            if value == needle or value.lower() == needle.lower():
                return "operator", value

    default = cfg.default_role.strip().lower()
    return (default if default in ("viewer", "operator", "admin") else "viewer"), matched


def authenticate_radius(username: str, password: str) -> Optional[dict]:
    """Проверка RADIUS (Access-Request/Accept). Возвращает {username, role, ...} или None."""
    if not radius_configured():
        return None
    if not username or not password:
        return None

    cfg = get_config()
    username = username.strip()

    try:
        import pyrad.packet
        from pyrad.client import Client
        from pyrad.dictionary import Dictionary

        client = Client(
            server=cfg.server,
            authport=cfg.port,
            secret=cfg.secret.encode("utf-8"),
            timeout=cfg.timeout,
            dict=Dictionary(),
        )
        req = client.CreateAuthPacket(code=pyrad.packet.AccessRequest, User_Name=username)
        req["User-Password"] = req.PwCrypt(password)
        if cfg.nas_identifier:
            req["NAS-Identifier"] = cfg.nas_identifier

        reply = client.SendPacket(req, retries=cfg.retries)

        if reply.code != pyrad.packet.AccessAccept:
            code = getattr(reply, "code", None)
            logger.info("radius | %s: Access-Reject (code=%s)", username, code)
            return None

        attr_values = _role_attribute_values(reply, cfg.role_attribute)
        role, matched = _map_role(cfg, attr_values)
        logger.info(
            "radius | вход %s, role=%s, атрибут=%s=%r",
            username,
            role,
            cfg.role_attribute,
            matched,
        )
        return {
            "username": username,
            "role": role,
            "role_attribute": cfg.role_attribute if matched else None,
            "role_attribute_value": matched,
            "role_values": attr_values,
        }
    except Exception as exc:
        logger.warning("radius | ошибка для %s: %s", username, exc)
        return None
