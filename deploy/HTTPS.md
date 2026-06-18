# Reverse proxy (HTTPS) example for Backup Tools

Place TLS termination in nginx/traefik/Caddy in front of `scanner:8000`.

## nginx

```nginx
server {
    listen 443 ssl http2;
    server_name backup.example.com;

    ssl_certificate     /etc/ssl/certs/backup.crt;
    ssl_certificate_key /etc/ssl/private/backup.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

## Scanner `.env`

```env
BEHIND_HTTPS_PROXY=true
ALLOWED_HOSTS=backup.example.com
JWT_SECRET=<random-string-at-least-32-characters>
ADMIN_PASSWORD=<strong-password>
```

With `BEHIND_HTTPS_PROXY=true` the app:

- trusts `X-Forwarded-Proto` for secure cookies;
- disables `Cross-Origin-Opener-Policy` on plain HTTP dev (no browser warning);
- sets `Secure` flag on auth cookie behind TLS.

## Health checks

| Endpoint | Use |
|----------|-----|
| `GET /health` | Liveness — process up, inventory readable |
| `GET /health/ready` | Readiness — DB + Oxidized worker (503 if not ready) |

Example probe in orchestrator:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8000
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8000
```
