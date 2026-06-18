"""Slack Block Kit и Microsoft Teams MessageCard."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 15.0

_KIND_COLORS = {
    "error": "#e01e5a",
    "report": "#2eb886",
    "degrade": "#ecb22e",
    "compliance": "#36a64f",
}


def send_slack(
    webhook_url: str,
    subject: str,
    body: str,
    *,
    kind: str = "error",
) -> tuple[bool, str]:
    url = (webhook_url or "").strip()
    if not url:
        return False, "Slack: webhook URL не задан"
    color = _KIND_COLORS.get(kind, "#439fe0")
    text = (body or "").strip()[:3000]
    title = (subject or "Backup Tools")[:150]
    payload: dict[str, Any] = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title, "emoji": True},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": text or "_empty_"},
            },
        ],
        "attachments": [{"color": color, "text": ""}],
    }
    try:
        resp = httpx.post(url, json=payload, timeout=TIMEOUT)
        if resp.is_success or resp.status_code == 200:
            return True, "Slack: отправлено"
        return False, f"Slack: HTTP {resp.status_code}"
    except Exception as exc:
        logger.warning("notify | slack failed: %s", exc)
        return False, f"Slack: {exc}"


def send_teams(
    webhook_url: str,
    subject: str,
    body: str,
    *,
    kind: str = "error",
) -> tuple[bool, str]:
    url = (webhook_url or "").strip()
    if not url:
        return False, "Teams: webhook URL не задан"
    color = _KIND_COLORS.get(kind, "#439FE0").lstrip("#")
    text = (body or "").strip()[:3000]
    title = (subject or "Backup Tools")[:150]
    payload: dict[str, Any] = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color,
        "summary": title,
        "sections": [
            {
                "activityTitle": title,
                "text": text or "—",
            }
        ],
    }
    try:
        resp = httpx.post(url, json=payload, timeout=TIMEOUT)
        if resp.is_success or resp.status_code == 200:
            return True, "Teams: отправлено"
        return False, f"Teams: HTTP {resp.status_code}"
    except Exception as exc:
        logger.warning("notify | teams failed: %s", exc)
        return False, f"Teams: {exc}"
