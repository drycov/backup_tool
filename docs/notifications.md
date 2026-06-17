# Уведомления о бэкапах

Backup Tools отправляет уведомления при ошибках и успешных бэкапах — аналог RealMikrotikBackup (Telegram + Email).

Настройки: **UI → Настройки → Уведомления** или `.env` / `GET/PUT /api/settings/backup`.

## Типы уведомлений

| Тип | Когда | Каналы |
|-----|-------|--------|
| **Error** | Ошибка MikroTik backup, сбой сбора | Telegram notify chat, Email notify |
| **Report** | После цикла worker (конфиг изменился или binary fail) | Telegram report chat, Email report |

Error-уведомления Oxidized (SSH fail, retries exhausted) логируются; отдельный hook для Ruby external — через логи контейнера.

## Переменные `.env`

```env
# Error notifications
ERROR_NOTIFICATION_TELEGRAM=false
ERROR_NOTIFICATION_EMAIL=false

# Success reports
REPORT_SEND_TELEGRAM=false
REPORT_SEND_EMAIL=false

# Telegram
TELEGRAM_ACCESS_TOKEN=
TELEGRAM_CHATID_NOTIFY=
TELEGRAM_CHATID_REPORT=

# SMTP
SMTP_SERVER=smtp.example.com
SMTP_PORT=465
SMTP_USER=
SMTP_PASSWORD=
SMTP_SSL=true
SMTP_FROM_MAIL=backup@example.com
SMTP_TO_MAIL_NOTIFY=ops@example.com
SMTP_TO_MAIL_REPORT=ops@example.com
```

| Переменная | Описание |
|------------|----------|
| `ERROR_NOTIFICATION_TELEGRAM` | Telegram при ошибках |
| `ERROR_NOTIFICATION_EMAIL` | Email при ошибках |
| `REPORT_SEND_TELEGRAM` | Telegram при успешном отчёте |
| `REPORT_SEND_EMAIL` | Email при успешном отчёте |
| `TELEGRAM_ACCESS_TOKEN` | Bot token от @BotFather |
| `TELEGRAM_CHATID_NOTIFY` | Chat ID для ошибок |
| `TELEGRAM_CHATID_REPORT` | Chat ID для отчётов |
| `SMTP_*` | Параметры SMTP (SSL или STARTTLS) |

Секреты (`telegram_token`, `smtp_password`, `encrypt_password`) в API маскируются как `*_set: true/false`.

## Web UI

**Настройки → Уведомления**

- Чекбоксы каналов error/report
- Поля Telegram и SMTP
- Кнопки **Тест error** / **Тест report**

## API

### Получить / сохранить

```http
GET  /api/settings/backup
PUT  /api/settings/backup
```

Permission: `oxidized:read` (GET), `oxidized:write` (PUT).

Пример PUT (фрагмент):

```json
{
  "error_notify_telegram": true,
  "telegram_token": "123456:ABC...",
  "telegram_chat_notify": "-1001234567890",
  "report_send_email": true,
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 465,
  "smtp_ssl": true,
  "smtp_from": "backup@corp.local",
  "smtp_to_report": "netops@corp.local"
}
```

Чтобы не менять пароль/token, передайте `"********"` или omit поле.

### Тест

```http
POST /api/settings/backup/test-notify
Content-Type: application/json

{"kind": "error"}
{"kind": "report"}
```

Ответ:

```json
{
  "ok": true,
  "messages": ["Telegram: отправлено", "Email → ops@example.com: отправлено"]
}
```

## Формат сообщений

**Error:**

```
Backup Tools — ошибка бэкапа
Устройство: hex_r1_ukg
IP: 10.216.92.1
Статус: mikrotik_backup
Детали: Connection timeout
```

**Report:**

```
Backup Tools — отчёт о бэкапе
Устройство: hex_r1_ukg
IP: 10.216.92.1
Git: конфиг изменён
Binary/export: OK
```

## Требования сети

Контейнер `scanner` должен иметь исходящий доступ:

- `https://api.telegram.org` — Telegram Bot API
- SMTP-сервер (порт 465/587)

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| Telegram 401 | Проверить `TELEGRAM_ACCESS_TOKEN` |
| Chat not found | Убедиться, что bot добавлен в chat; верный chat ID |
| SMTP auth fail | `SMTP_USER` / `SMTP_PASSWORD`, SSL vs STARTTLS |
| Тест OK, реальных нет | Включить соответствующий чекбокс error/report |
| Нет report | Report шлётся только если конфиг изменился **или** binary fail |
