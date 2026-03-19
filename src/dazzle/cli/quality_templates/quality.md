# Full Quality Pipeline

Run the complete quality pipeline unattended.

## Stages

1. **Nightly** — `/nightly` (upgrade check + validate + health)
2. **Actions** — `/actions` (discover issues + implement fixes)
3. **UX** — `/ux-actions` (evaluate + improve user experience)

Run sequentially. Stop on critical failures (site down, deploy failed, pipeline broken).

Write combined report to `dev_docs/quality-{date}.md`.
