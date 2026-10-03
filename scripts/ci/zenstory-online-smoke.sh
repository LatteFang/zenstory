#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL="${ZENSTORY_BACKEND_URL:-https://api.zenstory.ai}"
FRONTEND_URL="${ZENSTORY_FRONTEND_URL:-https://app.zenstory.ai}"
TIMEOUT_SECONDS="${ZENSTORY_SMOKE_TIMEOUT_SECONDS:-120}"
SLEEP_SECONDS=10
MAX_RETRIES=$(( TIMEOUT_SECONDS / SLEEP_SECONDS ))
if (( MAX_RETRIES < 1 )); then MAX_RETRIES=1; fi

BACKEND_URL="${BACKEND_URL%/}"
FRONTEND_URL="${FRONTEND_URL%/}"
case "$BACKEND_URL" in
  https://api.zenstory.ai) ;;
  *) echo "[zenstory-smoke] Refusing noncanonical backend origin: $BACKEND_URL" >&2; exit 1 ;;
esac
case "$FRONTEND_URL" in
  https://zenstory.ai|https://app.zenstory.ai) ;;
  *) echo "[zenstory-smoke] Refusing noncanonical frontend origin: $FRONTEND_URL" >&2; exit 1 ;;
esac

log() { echo "[zenstory-smoke] $1"; }

wait_for_backend_health() {
  local health_url="${BACKEND_URL}/health"
  local i=1
  log "Waiting for public backend health."
  while (( i <= MAX_RETRIES )); do
    if curl -fsS --max-time 10 "$health_url" >/tmp/zenstory_health.json 2>/tmp/zenstory_health.err; then
      log "Backend health endpoint is reachable."
      return 0
    fi
    log "Backend not ready yet (${i}/${MAX_RETRIES})."
    sleep "$SLEEP_SECONDS"
    (( i++ ))
  done
  log "Backend health check timed out."
  return 1
}

assert_frontend_available() {
  local status_code
  status_code="$(curl -sS -o /tmp/zenstory_frontend.html -w "%{http_code}" --max-time 15 "${FRONTEND_URL}/")"
  [[ "$status_code" == "200" ]] || { log "Frontend check failed with status ${status_code}."; return 1; }
  log "Frontend is reachable."
}

assert_unauth_projects_endpoint() {
  local status_code
  status_code="$(curl -sS -o /tmp/zenstory_projects_unauth.json -w "%{http_code}" --max-time 15 "${BACKEND_URL}/api/v1/projects")"
  [[ "$status_code" == "401" ]] || { log "Expected 401 for anonymous projects request, got ${status_code}."; return 1; }
  log "Anonymous API guard works (401)."
}

wait_for_backend_health
assert_frontend_available
assert_unauth_projects_endpoint
log "Public, credential-free readiness checks passed."
