# Уведомления о бэкапах

Telegram и Email для трёх типов событий. Настройки: **UI → Настройки → Уведомления** или `.env` / `PUT /api/settings/backup`.

## Типы уведомлений

| Тип | Когда | Telegram chat | Email to |
|-----|-------|---------------|----------|
| **Ошибки** | Сбой Oxidized (retries exhausted), ошибка MikroTik backup | `telegram_chat_notify` | `smtp_to_notify` |
| **Отчёты** | Успешный цикл: конфиг изменился **или** binary/export fail | `telegram_chat_report` (fallback: notify) | `smtp_to_report` |
| **Деградация** | Фоновая проверка compliance (stale/offline/overdue/failed) | `telegram_chat_notify` | `smtp_to_notify` |

### Ошибки (error)

- Oxidized worker: статус `fail` / `no_connection` после исчерпания retries
- MikroTik binary/export: исключение при SFTP/SSH

### Отчёты (report)

Отправляется **не на каждый успешный бэкап**, а когда:

- конфиг изменился в Git (`stored=true`), **или**
- MikroTik binary/export завершился с ошибкой

Если конфиг не менялся и binary OK — отчёт **не** шлётся (снижение шума).

### Деградация (degrade)

Фоновый поток `degradation_monitor` (старт при launch scanner):

| Категория | Условие |
|-----------|---------|
| Ошибки бэкапа | last status `fail` / `no_connection` |
| Просроченные | нет бэкапа / last backup старше `2 × interval` |
| Stale | конфиг не менялся > `stale_days_threshold` дней |
| Offline | scan: устройство offline |

Параметры UI:

| Поле | По умолчанию | Описание |
|------|--------------|----------|
| Stale, дней | 30 | Порог «нет изменений конфига» |
| Cooldown, ч | 24 | Не повторять alert с тем же числом устройств |
| Проверка, сек | 3600 | Интервал фоновой проверки |

**Cooldown:** повторное уведомление по категории подавляется, если число устройств не изменилось. Когда проблема исчезает — состояние сбрасывается, следующий инцидент снова уведомит.

## Telegram

1. Создайте bot через [@BotFather](https://t.me/BotFather)
2. Получите chat ID (`@userinfobot` или `getUpdates` после сообщения боту)
3. UI: Bot token, Chat ID (ошибки), Chat ID (отчёты)

Для групп chat ID отрицательный (напр. `-1001234567890`).

## SMTP

- SSL (SMTPS) на порту 465 по умолчанию
- Без SSL — STARTTLS на порту 587

## Переменные `.env`

```env
ERROR_NOTIFICATION_TELEGRAM=false
ERROR_NOTIFICATION_EMAIL=false
REPORT_SEND_TELEGRAM=false
REPORT_SEND_EMAIL=false
DEGRADE_NOTIFICATION_TELEGRAM=false
DEGRADE_NOTIFICATION_EMAIL=false
TELEGRAM_ACCESS_TOKEN=
TELEGRAM_CHATID_NOTIFY=
TELEGRAM_CHATID_REPORT=
STALE_DAYS_THRESHOLD=30
ALERT_COOLDOWN_HOURS=24
DEGRADE_CHECK_INTERVAL_SEC=3600
SMTP_SERVER=
SMTP_PORT=465
SMTP_USER=
SMTP_PASSWORD=
SMTP_SSL=true
SMTP_FROM_MAIL=
SMTP_TO_MAIL_NOTIFY=
SMTP_TO_MAIL_REPORT=
```

При первом запуске импортируются в `backup_config` (PostgreSQL).

## API

```http
GET  /api/settings/backup
PUT  /api/settings/backup
POST /api/settings/backup/test-notify
POST /api/settings/backup/degrade-check
```

### Тест уведомления

```http
POST /api/settings/backup/test-notify
{"kind": "error"}
{"kind": "report"}
{"kind": "degrade"}
```

Тест **использует галочки и chat ID из формы** (можно не сохранять перед тестом). Token/password — из формы, если введены; иначе из БД.

Пример с формой:

```json
{
  "kind": "error",
  "error_notify_telegram": true,
  "telegram_chat_notify": "8328036041"
}
```

### Ручная проверка деградации

```http
POST /api/settings/backup/degrade-check
```

Ответ: `{"status":"ok","sent":2}` или `{"skipped":1}` если каналы выключены.

## UI — кнопки

| Кнопка | Действие |
|--------|----------|
| Сохранить уведомления | `PUT /api/settings/backup` |
| Тест отчёта | test-notify `kind=report` |
| Тест ошибки | test-notify `kind=error` |
| Тест деградации | test-notify `kind=degrade` |
| Проверить деградацию | немедленный `degrade-check` |

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| Тест: «не задан bot token» | Введите token и **Сохранить**, или укажите в поле перед тестом |
| Telegram 401 Unauthorized | Неверный token |
| Chat not found | Напишите боту `/start`; проверьте chat ID |
| Тест OK, реальных error нет | Включите галочку + **Сохранить** |
| Нет report | Норма, если конфиг не менялся и binary OK |
| Нет degrade | Включите Telegram/Email в блоке «Деградация» + **Сохранить** |
| Degrade с cooldown | Подождите или изменится число устройств в категории |

Проверка исходящего доступа из контейнера:

```bash
docker compose exec scanner python -c "
import httpx
r = httpx.get('https://api.telegram.org')
print(r.status_code)
"
```

## Связанные документы

- [MikroTik бэкапы](mikrotik-backups.md) — ошибки binary → error notify
- [Oxidized](oxidized.md) — worker errors
- Dashboard → Compliance — те же метрики, что для degrade
