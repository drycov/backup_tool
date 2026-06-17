import asyncio
from typing import Callable
import ipaddress
import logging
import os
import platform
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from services.device_probe import fetch_device_hostname
from services.schemas import (
    CredentialProfile,
    Device,
    PortResult,
    ScanResult,
    ScanStatus,
    ScanSummary,
)

DEFAULT_ROUTEROS_SSH_PORT = int(os.environ.get("ROUTEROS_SSH_PORT", "44333"))
DISCOVERED_NAME_PREFIX = "discovered-"

PING_TIMEOUT_SEC = 2
PORT_TIMEOUT_SEC = 2
DEFAULT_SCAN_PORTS = [DEFAULT_ROUTEROS_SSH_PORT]

logger = logging.getLogger(__name__)


def _sanitize_device_name(raw: str) -> str:
    name = raw.strip().rstrip(".").lower()
    name = re.sub(r"[^\w\-.]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name


def fallback_device_name(ip: str) -> str:
    return f"{DISCOVERED_NAME_PREFIX}{ip.replace('.', '-')}"


def build_group_credentials(
    profiles: list[CredentialProfile],
) -> dict[str, tuple[str, str]]:
    return {p.group_name: (p.username, p.password) for p in profiles}


def _unique_device_name(candidate: str | None, ip: str, existing_names: set[str]) -> str:
    if candidate:
        safe = _sanitize_device_name(candidate)
        if safe and safe not in existing_names:
            return safe
        if safe:
            suffixed = f"{safe}-{ip.replace('.', '-')}"
            if suffixed not in existing_names:
                return suffixed

    fallback = fallback_device_name(ip)
    if fallback not in existing_names:
        return fallback
    return f"{fallback}-dup"


def _probe_device_name_sync(
    ip: str,
    port: int,
    group: str,
    model: str,
    credentials_by_group: dict[str, tuple[str, str]],
    existing_names: set[str],
) -> str:
    creds = credentials_by_group.get(group)
    if creds and port:
        hostname = fetch_device_hostname(ip, port, creds[0], creds[1], model)
        return _unique_device_name(hostname, ip, existing_names)
    return _unique_device_name(None, ip, existing_names)


async def device_name_from_device(
    ip: str,
    group: str,
    port: int,
    model: str,
    credentials_by_group: dict[str, tuple[str, str]],
    existing_names: set[str],
) -> tuple[str, bool]:
    """Имя устройства и флаг успешной проверки (SSH-порт доступен)."""
    port_result = await check_port(ip, port)
    if not port_result.open:
        return _unique_device_name(None, ip, existing_names), False

    name = await asyncio.to_thread(
        _probe_device_name_sync,
        ip,
        port,
        group,
        model,
        credentials_by_group,
        existing_names,
    )
    return name, True


async def probe_discovered_device(
    ip: str,
    group: str,
    port: int,
    model: str,
    credentials_by_group: dict[str, tuple[str, str]],
    existing_names: set[str],
) -> Device | None:
    """Проверить хост и вернуть устройство только при успешной проверке порта."""
    name, verified = await device_name_from_device(
        ip, group, port, model, credentials_by_group, existing_names
    )
    if not verified:
        logger.info("discover | skip | %s — SSH-порт %s недоступен", ip, port)
        return None

    return Device(
        name=name,
        ip=ip,
        model=model,
        group=group,
        enabled=True,
        ports=[port],
    )


def _log_scan_result(result: ScanResult) -> None:
    open_ports = [p.port for p in result.ports if p.open]
    logger.info(
        "scan | %-8s | %s (%s) | ping=%s | ports_open=%s | group=%s",
        result.status.value,
        result.name,
        result.ip,
        "yes" if result.ping_ok else "no",
        ",".join(map(str, open_ports)) or "-",
        result.group,
    )


def _should_rename_from_device(name: str, ip: str) -> bool:
    return name.startswith(DISCOVERED_NAME_PREFIX) or name == ip


async def apply_device_names(
    devices: list[Device],
    scan_results: list[ScanResult],
    credential_profiles: list[CredentialProfile],
) -> tuple[list[Device], bool]:
    """Обновить имена online/partial устройств из system identity (SSH)."""
    active_ips = {
        r.ip
        for r in scan_results
        if r.status in (ScanStatus.ONLINE, ScanStatus.PARTIAL)
    }
    if not active_ips:
        return devices, False

    credentials_by_group = build_group_credentials(credential_profiles)
    names_in_use = {d.name for d in devices}

    to_rename = [
        d
        for d in devices
        if d.ip in active_ips and _should_rename_from_device(d.name, d.ip)
    ]

    rename_map: dict[str, str] = {}
    for device in to_rename:
        port = device.ports[0] if device.ports else DEFAULT_ROUTEROS_SSH_PORT
        new_name, verified = await device_name_from_device(
            device.ip,
            device.group,
            port,
            device.model,
            credentials_by_group,
            names_in_use - {device.name},
        )
        if not verified:
            continue
        rename_map[device.ip] = new_name
        names_in_use.discard(device.name)
        names_in_use.add(new_name)
        if new_name != device.name:
            logger.info(
                "scan | rename | %s (%s) -> %s (SSH identity)",
                device.name,
                device.ip,
                new_name,
            )

    changed = False
    for device in devices:
        new_name = rename_map.get(device.ip)
        if not new_name or new_name == device.name:
            continue
        updated_device = device.model_copy(update={"name": new_name})
        from services.inventory import rename_device_async

        await rename_device_async(device.name, updated_device)
        changed = True

    if changed:
        from services.inventory import load_inventory_async

        inventory = await load_inventory_async()
        return inventory.devices, True

    return devices, False


async def ping_host(ip: str) -> bool:
    """ICMP ping (Windows / Linux)."""
    system = platform.system().lower()
    if system == "windows":
        cmd = ["ping", "-n", "1", "-w", str(PING_TIMEOUT_SEC * 1000), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(PING_TIMEOUT_SEC), ip]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return proc.returncode == 0


async def check_port(ip: str, port: int) -> PortResult:
    start = time.monotonic()
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(ip, port),
            timeout=PORT_TIMEOUT_SEC,
        )
        writer.close()
        await writer.wait_closed()
        latency = (time.monotonic() - start) * 1000
        return PortResult(port=port, open=True, latency_ms=round(latency, 1))
    except (asyncio.TimeoutError, OSError, ConnectionRefusedError):
        return PortResult(port=port, open=False)


