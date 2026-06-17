#!/usr/bin/env python3
"""CLI: сканирование сети по инвентарю и синхронизация с Oxidized."""

import argparse
import asyncio
import json
import os
import sys

# Позволяет запускать из корня проекта: python scanner/scan_inventory.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.log_config import setup_logging
from app.inventory import (
    load_inventory,
    update_oxidized_credentials,
    init_db,
)
from app.scanner import scan_devices, discover_and_enrich, apply_device_names


async def run_scan(discover: bool = False, sync: bool = True) -> None:
    setup_logging()
    init_db()
    inventory = load_inventory()

    if discover and inventory.networks:
        nets = ", ".join(n.network for n in inventory.networks)
        print(f"Сканирование подсетей: {nets}")
        saved = await discover_and_enrich(
            inventory.networks,
            inventory.devices,
            inventory.credential_profiles,
        )
        if saved:
            print(f"Сохранено новых устройств: {len(saved)}")
            inventory = load_inventory()
        else:
            print("Новых устройств не найдено")

    print(f"Сканирование {len(inventory.devices)} устройств...")
    summary = await scan_devices(inventory.devices)

    updated_devices, names_changed = await apply_device_names(
        inventory.devices,
        summary.results,
        inventory.credential_profiles,
    )
    if names_changed:
        inventory = load_inventory()
        print("Имена устройств обновлены с устройств (SSH identity)")

    print(f"\nРезультаты ({summary.scanned_at.isoformat()}):")
    print(f"  Всего:   {summary.total}")
    print(f"  Online:  {summary.online}")
    print(f"  Partial: {summary.partial}")
    print(f"  Offline: {summary.offline}")
    print()

    for r in summary.results:
        ports = ", ".join(
            f"{p.port}{'✓' if p.open else '✗'}" for p in r.ports
        )
        ping = "✓" if r.ping_ok else "✗"
        print(f"  [{r.status.value:8}] {r.name} ({r.ip}) ping={ping} ports={ports}")

    if sync:
        update_oxidized_credentials(inventory)
        print("\nКонфиг Oxidized обновлён (HTTP source сканера)")


def main():
    parser = argparse.ArgumentParser(
        description="Сканирование сети по инвентарю для Oxidized"
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Ping sweep подсетей из БД перед сканированием",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Не обновлять конфиг Oxidized",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывести результат в JSON",
    )
    args = parser.parse_args()

    if args.json:
        init_db()
        inventory = load_inventory()
        summary = asyncio.run(scan_devices(inventory.devices))
        print(json.dumps(summary.model_dump(), indent=2, default=str))
        return

    asyncio.run(run_scan(discover=args.discover, sync=not args.no_sync))


if __name__ == "__main__":
    main()
