---
id: shell_without_strict_mode
name: Shell scripts without strict mode
layer: filter
status: active
summary: >-
  Shell scripts in `scripts/` or `app/sync/` that don't start with
  `set -euo pipefail`. The corpus prior is the unhardened shell shape from
  ad-hoc one-liners; the result is scripts that silently continue past failed
  commands, propagate unset variables as empty strings, and swallow errors
  in piped commands. The fix is one line; the gate is a grep.
triggers_text:
  - "shell script"
  - "bash script"
  - "scripts directory"
  - "sync script"
  - "one-shot script"
triggers_code:
  - '^#!/(usr/)?bin/(ba)?sh\s*\n(?!.*set\s+-[eu])'
  - '^#!/usr/bin/env\s+bash\s*\n(?!.*set\s+-[eu])'
refs:
  adrs: []
  tests:
    - tests/unit/test_shell_strict_mode.py
---

# Shell scripts without strict mode

## The corpus prior

Shell scripts in tutorials and Stack Overflow answers almost never use `set -euo pipefail`. The canonical "quick bash one-liner" omits it because the example is small and the author tested it. The advice "always use strict mode" exists in every serious shell guide of the last 15 years — and is universally absent from copy-pasted examples.

LLMs reproduce the corpus. Given "write a bash script that backs up the database and uploads it to S3," the emitted script will have a shebang, the three commands, no error handling, and no strict mode. The first time one of the three commands fails (S3 credentials expired, disk full), the script reports success because the last command — `echo done` — succeeded.

## Wrong shape

```bash
#!/bin/bash

aws s3 cp /var/backups/db.sql.gz s3://my-backups/$(date +%F).sql.gz
psql -c "DELETE FROM staging.events WHERE created_at < NOW() - INTERVAL '30 days'"
curl -X POST https://status.example.com/cron/backup -d "ok=1"
echo "Backup complete."
```

If the `aws` command fails (credentials expired), the script continues, deletes thirty days of staging events, hits the status endpoint to claim success, and prints the reassuring message. The Monday standup hears "the backup script ran fine on Friday." The data loss surfaces three weeks later.

Other failure modes baked into the absence of strict mode:

- **Unset variable as empty string** — `cp $SOURCE $DEST` with `SOURCE` unset becomes `cp  $DEST` (copies from current directory). `set -u` would catch this.
- **Pipe failure invisible** — `curl ... | jq ...` succeeds if `jq` succeeds even if `curl` returned 404. `set -o pipefail` would catch this.
- **First-command failure silently ignored** — every line is independent without `set -e`.

## Right shape

```bash
#!/usr/bin/env bash
set -euo pipefail

aws s3 cp /var/backups/db.sql.gz s3://my-backups/"$(date +%F)".sql.gz
psql -c "DELETE FROM staging.events WHERE created_at < NOW() - INTERVAL '30 days'"
curl -X POST https://status.example.com/cron/backup -d "ok=1"
echo "Backup complete."
```

One line. The script now stops on the first failed command, refuses to continue with unset variables, and propagates pipe failures. Every consumer of the script (cron, CI, the human reading the exit code) gets correct signal.

For scripts that genuinely need to continue past a failure of one specific command, use `command || handle_failure` explicitly — the strict mode is the default; opt-outs are local and visible.

For scripts that need to act on the failure (cleanup, alert), pair strict mode with `trap`:

```bash
#!/usr/bin/env bash
set -euo pipefail

cleanup() {
    rm -f /tmp/work.$$
    curl -X POST https://status.example.com/cron/backup -d "ok=0"
}
trap cleanup ERR

# ... rest of script
```

## Why this matters here

Dazzle projects accumulate shell scripts in `scripts/` (one-shot migrations, ops tasks) and in `app/sync/` (cron-driven integration jobs). These are the user-frontier counterpart to user-authored Python: outside the substrate's primary coverage, but inside the project's blast radius. A failed-silently sync script ships exactly the same wrong-data outcome as an exception-swallowing Python handler — different language, same prior.

The fix is mechanical: one line at the top of every script. The gate is a grep: any script in `scripts/**/*.sh` or `app/**/*.sh` without `set -euo pipefail` near the top is drift. This is the cheapest counter-prior in the catalogue to enforce and one of the highest-leverage given how often LLM-emitted shell ships unprotected.

## Cross-references

- `dev_docs/2026-05-25-substrate-audit.md` §4.4 — the gap that motivated this entry.
- BashFAQ on strict mode — https://mywiki.wooledge.org/BashFAQ/105 documents the failure modes in detail.
