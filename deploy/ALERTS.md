# Алерты Grafana / Alertmanager

Метрики с `/metrics` — основа для алертов. Существующие Telegram/webhook для degrade и compliance остаются; Prometheus дополняет их для SRE-дашбордов.

## Примеры правил (Prometheus)

```yaml
groups:
  - name: backup-tools
    rules:
      - alert: BackupToolsComplianceLow
        expr: compliance_pct < 80
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Compliance ниже 80% ({{ $value }}%)"

      - alert: BackupToolsDevicesOffline
        expr: devices_offline > 5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "{{ $value }} устройств offline"

      - alert: BackupToolsOxidizedQueueBacklog
        expr: oxidized_queue_depth > 20
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Очередь Oxidized: {{ $value }} узлов"

      - alert: BackupToolsTaskFailures
        expr: increase(task_runs_total{status="failed"}[1h]) > 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Фоновые задачи падают (degrade/compliance/scan)"
```

## Alertmanager → webhook / Telegram

Используйте существующий webhook degrade (`degrade_webhook_enabled` в настройках backup) как шаблон URL.

Пример receiver (Alertmanager 0.27+):

```yaml
receivers:
  - name: backup-tools-telegram
    webhook_configs:
      - url: "https://api.telegram.org/bot<TOKEN>/sendMessage"
        send_resolved: true
        http_config:
          follow_redirects: true
```

Для кастомного JSON-webhook (как degrade notifier) — `webhook_configs` с телом через template или промежуточный bridge.

## Grafana

Дашборд: панели для `compliance_pct`, `devices_offline`, `oxidized_queue_depth`, `rate(backup_success_total[5m])`, `task_queue_depth`.

Datasource: Prometheus → target `scanner:8000/metrics`.

## Health vs readiness

- `GET /health` — liveness
- `GET /health/ready` — DB + Oxidized worker (для Kubernetes readiness)

Алерт на недоступность: `up{job="backup-tools"} == 0` или HTTP probe на `/health/ready` ≠ 200.
