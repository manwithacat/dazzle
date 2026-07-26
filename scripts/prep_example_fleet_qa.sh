#!/usr/bin/env bash
# Prep showcase example apps for human L4 QA.
# - Restarts each app with DAZZLE_QA_MODE=1 + --test-mode
# - Optional: --smoke to run dazzle qa smoke-dig --all --no-coverage
#
# Usage:
#   ./scripts/prep_example_fleet_qa.sh
#   ./scripts/prep_example_fleet_qa.sh --smoke
#   ./scripts/prep_example_fleet_qa.sh --smoke --max-clicks 8

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SMOKE=0
MAX_CLICKS=12
while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) SMOKE=1; shift ;;
    --max-clicks) MAX_CLICKS="${2:?}"; shift 2 ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

APPS=(
  simple_task
  support_tickets
  invoice_ops
  contact_manager
  ops_dashboard
  project_tracker
  design_studio
  hr_records
  fieldtest_hub
)

DAZZLE_BIN="${DAZZLE_BIN:-$ROOT/.venv/bin/dazzle}"
if [[ ! -x "$DAZZLE_BIN" ]]; then
  DAZZLE_BIN="$(command -v dazzle || true)"
fi
if [[ -z "${DAZZLE_BIN}" ]]; then
  echo "dazzle binary not found (set DAZZLE_BIN or use .venv)" >&2
  exit 1
fi

echo "==> Stopping listeners on 9100–9108 (if any)"
for port in 9100 9101 9102 9103 9104 9105 9106 9107 9108; do
  pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
  fi
done
sleep 2

echo "==> Starting showcase serves (DAZZLE_QA_MODE=1 --test-mode)"
i=0
for app in "${APPS[@]}"; do
  port=$((9100 + i))
  log="/tmp/serve-${app}.log"
  (
    cd "$ROOT/examples/${app}"
    set -a
    # shellcheck disable=SC1091
    [[ -f .env ]] && . ./.env
    set +a
    export DAZZLE_QA_MODE=1
    export DAZZLE_ENV="${DAZZLE_ENV:-development}"
    nohup "$DAZZLE_BIN" serve --host 127.0.0.1 --port "${port}" --test-mode \
      >"${log}" 2>&1 &
    echo "  ${app} :${port} (log ${log}) pid $!"
  )
  i=$((i + 1))
done

echo "==> Waiting for ports"
for port in 9100 9101 9102 9103 9104 9105 9106 9107 9108; do
  ok=0
  for _ in $(seq 1 40); do
    if lsof -ti "tcp:${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 0.5
  done
  if [[ "${ok}" -ne 1 ]]; then
    echo "  WARN: port ${port} not listening yet" >&2
  else
    echo "  port ${port} up"
  fi
done

echo "==> Magic-link smoke (simple_task manager)"
if ! "$DAZZLE_BIN" qa login manager -u "http://127.0.0.1:9100" 2>/dev/null | head -1 | grep -q '^http'; then
  echo "  WARN: magic-link failed — check /tmp/serve-simple_task.log" >&2
else
  echo "  magic-link OK"
fi

if [[ "${SMOKE}" -eq 1 ]]; then
  echo "==> Fleet smoke-dig (max-clicks=${MAX_CLICKS})"
  "$DAZZLE_BIN" qa smoke-dig --all --no-coverage --max-clicks "${MAX_CLICKS}"
  echo "==> Done. Review ok=True / auto_seed=0 above."
else
  echo "==> Ready for human QA (skip smoke; pass --smoke to verify floor)."
  echo "    Runbook: docs/recipes/human-qa-example-fleet.md"
fi
