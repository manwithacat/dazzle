#!/usr/bin/env bash
# macos_agent_volume_access.sh — diagnose + guide TCC for monorepos on /Volumes.
#
# Honest limits (Apple privacy model):
#   * No script can silently grant Full Disk Access or Removable Volumes.
#   * TCC is bound to the **host terminal app** identity (Ghostty, Terminal,
#     iTerm2, VS Code, Cursor, Grok Build shell parent, etc.) — not to python
#     or git binaries inside PATH.
#   * After granting access you MUST quit and relaunch that host app (not just
#     a tab). `os.access(path, R_OK)` and git/venv will keep failing until then.
#
# What this script does:
#   1. Detects monorepo root + whether it lives under /Volumes
#   2. Probes readability (stat, listdir, .git/config, .venv/pyvenv.cfg)
#   3. Identifies likely host terminal from parent process chain
#   4. Prints exact System Settings panes to open
#   5. Optionally opens those panes (`open` URLs) and re-runs Python health
#
# Usage:
#   ./scripts/macos_agent_volume_access.sh
#   ./scripts/macos_agent_volume_access.sh --open-settings
#   ./scripts/macos_agent_volume_access.sh --root /Volumes/SSD/Dazzle
#   ./scripts/macos_agent_volume_access.sh --health   # run agent_workspace_health

set -euo pipefail

ROOT=""
OPEN_SETTINGS=0
RUN_HEALTH=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT="${2:-}"
      shift 2
      ;;
    --open-settings)
      OPEN_SETTINGS=1
      shift
      ;;
    --health)
      RUN_HEALTH=1
      shift
      ;;
    -h|--help)
      sed -n '2,25p' "$0"
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$ROOT" ]]; then
  # Prefer script location → monorepo root
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

echo "=== macos_agent_volume_access ==="
echo "root: $ROOT"
echo "host: $(uname -s) $(uname -m) $(sw_vers -productVersion 2>/dev/null || true)"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Not macOS — volume TCC guidance is N/A. Exiting 0."
  exit 0
fi

