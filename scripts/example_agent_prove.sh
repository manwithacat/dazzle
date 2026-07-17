#!/usr/bin/env bash
# Fleet check: representation + journey prove across example apps.
# Usage: bash scripts/example_agent_prove.sh
# Optional: EXAMPLE_JOURNEY_MATURITY=1 also ranks residual journey work.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${EXAMPLE_JOURNEY_MATURITY:-0}" == "1" ]]; then
  python scripts/example_journey_maturity.py --status || true
  echo
fi

fail=0
journey_fail=0
for app in examples/*/; do
  name="$(basename "$app")"
  [[ -f "$app/dazzle.toml" ]] || continue
  echo "======== $name ========"
  if ! (cd "$app" && dazzle prove representation -p .); then
    echo "  [FAIL] representation"
    fail=1
  fi
  # Journey only when bound stories exist (executed_by)
  if grep -rqE '^\s*executed_by:\s*surface\.' "$app"/dsl 2>/dev/null; then
    out="$(cd "$app" && dazzle prove story --journey 2>&1)" || true
    echo "$out" | tail -8
    if echo "$out" | grep -qE 'failed=[1-9]'; then
      echo "  [FAIL] journey prove has failures"
      journey_fail=1
    fi
  fi
  echo
done

if [[ "$fail" -ne 0 ]]; then
  echo "One or more examples failed representation prove."
  exit 1
fi
if [[ "$journey_fail" -ne 0 ]]; then
  echo "One or more examples failed journey prove (bound stories)."
  exit 1
fi
echo "All examples pass representation prove (and bound journey proves where present)."
