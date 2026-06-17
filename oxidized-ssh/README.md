# SSH-ключи для push бэкапов Oxidized → Gitea

> Подробнее о бэкапах и Git push: [docs/oxidized.md](../docs/oxidized.md)

1. Сгенерировать ключ в формате **PEM** (Rugged/libssh2 не принимает OpenSSH-формат):

```bash
ssh-keygen -t rsa -b 4096 -m PEM -f oxidized-ssh/id_rsa -N ""
# или конвертировать существующий:
ssh-keygen -p -m PEM -f oxidized-ssh/id_rsa
```

2. Добавить `id_rsa.pub` в Gitea → репозиторий `Oxidized/sat_backup` → Deploy Keys (write).

3. Добавить host key:

```bash
ssh-keyscan 10.216.40.65 >> oxidized-ssh/known_hosts
```

4. В `.env` указать **SSH** URL (не HTTP):

```
GIT_REMOTE_URL=git@10.216.40.65:Oxidized/sat_backup.git
```

5. Перезапустить: `docker compose restart oxidized`
