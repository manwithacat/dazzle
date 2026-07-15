Dazzle /improve dead-man's switch (daily).

1. `cd` to the Dazzle repo root. Prefer uv toolchain:
   `export PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH"`
   `export UV_MANAGED_PYTHON=1` (and `PYENV_VERSION=system` if pyenv shims are present).
2. Call `scheduler_list`. Look for:
   - a pending one-shot whose prompt mentions `/improve` or `self-chained cycle`
   - this daily watchdog (yourself)
3. Read state:
   - `dev_docs/improve-backlog.md` (any REGRESSION / PENDING / OPEN_* / FIXED-VERIFY rows?)
   - `.dazzle/improve-explore-count` (explore budget used/100)
   - optional: `uv run python scripts/improve_schedule_next.py --result PASS --no-write-state`
4. If there is **no** pending improve one-shot AND any of:
   - actionable backlog remains, OR
   - explore budget `< 100`, OR
   - self-audit / capability-sweep would be due on the next cycle (see schedule script reasons), OR
   - only slow-poll situations (explore at cap, all-clear) still deserve a `2h` re-arm:
   then call `scheduler_create` with the fields from `scripts/improve_schedule_next.py` JSON
   (`scheduler_create` object: interval, prompt, recurring, **fire_immediately**, durable —
   honor `fire_immediately: true` when CI is green and work remains).
5. If a healthy `/improve` one-shot is already pending, **no-op** (do not schedule a second).
6. Do **not** run a full improve cycle in this watchdog turn unless the chain has been dead
   for **>24h** and work remains — then run one `/improve` and self-schedule as usual at REPORT.
7. Append a one-liner to `dev_docs/improve-log.md` only when you re-arm or note a gap:
   `**Watchdog:** re-armed {interval} reason={reason}` / `**Watchdog:** chain healthy no-op`.

Keep this daily durable recurring task alive; do not delete it.
