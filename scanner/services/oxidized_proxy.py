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
    r"(?P<attr>href|src|action)\s*=\s*(?P<q>['\"])/(?P<rest>[^'\"]*)"
)
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)/(?P<rest>[^)'\"\s]*)")
_QUOTED_ABS_PATH_RE = re.compile(r"""(?P<q>["'])/(?P<path>[^"']*)""")


def oxidized_base_url() -> str:
    """Upstream Oxidized root URL without accidental /oxidized-proxy suffix."""
    base = settings.OXIDIZED_URL.rstrip("/")
    if base.endswith(OXIDIZED_PROXY_PREFIX):
        base = base[: -len(OXIDIZED_PROXY_PREFIX)]
    return base


def _strip_proxy_slug(path: str) -> str:
    """Remove repeated oxidized-proxy/ prefixes from a relative path."""
    clean = (path or "").lstrip("/")
    while clean == _PROXY_PREFIX_SLUG or clean.startswith(f"{_PROXY_PREFIX_SLUG}/"):
        if clean == _PROXY_PREFIX_SLUG:
            return ""
        clean = clean[len(_PROXY_PREFIX_SLUG) + 1 :]
    return clean


def _path_needs_proxy(path: str) -> bool:
    clean = path.lstrip("/")
    if not clean:
        return False
    return not (
        clean == _PROXY_PREFIX_SLUG or clean.startswith(f"{_PROXY_PREFIX_SLUG}/")
    )


def upstream_target(path: str = "", query_string: str = "") -> str:
    """Map incoming /oxidized-proxy/... request to Oxidized upstream path."""
    clean = _strip_proxy_slug(path or "")
    target = f"/{clean}" if clean else "/"
    if query_string:
        target = f"{target}?{query_string}"
    return target


def _to_proxy_path(path: str) -> str:
    clean = _strip_proxy_slug(path)
    if not clean:
        return f"{OXIDIZED_PROXY_PREFIX}/"
    return f"{OXIDIZED_PROXY_PREFIX}/{clean}"


def rewrite_proxy_location(location: str) -> str:
    from services.git_settings import public_url

    location = location.strip()
    for base in (oxidized_base_url(), public_url()):
        if location.startswith(base):
            suffix = location[len(base) :] or "/"
            if not suffix.startswith("/"):
                suffix = f"/{suffix}"
            return _to_proxy_path(suffix.lstrip("/"))
    if location.startswith(OXIDIZED_PROXY_PREFIX):
        return _to_proxy_path(location[len(OXIDIZED_PROXY_PREFIX) :].lstrip("/"))
    if location.startswith("/"):
        return _to_proxy_path(location.lstrip("/"))
    return location


def _rewrite_quoted_paths(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        path = match.group("path")
        if path.startswith(("http://", "https://", "//")):
            return match.group(0)
        if not _path_needs_proxy(path):
            return match.group(0)
        return f'{match.group("q")}{_to_proxy_path(path)}'

    return _QUOTED_ABS_PATH_RE.sub(repl, text)


def rewrite_proxy_body(content: bytes, content_type: str) -> bytes:
    from services.git_settings import public_url

    if not content:
        return content
    ct = (content_type or "").lower()
    if not any(token in ct for token in ("html", "css", "javascript", "json", "text")):
        return content
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return content

    pub = public_url()
    for base in (oxidized_base_url(), pub):
        text = text.replace(f"{base}/", f"{OXIDIZED_PROXY_PREFIX}/")

    text = _rewrite_quoted_paths(text)

    if "html" in ct or "javascript" in ct or "json" in ct:
        text = _ROOT_ATTR_RE.sub(
            lambda m: (
                m.group(0)
                if not _path_needs_proxy(m.group("rest"))
                else (
                    f"{m.group('attr')}={m.group('q')}"
                    f"{_to_proxy_path(m.group('rest'))}"
                )
            ),
            text,
        )

    if "css" in ct:
        text = _CSS_URL_RE.sub(
            lambda m: (
                m.group(0)
                if not _path_needs_proxy(m.group("rest"))
                else f"url({m.group(1)}{_to_proxy_path(m.group('rest'))}"
            ),
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
