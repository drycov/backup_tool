"""Rewrite Oxidized Web UI responses for /oxidized-proxy embedding."""

from __future__ import annotations

import re

from django.conf import settings

OXIDIZED_PROXY_PREFIX = "/oxidized-proxy"
_PROXY_PREFIX_SLUG = "oxidized-proxy"

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

_ROOT_ATTR_RE = re.compile(
    r"(?P<attr>href|src|action)\s*=\s*(?P<q>['\"])/"
    r"(?!oxidized-proxy(?:/|$))(?P<rest>[^'\"]*)"
)
_CSS_URL_RE = re.compile(
    r"url\(\s*(['\"]?)/(?!oxidized-proxy(?:/|$))"
)
_QUOTED_ABS_PATH_RE = re.compile(
    r"""(?P<q>["'])/(?!oxidized-proxy(?:/|$))(?P<path>[^"']*)"""
)


def upstream_target(path: str = "", query_string: str = "") -> str:
    """Map incoming /oxidized-proxy/... request to Oxidized upstream path."""
    clean = (path or "").lstrip("/")
    if clean == _PROXY_PREFIX_SLUG:
        clean = ""
    elif clean.startswith(f"{_PROXY_PREFIX_SLUG}/"):
        clean = clean[len(_PROXY_PREFIX_SLUG) + 1 :]
    target = f"/{clean}" if clean else "/"
    if query_string:
        target = f"{target}?{query_string}"
    return target


def _to_proxy_path(path: str) -> str:
    path = path.lstrip("/")
    if not path or path == _PROXY_PREFIX_SLUG:
        return f"{OXIDIZED_PROXY_PREFIX}/"
    if path.startswith(f"{_PROXY_PREFIX_SLUG}/"):
        return f"{OXIDIZED_PROXY_PREFIX}/{path[len(_PROXY_PREFIX_SLUG) + 1:]}"
    return f"{OXIDIZED_PROXY_PREFIX}/{path}"


def rewrite_proxy_location(location: str) -> str:
    location = location.strip()
    for base in (settings.OXIDIZED_URL, settings.OXIDIZED_PUBLIC_URL):
        if location.startswith(base):
            suffix = location[len(base) :] or "/"
            if not suffix.startswith("/"):
                suffix = f"/{suffix}"
            if suffix.startswith(OXIDIZED_PROXY_PREFIX):
                return suffix
            return f"{OXIDIZED_PROXY_PREFIX}{suffix}"
    if location.startswith(OXIDIZED_PROXY_PREFIX):
        return location
    if location.startswith("/"):
        return f"{OXIDIZED_PROXY_PREFIX}{location}"
    return location


def _rewrite_quoted_paths(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        path = match.group("path")
        if path.startswith(("http://", "https://", "//")):
            return match.group(0)
        return f'{match.group("q")}{_to_proxy_path(path)}'

    return _QUOTED_ABS_PATH_RE.sub(repl, text)


def rewrite_proxy_body(content: bytes, content_type: str) -> bytes:
    if not content:
        return content
    ct = (content_type or "").lower()
    if not any(token in ct for token in ("html", "css", "javascript", "json", "text")):
        return content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content

    text = text.replace(f"{settings.OXIDIZED_URL}/", f"{OXIDIZED_PROXY_PREFIX}/")
    text = text.replace(
        f"{settings.OXIDIZED_PUBLIC_URL}/", f"{OXIDIZED_PROXY_PREFIX}/"
    )
    text = _rewrite_quoted_paths(text)

    if "html" in ct or "javascript" in ct or "json" in ct:
        text = _ROOT_ATTR_RE.sub(
            lambda m: (
                f"{m.group('attr')}={m.group('q')}"
                f"{_to_proxy_path(m.group('rest'))}"
            ),
            text,
        )

    if "css" in ct:
        text = _CSS_URL_RE.sub(
            lambda m: f"url({m.group(1)}{OXIDIZED_PROXY_PREFIX}/",
            text,
        )

    while f"{OXIDIZED_PROXY_PREFIX}/{_PROXY_PREFIX_SLUG}/" in text:
        text = text.replace(
            f"{OXIDIZED_PROXY_PREFIX}/{_PROXY_PREFIX_SLUG}/",
            f"{OXIDIZED_PROXY_PREFIX}/",
        )

    return text.encode("utf-8")


def hop_headers() -> frozenset[str]:
    return _HOP_HEADERS


def embed_block_headers() -> frozenset[str]:
    return _EMBED_BLOCK_HEADERS
