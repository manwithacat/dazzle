# DD-007: Messaging DSL (`message`, `channel`, `notification`, `asset`, `document`, `template`) — parked until a consumer must notify a person

```yaml
id: DD-007
status: PARKED
issues: [952]
adrs: [0057, 0003]
decided: 2026-10-12
decided_at_sha: 2de583aa741ecc4dfad1f369f6c773fa12f99966
parent: flense-programme
```

## One-line intent

No consumer declares a messaging construct. Flense ship F (ADR-0057) removes
the messaging DSL, `dazzle.notifications`, the channel manager / resolver /
template engine and the queue and stream adapters. The email kernel stays:
provider detection, the email adapters (Mailpit, SES, file), the
`_dazzle_outbox` delivery table and the SES bounce webhook that the auth
subsystem registers.

## Plan (what we already concluded)

Restore from the commit this DD was parked at
(`2de583aa741ecc4dfad1f369f6c773fa12f99966`), starting from the smallest
slice the forcing consumer needs — almost certainly `notification` alone:

- `notification <name>:` with `on: <Entity> <event>`, recipients by role or
  field path, channels (email first; in-app later), and a manifest
  `[notifications]` provider block (log / smtp / sendgrid / ses).
- Wiring: entity-event callbacks into a dispatcher
  (`http/runtime/notification_wiring.py`, `dazzle/notifications/`), sends
  through the kept email adapters and the `_dazzle_outbox` table so delivery
  is transactional and retried.
- SLA integration: `on_breach: notify: <role>` resolves the role to
  recipients and sends through the same dispatcher. Today
  `http/runtime/sla_manager.py` only writes a `logger.warning` line for
  it; that behaviour is unchanged by this park.
- The `message` / `channel` / `template` / `asset` / `document` grammar
  only if a second consumer needs typed message schemas; do not restore it
  for notifications alone.
- Counter-priors: no per-app SMTP code in `app/`; no sends outside the
  outbox; no recipient lists computed in templates.

## Reopen when (consumer force)

1. **Named consumer** — cyfuture's eight SLAs declare
   `on_breach: notify: manager` and expect a manager to be told; **or**
   AegisMark safeguarding alerts must reach a designated safeguarding lead.
2. **Evidence of host workaround** — a consumer sending email from a route
   override or a service stub, or reading SLA breach log lines.
3. **Acceptance that unblocks** — an SLA breach in the consumer's CI
   produces an outbox row addressed to the resolved manager.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan above; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- `http/channels`: `detection.py`, `providers/email.py`, `adapters/email.py`
  (+ `base.py`), `outbox.py` (`_dazzle_outbox`), `ses_webhooks.py`.
- `sla` with `on_breach` field updates and the notify log line.

## Explicitly out of scope until force

- Queue (RabbitMQ) and stream (Redis/Kafka) channels, inbound `receive`
  operations, document rendering and attachments, SMS/Slack channels.

## Trail

| Date | Event |
|------|--------|
| 2026-10-12 | Parked (this DD); messaging DSL removed in flense ship F |
