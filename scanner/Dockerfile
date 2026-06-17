FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping \
    git \
    ruby \
    ruby-dev \
    build-essential \
    cmake \
    pkg-config \
    libssl-dev \
    libssh2-1-dev \
    libgit2-dev \
    libicu-dev \
    libyaml-dev \
    libzstd-dev \
    zlib1g-dev \
    && gem install oxidized --no-document \
    && apt-get purge -y build-essential ruby-dev cmake pkg-config libgit2-dev \
    && apt-get autoremove -y \
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
COPY scripts ./scripts

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "backup_tools.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
