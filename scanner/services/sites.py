"""Иерархия sites (slug + parent) для фильтров compliance и object scope."""

from __future__ import annotations

from typing import Any

from core.models import Site


def upsert_site(slug: str, *, name: str = "", parent_slug: str = "") -> Site:
    slug = (slug or "").strip()
    if not slug:
        raise ValueError("site slug обязателен")
    parent = None
    parent_slug = (parent_slug or "").strip()
    if parent_slug and parent_slug != slug:
        parent = Site.objects.filter(slug=parent_slug).first()
        if parent is None:
            parent = Site.objects.create(slug=parent_slug, name=parent_slug)
    site, _ = Site.objects.update_or_create(
        slug=slug,
        defaults={"name": (name or slug).strip() or slug, "parent": parent},
    )
    return site


def expand_site_slugs(site_slug: str) -> set[str]:
    """Slug + все дочерние площадки (рекурсивно)."""
    needle = (site_slug or "").strip().lower()
    if not needle:
        return set()
    rows = list(Site.objects.all().only("id", "slug", "parent_id"))
    if not rows:
        return {site_slug}

    by_parent: dict[int | None, list[Site]] = {}
    by_slug: dict[str, Site] = {}
    for row in rows:
        by_slug[row.slug.lower()] = row
        by_parent.setdefault(row.parent_id, []).append(row)

    root = by_slug.get(needle)
    if root is None:
        return {site_slug}

    result: set[str] = set()

    def walk(site: Site) -> None:
        result.add(site.slug)
        for child in by_parent.get(site.id, []):
            walk(child)

    walk(root)
    return result


def site_matches_filter(device_site: str, filter_site: str) -> bool:
    if not filter_site:
        return True
    device_site = (device_site or "").strip()
    if not device_site:
        return False
    allowed = {s.lower() for s in expand_site_slugs(filter_site)}
    return device_site.lower() in allowed


def list_sites_public() -> list[dict[str, Any]]:
    rows = Site.objects.select_related("parent").order_by("slug")
    return [
        {
            "slug": row.slug,
            "name": row.name or row.slug,
            "parent_slug": row.parent.slug if row.parent else "",
        }
        for row in rows
    ]
