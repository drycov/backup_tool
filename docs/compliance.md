# Compliance бэкапов

Dashboard и фоновые уведомления о деградации используют одну логику классификации устройств (`services/compliance.py`).

## Где смотреть

- **Dashboard** — блок «Compliance бэкапов»: процент OK, счётчики по состояниям, таблица устройств
- **API** — `GET /api/compliance/summary`
- **Уведомления** — фоновый `degradation_monitor` агрегирует проблемы в 4 категории

## Состояния устройства

Для каждого **включённого** устройства из инвентаря вычисляется primary state (худший из найденных issues):

| State | Метка | Условие |
|-------|-------|---------|
| `unreachable` | Offline (scan) | Последний scan: устройство offline |
| `failed` | Ошибка бэкапа | last status `fail` / `no_connection` |
| `never` | Нет бэкапа | Статус `never` и нет файла конфига (`mtime ≤ 0`) |
| `overdue` | Просрочен бэкап | last backup или mtime конфига старше `2 × interval` Oxidized |
| `stale` | Нет изменений | Успешный бэкап, но mtime конфига старше `stale_days_threshold` дней |
| `ok` | OK | Нет проблем |

**Interval** берётся из настроек Oxidized worker (`PUT /api/settings/oxidized`).  
**Stale threshold** — из настроек уведомлений (`stale_days_threshold`, UI → Уведомления).

Reachability — из последнего scan job (`scan_history`).

## Compliance %

```
compliance_pct = 100 × (устройства в состоянии ok) / (все enabled)
```

Если enabled устройств нет — 100%.

## API

```http
GET /api/compliance/summary?site=dc1&role=core&group=hex&state=stale&critical=true
GET /api/compliance/export?site=dc1&role=core
```

Permission: `inventory:read`.

Фильтры (все опциональны): `site`, `role`, `group`, `state`, `critical` (`true` / `false`).

Экспорт CSV — те же query-параметры; кнопка **CSV** на Dashboard или прямой запрос с cookie сессии.

## Ежедневный отчёт

UI → **Настройки → Уведомления**:

- включить Telegram и/или Email для **Ежедневный compliance-отчёт**
- задать **Час UTC** (по умолчанию 7)
- **Тест compliance** — немедленная отправка

Фоновый планировщик (`compliance_report`) проверяет раз в 5 минут; не чаще одного раза в сутки.

Ручной запуск: `POST /api/settings/backup/compliance-report-test` (permission `oxidized:write`).

Переменные `.env` (fallback): `COMPLIANCE_REPORT_TELEGRAM`, `COMPLIANCE_REPORT_EMAIL`, `COMPLIANCE_REPORT_HOUR_UTC`.

## Теги устройств

В модалке устройства: **site**, **role**, **critical** — используются в фильтрах compliance и в тексте отчётов/алертов.

## Политики per-group

UI → **Настройки → Группы → Политики per-group**:

| Поле | Значение |
|------|----------|
| `backup_interval_sec` | 0 = глобальный interval Oxidized; иначе 60–604800 |
| `model` | Переопределение модели для группы |
| `mk_binary_enabled` / `mk_export_enabled` | `null` = наследовать глобальные MK-настройки |

API: `GET/PUT /api/policies/groups`, `DELETE /api/policies/groups/<group_name>`.

## Webhook при деградации

UI → **Уведомления** → Webhook: JSON POST на URL при срабатывании деградации (наряду с Telegram/Email).

`.env`: `DEGRADE_WEBHOOK_ENABLED`, `DEGRADE_WEBHOOK_URL`.

## API (summary)

Пример ответа (сокращённо):

```json
{
  "generated_at": "2026-06-17T12:00:00+00:00",
  "stale_days_threshold": 30,
  "backup_interval_sec": 3600,
  "total_enabled": 42,
  "compliance_pct": 85.7,
  "counts": {
    "ok": 36,
    "failed": 2,
    "stale": 3,
    "overdue": 1,
    "never": 0,
    "unreachable": 0
  },
  "state_labels": { "ok": "OK", "failed": "Ошибка бэкапа", "...": "..." },
  "nodes": [
    {
      "name": "router-1",
      "ip": "10.0.0.1",
      "group": "hex",
      "site": "dc1",
      "role": "core",
      "critical": true,
      "state": "stale",
      "state_label": "Нет изменений",
      "issues": ["stale"],
      "last_status": "success",
      "reachability": "online"
    }
  ],
  "oxidized_error": null
}
```

Поле `oxidized_error` заполняется, если не удалось получить список узлов Oxidized.

## Связь с уведомлениями деградации

`collect_degradation_issues()` группирует issues в 4 bucket'а для alert'ов:

| Bucket | Issues |
|--------|--------|
| `backup_failed` | `failed` |
| `backup_overdue` | `overdue`, `never` |
| `config_stale` | `stale` |
| `device_offline` | `unreachable` |

Фоновый поток `degradation_monitor`:

- интервал: `degrade_check_interval_sec` (мин. 300 сек)
- cooldown: `alert_cooldown_hours` — не повторять alert, если число устройств в категории не изменилось
- при исчезновении проблемы в категории — запись `AlertState` сбрасывается

Ручной запуск: UI **Проверить деградацию** или `POST /api/settings/backup/degrade-check`.

Подробнее: [notifications.md](notifications.md).

## Связанные документы

- [Web UI](ui.md) — Dashboard
- [API](api.md) — эндпоинты compliance и degrade-check
- [Сканирование](scanning.md) — reachability для offline
- [Oxidized](oxidized.md) — interval и статусы узлов
