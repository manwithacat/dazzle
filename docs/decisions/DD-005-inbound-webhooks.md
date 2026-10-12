# DD-005: inbound `webhook` construct — parked until a consumer asks

```yaml
id: DD-005
status: PARKED
issues: []
adrs: [0057, 0003]
decided: 2026-10-12
decided_at_sha: b60baaf4e
parent: flense-programme
```

## One-line intent

The removed top-level `webhook` construct was *outbound* (entity events →
HTTP) and no consumer used it. Both consumers that need webhooks need the
*inbound* direction, and both hand-write it. This DD records the inbound shape
so it is built once, against those consumers, rather than reviving the
outbound design.

## Plan (what we already concluded)

An inbound `webhook` construct that declares a vendor endpoint and lets the
framework own the transport concerns the consumers re-implement today:

- **Route** — `POST /webhooks/<name>`, CSRF-exempt (the framework already
  exempts the `/webhooks/` prefix), no session auth.
- **Signature verification** — declared scheme (HMAC-SHA256 over the raw body,
  header name, secret from an env/config reference), verified before parsing.
  Constant-time comparison; reject with 401 on mismatch. Support the
  intent-to-receive handshake shape Xero uses (respond 401 to a bad signature,
  200 to a good one, on an empty event list).
- **Idempotent dispatch** — a declared event-id path; a framework table records
  `(webhook, event_id)` so a replayed delivery is acknowledged and not
  re-dispatched. Dispatch goes to a declared handler (a `process` or a service
  hook), never to inline code in the DSL.
- **Health** — an optional `GET` for portal reachability checks (AegisMark
  ships `routes/wonde_webhook_health.py` for this).

Counter-priors: do not restore the outbound construct to stand in for this;
do not let the DSL carry payload-mapping logic (that is the handler's job); do
not accept a delivery whose signature was not checked when a secret is
configured.

## Reopen when (consumer force)

1. **Named consumer** — AegisMark (`routes/wonde_webhook.py`, Wonde partner
   lifecycle events) **or** cyfuture (`routes/xero_webhook.py`,
   `services/vendor/webhooks.py`) asks to replace its hand-written route with a
   declared webhook.
2. **Evidence of host workaround** — the routes above: route overrides that
   verify HMAC signatures and dispatch by hand.
3. **Acceptance that unblocks** — the consumer's webhook validates, rejects a
   bad signature, de-duplicates a replayed delivery, and dispatches to its
   handler in that consumer's CI.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan above; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- The outbound `webhook` construct (parser, IR, sentinel heuristics) is in
  history at the commit above; it was removed in flense ship D because no
  consumer used it.
- The `/webhooks/` CSRF exemption and route-override mechanism that the
  consumers' hand-written routes rely on stay.

## Explicitly out of scope until force

- Outbound webhooks (entity events → HTTP).
- Retry queues, dead-letter handling and delivery dashboards.

## Trail

| Date | Event |
|------|--------|
| 2026-10-12 | Parked (this DD); outbound `webhook` removed in flense ship D |