case "$ROOT" in
  /Volumes/*)
    echo "location: EXTERNAL VOLUME (TCC Removable Volumes / FDA often required)"
    ;;
  *)
    echo "location: under home/system disk (FDA still needed for some .git paths)"
    ;;
esac

probe_path() {
  local p="$1"
  local label="$2"
  if [[ ! -e "$p" ]]; then
    echo "  FAIL  $label: missing ($p)"
    return 1
  fi
  if [[ ! -r "$p" ]]; then
    echo "  FAIL  $label: not readable (shell -r) ($p)"
    return 1
  fi
  if [[ -d "$p" ]]; then
    if ! ls "$p" >/dev/null 2>&1; then
      echo "  FAIL  $label: listdir denied ($p)"
      return 1
    fi
  fi
  if [[ -f "$p" ]]; then
    if ! head -c 16 "$p" >/dev/null 2>&1; then
      echo "  FAIL  $label: open denied ($p)"
      return 1
    fi
  fi
  echo "  OK    $label: $p"
  return 0
}

echo
echo "--- FS probes ---"
FAILS=0
probe_path "$ROOT" "repo root" || FAILS=$((FAILS + 1))
probe_path "$ROOT/.git/config" ".git/config" || FAILS=$((FAILS + 1))
if [[ -f "$ROOT/.venv/pyvenv.cfg" ]]; then
  probe_path "$ROOT/.venv/pyvenv.cfg" "pyvenv.cfg" || FAILS=$((FAILS + 1))
else
  echo "  WARN  no .venv/pyvenv.cfg (run uv sync)"
fi
for app in invoice_ops ops_dashboard; do
  if [[ -d "$ROOT/examples/$app" ]]; then
    probe_path "$ROOT/examples/$app" "examples/$app" || FAILS=$((FAILS + 1))
  fi
done

echo
echo "--- Python os.access (matches agent_workspace_health) ---"
if command -v python3 >/dev/null 2>&1; then
  PY=python3
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PY="$ROOT/.venv/bin/python"
  fi
  ROOT_FOR_PY="$ROOT" "$PY" - <<'PY' || FAILS=$((FAILS + 1))
import os, sys
from pathlib import Path
root = Path(os.environ["ROOT_FOR_PY"])
paths = [root, root / ".git" / "config", root / ".venv" / "pyvenv.cfg"]
ok = True
for p in paths:
    if not p.exists():
        print(f"  SKIP  {p} (missing)")
        continue
    r = os.access(p, os.R_OK)
    print(f"  {'OK  ' if r else 'FAIL'}  os.access R_OK={r}  {p}")
    if not r:
        ok = False
sys.exit(0 if ok else 1)
PY
else
  echo "  WARN  python3 not on PATH — skip os.access probe"
fi

echo
echo "--- host terminal identity (TCC subject) ---"
# Walk PPID chain for common terminal app names. Prefer full command path
# (ps -o command=) so wrappers like grok/tmux still reveal Ghostty/Electron.
# Only GUI terminal/editor apps own TCC — never shells, tmux, or agent CLIs.
HOST_APP="unknown"
if [[ -n "${TERM_PROGRAM:-}" ]]; then
  echo "  TERM_PROGRAM=$TERM_PROGRAM"
  case "$TERM_PROGRAM" in
    ghostty|Ghostty) HOST_APP="Ghostty" ;;
    iTerm.app|iTerm2) HOST_APP="iTerm" ;;
    Apple_Terminal) HOST_APP="Terminal" ;;
    vscode) HOST_APP="Visual Studio Code" ;;
    WarpTerminal) HOST_APP="Warp" ;;
    # ignore tmux / unknown TERM_PROGRAM values
  esac
fi
if command -v ps >/dev/null 2>&1; then
  chain="$(ps -o comm= -p $$ 2>/dev/null || true)"
  ppid=$PPID
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    [[ -z "${ppid:-}" || "$ppid" == "0" || "$ppid" == "1" ]] && break
    name="$(ps -o comm= -p "$ppid" 2>/dev/null | tr -d ' ' || true)"
    full="$(ps -o command= -p "$ppid" 2>/dev/null || true)"
    chain="$name > $chain"
    haystack="$name $full"
    case "$haystack" in
      *[Gg]hostty*) HOST_APP="Ghostty" ;;
      *[Ii][Tt]erm*) HOST_APP="iTerm" ;;
      *Terminal.app*|*Apple_Terminal*) HOST_APP="Terminal" ;;
      *Cursor.app*|*Cursor\ Helper*) HOST_APP="Cursor" ;;
      *Visual\ Studio\ Code*|*Code\ Helper*) HOST_APP="Visual Studio Code" ;;
      *[Ww]arp*) HOST_APP="Warp" ;;
      *[Aa]lacritty*) HOST_APP="Alacritty" ;;
      *[Kk]itty*) HOST_APP="kitty" ;;
    esac
    ppid="$(ps -o ppid= -p "$ppid" 2>/dev/null | tr -d ' ' || true)"
  done
  echo "  process chain: $chain"
fi
if [[ "$HOST_APP" == "unknown" ]]; then
  # Grok Build on this host is usually under Ghostty; FDA/Removable Volumes
  # must be granted to that GUI app, not to tmux/zsh/python/grok.
  HOST_APP="Ghostty (or the GUI terminal that launched this agent)"
fi
echo "  likely host app for TCC: $HOST_APP"
echo "  (Grant access to THIS app — not to python/git/tmux.)"

echo
echo "--- remediation (manual; cannot automate grant) ---"
cat <<EOF
1. System Settings → Privacy & Security → **Files and Folders**
   → enable **Removable Volumes** (and Desktop/Documents if prompted)
   for: ${HOST_APP}

2. System Settings → Privacy & Security → **Full Disk Access**
   → enable ${HOST_APP}
   (required for some .git / agent shells on external volumes)

3. **Quit ${HOST_APP} completely** (Cmd-Q) and relaunch.
   New tabs in the same process keep the old TCC denial.

4. Re-probe:
     $ROOT/scripts/macos_agent_volume_access.sh
     $ROOT/.venv/bin/python $ROOT/scripts/agent_workspace_health.py --require-postgres

5. If grants keep failing: clone/move monorepo to ~/src/Dazzle (outside /Volumes).

Note: System Settings has no "add arbitrary executable by path" for FDA on
recent macOS — you toggle the host **app** that owns the agent shell.
EOF

if [[ "$OPEN_SETTINGS" -eq 1 ]]; then
  echo
  echo "--- opening System Settings panes ---"
  # Best-effort deep links (change across macOS versions; ignore failures).
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles" 2>/dev/null || true
  open "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension" 2>/dev/null || true
  open "x-apple.systempreferences:com.apple.preference.security?Privacy" 2>/dev/null || true
  echo "  opened Privacy & Security (navigate to Full Disk Access + Files and Folders)."
fi

if [[ "$RUN_HEALTH" -eq 1 ]]; then
  echo
  echo "--- agent_workspace_health --require-postgres ---"
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    "$ROOT/.venv/bin/python" "$ROOT/scripts/agent_workspace_health.py" --require-postgres || FAILS=$((FAILS + 1))
  else
    python3 "$ROOT/scripts/agent_workspace_health.py" --require-postgres || FAILS=$((FAILS + 1))
  fi
fi

echo
if [[ "$FAILS" -gt 0 ]]; then
  echo "OVERALL FAIL ($FAILS probe failure(s)) — fix TCC then relaunch host app."
  exit 1
fi
echo "OVERALL PASS — volume/FS probes ok for agent loops."
exit 0
