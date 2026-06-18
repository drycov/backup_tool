# DEPRECATED — legacy FastAPI application

The directory `scanner/app/` contains an **obsolete** FastAPI prototype of Backup Tools.

**Production uses Django only** (`scanner/api/`, `scanner/services/`, `scanner/backup_tools/`).

- Docker image builds from `scanner/Dockerfile` → Gunicorn + Django.
- `scanner/app/main.py` is **not** included in the image and **not** maintained.
- Static copies under `scanner/app/static/` may be out of date.

Do not add features here. Migrate any remaining references to the Django stack and remove this tree in a future cleanup PR.