async def scan_device(device: Device) -> ScanResult:
    now = datetime.now(timezone.utc)
    ping_ok = await ping_host(device.ip)

    ports_to_check = device.ports or DEFAULT_SCAN_PORTS
    port_results = await asyncio.gather(
        *[check_port(device.ip, p) for p in ports_to_check]
    )

    open_ports = [p for p in port_results if p.open]

    if ping_ok and open_ports:
        status = ScanStatus.ONLINE
    elif ping_ok and not open_ports:
        status = ScanStatus.PARTIAL
    elif not ping_ok and open_ports:
        status = ScanStatus.PARTIAL
    else:
        status = ScanStatus.OFFLINE

    return ScanResult(
        name=device.name,
        ip=device.ip,
        status=status,
        ping_ok=ping_ok,
        ports=list(port_results),
        scanned_at=now,
        model=device.model,
        group=device.group,
        enabled=device.enabled,
    )


async def scan_devices(
    devices: list[Device],
    on_progress: Callable[[int, int, ScanResult], None] | None = None,
) -> ScanSummary:
    enabled = [d for d in devices if d.enabled]
    logger.info("scan | start | devices=%d (enabled=%d)", len(devices), len(enabled))
    now = datetime.now(timezone.utc)

    total = len(enabled)
    results: list[ScanResult] = []
    if not enabled:
        return ScanSummary(
            total=0,
            online=0,
            offline=0,
            partial=0,
            scanned_at=now,
            results=[],
        )

    tasks = [asyncio.create_task(scan_device(d)) for d in enabled]
    done = 0
    for task in asyncio.as_completed(tasks):
        result = await task
        results.append(result)
        done += 1
        if on_progress:
            on_progress(done, total, result)

    for result in results:
        _log_scan_result(result)

    online = sum(1 for r in results if r.status == ScanStatus.ONLINE)
    offline = sum(1 for r in results if r.status == ScanStatus.OFFLINE)
    partial = sum(1 for r in results if r.status == ScanStatus.PARTIAL)

    logger.info(
        "scan | done | total=%d online=%d partial=%d offline=%d",
        len(results),
        online,
        partial,
        offline,
    )

    return ScanSummary(
        total=len(results),
        online=online,
        offline=offline,
        partial=partial,
        scanned_at=now,
        results=results,
    )


