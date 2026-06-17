"""Rewrite Oxidized Web UI responses for /oxidized-proxy embedding."""

from __future__ import annotations

import re

from django.conf import settings

OXIDIZED_PROXY_PREFIX = "/oxidized-proxy"

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
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)/")
_QUOTED_ABS_PATH_RE = re.compile(
    r"""(?P<q>["'])/(?!oxidized-proxy)(?P<path>[^"']*)"""
)
_BASE_TAG_RE = re.compile(r"<base\s[^>]*>", re.IGNORECASE)


def rewrite_proxy_location(location: str) -> str:
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


def _rewrite_quoted_paths(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        path = match.group("path")
        if path.startswith(("http://", "https://", "//")):
            return match.group(0)
        return f'{match.group("q")}{OXIDIZED_PROXY_PREFIX}/{path}'

    return _QUOTED_ABS_PATH_RE.sub(repl, text)


def _inject_base_tag(text: str) -> str:
    if _BASE_TAG_RE.search(text):
        return text
    base = f'<base href="{OXIDIZED_PROXY_PREFIX}/">'
    if re.search(r"<head[^>]*>", text, re.IGNORECASE):
        return re.sub(r"(<head[^>]*>)", rf"\1\n    {base}", text, count=1, flags=re.IGNORECASE)
    return text


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

    if "html" in ct:
        text = _ROOT_ATTR_RE.sub(
            lambda m: (
                f"{m.group('attr')}={m.group('q')}"
                f"{OXIDIZED_PROXY_PREFIX}/{m.group('rest')}"
            ),
            text,
        )
        text = _inject_base_tag(text)
    elif "javascript" in ct or "json" in ct:
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


def hop_headers() -> frozenset[str]:
    return _HOP_HEADERS


def embed_block_headers() -> frozenset[str]:
    return _EMBED_BLOCK_HEADERS
