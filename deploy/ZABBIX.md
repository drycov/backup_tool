# Zabbix — мониторинг Backup Tools

HTTP-интеграция для Zabbix 5.0+ (HTTP agent + LLD). Эндпоинты `/device/*` совместимы с legacy **RMB_Monitoring** (RealMikrotikBackup).

## Шаблоны

| Файл | Имя в Zabbix | Когда использовать |
|------|--------------|-------------------|
| **`deploy/zabbix/BackupTools_Monitoring.xml`** | `BackupTools_Monitoring` | **Рекомендуется** — полный мониторинг платформы + устройств |
| `deploy/zabbix/RMB_Monitoring.xml` | `RMB_Monitoring` | Миграция со старого RMB, только LLD устройств |

Импорт: **Configuration → Templates → Import**.

## Настройка Backup Tools

**UI (рекомендуется):** **Настройки → Система** — `Zabbix auth key`, включение мониторинга, TTL сессии, каталог бэкапов и др.

При первом запуске значения копируются из `.env`; дальше меняйте в UI. В `.env` остаются только bootstrap-параметры (`DATABASE_URL`, `JWT_SECRET`, порты).

```env
# bootstrap (опционально, если БД ещё пустая)
ZABBIX_AUTH_KEY=change-me-zabbix-secret
ZABBIX_MONITORING_ENABLED=true
SCANNER_PORT=8000
```

Пересборка после смены порта: `docker compose up -d --build scanner`

Альтернатива `{$AUTHKEY}`: API key `bk_...` (роль viewer) в заголовке `authkey`.

## Host в Zabbix

1. Host `backup-tools`, DNS/IP scanner → макрос `{HOST.CONN}`.
2. Шаблон **BackupTools_Monitoring**.
3. Макросы на host/template:

| Макрос | Пример | Описание |
|--------|--------|----------|
| `{$AUTHKEY}` | секрет из **Настройки → Система** | Обязательно |
| `{$BACKUPTOOLS.PORT}` | `8000` | `SCANNER_PORT` |
| `{$BACKUPTOOLS.SCHEME}` | `http` / `https` | За reverse proxy — `https` |
| `{$COMPLIANCE.WARN}` | `90` | Warning compliance % |
| `{$COMPLIANCE.CRIT}` | `80` | High compliance % |
| `{$DEVICES.OFFLINE.MAX}` | `5` | Порог offline |
| `{$OXIDIZED.QUEUE.MAX}` | `20` | Порог очереди Oxidized |

## Что мониторит BackupTools_Monitoring

### Платформа (без LLD)

| Item | Источник | Триггер |
|------|----------|---------|
| Health liveness | `GET /health` | status ≠ ok |
| Summary (master) | `GET /device/getsummary` | — |
| Compliance % | dependent | &lt; {$COMPLIANCE.WARN/CRIT} |
| Offline / failed / overdue | dependent counts | offline &gt; порога |
| Oxidized queue | dependent | &gt; {$OXIDIZED.QUEUE.MAX} |
| Platform ready | dependent `$.ready` | ≠ true (БД + worker) |

### Устройства (LLD из inventory)

Discovery `GET /device/getalldevices` → макросы `{#ID}`, `{#NAME}`, `{#IP}`, `{#GROUP}`, `{#SITE}`, `{#CRITICAL}`.

| Item prototype | Поле |
|----------------|------|
| Backup status | `$.laststatus` → `OK` или текст проблемы |
| Backup state code | `$.state` → ok / failed / overdue / … |

Триггеры:
- **Average** — любое устройство: laststatus ≠ OK
- **High** — только `critical=1` (фильтр LLD `{#CRITICAL}=1`)

## API

| URL | Auth | Ответ |
|-----|------|-------|
| `/health` | нет | Liveness scanner |
| `/device/getsummary` | authkey | Сводка compliance + Oxidized + ready |
| `/device/getalldevices` | authkey | LLD-массив устройств |
| `/device/getlaststatus?id=` | authkey | Статус одного устройства |

### getsummary (пример)

```json
{
  "status": "ok",
  "ready": true,
  "compliance_pct": 95.2,
  "devices_total": 1492,
  "devices_ok": 1420,
  "counts": {"ok": 1420, "failed": 12, "overdue": 30, "unreachable": 7},
  "oxidized_queue_depth": 3,
  "task_queue_pending": 0
}
```

### getlaststatus (пример)

```json
{
  "laststatus": "OK",
  "state": "ok",
  "ip": "10.0.0.1",
  "group": "hex",
  "site": "hex-dc1",
  "critical": "1",
  "reachability": "online",
  "last_backup_at": "2026-06-18T08:00:00+00:00"
}
```

`id` в query = поле `name` из inventory.

## Проверка

```bash
curl -s http://scanner:8000/health
curl -s -H "authkey: SECRET" http://scanner:8000/device/getsummary
curl -s -H "authkey: SECRET" http://scanner:8000/device/getalldevices | head
curl -s -H "authkey: SECRET" "http://scanner:8000/device/getlaststatus?id=ROUTER-01"
```

## Связанные документы

- [OBSERVABILITY.md](OBSERVABILITY.md) — Prometheus `/metrics`
- [ALERTS.md](ALERTS.md) — Grafana / Alertmanager
