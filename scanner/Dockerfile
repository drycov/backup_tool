FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY manage.py .
COPY backup_tools ./backup_tools
COPY core ./core
COPY api ./api
COPY services ./services
COPY static ./static

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "backup_tools.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
