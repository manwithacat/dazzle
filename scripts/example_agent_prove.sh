#!/usr/bin/env bash
# Fleet check: representation + journey prove across example apps.
# Usage: bash scripts/example_agent_prove.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
for app in examples/*/; do
  name="$(basename "$app")"
  [[ -f "$app/dazzle.toml" ]] || continue
  echo "======== $name ========"
  if ! (cd "$app" && dazzle prove representation -p .); then
    echo "  [FAIL] representation"
    fail=1
  fi
  # Journey only when stories exist
  if ls "$app"/dsl/*stories*.dsl >/dev/null 2>&1 || grep -q '^story ' "$app"/dsl/*.dsl 2>/dev/null; then
    if ! (cd "$app" && dazzle prove story --journey 2>/dev/null | tail -5); then
      echo "  [note] journey prove non-zero (see above)"
    fi
  fi
  echo
done

if [[ "$fail" -ne 0 ]]; then
  echo "One or more examples failed representation prove."
  exit 1
fi
echo "All examples pass representation prove."
