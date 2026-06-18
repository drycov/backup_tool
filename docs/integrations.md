# Интеграции Backup Tools

Примеры подключения Backup Tools к CI/CD, Ansible и внешним системам.

## API keys

Создание ключа (admin, UI **Пользователи → API keys** или REST):

```bash
curl -s -b cookies.txt -X POST http://scanner:8000/api/auth/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name":"ansible","role":"operator","allowed_groups":["hex"]}'
```

Ответ содержит `key` (`bk_…`) **один раз** — сохраните в secret store.

Использование:

```bash
curl -s -H "X-API-Key: bk_YOUR_SECRET" http://scanner:8000/api/compliance/summary
# или
curl -s -H "Authorization: Bearer bk_YOUR_SECRET" http://scanner:8000/scan/status
```

### Ротация

```bash
curl -s -b cookies.txt -X POST \
  http://scanner:8000/api/auth/api-keys/1/rotate
```

Новый `key` в ответе; старый секрет немедленно недействителен. Событие пишется в audit (`api_key.rotate`).

### Zabbix

Для мониторинга можно использовать тот же API key в заголовке `authkey` вместо `{$AUTHKEY}` — см. [deploy/ZABBIX.md](../deploy/ZABBIX.md).

## Ansible

Минимальный playbook — compliance перед деплоем:

```yaml
---
- name: Backup Tools compliance gate
  hosts: localhost
  gather_facts: false
  vars:
    backup_tools_url: "http://scanner:8000"
    backup_tools_api_key: "{{ lookup('env', 'BACKUP_TOOLS_API_KEY') }}"

  tasks:
    - name: Fetch compliance summary
      ansible.builtin.uri:
        url: "{{ backup_tools_url }}/api/compliance/summary"
        method: GET
        headers:
          X-API-Key: "{{ backup_tools_api_key }}"
        return_content: true
      register: compliance

    - name: Fail if compliance below threshold
      ansible.builtin.assert:
        that:
          - compliance.json.compliance_pct >= 90
        fail_msg: "Compliance {{ compliance.json.compliance_pct }}% < 90%"
```

Запуск scan после изменения инвентаря:

```yaml
    - name: Trigger network scan
      ansible.builtin.uri:
        url: "{{ backup_tools_url }}/scan?discover=false"
        method: POST
        headers:
          X-API-Key: "{{ backup_tools_api_key }}"
        status_code: [200, 202]
```

## GitHub Actions

```yaml
jobs:
  compliance:
    runs-on: ubuntu-latest
    steps:
      - name: Check backup compliance
        env:
          BACKUP_TOOLS_API_KEY: ${{ secrets.BACKUP_TOOLS_API_KEY }}
        run: |
          pct=$(curl -sf -H "X-API-Key: $BACKUP_TOOLS_API_KEY" \
            https://backup-tools.example.com/api/compliance/summary \
            | python -c "import sys,json; print(json.load(sys.stdin)['compliance_pct'])")
          echo "Compliance: ${pct}%"
          python -c "import sys; sys.exit(0 if float('$pct') >= 90 else 1)"
```

## NetBox

Импорт и синхронизация — **Настройки → Интеграции** или:

```bash
curl -s -b cookies.txt -X POST http://scanner:8000/api/inventory/import/netbox
```

Топология (граф кабелей, readonly):

```bash
curl -s -b cookies.txt http://scanner:8000/api/inventory/topology/netbox
```

## OpenAPI

- Спецификация: `GET /api/openapi.json`
- Swagger UI: `/api/docs`
- CI drift: `python manage.py dump_openapi` → `openapi.snapshot.json`

## Связанные документы

- [api.md](api.md) — каталог REST
- [authentication.md](authentication.md) — RBAC, LDAP, custom roles
- [deploy/ZABBIX.md](../deploy/ZABBIX.md) — мониторинг
