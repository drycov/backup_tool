# Сканирование

Scanner выполняет проверку доступности устройств из инвентаря и опционально **discovery** — автоматическое добавление новых хостов в подсетях.

## Режимы

| Режим | Параметр | Описание |
|-------|----------|----------|
| **Scan** | `POST /scan` | Проверка известных устройств из БД |
| **Discovery** | `POST /scan?discover=true` | Scan + ping sweep подсетей + добавление новых устройств |

## Алгоритм Scan

Для каждого устройства с `enabled: true`:

1. **ICMP ping** — timeout 2 сек
2. **TCP port check** — порты из поля `ports` (по умолчанию `44333`)
3. Статус:
   - `online` — ping OK и хотя бы один порт открыт
   - `partial` — ping OK, порты закрыты
   - `offline` — ping fail
   - `unknown` — ошибка проверки

Параллелизм ограничен `SCAN_CONCURRENCY` (по умолчанию 50). Редактируется в **UI → Настройки → Сервис** или через `PUT /api/settings/scan`.

## Алгоритм Discovery

1. Для каждой подсети из `networks`:
   - Генерация списка хостов (до `DISCOVER_MAX_HOSTS`, по умолчанию 4096)
   - Параллельный ping (`DISCOVER_PING_WORKERS`, по умолчанию 100)
2. Для отвечающих хостов, отсутствующих в инвентаре:
   - Проверка SSH-порта группы
   - SSH probe с credentials группы → получение identity (hostname)
   - Создание устройства с именем `discovered-<ip>` или hostname
3. Новые устройства сохраняются в PostgreSQL

### SSH probe

- Используется Paramiko
- Для RouterOS: определение identity через SSH
- Имя санитизируется: lowercase, только `[a-z0-9-.]`
- При коллизии имён добавляется суффикс IP

## Web UI — раздел «Scan»

- Кнопки **Scan** и **Scan + Discovery**
- Прогресс-бар и лог job в реальном времени
- Таблица результатов: имя, IP, статус, порты, latency
- Фильтрация по статусу

## API

### Запуск

```http
POST /scan
POST /scan?discover=true
Authorization: Bearer <token>
```

Ответ `202`:

```json
{
  "job_id": "abc123",
  "status": "running",
  "discover": false
}
```

Требуется право `scan:run` (роль operator или admin).

### Статус job

```http
GET /scan/status
```

```json
{
  "job_id": "abc123",
  "status": "running",
  "phase": "scanning",
  "message": "Checking router-01",
  "progress_current": 42,
  "progress_total": 100,
  "progress_pct": 42,
  "logs": [{"ts": "...", "level": "info", "message": "..."}]
}
```

Фазы: `idle`, `discovering`, `scanning`, `done`, `error`.

### Последний результат

```http
GET /scan/latest
```

Возвращает `ScanSummary` с агрегатами (`total`, `online`, `offline`, `partial`) и списком `results`.

## Ограничения и tuning

| Проблема | Решение |
|----------|---------|
| `Errno 24 Too many open files` | Уменьшить `SCAN_CONCURRENCY` и `DISCOVER_PING_WORKERS` |
| Долгий discovery в /16 | Разбить на меньшие подсети; `DISCOVER_MAX_HOSTS` ограничивает sweep |
| Устройства не обнаруживаются | Проверить ICMP с контейнера; firewall; credentials группы |
| Неверные имена | SSH probe не прошёл — устройство получит `discovered-x-x-x-x` |

Проверка ping из контейнера:

```bash
docker compose exec scanner ping -c 2 10.216.92.1
```

## Права доступа

| Действие | Право | Роли |
|----------|-------|------|
| Запуск scan | `scan:run` | operator, admin |
| Просмотр статуса/результатов | `scan:read` | viewer, operator, admin |

## Связь с Oxidized

Discovery добавляет устройства в инвентарь → они автоматически попадают в source Oxidized при следующей перезагрузке узлов. Рекомендуется после discovery выполнить **Oxidized → Sync** или дождаться интервала `OXIDIZED_INTERVAL`.


## Планировщик APScheduler

Периодические scan/discovery больше не должны зависеть от cron. В стеке запускается отдельный контейнер `scheduler`, который использует APScheduler и каждые `SCHEDULER_TICK_SEC` секунд проверяет настройки `ScanConfig` и ставит задачи в персистентную очередь PostgreSQL. Сам scanner-worker только исполняет очередь.

Это разделяет:
- scheduler — когда запускать;
- task queue — что поставить в очередь и обеспечить dedupe/retry;
- scanner worker — выполнение scan/discovery;
- web UI — ручной запуск и мониторинг.

## Локальный AI-анализ

AI является необязательным post-processing этапом. После завершения scan результат ставится в очередь `scan.ai_analysis`.

Рекомендуемый бесплатный локальный стек:
- Ollama;
- open-weight Qwen3;
- по умолчанию `qwen3:4b);
- endpoint `GET /api/scan/ai`.

AI не участвует в принятии решения о доступности устройства и не блокирует scan/discovery. Он используется для сводки, выделения рисков и рекомендаций только по фактически полученным данным.

Включение:
```env
AI_ENABLED=true
AI_OLLAMA_URL=http://ollama:11434
AI_MODEL=qwen3:4b
```

Запуск:
```bash
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull qwen3:4b
```


## AI Discovery Enrichment

При включённом `AI_DISCOVERY_ENABLED=true` каждый новый discovery device после детерминированной проверки ставится в очередь `discovery.ai_enrichment`. Локальный Ollama + Qwen3 возвращает предложение по `device_type`, `vendor`, `model_candidate`, `os_candidate`, `confidence`, `recommended_profile`, `risk` и `reason`.

AI не регистрирует устройства и не меняет сетевые параметры автоматически. Результат хранится в поле `ai_enrichment` устройства и используется как подсказка оператору. Для запуска достаточно:

```bash
AI_ENABLED=true
AI_DISCOVERY_ENABLED=true
```

Затем запустить Ollama и загрузить модель, например `qwen3:4b`. Основные проверки discovery остаются детерминированными.