def discover_hosts_in_network(network: str) -> list[str]:
    """Сканирование подсети: ping sweep (параллельно через subprocess)."""
    try:
        net = ipaddress.ip_network(network, strict=False)
    except ValueError:
        logger.warning("discover | invalid network=%s", network)
        return []

    hosts = [str(ip) for ip in net.hosts()]
    if len(hosts) > 254:
        hosts = hosts[:254]

    logger.info("discover | ping sweep | network=%s hosts=%d", network, len(hosts))

    alive: list[str] = []
    system = platform.system().lower()

    def ping_one(ip: str) -> bool:
        if system == "windows":
            cmd = ["ping", "-n", "1", "-w", "500", ip]
        else:
            cmd = ["ping", "-c", "1", "-W", "1", ip]
        result = subprocess.run(cmd, capture_output=True, timeout=3)
        return result.returncode == 0

    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = {pool.submit(ping_one, ip): ip for ip in hosts}
        for future in as_completed(futures):
            ip = futures[future]
            try:
                if future.result():
                    alive.append(ip)
            except Exception:
                pass

    alive_sorted = sorted(alive, key=lambda x: ipaddress.ip_address(x))
    logger.info(
        "discover | ping sweep | network=%s alive=%d",
        network,
        len(alive_sorted),
    )
    return alive_sorted


async def discover_and_enrich(
    network_entries: list,
    existing_devices: list[Device],
    credential_profiles: list[CredentialProfile] = [],
    default_model: str = "routeros",
    default_group: str = "discovered",
    on_progress: Callable[[int, int, str], None] | None = None,
    on_device_saved: Callable[[Device], None] | None = None,
) -> list[Device]:
    """Сканирует подсети; каждое проверенное устройство сразу сохраняется в БД."""
    from services.inventory import add_device_async

    logger.info(
        "discover | start | networks=%d existing_devices=%d",
        len(network_entries),
        len(existing_devices),
    )
    known_ips = {d.ip for d in existing_devices}
    names_in_use = {d.name for d in existing_devices}
    credentials_by_group = build_group_credentials(credential_profiles)
    saved_devices: list[Device] = []
    port = DEFAULT_ROUTEROS_SSH_PORT

    for idx, entry in enumerate(network_entries, start=1):
        subnet = entry.network if hasattr(entry, "network") else str(entry)
        group_name = (
            entry.group_name if hasattr(entry, "group_name") else default_group
        )

        if on_progress:
            on_progress(idx - 1, len(network_entries), subnet)

        alive_ips = await asyncio.to_thread(discover_hosts_in_network, subnet)
        skipped = sum(1 for ip in alive_ips if ip in known_ips)
        for ip in alive_ips:
            if ip in known_ips:
                continue

            device = await probe_discovered_device(
                ip,
                group_name,
                port,
                default_model,
                credentials_by_group,
                names_in_use,
            )
            if not device:
                continue

            await add_device_async(device)
            names_in_use.add(device.name)
            known_ips.add(ip)
            saved_devices.append(device)

            from_device = not device.name.startswith(DISCOVERED_NAME_PREFIX)
            logger.info(
                "discover | saved | %s (%s) group=%s name_from=%s",
                device.name,
                device.ip,
                group_name,
                "device" if from_device else "fallback",
            )
            if on_device_saved:
                on_device_saved(device)

        if skipped:
            logger.info(
                "discover | subnet=%s skipped_known=%d",
                subnet,
                skipped,
            )

        if on_progress:
            on_progress(idx, len(network_entries), subnet)

    logger.info("discover | done | saved=%d", len(saved_devices))
    return saved_devices
