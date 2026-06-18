# Наблюдаемость Backup Tools

## Структурированные логи

```env
LOG_FORMAT=json
LOG_LEVEL=INFO
```

Каждая запись — JSON в stdout с полями `ts`, `level`, `logger`, `message`, опционально `correlation_id`, `exception`.

Correlation ID:
- HTTP: заголовок `X-Correlation-ID` (если не передан — генерируется)
- Scan/backup job: `correlation_id` в `ScanJob` и `BackgroundTask`
- Ответ API возвращает `X-Correlation-ID`

## Prometheus

Эндпоинт: `GET /metrics` (без аутентификации; ограничьте доступ на reverse proxy).

| Метрика | Тип | Описание |
|---------|-----|----------|
| `backup_success_total{group,model}` | Counter | Успешные бэкапы Oxidized |
| `devices_offline` | Gauge | Offline по compliance/scan |
| `oxidized_queue_depth` | Gauge | Узлы due + running |
| `compliance_pct` | Gauge | % compliance |
| `task_queue_depth{task_type}` | Gauge | Pending задачи в БД |
| `task_runs_total{task_type,status}` | Counter | Выполнение фоновых задач |

```env
METRICS_ENABLED=true
```

### Пример scrape (Prometheus)

```yaml
scrape_configs:
  - job_name: backup-tools
    metrics_path: /metrics
    static_configs:
      - targets: ["scanner:8000"]
```

## Фоновые задачи

Очередь в PostgreSQL (`background_tasks`), без Redis.

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `TASK_WORKER_ENABLED` | `true` | Включить обработку очереди |
| `TASK_WORKER_INLINE` | `true` | Daemon-поток в web-контейнере |
| `TASK_WORKER_POLL_SEC` | `30` | Интервал опроса |

Отдельный воркер (production):

```bash
docker compose --profile worker up -d scanner-worker
```

С `scanner-worker` задайте `TASK_WORKER_INLINE=false` в `scanner`, чтобы не дублировать воркер.

### Периодический scan

Настройки → Scan: включить «Периодический scan», интервал (1–168 ч), discovery on/off.

Или через env при первой инициализации: `SCAN_SCHEDULE_ENABLED`, `SCAN_SCHEDULE_INTERVAL_HOURS`, `SCAN_SCHEDULE_DISCOVER`.

## Аудит

```env
AUDIT_RETENTION_DAYS=365
```

Ручная очистка: `python manage.py purge_audit`

Экспорт: `GET /api/audit/export` (admin, CSV).

Новые события: `settings.update`, `auth.login`, `auth.login_ldap`, `auth.login_failed`, `user.scope_update`, `compliance.export`, `compliance.report_send`.

## Zabbix

Шаблон **RMB_Monitoring** (HTTP LLD, статус бэкапа по устройствам): см. [ZABBIX.md](ZABBIX.md).
