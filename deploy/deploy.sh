#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="backup-tools"
DEFAULT_DIR="/opt/backup_tool"
ROOT="\${DEPLOY_DIR:-$DEFAULT_DIR}"
BRANCH="\${DEPLOY_BRANCH:-main}"
COMPOSE_FILE="\${COMPOSE_FILE:-docker-compose.yml}"
HEALTH_URL="\${HEALTH_URL:-http://127.0.0.1:\${SCANNER_PORT:-8000}/health}"
LOCK_FILE="\${ROOT}/.deploy.lock"
PROFILE="\${COMPOSE_PROFILE:-}"
NO_BUILD=false
NO_PULL=false
PRUNE=false

usage() {
  cat <<EOF
Usage: $0 [options]

Deploy Backup Tools from Git and Docker Compose.

Options:
  --dir PATH          deployment directory (default: $DEFAULT_DIR)
  --branch NAME       git branch (default: $BRANCH)
  --no-build          skip docker compose build
  --no-pull           skip git pull
  --prune             remove unused Docker images after deploy
  --profile NAME      enable compose profile (postgres, worker, external)
  -h, --help          show this help

Environment:
  DEPLOY_DIR, DEPLOY_BRANCH, COMPOSE_PROFILE, COMPOSE_FILE, HEALTH_URL
EOF
}

log()  { printf '[%s] %s\n' "$APP_NAME" "$*"; }
warn() { printf '[%s] %s\n' "$APP_NAME" "$*" >&2; }
die()  { printf '[%s] ERROR: %s\n' "$APP_NAME" "$*" >&2; exit 1; }

cleanup() { rm -f "$LOCK_FILE"; }
trap cleanup EXIT

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) ROOT="$2"; shift 2 ;;
    --branch) BRANCH="$2"; shift 2 ;;
    --no-build) NO_BUILD=true; shift ;;
    --no-pull) NO_PULL=true; shift ;;
    --prune) PRUNE=true; shift ;;
    --profile) PROFILE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

command -v git >/dev/null || die "git is required"
command -v docker >/dev/null || die "docker is required"
command -v curl >/dev/null || die "curl is required"
[[ -d "$ROOT/.git" ]] || die "not a git repository: $ROOT"
cd "$ROOT"

[[ ! -e "$LOCK_FILE" ]] || die "deployment is already running: $LOCK_FILE"
printf "%s\n" "$$" > "$LOCK_FILE"
git diff --quiet && git diff --cached --quiet || die "working tree contains uncommitted changes"

log "deploy directory: $ROOT"
log "branch: $BRANCH"

if [[ "$NO_PULL" == false ]]; then
  git fetch --prune origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
fi

REV="$(git rev-parse --short HEAD)"
printf "%s\n" "$REV" > .deploy-version
log "revision: $REV"
[[ -f "$COMPOSE_FILE" ]] || die "compose file not found: $COMPOSE_FILE"
mkdir -p inventory oxidized oxidized-ssh

if [[ ! -f .env ]]; then
  [[ -f .env.example ]] || die ".env and .env.example are missing"
  cp .env.example .env
  warn ".env created from .env.example; review secrets before production use"
fi

[[ ! -f deploy/init-stack.sh ]] || bash deploy/init-stack.sh "$ROOT"
[[ ! -f oxidized/entrypoint.sh ]] || chmod +x oxidized/entrypoint.sh

compose=(docker compose -f "$COMPOSE_FILE")
[[ -z "$PROFILE" ]] || compose+=(--profile "$PROFILE")
"${compose[@]}" config -q

if [[ "$NO_BUILD" == false ]]; then
  log "building scanner image"
  "${compose[@]}" build scanner
fi

log "starting stack"
"${compose[@]}" up -d

log "waiting for scanner health"
deadline=$((SECONDS + 120))
healthy=false
while (( SECONDS < deadline )); do
  if curl -fsS --max-time 5 "$HEALTH_URL" >/dev/null 2>&1; then healthy=true; break; fi
  sleep 3
done

if [[ "$healthy" != true ]]; then
  warn "health check failed: $HEALTH_URL"
  "${compose[@]}" ps
  "${compose[@]}" logs --tail=80 scanner || true
  exit 1
fi

[[ "$PRUNE" != true ]] || docker image prune -f
log "deployment completed successfully"
"${compose[@]}" ps
printf "\nRevision: %s\nHealth: %s\n" "$REV" "$HEALTH_URL"
